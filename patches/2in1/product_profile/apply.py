#!/usr/bin/env python3
"""Create an effective full 2in1 profile for standard QEMU products."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


UPSTREAM_PROFILE = "productdefine/common/inherit/2in1.json"
RICH_PROFILE = "productdefine/common/inherit/rich.json"
EFFECTIVE_PROFILE = "vendor/ohemu/virt/virt_2in1_full.json"
PROFILE_METADATA = "vendor/ohemu/virt/virt_2in1_full.meta.json"
PRODUCT_PARAM_FILE = "vendor/ohemu/virt/etc/param/product_virt.para"
APP_COMPAT_COMMENT = "# QEMU full device-profile compatibility for current system HAPs."
APP_COMPAT_PARAM = "const.bms.supportAppTypes=2in1,phone,default,tablet"
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
# current master branch, but their projects are no longer present in the
# master manifest. Keep them when a checkout explicitly provides the legacy
# sources; otherwise omit/map them so the current source tree can pass load.
LEGACY_COMPONENTS = {
    ("thirdparty", "eudev"): "third_party/eudev",
    ("thirdparty", "libsnd"): "third_party/libsnd",
    ("wukong", "wukong"): "test/wukong",
}

REQUIRED_2IN1_PARTS = {
    "applications:prebuilt_hap",
    "applications:dlp_manager",
    "arkui:ui_appearance",
    "bundlemanager:bundle_framework",
    "communication:t2stack",
    "filemanagement:storage_service",
    "hdf:drivers_peripheral_input",
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

    # Current master renamed the historical wukong:wukong part to
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

    effective_parts = {
        f"{subsystem}:{component}"
        for subsystem, component in component_map(effective)
    }
    missing = sorted(REQUIRED_2IN1_PARTS - effective_parts)
    if missing:
        die("effective 2in1 profile lost required parts: " + ", ".join(missing))

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
        "required_parts": sorted(REQUIRED_2IN1_PARTS),
    }
    return effective, metadata


def configure_product(root: Path, product: str, enable: bool) -> None:
    relative = PRODUCT_CONFIGS[product]
    path = root / relative
    document = load_json(path)
    inherit = document.get("inherit")
    if not isinstance(inherit, list):
        die(f"expected inherit array in {path}")

    inherit = [item for item in inherit if item != EFFECTIVE_PROFILE]
    if enable:
        try:
            rich_index = inherit.index(RICH_PROFILE)
        except ValueError:
            die(f"{path} does not inherit {RICH_PROFILE}")
        inherit.insert(rich_index + 1, EFFECTIVE_PROFILE)
    document["inherit"] = inherit
    write_json(path, document)


def configure_app_compatibility(root: Path, enable: bool) -> None:
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

    filtered = [line for line in lines if line not in MANAGED_APP_COMPAT_LINES]
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
        "vendor/ohemu/virt/virt_phone_full.json",
    }
    for relative in PRODUCT_CONFIGS.values():
        document = load_json(root / relative)
        if managed_profiles.intersection(document.get("inherit", [])):
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
    configure_app_compatibility(root, any_product_enabled(root))

    state = "configured" if action == "enable" else "disabled"
    print(f"full 2in1 QEMU source profile {state} for: {' '.join(products)}")


if __name__ == "__main__":
    main()
