#!/usr/bin/env python3
"""Fresh GN/link and real RenderService object compilation in an owned clone.

Production source/output remain read-only. A completed Camera scratch is only
a dependency cache, never runtime evidence or the first-package behavior gate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from compile_camera_component import assert_seed_inactive

COMPONENTS = (
    "patches/common/foundation/graphic/graphic_surface/shared_fence_owner",
    "patches/common/foundation/graphic/graphic_2d/render_connection_reply",
)
INPUTS = (
    "foundation/graphic/graphic_surface/utils/frame_report/BUILD.gn",
    "foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_connect_to_render_process.cpp",
    "foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_connect_to_render_process_stub.cpp",
)
OBJECTS = (
    "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/librender_service/rs_connect_to_render_process.o",
    "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/librender_service/rs_connect_to_render_process_stub.o",
)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--seed-source", type=Path, required=True)
    parser.add_argument("--scratch-source", type=Path, required=True)
    parser.add_argument("--product", choices=("arm64_virt", "armv7a_virt", "x86_64_virt"), required=True)
    args = parser.parse_args()
    root, repo, seed, staged = (path.resolve() for path in
                               (args.source_root, args.repo_root, args.seed_source, args.scratch_source))
    for production in (root, root / "out"):
        if not os.statvfs(production).f_flag & os.ST_RDONLY:
            raise ValueError("production source/output must be mounted read-only")
    for other in (root, seed, repo):
        if staged == other or staged.is_relative_to(other) or other.is_relative_to(staged):
            raise ValueError("scratch clone must be separate from every input")
    evidence = seed / ("camera-component-" + {"arm64_virt": "arm64-06", "x86_64_virt": "x64-07",
                                             "armv7a_virt": "armv7a-07"}[args.product] + "-evidence.json")
    prior = json.loads(evidence.read_text())
    if (prior.get("product") != args.product or prior.get("scratch_source") != str(seed)
            or prior.get("gn_exit_code") != 0 or prior.get("link_exit_code") != 0):
        raise ValueError("seed is not a completed matching actual GN/link tree")
    assert_seed_inactive(seed)
    staged.mkdir(parents=True, exist_ok=False)
    seed_hash = sha(evidence)
    result = {"scope": "fresh_GN_surface_shared_link_and_RenderService_objects_NOT_guest_acceptance",
              "first_artifact_behavior_gate_passed": False, "started_utc": datetime.now(timezone.utc).isoformat(),
              "product": args.product, "scratch_source": str(staged), "seed_source": str(seed),
              "seed_evidence_sha256": seed_hash, "production_source_and_out_mounted_readonly": True,
              "commands": [], "exit_code": 1}

    def run(command, name, environment=None, cwd=None):
        path = staged / (name + ".log")
        with path.open("x") as stream:
            completed = subprocess.run(command, cwd=cwd or staged, env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT)
        result["commands"].append({"argv": command, "exit_code": completed.returncode,
                                   "log": str(path), "log_sha256": sha(path)})
        if completed.returncode:
            raise RuntimeError(name + " failed; see preserved evidence log")

    try:
        run(["cp", "--archive", "--reflink=auto", str(seed) + "/.", str(staged)], "clone")
        for directory, directories, files in os.walk(staged, followlinks=False):
            for name in directories + files:
                path = Path(directory) / name
                if path.is_symlink():
                    target = path.resolve()
                    if target.is_relative_to(seed):
                        path.unlink()
                        path.symlink_to(staged / target.relative_to(seed))
        if sha(evidence) != seed_hash:
            raise ValueError("seed evidence changed during clone")
        result["original_input_sha256"] = {}
        for name in INPUTS:
            source, target = root / name, staged / name
            if target.is_symlink():
                if target.resolve() != source.resolve():
                    raise ValueError("unexpected source alias: " + name)
                target.unlink()
            elif not target.is_file() or sha(target) != sha(source):
                raise ValueError("owned cached source differs from production input: " + name)
            shutil.copy2(source, target)
            result["original_input_sha256"][name] = sha(source)
        frozen = staged / "graphics-patch-inputs"
        shutil.copytree(repo / "patches/lib", frozen / "patches/lib")
        for name in COMPONENTS:
            shutil.copytree(repo / name, frozen / name)
        result["patch_payload_sha256"] = {str(path.relative_to(frozen)): sha(path)
                                          for path in frozen.rglob("*") if path.is_file()}
        for index, name in enumerate(COMPONENTS):
            for iteration in range(2):
                run(["bash", str(frozen / name / "apply.sh"), "--source-root", str(staged)],
                    f"apply-{index}-{iteration}")
        result["patched_input_sha256"] = {name: sha(staged / name) for name in INPUTS}
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        environment["PATH"] = str(root / "prebuilts/build-tools/linux-x86/bin") + os.pathsep + environment["PATH"]
        command = [sys.executable, str(staged / "build/hb/main.py"), "build", "--no-indep", "--product-name",
                   args.product, "--prebuilt-sdk=true", "--build-target", "graphic_surface", "graphic_2d",
                   "--build-only-gn", "--ccache=false", "--gn-args", 'device_type="phone"']
        run(command, "gn", environment)
        output = staged / "out" / args.product
        ninja = str(root / "prebuilts/build-tools/linux-x86/bin/ninja")
        command = [ninja, "-w", "dupbuild=warn", "-C", str(output), "-j", "2", "surface", "sync_fence", *OBJECTS]
        run(command, "link", environment)
        surface, fence = output / "graphic/graphic_surface/libsurface.z.so", output / "graphic/graphic_surface/libsync_fence.z.so"
        run([sys.executable, str(repo / "scripts/verify_shared_fence_owner.py"), "--surface", str(surface),
             "--fence", str(fence), "--arch", {"arm64_virt": "arm64", "armv7a_virt": "armv7a",
                                             "x86_64_virt": "x86_64"}[args.product],
             "--output", str(staged / "shared-fence-elf-evidence.json")], "ownership", environment)
        result["artifacts"] = [{"path": str(path), "sha256": sha(path), "size": path.stat().st_size}
                               for path in (surface, fence, *(output / name for name in OBJECTS))]
        run(command, "link-repeat", environment)
        result["exit_code"] = 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    with (staged / "graphics-connection-evidence.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"exit_code": result["exit_code"], "scope": result["scope"], "error": result.get("error")}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
