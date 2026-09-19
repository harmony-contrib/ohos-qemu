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
PRODUCT_ETC_BUILD_FILE = "vendor/ohemu/virt/etc/BUILD.gn"
BOOT_UNLOCK_CONFIG_FILE = "vendor/ohemu/virt/etc/qemu_2in1_unlock.cfg"
SCENEBOARD_BUILD_FILE = "foundation/window/window_manager/etc/BUILD.gn"
SCENEBOARD_CONFIG_FILE = "foundation/window/window_manager/etc/sceneboard.config"
SANITIZER_CHECK_LIST = "vendor/ohemu/virt/security_config/sanitizer_check_list.gni"
PREINSTALL_LIST = "vendor/ohemu/virt/preinstall-config/install_list.json"
PREINSTALL_CAPABILITIES = "vendor/ohemu/virt/preinstall-config/install_list_capability.json"
SCENEBOARD_APP_DIR = "/system/app/SceneBoard"
SCENEBOARD_BUNDLE = "com.ohos.sceneboard"
SCENEBOARD_SIGNATURE = "8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5"
APP_COMPAT_COMMENT = "# QEMU full device-profile compatibility for current system HAPs."
APP_COMPAT_PARAM = "const.bms.supportAppTypes=2in1,phone,default,tablet"
PC_WINDOW_COMMENT = "# QEMU 2in1 uses the PC window layout."
PC_WINDOW_PARAM = "const.window.multiWindowUIType=FreeFormMultiWindow"
PC_MODE_PARAM = "persist.sceneboard.ispcmode=true"
BOOT_UNLOCK_EVENTS = [
    "usual.event.USER_UNLOCKED",
    "usual.event.SCREEN_UNLOCKED",
]
BOOT_UNLOCK_TRIGGER = "bootevent.boot.completed=true"
BOOT_UNLOCK_USER_ID = 100
BOOT_UNLOCK_BUILD_BLOCK = """
# QEMU 2in1 has no interactive lock screen during headless test boots.
ohos_prebuilt_etc("qemu_2in1_unlock_cfg") {
  source = "qemu_2in1_unlock.cfg"
  output = "qemu_2in1_unlock.cfg"
  relative_install_dir = "init"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}
""".strip()
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
        "window_architecture_feature": "window_manager_use_sceneboard = true",
        "pc_window_parameter": PC_WINDOW_PARAM,
        "pc_mode_parameter": PC_MODE_PARAM,
        "boot_unlock_events": BOOT_UNLOCK_EVENTS,
        "boot_unlock_trigger": BOOT_UNLOCK_TRIGGER,
        "boot_unlock_user_id": BOOT_UNLOCK_USER_ID,
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


def configure_sceneboard(root: Path, enabled: bool) -> None:
    """Install the runtime switch required by SceneBoardJudgement."""
    build_path = root / SCENEBOARD_BUILD_FILE
    config_path = root / SCENEBOARD_CONFIG_FILE
    build = build_path.read_text(encoding="utf-8")
    disabled = "if (!window_manager_use_sceneboard) {"
    enabled_condition = "if (window_manager_use_sceneboard) {"
    if build.count(disabled) + build.count(enabled_condition) != 2:
        die(f"unexpected SceneBoard build configuration: {build_path}")
    if enabled:
        build = build.replace(disabled, enabled_condition)
    else:
        build = build.replace(enabled_condition, disabled)
    if build_path.read_text(encoding="utf-8") != build:
        build_path.write_text(build, encoding="utf-8")
    expected = "ENABLED\n" if enabled else "DISABLED\n"
    if config_path.read_text(encoding="utf-8") != expected:
        config_path.write_text(expected, encoding="utf-8")


def configure_sceneboard_cfi_exception(root: Path, enabled: bool) -> None:
    """The unified build traverses a test-only target without CFI settings."""
    path = root / SANITIZER_CHECK_LIST
    content = path.read_text(encoding="utf-8")
    marker = '  "dm_unittest_common_lite",  # test-only target without CFI settings\n'
    if enabled:
        if marker not in content:
            anchor = 'bypass_window_manager = [\n'
            if content.count(anchor) != 1:
                die(f"unexpected CFI exception list: {path}")
            content = content.replace(anchor, anchor + marker, 1)
    else:
        content = content.replace(marker, "")
    if path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def configure_sceneboard_preinstall(root: Path, enabled: bool) -> None:
    """Register the SceneBoard HAPs before the first user starts."""
    entries = (
        (PREINSTALL_LIST, "app_dir", SCENEBOARD_APP_DIR,
         {"app_dir": SCENEBOARD_APP_DIR, "removable": False}),
        (PREINSTALL_CAPABILITIES, "bundleName", SCENEBOARD_BUNDLE,
         {"bundleName": SCENEBOARD_BUNDLE,
          "app_signature": [SCENEBOARD_SIGNATURE],
          "allowAppUsePrivilegeExtension": True,
          "allowAppDesktopIconHide": True}),
    )
    for relative, key, value, expected in entries:
        path = root / relative
        document = load_json(path)
        install_list = document.get("install_list")
        if not isinstance(install_list, list):
            die(f"missing install_list in {path}")
        matches = [entry for entry in install_list if entry.get(key) == value]
        if matches and matches != [expected]:
            die(f"conflicting SceneBoard preinstall entry in {path}")
        if enabled and not matches:
            install_list.insert(0, expected)
            write_json(path, document)
        elif not enabled and matches:
            document["install_list"] = [entry for entry in install_list if entry.get(key) != value]
            write_json(path, document)


def configure_boot_unlock_publisher(root: Path, enabled: bool) -> None:
    """Install the headless 2in1 user- and screen-unlock event services."""
    build_path = root / PRODUCT_ETC_BUILD_FILE
    config_path = root / BOOT_UNLOCK_CONFIG_FILE
    build = build_path.read_text(encoding="utf-8")
    dependency = '    ":qemu_2in1_unlock_cfg",\n'
    block = BOOT_UNLOCK_BUILD_BLOCK + "\n\n"
    build = build.replace(block, "").replace(dependency, "")
    if enabled:
        anchor = 'group("product_etc_conf") {\n'
        if build.count(anchor) != 1:
            die(f"unexpected QEMU product etc build file: {build_path}")
        build = build.replace(anchor, block + anchor, 1)
        deps_anchor = '  deps = [\n'
        group_offset = build.index(anchor)
        deps_offset = build.index(deps_anchor, group_offset) + len(deps_anchor)
        build = build[:deps_offset] + dependency + build[deps_offset:]
    if build_path.read_text(encoding="utf-8") != build:
        build_path.write_text(build, encoding="utf-8")

    if enabled:
        config = {
            "jobs": [{
                "name": f"param:{BOOT_UNLOCK_TRIGGER}",
                "condition": BOOT_UNLOCK_TRIGGER,
                "cmds": ["start qemu_2in1_user_unlock", "start qemu_2in1_unlock"],
            }],
            "services": [
                {
                    "name": "qemu_2in1_user_unlock",
                    "path": [
                        "/system/bin/cem", "publish", "-e", BOOT_UNLOCK_EVENTS[0],
                        "-c", str(BOOT_UNLOCK_USER_ID),
                    ],
                    "uid": "system",
                    "gid": ["system"],
                    "apl": "system_core",
                    "permission": [
                        "ohos.permission.PUBLISH_SYSTEM_COMMON_EVENT",
                        "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS",
                    ],
                    "once": 1,
                    "start-mode": "condition",
                    "secon": "u:r:cem:s0",
                },
                {
                    "name": "qemu_2in1_unlock",
                    "path": [
                        "/system/bin/cem", "publish", "-e", BOOT_UNLOCK_EVENTS[1],
                        "-u", str(BOOT_UNLOCK_USER_ID),
                    ],
                    "uid": "system",
                    "gid": ["system"],
                    "apl": "system_core",
                    "permission": [
                        "ohos.permission.PUBLISH_SYSTEM_COMMON_EVENT",
                        "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS",
                    ],
                    "once": 1,
                    "start-mode": "condition",
                    "secon": "u:r:cem:s0",
                },
            ],
        }
        write_json(config_path, config)
    elif config_path.exists():
        config_path.unlink()


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
    configure_sceneboard(root, any_2in1_enabled(root))
    configure_sceneboard_cfi_exception(root, any_2in1_enabled(root))
    configure_sceneboard_preinstall(root, any_2in1_enabled(root))
    configure_boot_unlock_publisher(root, any_2in1_enabled(root))

    state = "configured" if action == "enable" else "disabled"
    print(f"full 2in1 QEMU source profile {state} for: {' '.join(products)}")


if __name__ == "__main__":
    main()
