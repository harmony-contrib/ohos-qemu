#!/usr/bin/env python3
"""Turn boot, HAP and native probe evidence into backend readiness records."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEVICES = ("phone", "2in1")


BACKENDS: list[dict[str, Any]] = [
    {
        "id": "display-drm",
        "status": "functional",
        "syscaps": ["SystemCapability.Graphic.Graphic2D.", "SystemCapability.WindowManager."],
        "evidence": [("hardware", r"/dev/dri:[\s\S]*card0[\s\S]*renderD128"), ("hap", r"display\.width\.result=0 width=800")],
    },
    {
        "id": "vulkan-icd",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Graphic.Vulkan"],
        "evidence": [("native/vulkan", r"(?:VK_ERROR_INCOMPATIBLE_DRIVER|result=-9|vkCreateInstance.*-9)")],
    },
    {
        "id": "audio-pcm",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Multimedia.Audio.", "SystemCapability.AI.IntelligentVoice.Core"],
        "evidence": [("hardware", r"/dev/snd:[\s\S]{0,200}\btimer\b"), ("hap", r"audio\.stream\.start=2"), ("hap", r"audio\.stream\.callbacks=0 bytes=0")],
    },
    {
        "id": "camera-video-input",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Multimedia.Camera.Core", "SystemCapability.Multimedia.Media.AVRecorder", "SystemCapability.Multimedia.Media.VideoRecorder"],
        "evidence": [("hardware", r"/dev/video\*: No such file"), ("hap", r"camera\.devices\.result=7400101 count=0")],
    },
    {
        "id": "wifi-radio",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Communication.WiFi."],
        "evidence": [("serial", r"HDF_WLAN_CHIPS_AP6275S not found"), ("hardware", r"eth0[\s\S]*Driver virtio_net")],
    },
    {
        "id": "bluetooth-radio",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Communication.Bluetooth."],
        "evidence": [("radio", r"(?:libbt_vendor\.z\.so|STATE_TURN_OFF|ERR_BT_DISABLE_FAILED)")],
    },
    {
        "id": "ethernet-nat",
        "status": "functional",
        "syscaps": ["SystemCapability.Communication.NetManager.Ethernet", "SystemCapability.Communication.NetStack"],
        "evidence": [("hardware", r"inet addr:10\.0\.2\.15"), ("hap", r"network\.get_default\.result=0 net_id=100")],
    },
    {
        "id": "dns-mdns",
        "status": "functional",
        "syscaps": ["SystemCapability.Communication.NetManager.MDNS", "SystemCapability.Communication.NetStack"],
        "evidence": [("hap", r"network\.mdns\.discovery\.result=started:true"), ("hap", r"network\.dns\.external\.result=")],
    },
    {
        "id": "net-ebpf",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Communication.NetManager.Core"],
        "evidence": [("native/bpf", r"(?:ENOSYS|errno=38|Function not implemented)")],
    },
    {
        "id": "usb-host-device",
        "status": "partial",
        "syscaps": ["SystemCapability.USB.USBManager", "SystemCapability.Driver.USB.Extension"],
        "evidence": [("serial", r"(?:usb_gadget.*failed|/UDC failed)"), ("hap", r"usb\.devices\.result=count:0")],
    },
    {
        "id": "sensor-accelerometer",
        "status": "simulated",
        "syscaps": ["SystemCapability.Sensors.Sensor"],
        "evidence": [("hap", r"sensor\.infos\.enumerate\.result=0 count=1"), ("hap", r"sensor\.subscribe\.callback=0.*callbacks=9")],
    },
    {
        "id": "vibrator",
        "status": "simulated",
        "syscaps": ["SystemCapability.Sensors.MiscDevice"],
        "evidence": [("hap", r"vibrator\.play\.result=0 cancel=0")],
    },
    {
        "id": "location-provider",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Location.Location.Core", "SystemCapability.Location.Location.Gnss", "SystemCapability.Location.Location.Geofence"],
        "evidence": [("hap", r"location\.start\.result=.*callbacks=0")],
    },
    {
        "id": "thermal-sensors",
        "status": "partial",
        "syscaps": ["SystemCapability.PowerManager.ThermalManager"],
        "evidence": [("hap", r"thermal\.level\.result=0")],
    },
    {
        "id": "accessibility-input",
        "status": "conditional_host_flag",
        "syscaps": ["SystemCapability.BarrierFree.Accessibility.Core", "SystemCapability.BarrierFree.Accessibility.Vision"],
        "evidence": [("a11y", r"(?:PASS|passed|complete|multi-after-release)")],
    },
    {
        "id": "ftrace",
        "status": "unavailable",
        "syscaps": ["SystemCapability.HiviewDFX.HiTrace"],
        "evidence": [("serial", r"/sys/kernel/(?:debug/)?tracing.*err=2")],
    },
    {
        "id": "storage-quota",
        "status": "partial",
        "syscaps": ["SystemCapability.FileManagement.StorageService.SpatialStatistics"],
        "evidence": [("serial", r"(?:F2FS|f2fs).*(?:quota|Quota).*(?:fail|error|corrupt)")],
    },
    {
        "id": "access-token-kernel-driver",
        "status": "partial",
        "syscaps": ["SystemCapability.Security.AccessToken"],
        "evidence": [("serial", r"access tokenid cmd error")],
    },
    {
        "id": "qos-authorization",
        "status": "unavailable_for_application_process",
        "syscaps": ["SystemCapability.Resourceschedule.QoS.Core"],
        "evidence": [("serial", r"(?:AUTH_CTRL.*no auth data|QOS_CTRL.*not authorized)")],
    },
    {
        "id": "selection-input-service",
        "status": {
            "phone": "declared_outside_device_contract",
            "2in1": "partial_missing_configured_extension",
        },
        "syscaps": ["SystemCapability.SelectionInput.Selection"],
        "evidence": {
            "phone": [("hap", r"selection\.content\.error=.*33600001")],
            "2in1": [
                ("hap", r"selection\.listener\.error=.*33600003"),
                ("hap", r"selection\.content\.error=.*33600001"),
            ],
        },
    },
    {
        "id": "print-extension-and-cups",
        "status": {
            "phone": "declared_outside_device_contract",
            "2in1": "partial_missing_extension_and_driver",
        },
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "evidence": {
            "phone": [("hap", r"print\.discovery\.result=started:true")],
            "2in1": [("hap", r"print\.discovery\.error=13100004")],
        },
    },
    {
        "id": "window-session-features",
        "status": {
            "phone": "profile_gap_and_disabled_features",
            "2in1": "partial_pip_only",
        },
        "syscaps": [
            "SystemCapability.Window.SessionManager",
            "SystemCapability.WindowManager.WindowManager.Core",
        ],
        "evidence": {
            "phone": [
                ("hap", r"window\.pip\.enabled=false"),
                ("hap", r"window\.floating_ball\.enabled=false"),
                ("hap", r"window\.float_view\.enabled=false"),
            ],
            "2in1": [
                ("hap", r"window\.pip\.enabled=true"),
                ("hap", r"window\.floating_ball\.enabled=false"),
                ("hap", r"window\.float_view\.enabled=false"),
            ],
        },
    },
    {
        "id": "peer-device-network-topology",
        "status": "conditional_bridge_required",
        "syscaps": [
            "SystemCapability.Communication.SoftBus.Core",
            "SystemCapability.DistributedHardware.",
            "SystemCapability.DistributedDataManager.",
            "SystemCapability.DistributedSched.",
            "SystemCapability.FileManagement.File.DistributedFile",
            "SystemCapability.Multimedia.AVSession.AVCast",
        ],
        "evidence": [("serial", r"-netdev user,id=net0")],
    },
    {
        "id": "secure-hardware-devices",
        "status": "unavailable",
        "syscaps": [
            "SystemCapability.Security.DeviceSecurityLevel",
            "SystemCapability.Security.DeviceAuth",
            "SystemCapability.Security.Huks.Core",
        ],
        "evidence": [("serial", r"(?:/dev/tc_ns_client|/dev/tc_private|/sec_storage).*(?:err=2|failed)")],
    },
    {
        "id": "resource-control-cgroups",
        "status": "partial",
        "syscaps": [
            "SystemCapability.ResourceSchedule.",
            "SystemCapability.Resourceschedule.",
        ],
        "evidence": [("serial", r"/(?:memcg|stune|blkio)/.*(?:errno:2|err=2)")],
    },
    {
        "id": "hyperhold-memory-reclaim",
        "status": "unavailable",
        "syscaps": [
            "SystemCapability.Kernel.Memory",
            "SystemCapability.ResourceSchedule.SystemLoad",
        ],
        "evidence": [("serial", r"/proc/sys/kernel/hyperhold/.*failed")],
    },
]


SERIAL_ERROR_FAMILIES = {
    "access_token_ioctl": r"access tokenid cmd error",
    "qos_authorization": r"(?:AUTH_CTRL.*no auth data|QOS_CTRL.*not authorized)",
    "wifi_driver": r"(?:HDF_WLAN_CHIPS_AP6275S not found|cfg80211\.ko failed|mac80211\.ko failed|iwlwifi\.ko failed|iwlmvm\.ko failed)",
    "camera_isp": r"(?:ispserver start failed|/dev/v4l-subdev\d.*err=2|/dev/media\d.*err=2)",
    "usb_gadget": r"(?:usb_gadget.*failed|/config/usb_gadget|/UDC failed)",
    "tracing": r"/sys/kernel/(?:debug/)?tracing.*(?:failed|err=2)",
    "resource_cgroups": r"/(?:memcg|stune|blkio)/.*(?:errno:2|err=2)",
    "secure_hardware": r"(?:/dev/tc_ns_client|/dev/tc_private|/sec_storage).*(?:err=2|failed)",
    "quota": r"(?:F2FS|f2fs).*(?:quota|Quota).*(?:fail|error|corrupt)",
    "hyperhold": r"/proc/sys/kernel/hyperhold/.*failed",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_texts(root: Path) -> dict[str, str]:
    def combined(paths: list[Path]) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in paths if path.exists()
        )

    return {
        "serial": combined([root / "serial-boot.log", root / "serial-reprobe.log"]),
        "hardware": combined([root / "hardware-backends.txt", root / "hardware-backends-fresh.txt"]),
        "hap": combined([
            root / "hap-probe-v3/results.log",
            root / "hap-probe-v2/results.log",
            root / "hap-probe/results-expanded.log",
        ]),
        "radio": combined([root / "radio-cli-probes.txt", root / "thermal-radio-logs.txt"]),
        "a11y": combined(sorted((root / "accessibility-e2e").glob("*"))) if (root / "accessibility-e2e").is_dir() else "",
        "native/vulkan": combined([root / "native-probes/vulkan.txt"]),
        "native/bpf": combined([root / "native-probes/bpf.txt"]),
        "native/quota": combined([root / "native-probes/quota.txt"]),
    }


def main() -> int:
    args = arguments()
    result: dict[str, Any] = {"schema_version": 1, "devices": {}}
    for device in DEVICES:
        root = args.runtime_root / f"arm64-{device}"
        texts = load_texts(root)
        backends = []
        for definition in BACKENDS:
            matches = []
            evidence = definition["evidence"]
            if isinstance(evidence, dict):
                evidence = evidence[device]
            for source, pattern in evidence:
                match = re.search(pattern, texts[source], re.IGNORECASE | re.MULTILINE)
                if match:
                    excerpt = re.sub(r"\s+", " ", match.group(0)).strip()[:320]
                    matches.append({"source": source, "pattern": pattern, "excerpt": excerpt})
            backends.append({
                "id": definition["id"],
                "expected_status": (
                    definition["status"][device]
                    if isinstance(definition["status"], dict)
                    else definition["status"]
                ),
                "evidence_complete": len(matches) == len(evidence),
                "evidence_match_count": len(matches),
                "evidence_required_count": len(evidence),
                "syscap_dependencies": definition["syscaps"],
                "matches": matches,
            })
        serial_counts = Counter({
            family: len(re.findall(pattern, texts["serial"], re.IGNORECASE))
            for family, pattern in SERIAL_ERROR_FAMILIES.items()
        })
        result["devices"][device] = {
            "backends": backends,
            "summary": {
                "backend_count": len(backends),
                "complete_evidence_count": sum(row["evidence_complete"] for row in backends),
                "incomplete_evidence": [row["id"] for row in backends if not row["evidence_complete"]],
                "serial_error_family_counts": dict(serial_counts),
            },
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        device: result["devices"][device]["summary"] for device in DEVICES
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
