#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

PRODUCT_CONFIGS = {
    "armv7a_virt": "vendor/ohemu/virt/virt_common_armv7a.json",
    "arm64_virt": "vendor/ohemu/virt/virt_common.json",
    "x86_64_virt": "vendor/ohemu/virt/virt_common_x86_64.json",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        fail(f"required VPN integration file is missing: {path}")
        raise error


def validate_product(root: Path, product: str) -> None:
    path = root / PRODUCT_CONFIGS[product]
    document = read_json(path)
    components = [
        component.get("component")
        for subsystem in document.get("subsystems", [])
        if isinstance(subsystem, dict)
        for component in subsystem.get("components", [])
        if isinstance(component, dict)
    ]
    if "netmanager_ext" not in components:
        fail(f"netmanager_ext is missing from {path}")

    graphic = next(
        (
            component
            for subsystem in document.get("subsystems", [])
            if subsystem.get("subsystem") == "graphic"
            for component in subsystem.get("components", [])
            if component.get("component") == "graphic_2d"
        ),
        None,
    )
    if graphic is None:
        fail(f"graphic_2d is missing from {path}")
    features = "\n".join(graphic.get("features", []))
    for expected in (
        "graphic_2d_feature_ace_enable_gpu = true",
        "graphic_2d_feature_enable_opengl = true",
        "graphic_2d_feature_enable_vulkan = false",
        "graphic_2d_feature_rs_enable_eglimage = true",
        "graphic_2d_feature_parallel_render_enable = true",
    ):
        if not re.search(rf"(?m)^\s*{re.escape(expected)}\s*$", features):
            fail(f"missing QEMU graphics feature in {path}: {expected}")


def require_install_entry(path: Path, predicate, description: str) -> None:
    document = read_json(path)
    entries = document.get("install_list")
    if not isinstance(entries, list) or not any(
        isinstance(entry, dict) and predicate(entry) for entry in entries
    ):
        fail(f"{description} is missing from {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--product", action="append", choices=sorted(PRODUCT_CONFIGS))
    args = parser.parse_args()
    root = args.source_root.resolve()
    for product in args.product or sorted(PRODUCT_CONFIGS):
        validate_product(root, product)

    require_install_entry(
        root / "vendor/ohemu/virt/preinstall-config/install_list.json",
        lambda entry: entry.get("app_dir") == "/system/app/VpnDialog"
        and entry.get("removable") is False,
        "non-removable /system/app/VpnDialog",
    )
    require_install_entry(
        root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json",
        lambda entry: entry.get("bundleName") == "com.ohos.vpndialog"
        and entry.get("allowAppUsePrivilegeExtension") is True,
        "com.ohos.vpndialog privileged-extension capability",
    )
    feature_gni = root / "foundation/communication/netmanager_ext/netmanager_ext_config.gni"
    if "netmanager_ext_feature_vpn = true" not in feature_gni.read_text(encoding="utf-8"):
        fail(f"VPN feature is disabled in {feature_gni}")
    if not (root / "applications/standard/hap/SettingsData.hap").is_file():
        fail("SettingsData HAP is missing from applications/standard/hap")
    print("standard VPN component integration validated")


if __name__ == "__main__":
    main()
