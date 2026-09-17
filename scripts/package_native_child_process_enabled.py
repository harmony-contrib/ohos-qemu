#!/usr/bin/env python3
"""Make a new QEMU archive with Native child processes enabled at first boot."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import native_child_process_eligibility as eligibility
import repackage_native_child_process_phone as package_tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_archive.resolve()
    output_root = args.output_root.resolve()
    if not source.is_file() or not source.name.endswith(".tar.gz"):
        parser.error(f"missing source archive: {source}")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / source.name.removesuffix(".tar.gz")
    archive_out = output_root / source.name
    if destination.exists() or archive_out.exists():
        parser.error(f"output already exists: {destination} or {archive_out}")

    with tempfile.TemporaryDirectory(prefix="native-child-enabled-", dir=output_root) as temp:
        work = Path(temp)
        profile = package_tools.manifest(source, work)
        device_type = profile["device_type"]
        if device_type not in ("2in1", "phone"):
            raise RuntimeError(f"unexpected device profile: {device_type}")
        package_tools.command("tar", "-xzf", str(source), "-C", str(work))
        package = work / source.name.removesuffix(".tar.gz")
        package_tools.verify_checksums(package)
        image = package / "images/system.img"
        change = eligibility.enable(image)
        if eligibility.inspect(image) != eligibility.ENABLED:
            raise RuntimeError("updated image eligibility did not validate")
        fsck = shutil.which("e2fsck") or "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck"
        package_tools.command(fsck, "-fn", str(image), stdout=subprocess.DEVNULL)

        record = {
            "schema_version": 1,
            "purpose": "enable Native child processes at first boot",
            "source_archive": str(source),
            "source_archive_sha256": package_tools.digest(source),
            "device_type": device_type,
            "guest_arch": profile["guest_arch"],
            "source_manifest_revision": profile["source_baseline"]["manifest_revision"],
            **change,
        }
        (package / "native-child-process-eligibility.json").write_text(
            json.dumps(record, indent=2) + "\n")
        with (package / "README.md").open("a") as readme:
            readme.write("\nNative child processes are enabled at first boot; "
                         "see native-child-process-eligibility.json.\n")
        checksum_file = package / "SHA256SUMS"
        files = [line.split(maxsplit=1)[1] for line in checksum_file.read_text().splitlines()]
        checksum_file.write_text("\n".join(
            f"{package_tools.digest(package / relative)}  {relative}" for relative in files
        ) + "\n")
        package_tools.verify_checksums(package)
        package_tools.command(
            "python3", str(package_tools.ROOT / "scripts/verify_native_child_process_package.py"),
            "--package", str(package), "--output", str(work / "native-child-process-elf.json"))
        package_tools.command(
            "bash", str(package_tools.ROOT / "scripts/verify_device_type_package.sh"),
            "--package", str(package), "--expect-device-type", device_type,
            f"--require-full-{device_type}")
        env = dict(os.environ, LC_ALL="C", LANG="C", COPYFILE_DISABLE="1")
        package_tools.command("tar", "--no-mac-metadata", "-czf", str(work / source.name),
                              package.name, cwd=work, env=env)
        package.rename(destination)
        (work / source.name).rename(archive_out)
        print(f"enabled package: {archive_out}")
        print(f"SHA-256: {package_tools.digest(archive_out)}")


if __name__ == "__main__":
    main()
