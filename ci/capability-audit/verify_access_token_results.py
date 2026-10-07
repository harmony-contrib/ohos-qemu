#!/usr/bin/env python3
"""Reject partial/stale raw kernel ABI probe logs; not all AccessToken API proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PRIVILEGED_CASES = (
    "device_present_and_openable", "reserved_token_absent_before_test", "root_add_reserved_bitmap",
    "all_64_words_match", "all_2048_bits_match_single_query", "revoke_last_bit", "revocation_observed",
    "grant_last_bit_observed", "grant_bitmap_observed", "opcode_2048_rejected", "overflow_opcode_rejected",
    "null_argument_rejected", "invalid_user_address_rejected", "page_size_for_copyout_boundary",
    "copyout_boundary_mapping_created", "copyout_boundary_mapping_readonly", "readonly_copyout_rejected",
    "copyout_boundary_mapping_removed", "concurrent_reader_started",
    "concurrent_reader_joined", "remove_readd_reader_snapshot_consistency", "reserved_token_removed",
    "removed_token_has_no_permissions", "unsupported_spm_not_falsely_advertised",
)
NORMAL_CASES = (
    "device_present_and_openable", "reserved_token_absent_before_test", "normal_uid_cannot_add_permissions",
    "normal_uid_cannot_set_permissions", "normal_uid_cannot_remove_permissions", "normal_uid_read_own_token",
    "normal_uid_cannot_set_token",
)


def verify(rows, arch, mode, run_id, exit_code):
    if arch not in ("arm64", "armv7a", "x86_64") or mode not in ("privileged", "unprivileged"):
        raise ValueError("unsupported architecture or mode")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or type(exit_code) is not int or exit_code != 0:
        raise ValueError("fresh run ID and actual successful process exit code are required")
    if len(rows) < 3 or any(row.get("run_id") != run_id for row in rows):
        raise ValueError("missing or mixed run identity")
    first, last = rows[0], rows[-1]
    if first.get("kind") != "run" or last != {"kind": "complete", "run_id": run_id}:
        raise ValueError("missing complete run envelope")
    uid = first.get("uid")
    if (type(uid) is not int or uid < 0 or uid > 0xffffffff or first.get("mode") != mode or
        first.get("arch") != arch or first.get("pointer_bits") != (32 if arch == "armv7a" else 64)):
        raise ValueError("wrong architecture, mode or UID")
    if (mode == "privileged" and uid != 0) or (mode == "unprivileged" and uid in (0, 3020)):
        raise ValueError("not run under the required authorization role")
    cases = rows[1:-1]
    actual = tuple(row.get("name") for row in cases)
    expected = PRIVILEGED_CASES if mode == "privileged" else NORMAL_CASES
    denied_at_device = mode == "unprivileged" and actual == ("normal_uid_device_access_denied",)
    if not denied_at_device and actual != expected:
        raise ValueError("missing, duplicate, reordered or unknown test case")
    if any(row.get("kind") != "case" or row.get("pass") is not True for row in cases):
        raise ValueError("failed or malformed test case")
    return {"scope": "raw_bitmap_abi_and_authorization_not_all_access_token_apis",
            "enhanced_spm_implemented": False, "arch": arch, "mode": mode, "uid": uid,
            "device_access_denied": denied_at_device, "cases": list(actual)}


def digest(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"missing/empty evidence file: {path}")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--mode", choices=("privileged", "unprivileged"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--probe-exit-code", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive_sha, log_sha = digest(args.archive), digest(args.log)
    rows = [json.loads(line) for line in args.log.read_text().splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("JSONL object records required")
    result = verify(rows, args.arch, args.mode, args.run_id, args.probe_exit_code)
    result.update({"schema_version": 1, "archive": str(args.archive.resolve()), "archive_sha256": archive_sha,
                   "log_sha256": log_sha, "run_id": args.run_id, "probe_exit_code": args.probe_exit_code})
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {args.arch}/{args.mode} raw AccessToken ABI; enhanced SPM not implemented")


if __name__ == "__main__":
    main()
