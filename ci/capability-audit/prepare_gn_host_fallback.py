#!/usr/bin/env python3
"""Prepare an explicit QEMU-user host GN fallback only in an owned scratch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--scratch-source", type=Path, required=True)
    args = parser.parse_args()
    root, staged = args.source_root.resolve(), args.scratch_source.resolve()
    if (not os.statvfs(root).f_flag & os.ST_RDONLY or staged == root
            or staged.is_relative_to(root) or root.is_relative_to(staged)):
        raise ValueError("fallback must be outside read-only production source")
    prior = json.loads((staged / "graphics-connection-evidence.json").read_text())
    if prior.get("scratch_source") != str(staged) or prior.get("exit_code") != 1:
        raise ValueError("only the owned failed graphics scratch may be prepared")
    wrapper = Path(__file__).with_name("gn_under_qemu_user.sh")
    for relative in ("prebuilts", "prebuilts/build-tools", "prebuilts/build-tools/linux-x86",
                     "prebuilts/build-tools/linux-x86/bin"):
        original, target = root / relative, staged / relative
        if target.is_symlink():
            if target.resolve() != original.resolve():
                raise ValueError("unexpected host tool directory alias")
            target.unlink()
            target.mkdir()
            for child in original.iterdir():
                (target / child.name).symlink_to(child, target_is_directory=child.is_dir())
        elif not target.is_dir():
            raise ValueError("missing owned host tool directory")
    original = root / "prebuilts/build-tools/linux-x86/bin/gn"
    target = staged / "prebuilts/build-tools/linux-x86/bin/gn"
    backup = target.with_name("gn.pinned-executable")
    if (backup.exists() or target.resolve() != original.resolve() or not target.is_symlink()):
        raise ValueError("refusing to replace an unknown GN candidate")
    shutil.copy2(original, backup)
    target.unlink()
    shutil.copy2(wrapper, target)
    target.chmod(0o755)
    version = subprocess.run([str(target), "--version"], text=True, capture_output=True, check=True).stdout.strip()
    evidence = {"scope": "isolated_host_translation_fallback_NOT_production_tool_or_guest_change",
                "pinned_GN_sha256": sha(original), "owned_pinned_executable_sha256": sha(backup),
                "wrapper_sha256": sha(target), "GN_version": version,
                "qemu_user_sha256": sha(Path("/usr/bin/qemu-x86_64-static")),
                "first_artifact_behavior_gate_passed": False}
    (staged / "gn-host-fallback-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"GN_version": version, "pinned_executable_unchanged": sha(original) == sha(backup)}))


if __name__ == "__main__":
    main()
