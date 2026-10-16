#!/usr/bin/env python3
"""Create an effective full phone profile for standard QEMU products."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from device_contract import apply_contract_overrides, contract_overlay
from sceneboard_profile import (any_sceneboard_enabled, configure_sceneboard_runtime,
                                sceneboard_metadata)


UPSTREAM_PROFILE = "productdefine/common/inherit/phone.json"
RICH_PROFILE = "productdefine/common/inherit/rich.json"
EFFECTIVE_PROFILE = "vendor/ohemu/virt/virt_phone_full.json"
PROFILE_METADATA = "vendor/ohemu/virt/virt_phone_full.meta.json"
PRODUCT_PARAM_FILE = "vendor/ohemu/virt/etc/param/product_virt.para"
APP_COMPAT_COMMENT = "# QEMU full device-profile compatibility for current system HAPs."
APP_COMPAT_PARAM = "const.bms.supportAppTypes=2in1,phone,default,tablet"
PHONE_WINDOW_PARAM = "const.window.multiWindowUIType=HandsetSmartWindow"
PHONE_MODE_PARAM = "persist.sceneboard.ispcmode=false"
MANAGED_APP_COMPAT_LINES = {
    APP_COMPAT_COMMENT,
    APP_COMPAT_PARAM,
    "# QEMU full 2in1 compatibility for current default/tablet system HAPs.",
    "const.bms.supportAppTypes=2in1,default,tablet",
}

PRODUCT_CONFIGS = {
    "arm64_virt": "vendor/ohemu/qemu_arm64_linux_full/config.json",
    "x86_64_virt": "vendor/ohemu/qemu_x86_64_linux_full/config.json",
    "armv7a_virt": "vendor/ohemu/qemu_armv7a_linux_full/config.json",
}

LEGACY_COMPONENTS = {
    ("applications", "contacts"): "applications/standard/contacts/bundle.json",
    ("thirdparty", "eudev"): "third_party/eudev",
    ("thirdparty", "libsnd"): "third_party/libsnd",
    ("wukong", "wukong"): "test/wukong",
}

CURRENT_COMPONENT_REPLACEMENTS = {
    ("applications", "contacts"): (
        "contacts_data",
        "contacts_data",
        "applications/standard/contacts_data/bundle.json",
    ),
    ("wukong", "wukong"): (
        "ostest",
        "wukong",
        "test/ostest/wukong/bundle.json",
    ),
}

REQUIRED_PHONE_PARTS = {
    "account:os_account",
    "applications:camera",
    "applications:photos",
    "applications:prebuilt_hap",
    "arkui:ui_appearance",
    "bundlemanager:bundle_framework",
    "communication:netmanager_base",
    "communication:netmanager_ext",
    "contacts_data:contacts_data",
    "hdf:drivers_peripheral_display",
    "msdp:device_status",
    "multimodalinput:input",
    "multimedia:audio_framework",
    "multimedia:av_session",
    "telephony:core_service",
    "window:window_manager",
}


def die(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"missing required OpenHarmony file: {path}")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"expected a JSON object in {path}")
    return data


def write_json(path: Path, data: dict) -> None:
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def component_map(document: dict) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for subsystem in document.get("subsystems", []):
        subsystem_name = subsystem.get("subsystem")
        for component in subsystem.get("components", []):
            name = component.get("component")
            if isinstance(subsystem_name, str) and isinstance(name, str):
                result[(subsystem_name, name)] = component
    return result


def remove_component(document: dict, key: tuple[str, str]) -> bool:
    subsystem_name, component_name = key
    removed = False
    new_subsystems = []
    for subsystem in document.get("subsystems", []):
        if subsystem.get("subsystem") == subsystem_name:
            components = subsystem.get("components", [])
            filtered = [
                component
                for component in components
                if component.get("component") != component_name
            ]
            removed = removed or len(filtered) != len(components)
            subsystem["components"] = filtered
            if not filtered:
                continue
        new_subsystems.append(subsystem)
    document["subsystems"] = new_subsystems
    return removed


def add_component(document: dict, subsystem_name: str, component_name: str) -> None:
    if (subsystem_name, component_name) in component_map(document):
        return
    for subsystem in document.get("subsystems", []):
        if subsystem.get("subsystem") == subsystem_name:
            subsystem.setdefault("components", []).append(
                {"component": component_name, "features": []}
            )
            return
    document.setdefault("subsystems", []).append(
        {
            "subsystem": subsystem_name,
            "components": [{"component": component_name, "features": []}],
        }
    )


def make_effective_profile(root: Path) -> tuple[dict, dict]:
    upstream_path = root / UPSTREAM_PROFILE
    rich_path = root / RICH_PROFILE
    upstream = load_json(upstream_path)
    rich = load_json(rich_path)
    effective = json.loads(json.dumps(upstream))
    omitted = []
    mapped = []

    unavailable_legacy_components = set()
    for key, source_path in LEGACY_COMPONENTS.items():
        if (root / source_path).exists():
            continue
        unavailable_legacy_components.add(key)
        if remove_component(effective, key):
            omitted.append(":".join(key))

    for legacy_key, replacement in CURRENT_COMPONENT_REPLACEMENTS.items():
        subsystem_name, component_name, source_path = replacement
        if legacy_key not in unavailable_legacy_components:
            continue
        if not (root / source_path).is_file():
            continue
        add_component(effective, subsystem_name, component_name)
        mapped.append(
            f"{':'.join(legacy_key)}->{subsystem_name}:{component_name}"
        )

    # QEMU ships Launcher/SystemUI through this rich-profile part. Keep it
    # explicit so a later phone profile cannot drop the first-user desktop.
    add_component(effective, "applications", "prebuilt_hap")
    # It may be present only as a transitive HDI dependency upstream. Product
    # selection is needed for its feature/default config dependency closure.
    add_component(effective, "thirdparty", "alsa-lib")
    # Selecting only the HDI leaves no dynamically loaded VDI/config closure.
    add_component(effective, "hdf", "drivers_peripheral_camera")
    # The public device-status service owns the real sensor algorithm selected
    # below. It is absent from the generic phone inheritance on this release.
    add_component(effective, "msdp", "device_status")

    # These parts are already selected by the QEMU rich base, not newly
    # introduced phone capabilities. Carry their exact rich settings so the
    # later phone/board contract overlay can remove only false declarations.
    for owner in (("systemabilitymgr", "selectionfwk"), ("print", "print_fwk")):
        if owner not in component_map(effective):
            inherited = component_map(rich).get(owner)
            if inherited is None:
                die("rich contract owner missing: " + ":".join(owner))
            add_component(effective, *owner)
            component_map(effective)[owner].update(json.loads(json.dumps(inherited)))

    # The generic phone profile clears the display-interface features. QEMU's
    # community VDI is a board requirement, so retain the rich values.
    effective_components = component_map(effective)
    rich_components = component_map(rich)
    display_key = ("hdf", "drivers_interface_display")
    if display_key in effective_components and display_key in rich_components:
        effective_components[display_key]["features"] = list(
            rich_components[display_key].get("features", [])
        )

    effective_parts = {
        f"{subsystem}:{component}"
        for subsystem, component in component_map(effective)
    }
    missing = sorted(REQUIRED_PHONE_PARTS - effective_parts)
    if missing:
        die("effective phone profile lost required parts: " + ", ".join(missing))

    contract_metadata = apply_contract_overrides(
        root, effective, "phone",
        {
            "SystemCapability.Communication.NetManager.NetFirewall": (
                "communication", "netmanager_ext",
                "Not in the official phone contract; QEMU has no validated phone firewall stack.",
            ),
            "SystemCapability.Multimedia.VideoProcessingEngine": (
                "multimedia", "media_foundation",
                "Not in the official phone contract; public processing libraries are not packaged.",
            ),
            "SystemCapability.SelectionInput.Selection": (
                "systemabilitymgr", "selectionfwk",
                "Officially 2in1-only; do not advertise the PC selection framework on phone.",
            ),
            "SystemCapability.FileManagement.File.Environment.FolderObtain": (
                "filemanagement", "file_api",
                "Outside the official phone contract; the phone API correctly returns unsupported.",
            ),
            "SystemCapability.USB.USBManager.Serial": (
                "usb", "usb_manager",
                "Outside the official phone contract; keep the required 2in1 serial implementation unchanged.",
            ),
            "SystemCapability.Print.PrintFramework": (
                "print", "print_fwk",
                "Outside the official phone contract; no phone printer extension is provided.",
            ),
        },
        {
            ("hdf", "drivers_peripheral_sensor"): {
                "drivers_peripheral_sensor_feature_community": True,
                "drivers_peripheral_sensor_feature_qemu_external": True,
            },
            ("msdp", "device_status"): {
                "device_status_sensor_enable": True,
                "device_status_allow_mock_fallback": False,
            },
            # Both ends of the native IPC ABI must use the same switches.
            # Enabling only ext builds callers whose implementations are absent
            # from NetsysController / NetsysNativeService.
            ("communication", "netmanager_base"): {
                "netmanager_base_enable_feature_net_firewall": False,
                "netmanager_base_enable_feature_sysvpn": True,
            },
            ("communication", "netmanager_ext"): {
                "netmanager_ext_feature_net_firewall": False,
                "netmanager_ext_feature_sysvpn": True,
            },
            # A false flag still produces an empty ohaudiosuite.so. Enable
            # upstream implementation/SA rather than adding ABI stubs.
            ("multimedia", "audio_framework"): {
                "audio_framework_feature_audiosuite_support": True,
                "audio_framework_feature_audiosuite_format_convert_support": True,
            },
            ("multimedia", "av_session"): {"av_session_enable_input_redistribute": True},
            # Enable the existing RTT implementation on both IPC endpoints.
            # This does not fabricate a modem/IMS network or success callback.
            ("telephony", "call_manager"): {"call_manager_feature_support_rtt": True},
            ("telephony", "cellular_call"): {"cellular_call_support_rtt": True},
            ("window", "window_manager"): {"window_manager_use_sceneboard": True},
            # SceneBoard publishes logical displays/shadow surfaces. The
            # legacy non-unified renderer leaves that tree unprepared and
            # submits no composer layers, even while Web/Vulkan readback works.
            ("graphic", "graphic_2d"): {"graphic_2d_feature_rs_enable_uni_render": True},
            # The HDI uses named ALSA hw devices, not the MIDI-only empty
            # configuration. Package/enable upstream definitions for ES1370.
            ("thirdparty", "alsa-lib"): {"alsa_lib_feature_config_enable": True},
            ("hdf", "drivers_peripheral_camera"): {
                "drivers_peripheral_camera_feature_usb": True,
                "drivers_peripheral_camera_use_commom_usb_camera_host_config": True,
                "drivers_peripheral_camera_qemu_vivid_capture": True,
                # Express-camera is a different emulator protocol, not V4L2.
                "drivers_peripheral_camera_v4l2_emulator": False,
            },
        },
        {
            "SystemCapability.Multimedia.Audio.SuiteEngine": (
                "multimedia", "audio_framework",
                "Official phone capability; enable upstream AudioSuite implementation and matching declaration.",
            ),
            "SystemCapability.Multimedia.AVSession.AVInputCast": (
                "multimedia", "av_session",
                "Enable upstream input redistribution in both AVSession NAPI and service.",
            ),
            "SystemCapability.Window.SessionManager": (
                "window", "window_manager",
                "Enable actual SceneBoard service, runtime switch, signed HAPs and handset layout.",
            ),
        },
    )

    metadata = {
        "profile": "qemu_phone_full_source",
        "upstream_profile": UPSTREAM_PROFILE,
        "upstream_sha256": hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
        "effective_profile": EFFECTIVE_PROFILE,
        "base_profile": RICH_PROFILE,
        "strategy": "rich_plus_phone_with_qemu_board_overrides",
        "omitted_unavailable_legacy_components": sorted(omitted),
        "mapped_components": sorted(mapped),
        "app_compatibility_parameter": APP_COMPAT_PARAM,
        **sceneboard_metadata(),
        "window_layout_parameter": PHONE_WINDOW_PARAM,
        "sceneboard_mode_parameter": PHONE_MODE_PARAM,
        "required_parts": sorted(REQUIRED_PHONE_PARTS),
        **contract_metadata,
    }
    return effective, metadata


def configure_product(root: Path, product: str, enable: bool) -> None:
    path = root / PRODUCT_CONFIGS[product]
    document = load_json(path)
    inherit = document.get("inherit")
    if not isinstance(inherit, list):
        die(f"expected inherit array in {path}")
    overlay_path = f"vendor/ohemu/virt/virt_phone_contract_{product}.json"
    inherit = [item for item in inherit if item not in (EFFECTIVE_PROFILE, overlay_path)]
    if enable:
        try:
            rich_index = inherit.index(RICH_PROFILE)
        except ValueError:
            die(f"{path} does not inherit {RICH_PROFILE}")
        inherit.insert(rich_index + 1, EFFECTIVE_PROFILE)
    document["inherit"] = inherit
    if enable:
        metadata = load_json(root / PROFILE_METADATA)
        write_json(root / overlay_path, contract_overlay(root, document, metadata))
        document["inherit"].append(overlay_path)
    write_json(path, document)


def configure_app_compatibility(root: Path, enable: bool, phone_window: bool) -> None:
    path = root / PRODUCT_PARAM_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        die(f"missing required QEMU product parameter file: {path}")

    key = APP_COMPAT_PARAM.split("=", 1)[0] + "="
    conflicting = [
        line
        for line in lines
        if line.startswith(key) and line not in MANAGED_APP_COMPAT_LINES
    ]
    if conflicting:
        die(
            f"{path} already defines {key[:-1]} with a different value: "
            + ", ".join(conflicting)
        )
    filtered = [line for line in lines if line not in MANAGED_APP_COMPAT_LINES | {PHONE_WINDOW_PARAM, PHONE_MODE_PARAM}]
    if phone_window:
        # QEMU product parameters are shared across architectures. Refuse to
        # silently turn a phone into PC mode when profiles were mixed manually.
        keys = {parameter.split("=", 1)[0] for parameter in (PHONE_WINDOW_PARAM, PHONE_MODE_PARAM)}
        if any(line.split("=", 1)[0] in keys for line in filtered):
            die("conflicting phone SceneBoard layout parameters; disable the other device profile first")
        filtered.extend([PHONE_WINDOW_PARAM, PHONE_MODE_PARAM])
    if enable:
        if filtered and filtered[-1] != "":
            filtered.append("")
        filtered.extend([APP_COMPAT_COMMENT, APP_COMPAT_PARAM])
    content = "\n".join(filtered).rstrip() + "\n"
    if path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def any_product_enabled(root: Path) -> bool:
    managed_profiles = {
        EFFECTIVE_PROFILE,
        "vendor/ohemu/virt/virt_2in1_full.json",
    }
    for relative in PRODUCT_CONFIGS.values():
        path = root / relative
        # armv7a_virt is an optional product created by the QEMU patch set.
        # Do not make an arm64/x86_64-only build depend on that unselected
        # product. configure_product() above remains the strict check for an
        # explicitly selected product.
        if not path.is_file():
            continue
        document = load_json(path)
        if managed_profiles.intersection(document.get("inherit", [])):
            return True
    return False


def any_phone_enabled(root: Path) -> bool:
    return any(EFFECTIVE_PROFILE in load_json(root / relative).get("inherit", [])
               for relative in PRODUCT_CONFIGS.values() if (root / relative).is_file())


def main() -> None:
    if len(sys.argv) < 3:
        die("usage: apply.py OHOS_ROOT enable|disable [PRODUCT ...]")
    root = Path(sys.argv[1]).resolve()
    action = sys.argv[2]
    if action not in {"enable", "disable"}:
        die(f"unsupported action: {action}")
    products = sys.argv[3:] or list(PRODUCT_CONFIGS)
    unsupported = sorted(set(products) - set(PRODUCT_CONFIGS))
    if unsupported:
        die(f"unsupported QEMU products: {', '.join(unsupported)}")

    if action == "enable":
        effective, metadata = make_effective_profile(root)
        metadata["products"] = sorted(products)
        write_json(root / EFFECTIVE_PROFILE, effective)
        write_json(root / PROFILE_METADATA, metadata)

    for product in products:
        configure_product(root, product, action == "enable")
    configure_app_compatibility(root, any_product_enabled(root), any_phone_enabled(root))
    configure_sceneboard_runtime(root, any_sceneboard_enabled(root, PRODUCT_CONFIGS))

    state = "configured" if action == "enable" else "disabled"
    print(f"full phone QEMU source profile {state} for: {' '.join(products)}")


if __name__ == "__main__":
    main()
