#!/usr/bin/env python3
"""Build the real Linux driver for all three ABIs, without packaging a guest.

Reuse only a stopped, evidenced Vivid Kconfig/header preparation as read-only
inputs. Driver files and all generated configuration/output belong to this run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from check_camera_kernel_config import ARCHITECTURES
from compile_camera_component import assert_seed_inactive


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--seed-source", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--component", choices=("access_token_abi", "binder_async_sender"), default="access_token_abi")
    args = parser.parse_args()
    root, repo, seed, work = (path.resolve() for path in
                             (args.source_root, args.repo_root, args.seed_source, args.work_dir))
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError("production kernel source must be read-only")
    for original in (root, repo, seed):
        if work == original or work.is_relative_to(original) or original.is_relative_to(work):
            raise ValueError("kernel scratch must not overlap input trees")
    evidence = seed / "camera-kconfig-evidence.json"
    prior = json.loads(evidence.read_text())
    if (len(prior["results"]) != 3 or not all(item.get("configuration_passed") and
            item.get("targeted_driver_compile", {}).get("passed") for item in prior["results"])):
        raise ValueError("seed must have actual completed three-ABI kernel/header evidence")
    assert_seed_inactive(seed)
    work.mkdir(parents=True, exist_ok=False)
    staged = work / "source"
    kernel = staged / "kernel/linux/linux-6.6"
    original_kernel = seed / "source/kernel/linux/linux-6.6"
    shutil.copytree(original_kernel, kernel, symlinks=True,
                    copy_function=lambda original, target: os.symlink(original, target),
                    ignore=shutil.ignore_patterns(".git"))
    driver_directory, driver_names, driver_target = (
        ("drivers/android", ("binder.c", "binder_internal.h"), "drivers/android/binder.o")
        if args.component == "binder_async_sender" else
        ("drivers/accesstokenid", ("access_tokenid.c", "access_tokenid.h"), "drivers/accesstokenid/access_tokenid.o"))
    for name in driver_names:
        relative = Path(driver_directory) / name
        target = kernel / relative
        expected = root / "kernel/linux/linux-6.6" / relative
        if not target.is_symlink() or target.resolve() != expected.resolve():
            raise ValueError("unknown cached driver input: " + name)
        target.unlink()
        shutil.copy2(expected, target)
    component = repo / "patches/common/kernel/linux/linux_6_6" / args.component
    frozen = work / "inputs"
    shutil.copytree(repo / "patches/lib", frozen / "patches/lib")
    shutil.copytree(component, frozen / component.relative_to(repo))
    result = {"scope": "actual_three_ABI_kernel_driver_objects_NOT_linked_kernel_or_guest_security_validation",
              "component": args.component,
              "first_artifact_behavior_gate_passed": False, "started_utc": datetime.now(timezone.utc).isoformat(),
              "source_root": str(root), "scratch": str(work), "seed": str(seed),
              "seed_evidence_sha256": sha(evidence), "results": [], "status": "fail",
              "payload_sha256": {str(path.relative_to(frozen)): sha(path) for path in frozen.rglob("*") if path.is_file()}}
    try:
        for index in range(2):
            with (work / f"apply-{index}.log").open("x") as stream:
                subprocess.run(["bash", str(frozen / component.relative_to(repo) / "apply.sh"),
                                "--source-root", str(staged)], check=True, stdout=stream, stderr=subprocess.STDOUT)
        result["driver_sha256"] = sha(kernel / driver_directory / driver_names[0])
        for arch, (_, gcc_arch, gcc_directory, prefix) in ARCHITECTURES.items():
            output = work / arch
            output.mkdir()
            shutil.copy2(seed / arch / ".config", output / ".config")
            subprocess.run(["bash", str(kernel / "scripts/config"), "--file", str(output / ".config"),
                            "--enable", "ACCESS_TOKENID"], check=True)
            if args.component == "binder_async_sender":
                subprocess.run(["bash", str(kernel / "scripts/config"), "--file", str(output / ".config"),
                                "--enable", "BINDER_SENDER_INFO"], check=True)
            environment = dict(os.environ)
            command = ["make", "-C", str(kernel), "O=" + str(output), "ARCH=" + arch]
            if prefix:
                compiler = root / "prebuilts/gcc/linux-x86" / gcc_arch / gcc_directory / "bin"
                environment["PATH"] = str(compiler) + os.pathsep + environment["PATH"]
                command.append("CROSS_COMPILE=" + prefix)
            record = {"arch": arch, "commands": []}
            result["results"].append(record)
            for target in ("olddefconfig", driver_target):
                argv = command + ["-j2", target]
                log = work / (arch + "-" + ("config" if target == "olddefconfig" else "compile") + ".log")
                with log.open("x") as stream:
                    completed = subprocess.run(argv, env=environment, stdout=stream, stderr=subprocess.STDOUT)
                record["commands"].append({"argv": argv, "exit_code": completed.returncode, "log_sha256": sha(log)})
                if completed.returncode:
                    raise RuntimeError(arch + " real kernel " + target + " failed")
            if "CONFIG_ACCESS_TOKENID=y\n" not in (output / ".config").read_text():
                raise ValueError("driver configuration did not resolve to enabled")
            if args.component == "binder_async_sender" and "CONFIG_BINDER_SENDER_INFO=y\n" not in (output / ".config").read_text():
                raise ValueError("trusted sender-info configuration did not resolve to enabled")
            obj = output / driver_target
            header = obj.read_bytes()[:64]
            expected = {"arm": (1, 40), "arm64": (2, 183), "x86_64": (2, 62)}[arch]
            if (header[:7] != b"\x7fELF" + bytes((expected[0], 1, 1))
                    or struct.unpack_from("<HH", header, 16) != (1, expected[1])):
                raise ValueError("actual kernel object has incorrect ABI: " + arch)
            record.update(object_path=str(obj), object_sha256=sha(obj), config_sha256=sha(output / ".config"), passed=True)
        if sha(evidence) != result["seed_evidence_sha256"]:
            raise ValueError("seed evidence changed during build")
        result["status"] = "pass"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    evidence_name = "binder-async-driver-evidence.json" if args.component == "binder_async_sender" else "access-token-driver-evidence.json"
    (work / evidence_name).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "error": result.get("error")}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
