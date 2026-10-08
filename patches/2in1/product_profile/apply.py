#!/usr/bin/env python3
"""Create an effective full 2in1 profile for standard QEMU products."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from device_contract import apply_contract_overrides, contract_overlay
from sceneboard_profile import (any_sceneboard_enabled, configure_sceneboard_runtime,
                                sceneboard_metadata)


UPSTREAM_PROFILE = "productdefine/common/inherit/2in1.json"
RICH_PROFILE = "productdefine/common/inherit/rich.json"
EFFECTIVE_PROFILE = "vendor/ohemu/virt/virt_2in1_full.json"
PROFILE_METADATA = "vendor/ohemu/virt/virt_2in1_full.meta.json"
PRODUCT_PARAM_FILE = "vendor/ohemu/virt/etc/param/product_virt.para"
APP_COMPAT_COMMENT = "# QEMU full device-profile compatibility for current system HAPs."
APP_COMPAT_PARAM = "const.bms.supportAppTypes=2in1,phone,default,tablet"
PC_WINDOW_COMMENT = "# QEMU 2in1 uses the PC window layout."
PC_WINDOW_PARAM = "const.window.multiWindowUIType=FreeFormMultiWindow"
PC_MODE_PARAM = "persist.sceneboard.ispcmode=true"
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

# These entries still exist in productdefine/common/inherit/2in1.json on the
# OpenHarmony 7.0 Release baseline, but their projects are no longer present in
# the pinned manifest. Keep them when a checkout explicitly provides the legacy
# sources; otherwise omit/map them so the current source tree can pass load.
LEGACY_COMPONENTS = {
    ("thirdparty", "eudev"): "third_party/eudev",
    ("thirdparty", "libsnd"): "third_party/libsnd",
    ("wukong", "wukong"): "test/wukong",
}

REQUIRED_2IN1_PARTS = {
    "applications:prebuilt_hap",
    "applications:photos",
    "applications:dlp_manager",
    "arkui:ui_appearance",
    "bundlemanager:bundle_framework",
    "busmanager:serial_manager",
    "communication:t2stack",
    "communication:netmanager_base",
    "communication:netmanager_ext",
    "filemanagement:storage_service",
    "hdf:drivers_peripheral_input",
    "hdf:drivers_interface_serial",
    "hdf:drivers_peripheral_serial",
    "multimodalinput:input",
    "security:dlp_permission_service",
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
    upstream_bytes = upstream_path.read_bytes()
    effective = json.loads(json.dumps(upstream))
    omitted = []
    mapped = []

    for key, source_path in LEGACY_COMPONENTS.items():
        if (root / source_path).exists():
            continue
        if remove_component(effective, key):
            omitted.append(":".join(key))

    # The pinned 7.0 Release tree renamed the historical wukong:wukong part to
    # ostest:wukong. Preserve the capability when that replacement is present.
    current_wukong = root / "test/ostest/wukong/bundle.json"
    if current_wukong.is_file():
        add_component(effective, "ostest", "wukong")
        mapped.append("wukong:wukong->ostest:wukong")

    # The current source tree ships its Launcher/SystemUI as signed prebuilt
    # HAPs whose module profiles advertise default/tablet. A QEMU 2in1 image
    # still needs those system applications to finish the first-user switch,
    # so keep their owning part explicit in the effective profile.
    add_component(effective, "applications", "prebuilt_hap")
    # Recent/PhotoInfo/album-name providers are real source extensions, not
    # phone camera hardware. Their owning part must also be built on 2in1.
    add_component(effective, "applications", "photos")
    add_component(effective, "thirdparty", "alsa-lib")
    # The release manifest omits the Serial SIG repository. Its fixed source
    # is imported before profile generation; select the real service and HDI
    # together rather than retaining only the SDK/SysCap declaration.
    add_component(effective, "busmanager", "serial_manager")
    add_component(effective, "hdf", "drivers_interface_serial")
    add_component(effective, "hdf", "drivers_peripheral_serial")

    # rich.json installs camera_framework, although the official 2in1 SDK
    # contract omits Camera.Core and QEMU has no usable Camera VDI. Carry the
    # existing owner into this profile so the last contract overlay can revoke
    # only that false declaration. Preserve its existing board settings and
    # libraries; do not change the shared bundle or the required phone camera.
    camera_key = ("multimedia", "camera_framework")
    if camera_key not in component_map(effective):
        rich_camera = component_map(rich).get(camera_key)
        if rich_camera is None:
            die("rich profile lost camera_framework contract owner")
        add_component(effective, *camera_key)
        component_map(effective)[camera_key].update(json.loads(json.dumps(rich_camera)))

    # 2in1.json intentionally leaves this hardware-interface feature list
    # empty. QEMU's community display VDI requires the rich profile flags, so
    # retain those flags as a board adaptation while keeping all other 2in1
    # feature overrides (notably disabling hyperhold for memmgr).
    effective_components = component_map(effective)
    rich_components = component_map(rich)
    display_key = ("hdf", "drivers_interface_display")
    if display_key in effective_components and display_key in rich_components:
        effective_components[display_key]["features"] = list(
            rich_components[display_key].get("features", [])
        )

    window_key = ("window", "window_manager")
    if window_key in effective_components:
        features = effective_components[window_key].setdefault("features", [])
        features = [feature for feature in features if not feature.startswith("window_manager_use_sceneboard")]
        features.append("window_manager_use_sceneboard = true")
        effective_components[window_key]["features"] = features

    effective_parts = {
        f"{subsystem}:{component}"
        for subsystem, component in component_map(effective)
    }
    missing = sorted(REQUIRED_2IN1_PARTS - effective_parts)
    if missing:
        die("effective 2in1 profile lost required parts: " + ", ".join(missing))

    contract_metadata = apply_contract_overrides(
        root, effective, "2in1",
        {
            **{
                f"SystemCapability.DistributedDataManager.CloudSync.{name}": (
                    "distributeddatamgr", "relational_store",
                    "Outside the official 2in1 contract; the client hardcodes an absent com.example.cloudsync provider.",
                ) for name in ("Client", "Config", "Server")
            },
            "SystemCapability.FileManagement.DistributedFileService.CloudSync.Core": (
                "filemanagement", "dfs_service",
                "Outside the official 2in1 contract; no usable cloud-sync provider is packaged.",
            ),
            "SystemCapability.FileManagement.DistributedFileService.CloudSyncManager": (
                "filemanagement", "dfs_service",
                "Outside the official 2in1 contract; no usable cloud-sync provider is packaged.",
            ),
            "SystemCapability.Multimedia.VideoProcessingEngine": (
                "multimedia", "media_foundation",
                "Not in the official 2in1 contract; public processing libraries are not packaged.",
            ),
            "SystemCapability.Multimedia.Camera.Core": (
                "multimedia", "camera_framework",
                "Outside the official 2in1 SDK contract; QEMU has no usable Camera Host VDI.",
            ),
        },
        {
            ("communication", "netmanager_base"): {
                "netmanager_base_enable_feature_net_firewall": True,
                "netmanager_base_enable_feature_sysvpn": True,
            },
            ("communication", "netmanager_ext"): {
                "netmanager_ext_feature_net_firewall": True,
                "netmanager_ext_feature_sysvpn": True,
            },
            # Pair SceneBoard's logical display tree with the unified renderer,
            # not the historical QEMU legacy composition configuration.
            ("graphic", "graphic_2d"): {"graphic_2d_feature_rs_enable_uni_render": True},
            ("thirdparty", "alsa-lib"): {"alsa_lib_feature_config_enable": True},
        },
    )

    metadata = {
        "profile": "qemu_2in1_full_source",
        "upstream_profile": UPSTREAM_PROFILE,
        "upstream_sha256": hashlib.sha256(upstream_bytes).hexdigest(),
        "effective_profile": EFFECTIVE_PROFILE,
        "base_profile": RICH_PROFILE,
        "strategy": "rich_plus_2in1_with_qemu_board_overrides",
        "omitted_unavailable_legacy_components": sorted(omitted),
        "mapped_components": sorted(mapped),
        "app_compatibility_parameter": APP_COMPAT_PARAM,
        **sceneboard_metadata(),
        "pc_window_parameter": PC_WINDOW_PARAM,
        "pc_mode_parameter": PC_MODE_PARAM,
        "window_layout_parameter": PC_WINDOW_PARAM,
        "sceneboard_mode_parameter": PC_MODE_PARAM,
        "required_parts": sorted(REQUIRED_2IN1_PARTS),
        **contract_metadata,
    }
    return effective, metadata


def configure_product(root: Path, product: str, enable: bool) -> None:
    relative = PRODUCT_CONFIGS[product]
    path = root / relative
    document = load_json(path)
    inherit = document.get("inherit")
    if not isinstance(inherit, list):
        die(f"expected inherit array in {path}")

    overlay_path = f"vendor/ohemu/virt/virt_2in1_contract_{product}.json"
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


def configure_product_parameters(root: Path, enable_compatibility: bool, enable_pc_window: bool) -> None:
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

    for pc_parameter in (PC_WINDOW_PARAM, PC_MODE_PARAM):
        pc_key = pc_parameter.split("=", 1)[0] + "="
        conflicting_pc = [
            line for line in lines if line.startswith(pc_key) and line != pc_parameter
        ]
        if enable_pc_window and conflicting_pc:
            die(
                f"{path} already defines {pc_key[:-1]} with a different value: "
                + ", ".join(conflicting_pc)
            )

    filtered = [
        line for line in lines
        if line not in MANAGED_APP_COMPAT_LINES | {PC_WINDOW_COMMENT, PC_WINDOW_PARAM, PC_MODE_PARAM}
    ]
    if enable_compatibility:
        if filtered and filtered[-1] != "":
            filtered.append("")
        filtered.extend([APP_COMPAT_COMMENT, APP_COMPAT_PARAM])
    if enable_pc_window:
        filtered.extend([PC_WINDOW_COMMENT, PC_WINDOW_PARAM, PC_MODE_PARAM])

    content = "\n".join(filtered).rstrip() + "\n"
    if path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def any_product_enabled(root: Path) -> bool:
    managed_profiles = {
        EFFECTIVE_PROFILE,
        "vendor/ohemu/virt/virt_phone_full.json",
    }
    for relative in PRODUCT_CONFIGS.values():
        path = root / relative
        # armv7a_virt is an optional product created by the QEMU patch set.
        # A clean upstream checkout that is building only arm64/x86_64 must
        # not fail while checking whether another managed profile is active.
        # Explicitly selected products are still validated strictly by
        # configure_product() before this global state check.
        if not path.is_file():
            continue
        document = load_json(path)
        if managed_profiles.intersection(document.get("inherit", [])):
            return True
    return False


def any_2in1_enabled(root: Path) -> bool:
    for relative in PRODUCT_CONFIGS.values():
        path = root / relative
        if path.is_file() and EFFECTIVE_PROFILE in load_json(path).get("inherit", []):
            return True
    return False




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
    configure_product_parameters(root, any_product_enabled(root), any_2in1_enabled(root))
    configure_sceneboard_runtime(root, any_sceneboard_enabled(root, PRODUCT_CONFIGS))

    state = "configured" if action == "enable" else "disabled"
    print(f"full 2in1 QEMU source profile {state} for: {' '.join(products)}")


if __name__ == "__main__":
    main()
