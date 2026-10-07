#!/usr/bin/env python3
"""Run fresh system-DSO exit regressions; HDC transport success is not test success."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify_shared_fence_owner import needed_libraries, verify_pair

from build_library_exit_probes import CASES
from run_root_probe import digest, parse_exit, validate_elf, validate_identity


def verify(rows, repeats):
    expected = {(case, repeat) for case in CASES for repeat in range(repeats)}
    observed = [(row["case"], row["repeat"]) for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("missing, duplicate, or unexpected link-order executions")
    failures = [row for row in rows if row["guest_exit_code"] != 0]
    return {"status": "fail" if failures else "pass", "executions": len(rows),
            "failures": failures, "first_artifact_behavior_gate_passed": False,
            "scope": "isolated_root_empty_main_exit_cleanup_only"}


def candidate_inputs(args):
    paths = [getattr(args, name, None) for name in
             ("candidate_surface", "candidate_fence", "candidate_mapping_probe")]
    if not any(paths):
        return None
    if not all(paths):
        raise ValueError("candidate diagnosis requires both libraries and a stopped mapping probe")
    surface, fence, probe = paths
    records = verify_pair(surface, fence, args.arch)
    validate_elf(probe, args.arch)
    if not {"libavplayer.so", "libudmf.so"} <= needed_libraries(probe):
        raise ValueError("mapping probe must link AVPlayer and UDMF")
    return {"surface": {**records["surface"], "path": str(surface)},
            "fence": {**records["fence"], "path": str(fence)},
            "mapping_probe": {"path": str(probe), "sha256": digest(probe)}}


def verify_candidate_maps(maps, remote):
    expected = {remote + "/candidate/" + name
                for name in ("libsurface.z.so", "libsync_fence.z.so")}
    observed = set()
    for line in maps.splitlines():
        fields = line.split()
        if len(fields) >= 6 and fields[5].split("/")[-1] in ("libsurface.z.so", "libsync_fence.z.so"):
            if len(fields) != 6:
                raise ValueError("ambiguous/deleted candidate library mapping")
            observed.add(fields[5])
    if observed != expected:
        raise ValueError("process did not exclusively map the actual candidate library pair")
    return sorted(observed)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = secrets.token_hex(16)
    remote = "/data/local/tmp/ohos-library-exit-" + run_id
    evidence = {"schema_version": 1, "status": "fail", "run_id": run_id,
                "arch": args.arch, "device": args.device, "target": args.target,
                "hdc_server_port": os.environ.get("OHOS_HDC_SERVER_PORT", "8710"),
                "commands": [], "results": [], "failures": [],
                "first_artifact_behavior_gate_passed": False,
                "archive_binding": "not_attested_by_this_diagnostic_runner"}

    def command(argv):
        record = {"argv": [str(value) for value in argv]}
        evidence["commands"].append(record)
        result = subprocess.run(record["argv"], capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=60, check=False)
        record.update(transport_exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if result.returncode:
            raise ValueError("HDC transport failure, not an observed process exit")
        return result.stdout.replace("\r", "")

    def shell(script):
        return command([args.hdc, "-t", args.target, "shell", script])

    try:
        candidate = candidate_inputs(args)
        if candidate:
            evidence.update(scope="private_candidate_DSOs_on_old_guest_NOT_new_package_acceptance",
                            candidate_inputs=candidate)
        manifest = json.loads((args.probes / "manifest.json").read_text())
        command([args.hdc, "tconn", args.target])
        validate_identity(shell("id -u; param get const.product.devicetype; uname -m"), args.arch, args.device)
        evidence["environment"] = shell("param get const.ohos.fullname; uname -a; ls /data/log/faultlog/faultlogger")
        marker = "__OHOS_LIBRARY_EXIT_CREATED_" + run_id
        if shell("umask 077; mkdir " + shlex.quote(remote) + " && printf '" + marker + "\\n'").strip() != marker:
            raise ValueError("fresh guest run directory was not created")
        if candidate:
            shell("mkdir " + shlex.quote(remote + "/candidate"))
            for key, name in (("surface", "candidate/libsurface.z.so"),
                              ("fence", "candidate/libsync_fence.z.so"),
                              ("mapping_probe", "mapping-probe")):
                record = candidate[key]
                destination = remote + "/" + name
                command([args.hdc, "-t", args.target, "file", "send", record["path"], destination])
                if shell("chmod 700 " + shlex.quote(destination) + "; sha256sum " + shlex.quote(destination)).split() != [record["sha256"], destination]:
                    raise ValueError("guest candidate input hash mismatch")
            nonce = secrets.token_hex(16)
            wrapper = ("unset LD_LIBRARY_PATH LD_PRELOAD; LD_LIBRARY_PATH=" + shlex.quote(remote + "/candidate") +
                       " " + shlex.quote(remote + "/mapping-probe") + " >" + shlex.quote(remote + "/mapping.out") +
                       " 2>" + shlex.quote(remote + "/mapping.err") + " & owned_pid=$!; printf '%s\\n' \"$owned_pid\" >" +
                       shlex.quote(remote + "/mapping.pid") + "; wait \"$owned_pid\"; owned_status=$?; " +
                       "printf '__OHOS_PROBE_EXIT_" + nonce + "=%s\\n' \"$owned_status\" >" + shlex.quote(remote + "/mapping.exit"))
            shell("sh -c " + shlex.quote(wrapper) + " >/dev/null 2>&1 </dev/null &")
            pid = None
            for _ in range(30):
                early_exit = shell("cat " + shlex.quote(remote + "/mapping.exit") + " 2>/dev/null")
                if early_exit:
                    evidence["mapping_probe_exit_code"] = parse_exit(early_exit, nonce)
                    (args.output / "mapping.err").write_text(shell("cat " + shlex.quote(remote + "/mapping.err")))
                    raise ValueError("mapping probe exited before candidate attestation: " + str(evidence["mapping_probe_exit_code"]))
                value = shell("cat " + shlex.quote(remote + "/mapping.pid") + " 2>/dev/null").strip()
                if value.isascii() and value.isdecimal() and int(value) > 1:
                    pid = value
                    status = shell("cat /proc/" + pid + "/status")
                    if any(line.startswith("State:") and line.split()[1] in ("T", "t") for line in status.splitlines()):
                        break
                time.sleep(0.2)
            else:
                if pid:
                    shell("if test \"$(readlink /proc/" + pid + "/exe)\" = " + shlex.quote(remote + "/mapping-probe") +
                          "; then kill -CONT " + pid + "; fi")
                raise ValueError("mapping probe did not stop for candidate attestation")
            try:
                maps = shell("cat /proc/" + pid + "/maps")
                (args.output / "candidate-maps.txt").write_text(maps)
                evidence["candidate_mappings"] = verify_candidate_maps(maps, remote)
            finally:
                # Resume only our stopped executable, never an unrelated/reused PID.
                shell("test \"$(readlink /proc/" + pid + "/exe)\" = " + shlex.quote(remote + "/mapping-probe") +
                      " && kill -CONT " + pid)
            for _ in range(30):
                value = shell("cat " + shlex.quote(remote + "/mapping.exit") + " 2>/dev/null")
                if value:
                    evidence["mapping_probe_exit_code"] = parse_exit(value, nonce)
                    if evidence["mapping_probe_exit_code"] != 0:
                        raise ValueError("candidate mapping probe failed on process exit")
                    break
                time.sleep(0.2)
            else:
                raise ValueError("mapping probe did not report its actual process exit")
        for case in CASES:
            executable = args.probes / args.arch / case
            validate_elf(executable, args.arch)
            sha = digest(executable)
            record = manifest["artifacts"][args.arch + "/" + case]
            if record["sha256"] != sha or record["link_order"] != list(CASES[case]):
                raise ValueError("executable/manifest link-order mismatch")
            destination = remote + "/" + case
            command([args.hdc, "-t", args.target, "file", "send", str(executable), destination])
            if shell("chmod 700 " + shlex.quote(destination) + "; sha256sum " + shlex.quote(destination)).split() != [sha, destination]:
                raise ValueError("guest executable hash mismatch")
            for repeat in range(args.repeats):
                nonce = secrets.token_hex(16)
                stem = destination + "-" + str(repeat)
                library_environment = ("LD_LIBRARY_PATH=" + shlex.quote(remote + "/candidate") + " ") if candidate else ""
                code = parse_exit(shell("unset LD_LIBRARY_PATH LD_PRELOAD; " + library_environment + shlex.quote(destination) +
                    " >" + shlex.quote(stem + ".out") + " 2>" + shlex.quote(stem + ".err") +
                    "; probe_status=$?; printf '__OHOS_PROBE_EXIT_" + nonce + "=%s\\n' \"$probe_status\""), nonce)
                row = {"case": case, "repeat": repeat, "guest_exit_code": code, "probe_sha256": sha,
                       "link_order": record["link_order"], "nonce": nonce}
                evidence["results"].append(row)
                for suffix in ("out", "err"):
                    (args.output / (case + "-" + str(repeat) + "." + suffix)).write_text(shell("cat " + shlex.quote(stem + "." + suffix)))
        evidence["result"] = verify(evidence["results"], args.repeats)
        if candidate:
            evidence["result"]["scope"] = "private_candidate_empty_main_exit_only_NOT_packaged_system_DSOs"
        evidence["status"] = evidence["result"]["status"]
        evidence["fault_files_after"] = shell("ls /data/log/faultlog/faultlogger")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        evidence["failures"].append(str(exc))
    finally:
        (args.output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--device", choices=("phone", "2in1"), required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=range(3, 11), default=3)
    parser.add_argument("--candidate-surface", type=Path,
                        help="diagnostic only: stage a new libsurface in a private guest directory")
    parser.add_argument("--candidate-fence", type=Path,
                        help="diagnostic only: stage the matching shared fence provider")
    parser.add_argument("--candidate-mapping-probe", type=Path,
                        help="AVPlayer/UDMF probe that raises SIGSTOP before returning from main")
    parser.add_argument("--hdc", default="/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({"status": result["status"], "executions": len(result["results"]),
                      "failures": result["failures"], "evidence": str(args.output / "result.json")}))
    raise SystemExit(0 if result["status"] == "pass" else 1)
