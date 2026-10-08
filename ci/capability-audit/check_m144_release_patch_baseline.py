#!/usr/bin/env python3
"""Check component patches against real locked Git blobs, before a full build.

This is a source-context diagnostic, never compilation or guest acceptance.
Generated-only inputs are reported separately, not fabricated as source files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_m144_release_cache import load_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    lock = ROOT / "scripts/m144_release_source_lock.json"
    data = load_lock(lock)
    projects = sorted(data["projects"], key=lambda p: len(p["path"]), reverse=True)
    component_root = ROOT / "patches/common/web/arkweb"
    components = ("m144_v8_shared", "m144_core_build", "m144_webrtc_thread_id", "m144_angle_includes",
                  "m144_adapter_header_format", "m144_media_document_binding",
                  "m144_window_contract", "m144_private_contract", "m144_core_package",
                  "m144_swiftshader", "m144_avc_encoder")
    patches = [path for name in components for path in sorted((component_root / name).glob("[0-9]*.patch"))]
    files = sorted({name for path in patches for name in re.findall(r"^--- a/(.+)$", path.read_text(), re.M)})
    source_records, missing = {}, []
    work = args.output / "actual-source-context"
    work.mkdir()
    for name in files:
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError("unsafe patch source path")
        project = next(p for p in projects if name.startswith(p["path"] + "/"))
        relative = name[len(project["path"]) + 1:]
        command = ["git", "-C", str(args.cache_root / (project["name"] + ".git")),
                   "show", project["revision"] + ":" + relative]
        result = subprocess.run(command, capture_output=True)
        if result.returncode:
            missing.append({"path": name, "reason": result.stderr.decode(errors="replace")})
            continue
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.stdout)
        source_records[name] = {"repository": project["name"], "revision": project["revision"],
                                "sha256": hashlib.sha256(result.stdout).hexdigest()}
    results = []
    for path in patches:
        args_list = ["git", "-C", str(work), "apply", "--ignore-space-change", "--whitespace=nowarn", str(path)]
        check = subprocess.run(args_list[:4] + ["--check"] + args_list[4:], capture_output=True, text=True)
        if check.returncode == 0:
            subprocess.run(args_list, check=True, capture_output=True)
            status = "applied_to_actual_locked_source"
        else:
            reverse = subprocess.run(args_list[:4] + ["--check", "--reverse"] + args_list[4:], capture_output=True, text=True)
            status = "already_in_actual_locked_source" if reverse.returncode == 0 else "source_context_differs_or_generated_input"
        results.append({"patch": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "status": status, "check_stderr": check.stderr})
    evidence = {"scope": "actual_git_blob_patch_context_NOT_compilation_or_guest_acceptance",
                "source_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                "source_files": source_records, "missing_source_inputs": missing, "patches": results,
                "first_artifact_behavior_gate_passed": False}
    (args.output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"source_files": len(source_records), "missing_source_inputs": missing,
                      "patches_requiring_review": [p for p in results if p["status"] == "source_context_differs_or_generated_input"]}, indent=2))


if __name__ == "__main__":
    main()
