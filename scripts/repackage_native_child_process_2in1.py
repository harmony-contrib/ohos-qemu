#!/usr/bin/env python3
"""Repackage a pinned 2in1 archive using the freshly compiled libraries.

The source build must use the same pinned OpenHarmony manifest as the base
archive. The resulting archive is a binary update of the original full 2in1
profile, and must pass the QEMU Native child-process runtime regression before
it can be used as a source for the matching phone archive.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import repackage_native_child_process_phone as common


PATCH_DIR = common.ROOT / "patches/common/foundation/ability/ability_runtime/native_child_process"
ARMV7_PATCH_DIR = common.ROOT / "patches/common/device/qemu/armv7a_product/components/appspawn_cleanup"
ARMV7_COMPACT_PATCH_DIR = common.ROOT / "patches/common/device/qemu/armv7a_product/components/compact_child_args"
PINNED_REVISION = "f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-2in1-archive", type=Path, required=True)
    parser.add_argument("--libraries-dir", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--armv7a-appspawn-build-log", type=Path)
    parser.add_argument("--armv7a-sandbox-build-log", type=Path)
    parser.add_argument("--armv7a-compact-build-log", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    base, libraries, build_log, output_root = (
        path.resolve() for path in
        (args.base_2in1_archive, args.libraries_dir, args.build_log, args.output_root)
    )
    if not build_log.is_file() or not all((libraries / name).is_file() for name, _ in common.LIBRARIES):
        parser.error("the source build log and all three new libraries are required")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / base.name.removesuffix(".tar.gz")
    archive_out = output_root / base.name
    if destination.exists() or archive_out.exists():
        parser.error(f"output already exists: {destination} or {archive_out}")
    debugfs_tool = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    fsck_tool = shutil.which("e2fsck") or "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck"
    for tool in (debugfs_tool, fsck_tool):
        if not Path(tool).is_file():
            parser.error(f"missing e2fsprogs tool: {tool}")
    if "[" not in build_log.read_text(errors="replace") or "SOLINK ability/ability_runtime/libchild_process.so" not in build_log.read_text(errors="replace"):
        parser.error("source build log does not show a completed child-process C library link")

    with tempfile.TemporaryDirectory(prefix="child-2in1-repack-", dir=output_root) as temp:
        work = Path(temp)
        profile = common.manifest(base, work)
        if profile["device_type"] != "2in1" or profile["source_baseline"]["manifest_revision"] != PINNED_REVISION:
            raise RuntimeError("base archive has the wrong device profile or source revision")
        arch = profile["guest_arch"]
        appspawn_log = args.armv7a_appspawn_build_log
        sandbox_log = args.armv7a_sandbox_build_log
        compact_log = args.armv7a_compact_build_log
        if arch == "armv7a":
            if appspawn_log is None or not appspawn_log.is_file() or \
                    "SOLINK startup/appspawn/libappspawn_common.z.so" not in appspawn_log.read_text(errors="replace"):
                raise RuntimeError("armv7a requires a completed native spawn cleanup build log")
            if sandbox_log is None or not sandbox_log.is_file() or \
                    "SOLINK startup/appspawn/libappspawn_sandbox.z.so" not in sandbox_log.read_text(errors="replace"):
                raise RuntimeError("armv7a requires a completed spawn sandbox build log")
            if compact_log is None or not compact_log.is_file() or \
                    "SOLINK ability/ability_runtime/libapp_manager.z.so" not in compact_log.read_text(errors="replace"):
                raise RuntimeError("armv7a requires a completed compact child argument build log")
        libdir = "lib" if arch == "armv7a" else "lib64"
        common.command("tar", "-xzf", str(base), "-C", str(work))
        package = work / base.name.removesuffix(".tar.gz")
        common.verify_checksums(package)
        image = package / "images/system.img"
        evidence = {}
        if not all((libraries / name).is_file() for name, _ in common.libraries_for_arch(arch)):
            raise RuntimeError(f"missing compiled libraries for {arch}")
        for name, subdir in common.libraries_for_arch(arch):
            image_path = f"/system/{libdir}/{subdir}/{name}"
            original = work / (name + ".original")
            replacement = libraries / name
            common.extract_lib(debugfs_tool, image, image_path, original)
            metadata = common.file_metadata(debugfs_tool, image, image_path)
            write_input = work / (name + ".write")
            shutil.copyfile(replacement, write_input)
            write_input.chmod(int(metadata[0], 8))
            label = work / (name + ".selinux")
            common.debugfs(debugfs_tool, image, f"ea_get -f {label} {image_path} security.selinux")
            if not label.is_file() or not label.stat().st_size:
                raise RuntimeError(f"missing SELinux label: {name}")
            common.debugfs(debugfs_tool, image, f"rm {image_path}", writable=True)
            common.debugfs(debugfs_tool, image, f"write {write_input} {image_path}", writable=True)
            common.debugfs(debugfs_tool, image, f"ea_set -f {label} {image_path} security.selinux", writable=True)
            if common.file_metadata(debugfs_tool, image, image_path) != metadata:
                raise RuntimeError(f"permissions changed: {name}")
            actual = work / (name + ".check")
            common.extract_lib(debugfs_tool, image, image_path, actual)
            if common.digest(actual) != common.digest(replacement):
                raise RuntimeError(f"replacement mismatch: {name}")
            evidence[name] = {
                "image_path": image_path,
                "baseline_sha256": common.digest(original),
                "patched_sha256": common.digest(replacement),
            }
            print(f"replaced and verified: {image_path}", flush=True)
        common.command(fsck_tool, "-fn", str(image))
        patches = {path.name: common.digest(path) for path in sorted(PATCH_DIR.glob("*.patch"))}
        if len(patches) != 2:
            raise RuntimeError("expected exactly the two Native child-process patches")
        if arch == "armv7a":
            armv7_patches = sorted(ARMV7_PATCH_DIR.glob("*.patch"))
            armv7_patches += sorted(ARMV7_COMPACT_PATCH_DIR.glob("*.patch"))
            if len(armv7_patches) != 3:
                raise RuntimeError("expected ARMv7a spawn cleanup and compact argument patches")
            patches.update({path.name: common.digest(path) for path in armv7_patches})
        (package / "native-child-process-patches.json").write_text(
            json.dumps({"schema_version": 1, "patches": patches}, indent=2) + "\n"
        )
        record = {
            "schema_version": 1,
            "method": "same-release full 2in1 image with affected libraries compiled from patched source",
            "base_2in1_archive": str(base),
            "base_2in1_sha256": common.digest(base),
            "source_manifest_revision": PINNED_REVISION,
            "build_log": str(build_log),
            "build_log_sha256": common.digest(build_log),
            "armv7a_appspawn_build_log": str(appspawn_log.resolve()) if appspawn_log else None,
            "armv7a_appspawn_build_log_sha256": common.digest(appspawn_log.resolve()) if appspawn_log else None,
            "armv7a_sandbox_build_log": str(sandbox_log.resolve()) if sandbox_log else None,
            "armv7a_sandbox_build_log_sha256": common.digest(sandbox_log.resolve()) if sandbox_log else None,
            "armv7a_compact_build_log": str(compact_log.resolve()) if compact_log else None,
            "armv7a_compact_build_log_sha256": common.digest(compact_log.resolve()) if compact_log else None,
            "libraries": evidence,
        }
        (package / "native-child-process-repack.json").write_text(json.dumps(record, indent=2) + "\n")
        with (package / "README.md").open("a") as readme:
            readme.write("\nNative child-process fix: see native-child-process-repack.json for "
                         "the source build and binary provenance.\n")
        checksums = package / "SHA256SUMS"
        checksums.write_text("\n".join(
            common.digest(package / relative) + "  " + relative
            for _, relative in (line.split(maxsplit=1) for line in checksums.read_text().splitlines())
        ) + "\n")
        common.verify_checksums(package)
        common.command("python3", str(common.ROOT / "scripts/verify_native_child_process_package.py"),
                       "--package", str(package), "--output", str(package / "native-child-process-elf.json"))
        common.command("bash", str(common.ROOT / "scripts/verify_device_type_package.sh"),
                       "--package", str(package), "--expect-device-type", "2in1", "--require-full-2in1")
        env = dict(os.environ, LC_ALL="C", LANG="C", COPYFILE_DISABLE="1")
        common.command("tar", "--no-mac-metadata", "-czf", str(work / base.name), package.name,
                       cwd=work, env=env)
        package.rename(destination)
        (work / base.name).rename(archive_out)
        print(f"new 2in1 package: {archive_out}\nSHA-256: {common.digest(archive_out)}")


if __name__ == "__main__":
    main()
