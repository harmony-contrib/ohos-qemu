#!/usr/bin/env python3
"""Audit system-app providers used behind public OHOS APIs on phone and 2in1.

SysCap and System Ability checks cannot detect an API whose service delegates to
a missing, disabled, wrongly signed, or wrongly named HAP.  This audit joins
production source references with the packaged HAP inventory and live BMS state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
from typing import Any


DEVICES = ("phone", "2in1")
BUNDLE_RE = re.compile(r"com\.(?:ohos|hmos)\.[A-Za-z0-9_.]+|com\.usb\.[A-Za-z0-9_.]+")

RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "ability-share-picker",
        "public_surfaces": ["UIAbilityContext.startAbilityByType('share')"],
        "syscaps": ["SystemCapability.Ability.AbilityRuntime.Core"],
        "providers": ["com.ohos.sharepickerdialog"],
        "implementation_targets": ["com.ohos.sharepickerdialog"],
        "required_entrypoints": ["PickerDialog"],
    },
    {
        "id": "distributed-hardware-ui",
        "public_surfaces": ["@ohos.distributedHardware.deviceManager UI flows"],
        "syscaps": ["SystemCapability.DistributedHardware.DeviceManager"],
        "providers": ["com.ohos.dhardwareui"],
        "implementation_targets": ["com.ohos.dhardwareui"],
        "required_entrypoints": ["MechExtAbility"],
    },
    {
        "id": "device-manager-pairing-ui",
        "public_surfaces": ["@ohos.distributedDeviceManager authentication and pairing UI"],
        "syscaps": ["SystemCapability.DistributedHardware.DeviceManager"],
        "providers": ["com.ohos.devicemanagerui"],
        "implementation_targets": ["com.ohos.devicemanagerui"],
        "required_entrypoints": ["ConfirmUIExtAbility", "PincodeUIExtAbility", "InputUIExtAbility"],
    },
    {
        "id": "dlp-management-ui",
        "public_surfaces": ["@ohos.dlpPermission"],
        "syscaps": ["SystemCapability.Security.DataLossPrevention"],
        "providers": ["com.ohos.dlpmanager"],
        "implementation_targets": ["com.ohos.dlpmanager"],
    },
    {
        "id": "photo-picker-and-photo-ui",
        "public_surfaces": ["PhotoViewPicker", "PhotoAccessHelper UI operations"],
        "syscaps": ["SystemCapability.FileManagement.PhotoAccessHelper.Core"],
        "providers": ["com.ohos.photos"],
        "implementation_targets": ["com.ohos.photos"],
        "required_entrypoints": ["PickerUIExtensionAbility", "DeleteUIExtensionAbility", "SaveUIExtensionAbility"],
    },
    {
        "id": "print-spooler",
        "public_surfaces": ["@ohos.print", "@ohos.printManager"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.spooler"],
        "implementation_targets": ["com.ohos.spooler"],
        "required_entrypoints": ["PrintServiceExtAbility"],
    },
    {
        "id": "calendar-data",
        "public_surfaces": ["@ohos.calendarManager", "@ohos.reminderAgentManager"],
        "syscaps": ["SystemCapability.Applications.CalendarData"],
        "providers": ["com.ohos.calendardata"],
        "implementation_targets": ["com.ohos.calendardata"],
    },
    {
        "id": "media-control-ui",
        "public_surfaces": ["AVCastPickerHelper", "AVCastPicker", "AVInputCastPicker", "AVVolumePanel"],
        "syscaps": ["SystemCapability.Multimedia.AVSession.Core"],
        "providers": ["com.hmos.mediacontroller"],
        "implementation_targets": ["com.ohos.mediacontroller", "com.hmos.mediacontroller"],
        "required_entrypoints": ["UIExtAbility", "AVVolumeExtension", "AVInputCastPickerAbility", "DialogExtension"],
    },
    {
        "id": "file-picker",
        "public_surfaces": ["@ohos.file.picker", "@ohos.file.fileAccess"],
        "syscaps": ["SystemCapability.FileManagement.UserFileService"],
        "providers": ["com.ohos.filepicker", "com.ohos.filemanager"],
        "implementation_targets": ["com.ohos.filepicker", "com.ohos.filemanager"],
        "provider_mode": "any",
        "required_entrypoints": ["FilePickerUIExtAbility"],
    },
    {
        "id": "external-file-manager",
        "public_surfaces": ["@ohos.file.volumeManager", "StorageManager file-access UI"],
        "syscaps": ["SystemCapability.FileManagement.StorageService"],
        "providers": ["com.ohos.UserFile.ExternalFileManager"],
        "implementation_targets": ["com.ohos.UserFile.ExternalFileManager"],
    },
    {
        "id": "privacy-center",
        "public_surfaces": ["relational-store privacy and silent-access UI"],
        "syscaps": ["SystemCapability.DistributedDataManager.RelationalStore.Core"],
        "providers": ["com.ohos.security.privacycenter"],
        "implementation_targets": ["com.ohos.security.privacycenter"],
    },
    {
        "id": "permission-manager-dialogs",
        "public_surfaces": ["AccessToken permission request, permission settings and security-component dialogs"],
        "syscaps": ["SystemCapability.Security.AccessToken"],
        "providers": ["com.ohos.permissionmanager"],
        "implementation_targets": ["com.ohos.permissionmanager"],
        "required_entrypoints": [
            "GrantAbility",
            "GlobalExtAbility",
            "SecurityExtAbility",
            "PermissionStateSheetAbility",
            "GlobalSwitchSheetAbility",
            "MainAbility",
            "OpenSettingAbility",
        ],
    },
    {
        "id": "accessibility-screen-reader",
        "public_surfaces": ["AccessibilityManager screen-reader enablement and accessibility shortcut"],
        "syscaps": [
            "SystemCapability.BarrierFree.Accessibility.Core",
            "SystemCapability.BarrierFree.Accessibility.Vision",
        ],
        "providers": ["com.ohos.screenreader", "com.ohos.hmos.screenreader"],
        "implementation_targets": ["com.ohos.screenreader", "com.ohos.hmos.screenreader"],
        "provider_mode": "any",
        "required_entrypoints": ["AccessibilityExtAbility"],
    },
    {
        "id": "accessibility-caption-assistant",
        "public_surfaces": ["Accessibility CaptionsManager caption assistant activation"],
        "syscaps": ["SystemCapability.BarrierFree.Accessibility.Hearing"],
        "providers": ["com.ohos.vassistant"],
        "implementation_targets": ["com.ohos.vassistant"],
        "required_entrypoints": ["AiCaptionServiceExtAbility"],
    },
    {
        "id": "location-dialog",
        "public_surfaces": ["location permission and switch dialogs"],
        "syscaps": ["SystemCapability.Location.Location.Core"],
        "providers": ["com.ohos.locationdialog"],
        "implementation_targets": ["com.ohos.locationdialog"],
    },
    {
        "id": "bluetooth-dialog",
        "public_surfaces": ["Bluetooth pairing and sharing UI"],
        "syscaps": ["SystemCapability.Communication.Bluetooth.Core"],
        "providers": ["com.ohos.bluetooth"],
        "implementation_targets": ["com.ohos.bluetooth"],
    },
    {
        "id": "camera-picker-ui",
        "public_surfaces": ["@ohos.multimedia.cameraPicker", "camera capture UI"],
        "syscaps": ["SystemCapability.Multimedia.Camera.Core"],
        "providers": ["com.ohos.camera"],
        "implementation_targets": ["com.ohos.camera"],
        "required_entrypoints": ["ExtensionPickerAbility"],
    },
    {
        "id": "settings-ui",
        "public_surfaces": ["Settings UIExtension and settings ability flows"],
        "syscaps": ["SystemCapability.Applications.Settings.Core"],
        "providers": ["com.ohos.settings"],
        "implementation_targets": ["com.ohos.settings"],
    },
    {
        "id": "system-ui",
        "public_surfaces": ["notification, system-dialog, status-bar and screen-lock UI"],
        "syscaps": ["SystemCapability.Notification.Notification"],
        "providers": ["com.ohos.systemui", "com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.systemui", "com.ohos.sceneboard"],
        "provider_mode": "any",
    },
    {
        "id": "launcher-ui",
        "public_surfaces": ["launcher and recent-task UI"],
        "syscaps": ["SystemCapability.BundleManager.BundleFramework.Launcher"],
        "providers": ["com.ohos.launcher", "com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.launcher", "com.ohos.sceneboard"],
        "provider_mode": "any",
    },
    {
        "id": "contacts-ui",
        "public_surfaces": ["contacts picker and contacts UI operations"],
        "syscaps": ["SystemCapability.Applications.Contacts"],
        "providers": ["com.ohos.contacts"],
        "implementation_targets": ["com.ohos.contacts"],
    },
    {
        "id": "telephony-call-and-message-ui",
        "public_surfaces": ["call-management and SMS/MMS UI flows"],
        "syscaps": ["SystemCapability.Telephony.CallManager", "SystemCapability.Telephony.SmsMms"],
        "providers": ["com.ohos.callui", "com.ohos.mms"],
        "implementation_targets": ["com.ohos.callui", "com.ohos.mms"],
        "provider_mode": "all",
    },
    {
        "id": "intelligent-scene",
        "public_surfaces": ["@ohos.intelligentScene"],
        "syscaps": ["SystemCapability.Applications.IntelligentScene"],
        "providers": ["com.ohos.intelligentscene"],
        "implementation_targets": ["com.ohos.intelligentscene"],
    },
    {
        "id": "emergency-communication",
        "public_surfaces": ["telephony emergency communication UI"],
        "syscaps": ["SystemCapability.Telephony.CoreService"],
        "providers": ["com.ohos.emergencycommunication"],
        "implementation_targets": ["com.ohos.emergencycommunication"],
    },
    {
        "id": "enterprise-provisioning",
        "public_surfaces": ["@ohos.enterprise.adminManager provisioning"],
        "syscaps": ["SystemCapability.Customization.EnterpriseDeviceManager"],
        "providers": ["com.ohos.adminprovisioning"],
        "implementation_targets": ["com.ohos.adminprovisioning"],
    },
    {
        "id": "wallpaper-ui",
        "public_surfaces": ["@ohos.wallpaper UI extension operations"],
        "syscaps": ["SystemCapability.MiscServices.Wallpaper"],
        "providers": ["com.ohos.wallpaper"],
        "implementation_targets": ["com.ohos.wallpaper"],
    },
    {
        "id": "usb-dialog",
        "public_surfaces": ["@ohos.usbManager permission and function-switch dialogs"],
        "syscaps": ["SystemCapability.USB.USBManager"],
        "providers": ["com.usb.right"],
        "implementation_targets": ["com.usb.right"],
        "stale_config_targets": ["com.usb.function"],
        "required_entrypoints": ["UsbFunctionSwitchExtAbility"],
    },
    {
        "id": "notification-enable-dialog",
        "public_surfaces": ["Notification authorization dialog"],
        "syscaps": ["SystemCapability.Notification.Notification"],
        "providers": ["com.ohos.notificationdialog"],
        "implementation_targets": ["com.ohos.notificationdialog"],
        "required_entrypoints": ["EnableNotificationDialog"],
    },
    {
        "id": "pasteboard-privacy-dialog",
        "public_surfaces": ["Pasteboard privacy toast and progress UI"],
        "syscaps": ["SystemCapability.MiscServices.Pasteboard"],
        "providers": ["com.ohos.pasteboarddialog"],
        "implementation_targets": ["com.ohos.pasteboarddialog"],
        "required_entrypoints": ["ToastExtensionAbility", "PasteboardProgressAbility"],
    },
    {
        "id": "background-task-authorization-dialog",
        "public_surfaces": ["BackgroundTaskManager continuous-task authorization UI"],
        "syscaps": ["SystemCapability.ResourceSchedule.BackgroundTaskManager.ContinuousTask"],
        "providers": ["com.ohos.backgroundtaskmgr.resources"],
        "implementation_targets": ["com.ohos.backgroundtaskmgr.resources"],
        "required_entrypoints": ["EnableBgTaskAuthDialog"],
    },
    {
        "id": "input-method-chooser-dialog",
        "public_surfaces": ["InputMethodController input-method chooser"],
        "syscaps": ["SystemCapability.MiscServices.InputMethodFramework"],
        "providers": ["com.ohos.inputmethodchoosedialog"],
        "implementation_targets": ["com.ohos.inputmethodchoosedialog"],
        "required_entrypoints": ["InputMethod"],
    },
    {
        "id": "vpn-dialog",
        "public_surfaces": ["VpnExtension authorization and status UI"],
        "syscaps": ["SystemCapability.Communication.NetManager.Vpn"],
        "providers": ["com.ohos.vpndialog"],
        "implementation_targets": ["com.ohos.vpndialog"],
        "required_entrypoints": ["VpnServiceExtAbility"],
    },
    {
        "id": "certificate-manager-dialog",
        "public_surfaces": ["CertificateManagerDialog certificate picker and management UI"],
        "syscaps": ["SystemCapability.Security.CertificateManagerDialog"],
        "providers": ["com.ohos.certmanager"],
        "implementation_targets": ["com.ohos.certmanager"],
        "required_entrypoints": ["MainExtensionAbility", "CertPickerUIExtAbility"],
    },
    {
        "id": "user-auth-widget",
        "public_surfaces": ["UserAuth authentication modal UI"],
        "syscaps": ["SystemCapability.UserIAM.UserAuth.Core"],
        "providers": ["com.ohos.useriam.authwidget"],
        "implementation_targets": ["com.ohos.useriam.authwidget"],
        "required_entrypoints": ["userauthuiextensionability"],
    },
    {
        "id": "form-render-service",
        "public_surfaces": ["FormExtension hosted rendering"],
        "syscaps": ["SystemCapability.Ability.Form"],
        "providers": ["com.ohos.formrenderservice"],
        "implementation_targets": ["com.ohos.formrenderservice"],
        "required_entrypoints": ["ServiceExtension"],
    },
    {
        "id": "power-and-thermal-dialog",
        "public_surfaces": ["PowerManager and ThermalManager system UI"],
        "syscaps": [
            "SystemCapability.PowerManager.PowerManager.Core",
            "SystemCapability.PowerManager.ThermalManager",
        ],
        "providers": ["com.ohos.powerdialog"],
        "implementation_targets": ["com.ohos.powerdialog"],
        "required_entrypoints": ["PowerUiExtensionAbility"],
    },
    {
        "id": "ability-manager-system-dialog",
        "public_surfaces": ["AbilityManager selector, interceptor, user-switch and assertion dialogs"],
        "syscaps": ["SystemCapability.Ability.AbilityRuntime.Core"],
        "providers": ["com.ohos.amsdialog"],
        "implementation_targets": ["com.ohos.amsdialog"],
        "required_entrypoints": ["SelectorDialog", "JumpInterceptorDialog", "SwitchUserDialog"],
    },
    {
        "id": "print-vendor-extension",
        "public_surfaces": ["PrintService printer discovery and vendor extension"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.hwprintext"],
        "implementation_targets": ["com.ohos.hwprintext"],
    },
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohos-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enabled_bundles(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if BUNDLE_RE.fullmatch(line.strip())
    }


def source_references(
    root: Path,
) -> tuple[Counter[str], dict[str, list[str]], dict[str, Counter[str]]]:
    paths = [root / name for name in ("base", "foundation", "applications") if (root / name).is_dir()]
    command = [
        "rg", "-n", "--no-heading", "-o", BUNDLE_RE.pattern,
        *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "*.json", "-g", "*.json5", "-g", "*.cfg", "-g", "*.conf",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg source scan failed")
    counts: Counter[str] = Counter()
    locations: dict[str, list[str]] = defaultdict(list)
    areas: dict[str, Counter[str]] = defaultdict(Counter)
    for line in proc.stdout.splitlines():
        match = re.match(r"(.+?):(\d+):(" + BUNDLE_RE.pattern + r")$", line)
        if not match:
            continue
        bundle = match.group(3).rstrip(".")
        counts[bundle] += 1
        try:
            relative = Path(match.group(1)).relative_to(root)
            area = relative.parts[0] if relative.parts else "unknown"
        except ValueError:
            relative = Path(match.group(1))
            area = "external"
        areas[bundle][area] += 1
        if len(locations[bundle]) < 20:
            source = str(relative)
            locations[bundle].append(f"{source}:{match.group(2)}")
    return counts, locations, areas


def source_declared_bundles(root: Path) -> dict[str, list[str]]:
    """Collect actual app bundle declarations for token normalization."""
    paths = [root / name for name in ("base", "foundation", "applications") if (root / name).is_dir()]
    command = [
        "rg", "-n", "bundleName", *map(str, paths),
        "-g", "**/AppScope/app.json", "-g", "**/AppScope/app.json5",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/ohosTest/**",
        "-g", "!**/example/**", "-g", "!**/examples/**",
        "-g", "!**/sample/**", "-g", "!**/samples/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg bundle declaration scan failed")
    declared: dict[str, list[str]] = defaultdict(list)
    declaration = re.compile(
        r"^(.+?):(\d+):.*?[\"']bundleName[\"']\s*:\s*[\"'](" + BUNDLE_RE.pattern + r")[\"']"
    )
    for line in proc.stdout.splitlines():
        match = declaration.match(line)
        if not match:
            continue
        try:
            source = str(Path(match.group(1)).relative_to(root))
        except ValueError:
            source = match.group(1)
        declared[match.group(3)].append(f"{source}:{match.group(2)}")
    return declared


def bundle_state(bundle: str, enabled: set[str], payload: set[str], configured: set[str]) -> str:
    if bundle in enabled:
        return "enabled"
    if bundle in payload:
        return "payload_not_enabled"
    if bundle in configured:
        return "configured_but_payload_missing"
    return "absent"


def has_entrypoint(available: set[str], required: str) -> bool:
    return any(value == required or value.endswith("." + required) for value in available)


def main() -> int:
    args = arguments()
    counts, locations, areas = source_references(args.ohos_root)
    declared_bundles = source_declared_bundles(args.ohos_root)
    matrix = {row["syscap"]: row for row in read(args.matrix)["capabilities"]}
    device_data: dict[str, dict[str, Any]] = {}
    known_bundles: set[str] = set()
    for device in DEVICES:
        root = args.runtime_root / f"arm64-{device}"
        preinstall = read(root / "preinstalled-hap-audit.json")
        config = read(root / "config-bundle-reference-audit.json")
        payload = {row["bundle"] for row in preinstall["haps"] if row.get("bundle")}
        enabled = enabled_bundles(root / "bundles.txt")
        configured = {row["bundle"] for row in config["references"]}
        entrypoints: dict[str, set[str]] = defaultdict(set)
        for row in preinstall["haps"]:
            if not row.get("bundle"):
                continue
            entrypoints[row["bundle"]].update(
                item["name"] for item in row.get("abilities", []) if item.get("name")
            )
            entrypoints[row["bundle"]].update(
                item["name"] for item in row.get("extensions", []) if item.get("name")
            )
        known_bundles.update(payload | enabled | configured)
        device_data[device] = {
            "enabled": enabled,
            "payload": payload,
            "configured": configured,
            "certificate_mismatches": {
                row["bundle"] for row in preinstall["certificate_mismatches"] if row.get("bundle")
            },
            "path_mismatches": {
                bundle
                for row in preinstall.get("preinstall_path_mismatch_candidates", [])
                for bundle in [Path(row["app_dir"]).name]
            },
            "entrypoints": entrypoints,
        }

    all_rule_targets = {
        bundle
        for rule in RULES
        for key in ("providers", "implementation_targets", "stale_config_targets")
        for bundle in rule.get(key, [])
    }
    # Every production token is retained.  The previous implementation first
    # intersected source tokens with already-known packages, which hid exactly
    # the most important case: a framework naming a provider that is absent
    # from both the image and its install configuration.
    canonical_bundles = known_bundles | all_rule_targets | set(declared_bundles)
    source_rows: list[dict[str, Any]] = []
    for token in sorted(counts):
        candidates = [
            bundle
            for bundle in canonical_bundles
            if token == bundle or token.startswith(bundle + ".") or token.startswith(bundle + "_")
        ]
        bundle = max(candidates, key=len) if candidates else None
        source_rows.append({
            "token": token,
            "normalized_bundle": bundle,
            "classification": (
                "exact_bundle"
                if token == bundle
                else "bundle_entrypoint_or_namespace"
                if bundle
                else "nonlocal_namespace_or_external_bundle"
            ),
            "declared_in_source_tree": bool(bundle and bundle in declared_bundles),
            "declaration_locations": declared_bundles.get(bundle, [])[:10] if bundle else [],
            "production_source_reference_count": counts[token],
            "source_area_counts": dict(sorted(areas[token].items())),
            "sample_locations": sorted(set(locations[token]))[:20],
            "devices": {
                device: (
                    bundle_state(
                        bundle,
                        device_data[device]["enabled"],
                        device_data[device]["payload"],
                        device_data[device]["configured"],
                    )
                    if bundle else "unresolved_token"
                )
                for device in DEVICES
            },
        })

    rule_rows: list[dict[str, Any]] = []
    for rule in RULES:
        devices: dict[str, Any] = {}
        for device in DEVICES:
            data = device_data[device]
            provider_states = {
                bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                for bundle in rule["providers"]
            }
            target_states = {
                bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                for bundle in rule["implementation_targets"]
            }
            enabled_providers = [bundle for bundle, state in provider_states.items() if state == "enabled"]
            payload_providers = [
                bundle for bundle, state in provider_states.items() if state == "payload_not_enabled"
            ]
            wrong_targets = [
                bundle
                for bundle, state in target_states.items()
                if state in {"absent", "configured_but_payload_missing"}
                and counts.get(bundle, 0) > 0
                and any(
                    other.split(".", 2)[-1] == bundle.split(".", 2)[-1]
                    for other in data["payload"] | data["enabled"]
                )
            ]
            required_entrypoints = rule.get("required_entrypoints", [])
            available_entrypoints = {
                value
                for bundle in rule["providers"]
                for value in data["entrypoints"].get(bundle, set())
            }
            missing_entrypoints = [
                value for value in required_entrypoints if not has_entrypoint(available_entrypoints, value)
            ]
            mode = rule.get("provider_mode", "all")
            providers_enabled = (
                bool(enabled_providers)
                if mode == "any"
                else len(enabled_providers) == len(rule["providers"])
            )
            providers_in_payload = (
                bool(enabled_providers or payload_providers)
                if mode == "any"
                else len(enabled_providers) + len(payload_providers) == len(rule["providers"])
            )
            if wrong_targets:
                status = "implementation_target_mismatch"
            elif providers_enabled and missing_entrypoints:
                status = "provider_entrypoint_missing"
            elif providers_enabled:
                status = "provider_enabled"
            elif providers_in_payload:
                status = "provider_payload_not_enabled"
            elif any(state == "configured_but_payload_missing" for state in provider_states.values()):
                status = "provider_configured_but_payload_missing"
            else:
                status = "provider_absent"
            devices[device] = {
                "contract_expected": any(
                    matrix.get(syscap, {}).get("devices", {}).get(device, {}).get("contract_expected", False)
                    for syscap in rule["syscaps"]
                ),
                "status": status,
                "provider_states": provider_states,
                "implementation_target_states": target_states,
                "certificate_mismatch_providers": sorted(set(rule["providers"]) & data["certificate_mismatches"]),
                "preinstall_path_mismatch_providers": sorted(set(rule["providers"]) & data["path_mismatches"]),
                "available_provider_entrypoints": sorted(available_entrypoints),
                "missing_required_entrypoints": missing_entrypoints,
                "stale_config_target_states": {
                    bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                    for bundle in rule.get("stale_config_targets", [])
                },
            }
        rule_rows.append({**rule, "devices": devices})

    unresolved = {
        device: sum(
            row["devices"][device]["contract_expected"]
            and row["devices"][device]["status"] != "provider_enabled"
            for row in rule_rows
        )
        for device in DEVICES
    }
    result = {
        "schema_version": 2,
        "summary": {
            "production_bundle_token_count": sum(counts.values()),
            "production_bundle_token_unique_count": len(counts),
            "system_bundle_reference_count": len(source_rows),
            "framework_or_service_bundle_token_count": sum(
                bool(row["source_area_counts"].get("base") or row["source_area_counts"].get("foundation"))
                for row in source_rows
            ),
            "nonlocal_namespace_or_external_bundle_token_count": sum(
                row["classification"] == "nonlocal_namespace_or_external_bundle" for row in source_rows
            ),
            "source_declared_bundle_count": len(declared_bundles),
            "provider_rule_count": len(rule_rows),
            "phone_non_usable_provider_rule_count": unresolved["phone"],
            "2in1_non_usable_provider_rule_count": unresolved["2in1"],
        },
        "provider_rules": rule_rows,
        "source_bundle_references": source_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
