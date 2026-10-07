"""Shared SceneBoard installation; phone and 2in1 keep separate product policies."""
from __future__ import annotations

import json
from pathlib import Path

PRODUCT_ETC_BUILD_FILE = "vendor/ohemu/virt/etc/BUILD.gn"
BOOT_UNLOCK_CONFIG_FILE = "vendor/ohemu/virt/etc/qemu_sceneboard_unlock.cfg"
SCENEBOARD_BUILD_FILE = "foundation/window/window_manager/etc/BUILD.gn"
SCENEBOARD_CONFIG_FILE = "foundation/window/window_manager/etc/sceneboard.config"
SANITIZER_CHECK_LIST = "vendor/ohemu/virt/security_config/sanitizer_check_list.gni"
PREINSTALL_LIST = "vendor/ohemu/virt/preinstall-config/install_list.json"
PREINSTALL_CAPABILITIES = "vendor/ohemu/virt/preinstall-config/install_list_capability.json"
SCENEBOARD_APP_DIR = "/system/app/SceneBoard"
SCENEBOARD_BUNDLE = "com.ohos.sceneboard"
SCENEBOARD_SIGNATURE = "8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5"
BOOT_UNLOCK_EVENTS = ["usual.event.USER_UNLOCKED", "usual.event.SCREEN_UNLOCKED"]
BOOT_UNLOCK_TRIGGER = "bootevent.boot.completed=true"
BOOT_UNLOCK_USER_ID = 100
BOOT_UNLOCK_BUILD_BLOCK = """
# QEMU headless SceneBoard needs first-user unlock notifications.
ohos_prebuilt_etc("qemu_sceneboard_unlock_cfg") {
  source = "qemu_sceneboard_unlock.cfg"
  output = "qemu_sceneboard_unlock.cfg"
  relative_install_dir = "init"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}
""".strip()


def die(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        die(f"expected JSON object: {path}")
    return document


def write_json(path: Path, document: dict) -> None:
    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text() != content:
        path.write_text(content)


def any_sceneboard_enabled(root: Path, products: dict) -> bool:
    profiles = {"vendor/ohemu/virt/virt_2in1_full.json", "vendor/ohemu/virt/virt_phone_full.json"}
    return any(profiles.intersection(load_json(root / relative).get("inherit", []))
               for relative in products.values() if (root / relative).is_file())


def sceneboard_metadata() -> dict:
    return {
        "window_architecture_feature": "window_manager_use_sceneboard = true",
        "boot_unlock_events": BOOT_UNLOCK_EVENTS,
        "boot_unlock_trigger": BOOT_UNLOCK_TRIGGER,
        "boot_unlock_user_id": BOOT_UNLOCK_USER_ID,
        "boot_unlock_config": "/system/etc/init/qemu_sceneboard_unlock.cfg",
    }


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


def boot_unlock_configuration() -> dict:
    return {
        "jobs": [{
            "name": f"param:{BOOT_UNLOCK_TRIGGER}",
            "condition": BOOT_UNLOCK_TRIGGER,
            "cmds": ["start qemu_sceneboard_user_unlock", "start qemu_sceneboard_unlock"],
        }],
        "services": [
            {
                "name": "qemu_sceneboard_user_unlock",
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
                "name": "qemu_sceneboard_unlock",
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


def configure_boot_unlock_publisher(root: Path, enabled: bool) -> None:
    """Install the headless SceneBoard user- and screen-unlock event services."""
    build_path = root / PRODUCT_ETC_BUILD_FILE
    config_path = root / BOOT_UNLOCK_CONFIG_FILE
    build = build_path.read_text(encoding="utf-8")
    # Migrate our former device-specific generated config; no legacy init
    # service is left in a phone or 2in1 image after this transition.
    legacy_block = '''# QEMU 2in1 has no interactive lock screen during headless test boots.
ohos_prebuilt_etc("qemu_2in1_unlock_cfg") {
  source = "qemu_2in1_unlock.cfg"
  output = "qemu_2in1_unlock.cfg"
  relative_install_dir = "init"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}

'''
    build = build.replace(legacy_block, "").replace('    ":qemu_2in1_unlock_cfg",\n', "")
    legacy_config = root / "vendor/ohemu/virt/etc/qemu_2in1_unlock.cfg"
    if legacy_config.is_file():
        legacy = load_json(legacy_config)
        canonical = json.loads(json.dumps(legacy).replace("qemu_2in1", "qemu_sceneboard"))
        if canonical != boot_unlock_configuration():
            die(f"unexpected non-managed legacy unlock configuration: {legacy_config}")
        legacy_config.unlink()
    if "qemu_2in1_unlock" in build:
        die(f"unexpected legacy unlock build definition: {build_path}")
    dependency = '    ":qemu_sceneboard_unlock_cfg",\n'
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
        config = boot_unlock_configuration()
        write_json(config_path, config)
    elif config_path.exists():
        config_path.unlink()



def configure_sceneboard_runtime(root: Path, enabled: bool) -> None:
    configure_sceneboard(root, enabled)
    configure_sceneboard_cfi_exception(root, enabled)
    configure_sceneboard_preinstall(root, enabled)
    configure_boot_unlock_publisher(root, enabled)
