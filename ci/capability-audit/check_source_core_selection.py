#!/usr/bin/env python3
"""Apply the ABI selector to the actual fixed main webview blob in scratch.

This is source-context verification, not a native build, HAP or guest gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

REVISION = "d421b6b549fa3038ad01cf34589b959286137be9"
SOURCE_PATH = "ohos_nweb/BUILD.gn"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohos-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("refusing to replace actual-source selection evidence")
    root = Path(__file__).resolve().parents[2]
    repository = args.ohos_root / "base/web/webview"
    actual = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    if actual != REVISION:
        raise ValueError("main source release revision differs")
    source = subprocess.check_output(["git", "-C", str(repository), "show", REVISION + ":" + SOURCE_PATH])
    component = root / "patches/common/base/web/webview/core_hap_source"
    commands = []
    with tempfile.TemporaryDirectory(prefix="qemu-actual-core-selector-") as directory:
        scratch = Path(directory)
        path = scratch / "base/web/webview" / SOURCE_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(source)
        for _ in range(2):
            command = ["bash", str(root / "patches/lib/apply_component_dir.sh"), str(component),
                       "--source-root", str(scratch)]
            result = subprocess.run(command, capture_output=True, text=True)
            commands.append({"argv": command, "exit_code": result.returncode})
            if result.returncode:
                raise ValueError("ABI selector does not apply to actual fixed source")
        for patch in component.glob("*.patch"):
            subprocess.run(["git", "-C", str(scratch), "apply", "--check", "--reverse", str(patch)], check=True)
        patched = path.read_text()
        for arch in ("arm", "arm64", "x86_64"):
            if patched.count(f'web_source = "qemu-core/{arch}/ArkWebCore.hap"') != 1:
                raise ValueError("missing unique exact-ABI core selector")
        if 'web_source = "prebuilts/' in patched:
            raise ValueError("official prebuilt/wrong-ABI fallback remains")
        result = {"status": "pass", "scope": "actual_fixed_webview_blob_source_context_NOT_HAP_or_guest_acceptance",
                  "source_revision": REVISION, "source_file": SOURCE_PATH,
                  "source_sha256": hashlib.sha256(source).hexdigest(),
                  "patched_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "commands": commands, "first_artifact_behavior_gate_passed": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
