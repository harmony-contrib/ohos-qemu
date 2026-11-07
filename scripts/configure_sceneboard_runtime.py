#!/usr/bin/env python3
"""Scale SceneBoard lifecycle and AppFreeze/ANR watchdog timeouts for QEMU TCG guests."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "patches" / "lib"))
from sceneboard_profile import boot_unlock_configuration


PARAMETERS = (
    ("persist.sys.abilityms.timeout_unit_time_ratio", "10"),
    # AppExecFwk::Watchdog and MMI::ANRManager divide this <=4-digit integer by 1000.
    ("const.sys.dfx.appfreeze.timeout_unit_time_ratio", "9999"),
)
DAC_PARAMETERS = (
    ("const.sys.dfx.appfreeze.timeout_unit_time_ratio", "foundation:foundation:0755"),
)
IMAGE_PATHS = ("/etc/param/appfwk.para", "/system/etc/param/appfwk.para")
UNLOCK_CFG_PATHS = ("/etc/init/qemu_sceneboard_unlock.cfg", "/system/etc/init/qemu_sceneboard_unlock.cfg")


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


def upsert_parameters(text: str, entries: tuple[tuple[str, str], ...]) -> str:
    updated = text
    for name, value in entries:
        updated, count = re.subn(
            rf"(?m)^\s*{re.escape(name)}\s*=.*$",
            f"{name} = {value}",
            updated,
        )
        if count > 1:
            raise RuntimeError(f"found {count} conflicting {name} entries")
        if count == 0:
            updated = updated.rstrip("\n") + f"\n{name} = {value}\n"
    return updated


def update_image_file(
    debugfs: str,
    image: Path,
    work: Path,
    path: str,
    entries: tuple[tuple[str, str], ...],
    stem: str,
) -> None:
    original = work / f"{stem}.original"
    replacement = work / f"{stem}.replacement"
    actual = work / f"{stem}.actual"
    label = work / f"{stem}.selinux"
    run_debugfs(debugfs, image, f"dump {path} {original}")
    updated = upsert_parameters(original.read_text(), entries)

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
        raise RuntimeError(f"failed to persist updates to {path}")


def update_unlock_cfg(debugfs: str, image: Path, work: Path) -> None:
    unlock_path = None
    for candidate in UNLOCK_CFG_PATHS:
        output = subprocess.run(
            [debugfs, "-R", f"stat {candidate}", str(image)],
            capture_output=True,
            text=True,
        )
        if output.returncode == 0 and "Inode:" in output.stdout:
            unlock_path = candidate
            break
    if not unlock_path:
        return

    updated = json.dumps(boot_unlock_configuration(), indent=2, ensure_ascii=False) + "\n"
    replacement = work / "qemu_sceneboard_unlock.cfg.replacement"
    actual = work / "qemu_sceneboard_unlock.cfg.actual"
    label = work / "qemu_sceneboard_unlock.cfg.selinux"
    metadata = file_metadata(debugfs, image, unlock_path)
    replacement.write_text(updated)
    replacement.chmod(int(metadata[0], 8))
    run_debugfs(debugfs, image, f"ea_get -f {label} {unlock_path} security.selinux")
    if not label.is_file() or not label.stat().st_size:
        raise RuntimeError(f"missing SELinux label on {unlock_path}")

    run_debugfs(debugfs, image, f"rm {unlock_path}", writable=True)
    run_debugfs(debugfs, image, f"write {replacement} {unlock_path}", writable=True)
    run_debugfs(
        debugfs,
        image,
        f"ea_set -f {label} {unlock_path} security.selinux",
        writable=True,
    )
    if file_metadata(debugfs, image, unlock_path) != metadata:
        raise RuntimeError(f"metadata changed while updating {unlock_path}")
    run_debugfs(debugfs, image, f"dump {unlock_path} {actual}")
    if actual.read_text() != updated:
        raise RuntimeError(f"failed to persist updates to {unlock_path}")


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
    dac_path = f"{path}.dac"
    dac_stat = subprocess.run(
        [debugfs, "-R", f"stat {dac_path}", str(image)],
        capture_output=True,
        text=True,
    )
    has_dac = dac_stat.returncode == 0 and "Inode:" in dac_stat.stdout

    with tempfile.TemporaryDirectory(prefix="qemu-2in1-runtime-") as directory:
        work = Path(directory)
        update_image_file(debugfs, image, work, path, PARAMETERS, "appfwk.para")
        if has_dac:
            update_image_file(debugfs, image, work, dac_path, DAC_PARAMETERS, "appfwk.para.dac")
        update_unlock_cfg(debugfs, image, work)

    print(f"SceneBoard lifecycle timeout configured in {image}")


if __name__ == "__main__":
    main()
