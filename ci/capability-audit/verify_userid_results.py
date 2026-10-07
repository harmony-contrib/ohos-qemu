#!/usr/bin/env python3
"""Validate real task user-ID state and AppSpawn isolation, not all AccessToken APIs."""
import argparse
import json
from pathlib import Path
import re
from verify_access_token_results import digest

COMMON = ("userid_device_openable", "userid_initial_read")
ROOT = ("root_set_distinct_userid", "userid_actual_roundtrip", "userid_fork_created",
        "userid_fork_inherited_and_child_changed", "child_userid_does_not_change_parent",
        "userid_null_set_rejected", "userid_invalid_input_rejected", "bad_set_keeps_userid",
        "userid_original_restored", "userid_restore_observed")
APP = ("appspawn_userid_matches_os_account", "normal_uid_cannot_retag_account", "normal_uid_account_unchanged")
BOUNDARY = ("userid_null_get_rejected", "userid_invalid_output_rejected", "userid_boundary_page_size",
            "userid_boundary_mapping_created", "userid_boundary_mapping_readonly",
            "userid_readonly_copyout_rejected", "userid_boundary_mapping_removed", "userid_final_state_unchanged")


def verify(rows, arch, mode, run_id, exit_code, expected_user_id=None, app_context=False):
    if arch not in ("arm64", "armv7a", "x86_64") or mode not in ("privileged", "unprivileged"):
        raise ValueError("unsupported architecture or role")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or type(exit_code) is not int or exit_code != 0:
        raise ValueError("fresh identity and actual successful probe exit required")
    if not rows or any(not isinstance(row, dict) or row.get("run_id") != run_id for row in rows):
        raise ValueError("missing/mixed user-ID records")
    first = rows[0]
    uid, euid = first.get("uid"), first.get("euid")
    if (first.get("kind") != "userid_run" or first.get("arch") != arch or first.get("mode") != mode or
        first.get("pointer_bits") != (32 if arch == "armv7a" else 64) or
        any(type(value) is not int or not 0 <= value <= 0xffffffff for value in (uid, euid))):
        raise ValueError("wrong user-ID run environment")
    if (mode == "privileged" and (uid != 0 or euid != 0)) or (
            mode == "unprivileged" and (uid in (0, 3020) or euid in (0, 3020))):
        raise ValueError("incorrect authorization role")
    if mode == "unprivileged":
        if (type(expected_user_id) is not int or not 0 <= expected_user_id <= 0xffffffff or
                type(first.get("expected_user_id")) is not int or
                first.get("expected_user_id") != expected_user_id):
            raise ValueError("explicit OS account expectation required")
    if app_context:
        if (mode != "unprivileged" or uid != euid or uid % 200000 < 10000 or
                uid // 200000 != expected_user_id):
            raise ValueError("not an ordinary application in the expected OS account")
        result = {"kind": "native_result", "run_id": run_id, "exit_code": 0}
        if rows[-1] != result or type(rows[-1].get("exit_code")) is not int:
            raise ValueError("missing successful in-app native result")
        rows = rows[:-1]
    if rows[-1] != {"kind": "complete", "run_id": run_id}:
        raise ValueError("incomplete user-ID test")
    cases = rows[1:-1]
    names = COMMON + (ROOT if mode == "privileged" else APP) + BOUNDARY
    if (tuple(row.get("name") for row in cases) != names or
            any(row.get("kind") != "case" or row.get("pass") is not True for row in cases)):
        raise ValueError("failed, missing, duplicate, reordered or malformed user-ID case")
    return {"scope": "task_userid_storage_boundaries_and_appspawn_not_all_access_token_apis",
            "arch": arch, "mode": mode, "uid": uid, "euid": euid, "app_context": app_context,
            "expected_user_id": expected_user_id, "cases": list(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--mode", choices=("privileged", "unprivileged"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--probe-exit-code", type=int, required=True)
    parser.add_argument("--expected-user-id", type=int)
    parser.add_argument("--app-context", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"schema_version": 1, "status": "fail", "failures": [],
              "scope": "task_userid_storage_boundaries_and_appspawn_not_all_access_token_apis",
              "archive": str(args.archive.resolve()), "run_id": args.run_id,
              "probe_exit_code": args.probe_exit_code, "first_artifact_behavior_gate_passed": False}
    try:
        result.update(archive_sha256=digest(args.archive), log_sha256=digest(args.log))
        rows = [json.loads(line) for line in args.log.read_text().splitlines() if line.strip()]
        result["observations"] = rows
        result["result"] = verify(rows, args.arch, args.mode, args.run_id, args.probe_exit_code,
                                  args.expected_user_id, args.app_context)
        result["status"] = "pass"
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["failures"].append(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
