#!/usr/bin/env python3
"""Inspect or enable Native child-process eligibility in a QEMU system image."""

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tempfile

import repackage_native_child_process_phone as image_tools


PARAM_PATH = "/system/etc/param/appfwk.para"
DISABLED = {
    "persist.sys.abilityms.multi_process_model": "false",
    "const.max_native_child_process": "0",
}
ENABLED = {
    "persist.sys.abilityms.multi_process_model": "true",
    "const.max_native_child_process": "50",
}


def tool_path():
    path = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    if not Path(path).is_file():
        raise RuntimeError(f"debugfs not found: {path}")
    return path


def values(content):
    found = {}
    for name in ENABLED:
        matches = re.findall(rf"(?m)^{re.escape(name)}\s*=\s*([^\s#]+)", content)
        if len(matches) != 1:
            raise RuntimeError(f"expected one {name} entry, found {len(matches)}")
        found[name] = matches[0]
    return found


def inspect(image):
    with tempfile.TemporaryDirectory(prefix="native-child-param-read-") as tmp:
        original = Path(tmp) / "appfwk.para"
        image_tools.extract_lib(tool_path(), image, PARAM_PATH, original)
        return values(original.read_text())


def enable(image):
    """Change only the two eligibility values, preserving metadata and label."""
    debugfs = tool_path()
    with tempfile.TemporaryDirectory(prefix="native-child-param-write-") as tmp:
        work = Path(tmp)
        original, replacement, label, actual = (work / name for name in
            ("original.para", "replacement.para", "selinux", "actual.para"))
        image_tools.extract_lib(debugfs, image, PARAM_PATH, original)
        source = original.read_text()
        if values(source) != DISABLED:
            raise RuntimeError(f"source eligibility is not disabled: {values(source)}")
        updated = source
        for name, value in ENABLED.items():
            updated, count = re.subn(rf"(?m)^({re.escape(name)}\s*=\s*)[^\n#]+",
                                      lambda match: match.group(1) + value, updated)
            if count != 1:
                raise RuntimeError(f"could not update {name}")
        if values(updated) != ENABLED:
            raise RuntimeError("replacement eligibility did not validate")
        metadata = image_tools.file_metadata(debugfs, image, PARAM_PATH)
        replacement.write_text(updated)
        replacement.chmod(int(metadata[0], 8))
        image_tools.debugfs(debugfs, image,
                            f"ea_get -f {label} {PARAM_PATH} security.selinux")
        if not label.is_file() or not label.stat().st_size:
            raise RuntimeError("missing appfwk.para SELinux label")
        image_tools.debugfs(debugfs, image, f"rm {PARAM_PATH}", writable=True)
        image_tools.debugfs(debugfs, image, f"write {replacement} {PARAM_PATH}", writable=True)
        image_tools.debugfs(debugfs, image,
                            f"ea_set -f {label} {PARAM_PATH} security.selinux", writable=True)
        if image_tools.file_metadata(debugfs, image, PARAM_PATH) != metadata:
            raise RuntimeError("appfwk.para file metadata changed")
        image_tools.extract_lib(debugfs, image, PARAM_PATH, actual)
        if actual.read_text() != updated:
            raise RuntimeError("eligibility update did not persist")
        return {
            "before": DISABLED,
            "after": ENABLED,
            "appfwk_before_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "appfwk_after_sha256": hashlib.sha256(updated.encode()).hexdigest(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--require-enabled", action="store_true")
    args = parser.parse_args()
    if args.enable == args.require_enabled:
        parser.error("choose exactly one of --enable or --require-enabled")
    image = args.image.resolve()
    if not image.is_file():
        parser.error(f"missing image: {image}")
    if args.enable:
        print(enable(image))
    else:
        actual = inspect(image)
        if actual != ENABLED:
            raise SystemExit(f"Native child process is not enabled in package: {actual}")
        print(f"Native child-process package eligibility verified: {image}")


if __name__ == "__main__":
    main()
