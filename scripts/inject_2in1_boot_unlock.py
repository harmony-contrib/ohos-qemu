#!/usr/bin/env python3
"""Install the 2in1 boot-unlock event publisher into an extracted package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

import repackage_native_child_process_phone as common


CEM_PATH = "/system/bin/cem"
CONFIG_PATH = "/system/etc/init/qemu_2in1_unlock.cfg"
CONFIG_TEMPLATE = "/system/etc/init/accountmgr.cfg"
EVIDENCE_FILE = "qemu-2in1-boot-unlock.json"
USER_UNLOCK_EVENT = "usual.event.USER_UNLOCKED"
SCREEN_UNLOCK_EVENT = "usual.event.SCREEN_UNLOCKED"
EVENTS = [USER_UNLOCK_EVENT, SCREEN_UNLOCK_EVENT]
USER_ID = 100
TRIGGER = "bootevent.boot.completed=true"


CONFIG = {
    "jobs": [{
        "name": f"param:{TRIGGER}",
        "condition": TRIGGER,
        "cmds": ["start qemu_2in1_user_unlock", "start qemu_2in1_unlock"],
    }],
    "services": [
        {
            "name": "qemu_2in1_user_unlock",
            "path": [CEM_PATH, "publish", "-e", USER_UNLOCK_EVENT, "-c", str(USER_ID)],
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
            "path": [CEM_PATH, "publish", "-e", SCREEN_UNLOCK_EVENT, "-u", str(USER_ID)],
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


def refresh_checksums(package: Path) -> None:
    checksum_file = package / "SHA256SUMS"
    relatives = [
        line.split(maxsplit=1)[1]
        for line in checksum_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if EVIDENCE_FILE not in relatives:
        relatives.append(EVIDENCE_FILE)
    checksum_file.write_text(
        "\n".join(f"{common.digest(package / relative)}  {relative}" for relative in relatives) + "\n",
        encoding="utf-8",
    )


def read_label(debugfs: str, image: Path, image_path: str, destination: Path) -> None:
    common.debugfs(debugfs, image, f"ea_get -f {destination} {image_path} security.selinux")
    if not destination.is_file() or not destination.stat().st_size:
        raise RuntimeError(f"missing SELinux label: {image_path}")


def replace_file(
    debugfs: str, image: Path, image_path: str, source: Path, metadata: tuple[str, str, str], label: Path
) -> None:
    common.debugfs(debugfs, image, f"rm {image_path}", writable=True)
    common.debugfs(debugfs, image, f"write {source} {image_path}", writable=True)
    common.debugfs(debugfs, image, f"set_inode_field {image_path} mode 010{metadata[0]}", writable=True)
    common.debugfs(debugfs, image, f"set_inode_field {image_path} uid {metadata[1]}", writable=True)
    common.debugfs(debugfs, image, f"set_inode_field {image_path} gid {metadata[2]}", writable=True)
    common.debugfs(debugfs, image, f"ea_set -f {label} {image_path} security.selinux", writable=True)
    if common.file_metadata(debugfs, image, image_path) != metadata:
        raise RuntimeError(f"metadata changed during injection: {image_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--cem", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    cem = args.cem.resolve()
    manifest_path = package / "manifest.json"
    profile_path = package / "device-profile.json"
    image = package / "images/system.img"
    if not all(path.is_file() for path in (manifest_path, profile_path, image, cem)):
        parser.error("package metadata, system.img, and patched cem are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("device_type") != "2in1" or manifest.get("device_type_profile") != "qemu_2in1_full_source":
        raise RuntimeError("boot-unlock injection requires a full 2in1 package")

    debugfs = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    fsck = shutil.which("e2fsck") or "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck"
    for tool in (debugfs, fsck):
        if not Path(tool).is_file():
            parser.error(f"missing e2fsprogs tool: {tool}")

    with tempfile.TemporaryDirectory(prefix="qemu-2in1-unlock-", dir=package.parent) as temporary:
        work = Path(temporary)
        old_cem = work / "cem.original"
        checked_cem = work / "cem.checked"
        cem_label = work / "cem.selinux"
        common.extract_lib(debugfs, image, CEM_PATH, old_cem)
        cem_metadata = common.file_metadata(debugfs, image, CEM_PATH)
        read_label(debugfs, image, CEM_PATH, cem_label)
        cem_input = work / "cem"
        shutil.copyfile(cem, cem_input)
        cem_input.chmod(int(cem_metadata[0], 8))
        replace_file(debugfs, image, CEM_PATH, cem_input, cem_metadata, cem_label)
        common.extract_lib(debugfs, image, CEM_PATH, checked_cem)
        if common.digest(checked_cem) != common.digest(cem):
            raise RuntimeError("patched cem verification failed")

        config_input = work / "qemu_2in1_unlock.cfg"
        config_input.write_text(json.dumps(CONFIG, indent=4) + "\n", encoding="utf-8")
        config_metadata = common.file_metadata(debugfs, image, CONFIG_TEMPLATE)
        config_input.chmod(int(config_metadata[0], 8))
        config_label = work / "config.selinux"
        read_label(debugfs, image, CONFIG_TEMPLATE, config_label)
        existing = work / "config.existing"
        try:
            common.extract_lib(debugfs, image, CONFIG_PATH, existing)
        except RuntimeError:
            pass
        else:
            common.debugfs(debugfs, image, f"rm {CONFIG_PATH}", writable=True)
        common.debugfs(debugfs, image, f"write {config_input} {CONFIG_PATH}", writable=True)
        common.debugfs(debugfs, image, f"set_inode_field {CONFIG_PATH} mode 010{config_metadata[0]}", writable=True)
        common.debugfs(debugfs, image, f"set_inode_field {CONFIG_PATH} uid {config_metadata[1]}", writable=True)
        common.debugfs(debugfs, image, f"set_inode_field {CONFIG_PATH} gid {config_metadata[2]}", writable=True)
        common.debugfs(debugfs, image, f"ea_set -f {config_label} {CONFIG_PATH} security.selinux", writable=True)
        if common.file_metadata(debugfs, image, CONFIG_PATH) != config_metadata:
            raise RuntimeError("boot-unlock init config metadata changed during injection")
        checked_config = work / "config.checked"
        common.extract_lib(debugfs, image, CONFIG_PATH, checked_config)
        if checked_config.read_bytes() != config_input.read_bytes():
            raise RuntimeError("boot-unlock init config verification failed")

        common.command(fsck, "-fn", str(image))
        evidence = {
            "schema_version": 2,
            "events": EVENTS,
            "user_id": USER_ID,
            "trigger": TRIGGER,
            "cem_path": CEM_PATH,
            "baseline_cem_sha256": common.digest(old_cem),
            "patched_cem_sha256": common.digest(cem),
            "init_config_path": CONFIG_PATH,
            "init_config_sha256": common.digest(config_input),
        }
        (package / EVIDENCE_FILE).write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        adaptations = profile.setdefault("qemu_adaptations", {})
        adaptations.update({
            "boot_unlock_events": EVENTS,
            "boot_unlock_trigger": TRIGGER,
            "boot_unlock_user_id": USER_ID,
        })
        profile_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        refresh_checksums(package)
        common.verify_checksums(package)
        print(f"installed {', '.join(EVENTS)} boot publishers for user {USER_ID}")
        print(f"cem SHA-256: {common.digest(cem)}")


if __name__ == "__main__":
    main()
