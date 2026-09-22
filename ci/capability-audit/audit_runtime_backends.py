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
        "id": "egl-gles-software-renderer",
        "status": "functional_software_renderer",
        "syscaps": [
            "SystemCapability.Graphic.Graphic2D.EGL",
            "SystemCapability.Graphic.Graphic2D.GLES2",
            "SystemCapability.Graphic.Graphic2D.GLES3",
        ],
        "evidence": [
            ("native/egl", r"gles2\.surface=1 context=1 current=1"),
            ("native/egl", r"gles3\.surface=1 context=1 current=1"),
            ("native/egl", r"renderer=softpipe"),
        ],
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
        "id": "web-basic-page-load",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Web.Webview.Core"],
        "evidence": [
            ("hap", r"web\.page_end=true"),
            ("hap", r"web\.title=Example Domain"),
            ("hap", r"web\.url=https://example\.com/"),
        ],
    },
    {
        "id": "web-gpu-context",
        "status": "partial_gpu_context_unavailable",
        "syscaps": [
            "SystemCapability.Web.Webview.Core",
            "SystemCapability.Graphic.Graphic2D.WebGL",
            "SystemCapability.Graphic.Graphic2D.WebGL2",
        ],
        "evidence": [
            ("hap", r"web\.graphics\.begin=true"),
            ("web_hilog", r"eglCreateContext failed with error EGL_BAD_ATTRIBUTE"),
            ("web_hilog", r"Failed to create shared context for virtualization"),
            ("web_hilog", r"Failed to create SharedImageStub"),
        ],
    },
    {
        "id": "huks-key-lifecycle",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Security.Huks.Core"],
        "evidence": [
            ("hap", r"security\.huks\.key_lifecycle=generated:true,present:true"),
            ("hap", r"security\.huks\.key_deleted=true"),
            ("native/huks", r"get_sdk_version\.code=0.*value=2\.0\.0\.5"),
        ],
    },
    {
        "id": "huks-compatibility-migration",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Security.Huks.Extension"],
        "evidence": [("serial", r'DoExec: execute "/system/bin/hks_compatibility_bin" failed: 2')],
    },
    {
        "id": "i18n-basic-query",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Global.I18n"],
        "evidence": [
            ("hap", r"i18n\.system_languages\.count=5"),
            ("hap", r"i18n\.system_countries\.count=245"),
        ],
    },
    {
        "id": "i18n-customization",
        "status": "partial_invalid_owner_and_missing_helpers",
        "syscaps": ["SystemCapability.Global.I18n"],
        "evidence": [
            ("serial", r"SetOwner invalid uid : i18n_service"),
            ("serial", r'hmos_cust_timezone_mount" failed: 2'),
            ("serial", r'hmos_cust_libphonenumber_mount" failed: 2'),
            ("serial", r'hmos_cust_taboo_mount" failed: 2'),
        ],
    },
    {
        "id": "app-sandbox-file-io",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.FileManagement.File.FileIO"],
        "evidence": [("hap", r"file\.io\.lifecycle=value:ohos-qemu-capability-audit,removed:true")],
    },
    {
        "id": "local-preferences",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.DistributedDataManager.Preferences.Core"],
        "evidence": [("hap", r"data\.preferences\.lifecycle=value:ohos-qemu-capability-audit,removed:true")],
    },
    {
        "id": "crypto-random-message-digest",
        "status": "functional_subset",
        "syscaps": [
            "SystemCapability.Security.CryptoFramework.Rand",
            "SystemCapability.Security.CryptoFramework.MessageDigest",
        ],
        "evidence": [("hap", r"security\.crypto\.lifecycle=random:32,sha256:32")],
    },
    {
        "id": "bundle-self-query",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.BundleManager.BundleFramework"],
        "evidence": [("hap", r"bundle\.self\.result=org\.harmonycontrib\.capabilityaudit:1\.0\.0")],
    },
    {
        "id": "notification-and-local-emitter",
        "status": "functional_subset",
        "syscaps": [
            "SystemCapability.Notification.Notification",
            "SystemCapability.Notification.Emitter",
        ],
        "evidence": [
            ("hap", r"notification\.enabled\.result=(?:true|false)"),
            ("hap", r"notification\.emitter\.lifecycle=callbacks:1"),
        ],
    },
    {
        "id": "common-event-publish-subscribe",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Notification.CommonEvent"],
        "evidence": [("hap", r"common_event\.lifecycle=published:true,callbacks:1")],
    },
    {
        "id": "pasteboard-permissioned-lifecycle",
        "status": "functional_with_permission",
        "syscaps": ["SystemCapability.MiscServices.Pasteboard"],
        "evidence": [("hap", r"pasteboard\.lifecycle=value:ohos-qemu-capability-audit,cleared:true")],
    },
    {
        "id": "power-state-query",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.PowerManager.PowerManager.Core"],
        "evidence": [("hap", r"power\.state\.result=active:true,screen:true,mode:\d+")],
    },
    {
        "id": "system-time-timezone",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.MiscServices.Time"],
        "evidence": [("hap", r"time\.state\.result=time:\d+,timezone:Asia/Shanghai")],
    },
    {
        "id": "wallpaper-color-query",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.MiscServices.Wallpaper"],
        "evidence": [("hap", r"wallpaper\.colors\.result=count:1")],
    },
    {
        "id": "input-device-enumeration",
        "status": "functional_virtual_devices",
        "syscaps": ["SystemCapability.MultimodalInput.Input.InputDevice"],
        "evidence": [("hap", r"input\.devices\.result=\[0,1,2\]")],
    },
    {
        "id": "image-decode-pixelmap-encode",
        "status": "functional_subset",
        "syscaps": [
            "SystemCapability.Multimedia.Image.ImageSource",
            "SystemCapability.Multimedia.Image.ImagePacker",
        ],
        "evidence": [("hap", r"image\.codec\.lifecycle=source:1x1,pixel:1x1,encoded:99")],
    },
    {
        "id": "app-account-lifecycle",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Account.AppAccount"],
        "evidence": [("hap", r"account\.app\.lifecycle=created:true,removed:true")],
    },
    {
        "id": "relational-store-lifecycle",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.DistributedDataManager.RelationalStore.Core"],
        "evidence": [("hap", r"data\.rdb\.lifecycle=value:ohos-qemu-capability-audit,removed:true")],
    },
    {
        "id": "asset-store-lifecycle",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Security.Asset"],
        "evidence": [("hap", r"security\.asset\.lifecycle=initial:1,updated_secret:10,removed:true")],
    },
    {
        "id": "contacts-lifecycle",
        "status": {
            "phone": "functional_subset",
            "2in1": "functional_but_outside_official_device_contract",
        },
        "syscaps": [
            "SystemCapability.Applications.Contacts",
            "SystemCapability.Applications.ContactsData",
        ],
        "evidence": [("hap", r"contacts\.lifecycle=id:\d+,found:true,removed:true")],
    },
    {
        "id": "calendar-lifecycle",
        "status": {
            "phone": "functional_subset",
            "2in1": "broken_permission_path",
        },
        "syscaps": ["SystemCapability.Applications.CalendarData"],
        "evidence": {
            "phone": [("hap", r"calendar\.lifecycle=count:\d+,removed:true")],
            "2in1": [("hap", r"calendar\.error=Error: CreateCalendar failed!:\{\"code\":201\}")],
        },
    },
    {
        "id": "notification-publish-authorization",
        "status": "conditional_user_authorization_required",
        "syscaps": ["SystemCapability.Notification.Notification"],
        "evidence": [("hap", r"notification\.publish\.error=Error: Notification disabled:\{\"code\":1600004\}")],
    },
    {
        "id": "native-binding-regression-suite",
        "status": {
            "phone": "96_pass_3_device_boundary_failures",
            "2in1": "96_pass_3_permission_or_fixture_failures",
        },
        "syscaps": [
            "SystemCapability.ArkUI.ArkUI.Full",
            "SystemCapability.ArkCompiler.JSVM",
            "SystemCapability.Graphic.Graphic2D.NativeDrawing",
            "SystemCapability.Graphic.Graphic2D.NativeVsync",
            "SystemCapability.WindowManager.WindowManager.Core",
        ],
        "evidence": [("native_suite", r'"failed": 3,[\s\S]{0,120}"id": "full_suite"[\s\S]{0,200}"module_count": 33')],
    },
    {
        "id": "oaid-permission-boundary",
        "status": "functional_with_user_permission",
        "syscaps": ["SystemCapability.Advertising.OAID"],
        "evidence": [("hap", r"advertising\.oaid\.result=(?!00000000-0000-0000-0000-000000000000)[0-9a-f-]{36}")],
    },
    {
        "id": "crypto-cipher-and-mac",
        "status": "functional_subset",
        "syscaps": [
            "SystemCapability.Security.CryptoFramework",
            "SystemCapability.Security.CryptoFramework.Cipher",
            "SystemCapability.Security.CryptoFramework.Key.SymKey",
            "SystemCapability.Security.CryptoFramework.Mac",
        ],
        "evidence": [("hap", r"security\.crypto\.extended=cipher:32,mac:32")],
    },
    {
        "id": "local-single-version-kv-store",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.DistributedDataManager.KVStore.Core"],
        "evidence": [("hap", r"data\.kv\.lifecycle=value:ohos-qemu-capability-audit,removed:true")],
    },
    {
        "id": "zlib-file-roundtrip",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.BundleManager.Zlib"],
        "evidence": [("hap", r"bundle\.zlib\.lifecycle=archive:\d+,roundtrip:true")],
    },
    {
        "id": "dfx-application-event-and-checker",
        "status": "functional_subset",
        "syscaps": [
            "SystemCapability.HiviewDFX.HiAppEvent",
            "SystemCapability.HiviewDFX.HiChecker",
        ],
        "evidence": [
            ("hap", r"dfx\.hiappevent\.result=written:true"),
            ("hap", r"dfx\.hichecker\.lifecycle=added:true,removed:true"),
        ],
    },
    {
        "id": "avsession-lifecycle",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.Multimedia.AVSession.Core"],
        "evidence": [("hap", r"media\.avsession\.lifecycle=active:true,destroyed:true")],
    },
    {
        "id": "ability-share-picker-provider",
        "status": "unavailable_missing_system_provider",
        "syscaps": ["SystemCapability.Ability.AbilityRuntime.Core"],
        "evidence": [
            ("hap", r"ability\.share_picker\.start=success:true"),
            ("hap", r"ability\.share_picker\.callback_error=code:16000050"),
        ],
    },
    {
        "id": "photo-picker-provider",
        "status": {
            "phone": "functional_system_ui_extension",
            "2in1": "false_success_empty_result_provider_not_enabled",
        },
        "syscaps": ["SystemCapability.FileManagement.PhotoAccessHelper.Core"],
        "evidence": {
            "phone": [("provider_hilog", r"com\.ohos\.photos/PickerUIExtensionAbility.*FOREGROUND")],
            "2in1": [("hap", r"file\.photo_picker\.result=\{\"photoUris\":\[\]")],
        },
    },
    {
        "id": "avcast-picker-provider",
        "status": "false_success_system_provider_unusable",
        "syscaps": [
            "SystemCapability.Multimedia.AVSession.AVCast",
            "SystemCapability.Multimedia.AVSession.AVInputCast",
        ],
        "evidence": [("hap", r"media\.avcast_picker\.immediate_result=success:true")],
    },
    {
        "id": "background-transient-task",
        "status": "functional_subset",
        "syscaps": ["SystemCapability.ResourceSchedule.BackgroundTaskManager.TransientTask"],
        "evidence": [("hap", r"resource\.background_suspend\.lifecycle=request:\d+,cancelled:true")],
    },
    {
        "id": "folder-obtain",
        "status": {
            "phone": "advertised_outside_contract_and_unsupported",
            "2in1": "unavailable_despite_official_contract",
        },
        "syscaps": ["SystemCapability.FileManagement.File.Environment.FolderObtain"],
        "evidence": [("hap", r"file\.environment\.result=download:error:Error: The device doesn't support this api:\{\"code\":801\}")],
    },
    {
        "id": "fusion-connectivity-services",
        "status": "unavailable_invalid_service_accounts",
        "syscaps": ["SystemCapability.Communication.FusionConnectivity.Core"],
        "evidence": [
            ("serial", r"failed get uid for service fusion_ranging"),
            ("serial", r"failed get uid for service partner_device_agent"),
        ],
    },
    {
        "id": "backup-service-init",
        "status": "unavailable_invalid_capability",
        "syscaps": ["SystemCapability.FileManagement.StorageService.Backup"],
        "evidence": [("serial", r"service=backup_sa not support caps = CAP_CHMOD")],
    },
    {
        "id": "module-update-initializer",
        "status": "partial_missing_initializer",
        "syscaps": ["SystemCapability.Update.UpdateService"],
        "evidence": [("serial", r"module_update_init\.cpp:.*No such file or directory")],
    },
    {
        "id": "usage-statistics-init-profile",
        "status": "partial_invalid_duplicate_profile",
        "syscaps": ["SystemCapability.ResourceSchedule.UsageStatistics.App"],
        "evidence": [("serial", r"failed get path for service device_usage_stats_service")],
    },
    {
        "id": "wifi-hal-packaging",
        "status": "unavailable",
        "syscaps": ["SystemCapability.Communication.WiFi.Core"],
        "evidence": [("serial", r"wifi_hal_service,/system/bin/wifi_hal_service")],
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
        "id": "thermal-init-account",
        "status": "partial_invalid_data_directory_owner",
        "syscaps": ["SystemCapability.PowerManager.ThermalManager"],
        "evidence": [("serial", r"SetOwner invalid uid : thermal")],
    },
    {
        "id": "useriam-fingerprint-enrollment",
        "status": "service_reachable_no_enrollment",
        "syscaps": ["SystemCapability.UserIAM.UserAuth.Core"],
        "evidence": [("hap", r"useriam\.fingerprint\.available_status\.error=.*12500010")],
    },
    {
        "id": "advertising-oaid-consent",
        "status": "conditional_consent_not_granted",
        "syscaps": ["SystemCapability.Advertising.OAID"],
        "evidence": [("hap", r"advertising\.oaid\.result=00000000-0000-0000-0000-000000000000")],
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

    def compact_or_raw(compact: Path, raw: list[Path]) -> str:
        """Use the checked-in compact evidence when available.

        The versioned probe directories are useful while investigating a live
        image, but most of them contain repeated module inventories and large
        hilog captures.  The compact files retain every expression consumed by
        this audit and make a clean checkout independently reproducible.
        """
        return combined([compact]) if compact.exists() else combined(raw)

    serial_log = root / "serial-reprobe.log"
    if not serial_log.exists():
        serial_log = root / "serial-boot.log"

    return {
        "serial": combined([serial_log]),
        "hardware": combined([root / "hardware-backends.txt", root / "hardware-backends-fresh.txt"]),
        "hap": compact_or_raw(root / "hap-probe-evidence.log", [
            root / "hap-probe-v41-provider-only/results.log",
            root / "hap-probe-v41-after-provider-install/results-fresh.log",
            root / "hap-probe-v40-system-core/results.log",
            root / "hap-probe-v38-system-core/results.log",
            root / "hap-probe-v35-system-core/results.log",
            root / "hap-probe-v33-system-core/results.log",
            root / "hap-probe-v32-system-core/results.log",
            root / "hap-probe-v31-system-core/results.log",
            root / "hap-probe-v30-system-core/results.log",
            root / "hap-probe-v29-system-core/results.log",
            root / "hap-probe-v26-system-core/results.log",
            root / "hap-probe-v19-system-core/results.log",
            root / "hap-probe-v15/results.log",
            root / "hap-probe-v14/results.log",
            root / "hap-probe-v13/results.log",
            root / "hap-probe-v12/results.log",
            root / "hap-probe-v11/results.log",
            root / "hap-probe-v10/results.log",
            root / "hap-probe-v9/results.log",
            root / "hap-probe-v8/results.log",
            root / "hap-probe-v7/results.log",
            root / "hap-probe-v6/results.log",
            root / "hap-probe-v5/results.log",
            root / "hap-probe-v4/results.log",
            root / "hap-probe-v3/results.log",
            root / "hap-probe-v2/results.log",
            root / "hap-probe/results-expanded.log",
        ]),
        "radio": combined([root / "radio-cli-probes.txt", root / "thermal-radio-logs.txt"]),
        "a11y": combined(sorted((root / "accessibility-e2e").glob("*"))) if (root / "accessibility-e2e").is_dir() else "",
        "native/vulkan": combined([root / "native-probes/vulkan.txt"]),
        "native/bpf": combined([root / "native-probes/bpf.txt"]),
        "native/quota": combined([root / "native-probes/quota.txt"]),
        "native/egl": combined([root / "native-probes/egl-gles.txt"]),
        "native/huks": combined([root / "native-probes/huks.txt"]),
        "native_suite": combined([root / "native-ohostest-summary.json"]),
        "web_hilog": compact_or_raw(root / "web-gpu-evidence.log", [
            root / "hap-probe-v9/web-gpu-hilog.txt",
            root / "hap-probe-v8/web-gpu-hilog.txt",
            root / "hap-probe-v4/hilog.txt",
        ]),
        "provider_hilog": compact_or_raw(root / "provider-ui-evidence.log", [
            root / "hap-probe-v32-system-core/picker-hilog.txt",
            root / "hap-probe-v35-system-core/hilog.txt",
            root / "hap-probe-v33-system-core/hilog.txt",
            root / "hap-probe-v41-provider-only/hilog.txt",
        ]),
        "preinstall": combined([root / "preinstalled-hap-audit.json"]),
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
