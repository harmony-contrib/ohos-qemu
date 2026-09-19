#!/usr/bin/env python3
"""Scale the SceneBoard lifecycle timeout for 2in1 QEMU TCG guests."""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


PARAMETER = "persist.sys.abilityms.timeout_unit_time_ratio"
VALUE = "10"
IMAGE_PATHS = ("/etc/param/appfwk.para", "/system/etc/param/appfwk.para")


def run_debugfs(tool: str, image: Path, operation: str, *, writable: bool = False) -> str:
    command = [tool]
    if writable:
        command.append("-w")
    command += ["-R", operation, str(image)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    if re.search(r"(?:error|not found|no such file|file exists)", result.stderr, re.I):
        raise RuntimeError(f"debugfs {operation}: {result.stderr.strip()}")
    return result.stdout


def find_parameter_file(tool: str, image: Path) -> str:
    for path in IMAGE_PATHS:
        output = subprocess.run(
            [tool, "-R", f"stat {path}", str(image)],
            capture_output=True,
            text=True,
        )
        if output.returncode == 0 and "Inode:" in output.stdout:
            return path
    raise RuntimeError("appfwk.para is missing from system.img")


def file_metadata(tool: str, image: Path, path: str) -> tuple[str, str, str]:
    stat = run_debugfs(tool, image, f"stat {path}")
    mode = re.search(r"Mode:\s+(\d+)", stat)
    owner = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", stat)
    if not mode or not owner or stat.count("security.selinux") != 1:
        raise RuntimeError(f"unexpected metadata for {path}: {stat}")
    attributes = re.split(
        r"\n(?:Inode checksum:|BLOCKS:|EXTENTS:)",
        stat.split("Extended attributes:", 1)[-1],
        maxsplit=1,
    )[0]
    if len([line for line in attributes.splitlines() if line.strip()]) != 1:
        raise RuntimeError(f"refusing to discard other extended attributes from {path}")
    return mode.group(1), owner.group(1), owner.group(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("system_image", type=Path)
    args = parser.parse_args()
    image = args.system_image.resolve()
    if not image.is_file():
        parser.error(f"system image does not exist: {image}")

    debugfs = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    if not Path(debugfs).is_file():
        parser.error("debugfs was not found")
    path = find_parameter_file(debugfs, image)

    with tempfile.TemporaryDirectory(prefix="qemu-2in1-runtime-") as directory:
        work = Path(directory)
        original = work / "appfwk.original.para"
        replacement = work / "appfwk.replacement.para"
        actual = work / "appfwk.actual.para"
        label = work / "appfwk.selinux"
        run_debugfs(debugfs, image, f"dump {path} {original}")
        text = original.read_text()
        updated, count = re.subn(
            rf"(?m)^\s*{re.escape(PARAMETER)}\s*=.*$",
            f"{PARAMETER} = {VALUE}",
            text,
        )
        if count > 1:
            raise RuntimeError(f"found {count} conflicting {PARAMETER} entries")
        if count == 0:
            updated = text.rstrip("\n") + f"\n{PARAMETER} = {VALUE}\n"

        metadata = file_metadata(debugfs, image, path)
        replacement.write_text(updated)
        replacement.chmod(int(metadata[0], 8))
        run_debugfs(debugfs, image, f"ea_get -f {label} {path} security.selinux")
        if not label.is_file() or not label.stat().st_size:
            raise RuntimeError(f"missing SELinux label on {path}")

        run_debugfs(debugfs, image, f"rm {path}", writable=True)
        run_debugfs(debugfs, image, f"write {replacement} {path}", writable=True)
        run_debugfs(
            debugfs,
            image,
            f"ea_set -f {label} {path} security.selinux",
            writable=True,
        )
        if file_metadata(debugfs, image, path) != metadata:
            raise RuntimeError(f"metadata changed while updating {path}")
        run_debugfs(debugfs, image, f"dump {path} {actual}")
        if actual.read_text() != updated:
            raise RuntimeError(f"failed to persist {PARAMETER}")

    print(f"2in1 SceneBoard lifecycle timeout configured in {image}")


if __name__ == "__main__":
    main()
