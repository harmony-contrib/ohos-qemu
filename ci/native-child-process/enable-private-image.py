#!/usr/bin/env python3
"""Enable child-process tests in an extracted private system image."""
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import repackage_native_child_process_phone as package_tools

if len(sys.argv) != 2:
    raise SystemExit("usage: enable-private-image.py EXTRACTED_SYSTEM_IMG")
image = Path(sys.argv[1]).resolve()
if not image.is_file() or "/extract/" not in str(image):
    raise SystemExit("refusing to modify anything but an extracted test image")
debugfs = shutil.which("debugfs") or "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
path = "/system/etc/param/appfwk.para"
with tempfile.TemporaryDirectory(prefix="child-process-private-param-") as tmp:
    work = Path(tmp)
    original, replacement, label, actual = (work / name for name in
        ("original.para", "replacement.para", "selinux", "actual.para"))
    package_tools.extract_lib(debugfs, image, path, original)
    text = original.read_text()
    for name, value in (("const.max_native_child_process", "50"),
                        ("persist.sys.abilityms.multi_process_model", "true")):
        text, count = re.subn(rf"(?m)^{re.escape(name)}\s*=\s*.*$",
                              f"{name} = {value}", text)
        if count != 1:
            raise RuntimeError(f"expected one {name} entry, found {count}")
    metadata = package_tools.file_metadata(debugfs, image, path)
    replacement.write_text(text)
    replacement.chmod(int(metadata[0], 8))
    package_tools.debugfs(debugfs, image, f"ea_get -f {label} {path} security.selinux")
    if not label.is_file() or not label.stat().st_size:
        raise RuntimeError("missing parameter file SELinux label")
    package_tools.debugfs(debugfs, image, f"rm {path}", writable=True)
    package_tools.debugfs(debugfs, image, f"write {replacement} {path}", writable=True)
    package_tools.debugfs(debugfs, image, f"ea_set -f {label} {path} security.selinux", writable=True)
    if package_tools.file_metadata(debugfs, image, path) != metadata:
        raise RuntimeError("parameter file metadata changed")
    package_tools.extract_lib(debugfs, image, path, actual)
    if actual.read_text() != text:
        raise RuntimeError("parameter file update did not persist")
print(f"private image Native eligibility enabled: {image}")
