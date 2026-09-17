#!/usr/bin/env python3
"""Repackage a same-release phone image with validated 2in1 child-process libs.

The affected libraries must be byte-identical in the original phone and
2in1 archives. The new libraries come from a fully built 2in1 archive of the
same architecture and source manifest. This preserves every other phone image
component and records the exact binary provenance in the resulting package.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


LIBRARIES = (
    ("libchild_process_manager.z.so", "platformsdk"),
    ("libchild_process.so", "ndk"),
    ("libapp_manager.z.so", "platformsdk"),
)
ARMV7_EXTRA = (
    ("libappspawn_common.z.so", "appspawn/common"),
    ("libappspawn_sandbox.z.so", "appspawn/common"),
)
ROOT = Path(__file__).resolve().parent.parent


def libraries_for_arch(arch):
    return LIBRARIES + (ARMV7_EXTRA if arch == "armv7a" else ())


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def command(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def member(archive, relative):
    return archive.name.removesuffix(".tar.gz") + "/" + relative


def from_archive(archive, relative, destination):
    with tarfile.open(archive, "r:gz") as source:
        entry = source.extractfile(member(archive, relative))
        if entry is None:
            raise RuntimeError(f"missing {relative} in {archive}")
        with destination.open("wb") as output:
            shutil.copyfileobj(entry, output, 8 * 1024 * 1024)


def verify_checksums(package):
    for line in (package / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        actual = digest(package / relative)
        if actual != expected:
            raise RuntimeError(f"package checksum mismatch: {relative}")


def debugfs(tool, image, operation, writable=False):
    result = subprocess.run(
        [tool, "-w"] + ["-R", operation, str(image)] if writable
        else [tool, "-R", operation, str(image)],
        capture_output=True, text=True, check=True,
    )
    if re.search(r"(?:error|not found|no such file|file exists)", result.stderr, re.I):
        raise RuntimeError(f"debugfs {operation}: {result.stderr}")
    return result.stdout


def extract_lib(tool, image, image_path, destination):
    debugfs(tool, image, f"dump {image_path} {destination}")
    if not destination.is_file() or not destination.stat().st_size:
        raise RuntimeError(f"missing {image_path} in {image}")


def file_metadata(tool, image, image_path):
    stat = debugfs(tool, image, f"stat {image_path}")
    mode = re.search(r"Mode:\s+(\d+)", stat)
    owner = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", stat)
    if not mode or not owner or stat.count("security.selinux") != 1:
        raise RuntimeError(f"unexpected file metadata for {image_path}: {stat}")
    # These system libraries are regular files with only this extended attribute.
    attributes = stat.split("Extended attributes:", 1)[-1].split("Inode checksum:", 1)[0]
    if len([line for line in attributes.splitlines() if line.strip()]) != 1:
        raise RuntimeError(f"other xattrs would be lost: {image_path}")
    return (mode.group(1), owner.group(1), owner.group(2))


def manifest(archive, workspace):
    output = workspace / (archive.name + ".manifest.json")
    from_archive(archive, "manifest.json", output)
    return json.loads(output.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-phone-archive", type=Path, required=True)
    parser.add_argument("--baseline-2in1-archive", type=Path, required=True)
    parser.add_argument("--patched-2in1-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    phone, baseline, patched = (
        path.resolve() for path in (
            args.base_phone_archive,
            args.baseline_2in1_archive,
            args.patched_2in1_archive,
        )
    )
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / phone.name.removesuffix(".tar.gz")
    archive_out = output_root / phone.name
    if destination.exists() or archive_out.exists():
        parser.error(f"output already exists: {destination} or {archive_out}")
    debugfs_tool = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    fsck_tool = shutil.which("e2fsck") or "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck"
    for tool in (debugfs_tool, fsck_tool):
        if not Path(tool).is_file():
            parser.error(f"missing e2fsprogs tool: {tool}")

    with tempfile.TemporaryDirectory(prefix="child-phone-repack-", dir=output_root) as temp:
        work = Path(temp)
        profiles = [manifest(archive, work) for archive in (phone, baseline, patched)]
        if [profile["device_type"] for profile in profiles] != ["phone", "2in1", "2in1"]:
            raise RuntimeError("expected phone baseline and two 2in1 archives")
        if len({profile["guest_arch"] for profile in profiles}) != 1:
            raise RuntimeError("source and destination architectures differ")
        # The source preparation metadata records its selected device profile;
        # that field must differ between phone and 2in1. All pinned revisions
        # and resolved source checksums must match.
        baselines = [
            {key: value for key, value in profile["source_baseline"].items()
             if key != "prepared_device_type"}
            for profile in profiles
        ]
        if len({json.dumps(item, sort_keys=True) for item in baselines}) != 1:
            raise RuntimeError("source baselines differ")
        arch = profiles[0]["guest_arch"]
        libdir = "lib" if arch == "armv7a" else "lib64"
        old_image, new_image = work / "old-2in1-system.img", work / "new-2in1-system.img"
        from_archive(baseline, "images/system.img", old_image)
        from_archive(patched, "images/system.img", new_image)
        command("tar", "-xzf", str(phone), "-C", str(work))
        package = work / phone.name.removesuffix(".tar.gz")
        verify_checksums(package)  # Never use a previously booted, dirty directory.
        phone_image = package / "images/system.img"
        evidence = {}
        for name, subdir in libraries_for_arch(arch):
            image_path = f"/system/{libdir}/{subdir}/{name}"
            old_phone = work / (name + ".phone")
            old_pair = work / (name + ".old-2in1")
            replacement = work / (name + ".patched")
            extract_lib(debugfs_tool, phone_image, image_path, old_phone)
            extract_lib(debugfs_tool, old_image, image_path, old_pair)
            extract_lib(debugfs_tool, new_image, image_path, replacement)
            if digest(old_phone) != digest(old_pair):
                raise RuntimeError(f"baseline phone/2in1 binaries differ: {name}")
            metadata = file_metadata(debugfs_tool, phone_image, image_path)
            write_input = work / (name + ".write")
            shutil.copyfile(replacement, write_input)
            write_input.chmod(int(metadata[0], 8))
            label = work / (name + ".selinux")
            debugfs(debugfs_tool, phone_image, f"ea_get -f {label} {image_path} security.selinux")
            if not label.is_file() or not label.stat().st_size:
                raise RuntimeError(f"missing SELinux label: {name}")
            debugfs(debugfs_tool, phone_image, f"rm {image_path}", writable=True)
            debugfs(debugfs_tool, phone_image, f"write {write_input} {image_path}", writable=True)
            debugfs(debugfs_tool, phone_image, f"ea_set -f {label} {image_path} security.selinux", writable=True)
            if file_metadata(debugfs_tool, phone_image, image_path) != metadata:
                raise RuntimeError(f"permissions changed: {name}")
            actual = work / (name + ".check")
            extract_lib(debugfs_tool, phone_image, image_path, actual)
            if digest(actual) != digest(replacement):
                raise RuntimeError(f"replacement mismatch: {name}")
            evidence[name] = {
                "image_path": image_path,
                "baseline_sha256": digest(old_phone),
                "patched_sha256": digest(replacement),
            }
            print(f"replaced and verified: {image_path}", flush=True)

        command(fsck_tool, "-fn", str(phone_image))
        from_archive(patched, "native-child-process-patches.json", package / "native-child-process-patches.json")
        record = {
            "schema_version": 1,
            "method": "same-release phone image with patched libraries from validated 2in1 build",
            "base_phone_archive": str(phone),
            "base_phone_sha256": digest(phone),
            "baseline_2in1_archive": str(baseline),
            "baseline_2in1_sha256": digest(baseline),
            "patched_library_source_archive": str(patched),
            "patched_library_source_sha256": digest(patched),
            "source_manifest_revision": profiles[0]["source_baseline"]["manifest_revision"],
            "libraries": evidence,
        }
        (package / "native-child-process-repack.json").write_text(json.dumps(record, indent=2) + "\n")
        with (package / "README.md").open("a") as readme:
            readme.write("\nNative child-process fix: see native-child-process-repack.json for the "
                         "same-release binary provenance and patch hashes.\n")
        checksum_file = package / "SHA256SUMS"
        checksum_file.write_text("\n".join(
            digest(package / relative) + "  " + relative
            for _, relative in (line.split(maxsplit=1) for line in checksum_file.read_text().splitlines())
        ) + "\n")
        verify_checksums(package)
        command("python3", str(ROOT / "scripts/verify_native_child_process_package.py"),
                "--package", str(package), "--output", str(package / "native-child-process-elf.json"))
        command("bash", str(ROOT / "scripts/verify_device_type_package.sh"),
                "--package", str(package), "--expect-device-type", "phone", "--require-full-phone")
        env = dict(os.environ, LC_ALL="C", LANG="C", COPYFILE_DISABLE="1")
        tar = ["tar", "--no-mac-metadata", "-czf", str(work / phone.name), package.name]
        command(*tar, cwd=work, env=env)
        package.rename(destination)
        (work / phone.name).rename(archive_out)
        print(f"new phone package: {archive_out}\nSHA-256: {digest(archive_out)}")


if __name__ == "__main__":
    main()
