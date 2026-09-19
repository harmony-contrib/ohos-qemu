#!/usr/bin/env python3
"""Inject the validated SceneBoard unlock-event HAP into a 2in1 package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile

import patch_sceneboard_unlock_event as event_patch
import repackage_native_child_process_phone as common


IMAGE_PATH = "/system/app/SceneBoard/SceneBoard.hap"
EVIDENCE_FILE = "sceneboard-unlock-event.json"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--hap", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    hap = args.hap.resolve()
    manifest_path = package / "manifest.json"
    profile_path = package / "device-profile.json"
    image = package / "images/system.img"
    if not all(path.is_file() for path in (manifest_path, profile_path, image, hap)):
        parser.error("package metadata, system.img, and the replacement HAP are required")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("device_type") != "2in1" or manifest.get("device_type_profile") != "qemu_2in1_full_source":
        raise RuntimeError("SceneBoard unlock-event injection requires a full 2in1 package")
    with ZipFile(hap) as archive:
        abc = archive.read(event_patch.MODULES_ABC)
    if event_patch.sha256(abc) != event_patch.PATCHED_ABC_SHA256:
        raise RuntimeError("replacement SceneBoard HAP does not contain the validated unlock-event ABC")

    debugfs_tool = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    fsck_tool = shutil.which("e2fsck") or "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck"
    for tool in (debugfs_tool, fsck_tool):
        if not Path(tool).is_file():
            parser.error(f"missing e2fsprogs tool: {tool}")

    with tempfile.TemporaryDirectory(prefix="sceneboard-unlock-inject-", dir=package.parent) as temporary:
        work = Path(temporary)
        original = work / "SceneBoard.original.hap"
        checked = work / "SceneBoard.checked.hap"
        label = work / "SceneBoard.selinux"
        write_input = work / "SceneBoard.write.hap"
        common.extract_lib(debugfs_tool, image, IMAGE_PATH, original)
        metadata = common.file_metadata(debugfs_tool, image, IMAGE_PATH)
        common.debugfs(debugfs_tool, image, f"ea_get -f {label} {IMAGE_PATH} security.selinux")
        if not label.is_file() or not label.stat().st_size:
            raise RuntimeError("SceneBoard HAP has no SELinux label")
        shutil.copyfile(hap, write_input)
        write_input.chmod(int(metadata[0], 8))
        common.debugfs(debugfs_tool, image, f"rm {IMAGE_PATH}", writable=True)
        common.debugfs(debugfs_tool, image, f"write {write_input} {IMAGE_PATH}", writable=True)
        common.debugfs(
            debugfs_tool, image, f"ea_set -f {label} {IMAGE_PATH} security.selinux", writable=True
        )
        if common.file_metadata(debugfs_tool, image, IMAGE_PATH) != metadata:
            raise RuntimeError("SceneBoard HAP permissions changed during injection")
        common.extract_lib(debugfs_tool, image, IMAGE_PATH, checked)
        if common.digest(checked) != common.digest(hap):
            raise RuntimeError("SceneBoard HAP injection verification failed")
        common.command(fsck_tool, "-fn", str(image))

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        runtime = profile["qemu_adaptations"]["sceneboard_runtime"]
        previous_evidence_hash = runtime["hap_sha256"]["SceneBoard.hap"]
        if previous_evidence_hash != common.digest(original):
            raise RuntimeError("device-profile SceneBoard hash does not match the package image")
        runtime["hap_sha256"]["SceneBoard.hap"] = common.digest(hap)
        profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        evidence_path = package / EVIDENCE_FILE
        previous_evidence = (
            json.loads(evidence_path.read_text(encoding="utf-8"))
            if evidence_path.is_file() else {}
        )
        evidence = {
            "schema_version": 1,
            "image_path": IMAGE_PATH,
            "legacy_event": event_patch.OLD_EVENT.rstrip(b"\0").decode(),
            "ability_manager_event": event_patch.NEW_EVENT.rstrip(b"\0").decode(),
            "baseline_hap_sha256": previous_evidence.get(
                "baseline_hap_sha256", common.digest(original)
            ),
            "patched_hap_sha256": common.digest(hap),
            "baseline_modules_abc_sha256": event_patch.ORIGINAL_ABC_SHA256,
            "patched_modules_abc_sha256": event_patch.PATCHED_ABC_SHA256,
            "patch_script_sha256": common.digest(Path(event_patch.__file__)),
        }
        evidence_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        refresh_checksums(package)
        common.verify_checksums(package)
        print(f"injected and verified: {IMAGE_PATH}")
        print(f"SceneBoard HAP SHA-256: {common.digest(hap)}")


if __name__ == "__main__":
    main()
