#!/usr/bin/env python3
"""Install real QEMU DSP sources after checking the exact 7.0 algorithm ABI."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

REVISION = "6932fa64335b8272ca4a59de7808ab0d6c9eae7a"
HEADER_HASH = "594213e69c813012a2b6beac06467e2aa00736756e3beee329976851be2b1e01"
CONFIG = "services/audio_suite/client/config/file/audio_suite_capabilities.xml"
BUILD = "services/audio_suite/BUILD.gn"
PRE_SPECS_FILES = {
    "qemu_audio_suite_dsp.cpp": "1fe6c157f9bf560a5afd871bcdd1c958a899deb1ea16b31d71b140541da45476",
    "qemu_audio_suite_dsp.map": "77b5213b665a138c18200ff7452945399051e0d4a978f70cb2ae49876e63352d",
}


def repaired_configuration(original):
    old = b'soName="libimedia_sws.z.so"'
    if original.count(old) != 3:
        raise ValueError("unexpected pinned DSP algorithm routes")
    return original.replace(old, b'soName="libqemu_audio_suite_dsp.z.so"')


def repaired_build(original):
    anchor = b'    ":audio_suite_capabilities",\n'
    if original.count(anchor) != 1:
        raise ValueError("unexpected pinned DSP package dependency")
    return original.replace(anchor, anchor + b'    "qemu_dsp:package",\n')


def reject_symlinks(root, path):
    if not path.is_relative_to(root):
        raise SystemExit("DSP source is outside the specified source root")
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise SystemExit("DSP source destination contains a symlink")
        cursor = cursor.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product", action="append", default=[])
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / "foundation/multimedia/audio_framework"
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != REVISION:
        raise SystemExit(f"DSP requires pinned audio_framework {REVISION}, got {head}")
    header = source / "services/audio_suite/client/utils/include/imedia_api.h"
    for path in (header, source / CONFIG, source / BUILD, source / "services/audio_suite/qemu_dsp"):
        reject_symlinks(root, path)
    if hashlib.sha256(header.read_bytes()).hexdigest() != HEADER_HASH:
        raise SystemExit("DSP ABI header changed; refusing to install")
    for name, transform in ((CONFIG, repaired_configuration), (BUILD, repaired_build)):
        original = subprocess.check_output(["git", "-C", str(source), "show", "HEAD:" + name])
        candidate = transform(original)
        current = (source / name).read_bytes()
        accepted = (original, candidate) if args.check_only else (candidate,)
        if current not in accepted:
            raise SystemExit(f"unknown or missing DSP package/config repair; preserving {name}")
    files = Path(__file__).parent / "files"
    target = source / "services/audio_suite/qemu_dsp"
    for name in ("BUILD.gn", "qemu_audio_suite_dsp.cpp", "qemu_audio_suite_dsp.map"):
        destination = target / name
        current = destination.read_bytes() if destination.is_file() and not destination.is_symlink() else None
        known_previous = current is not None and hashlib.sha256(current).hexdigest() == PRE_SPECS_FILES.get(name)
        if destination.is_symlink() or (destination.exists() and
                current != (files / name).read_bytes() and not known_previous):
            raise SystemExit(f"unrecognized existing DSP source; preserving {destination}")
    if args.check_only:
        print("QEMU AudioSuite DSP ABI and source destination preflight passed")
        return
    target.mkdir(parents=True, exist_ok=True)
    for path in files.iterdir():
        if path.is_file():
            shutil.copyfile(path, target / path.name)
    print("installed QEMU AudioSuite CPU DSP (three effects only; runtime gate not passed)")


if __name__ == "__main__":
    main()
