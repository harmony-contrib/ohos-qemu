#!/usr/bin/env python3
"""Require a fresh, complete actual registry query with unchanged privilege policy."""
import argparse
import hashlib
import json
from pathlib import Path
import re

GRANT_MODE = {"user_grant": 0, "system_grant": 1, "manual_settings": 2}
APL = {"normal": 1, "system_basic": 2, "system_core": 3}
AVAILABLE_TYPE = {"NORMAL": 0, "SYSTEM": 1, "MDM": 2, "SYSTEM_AND_MDM": 3,
                  "SERVICE": 4, "ENTERPRISE_NORMAL": 5}
ABSENT = 12100007
INVALID = 12100001
OVERLONG_NAME = "A" * 257
BOOL_FIELDS = ("provisionEnable", "distributedSceneEnable", "isKernelEffect", "hasValue")


def verify(definitions, text, device, run_id, exit_code):
    if device not in ("phone", "2in1") or re.fullmatch("[0-9a-f]{32}", run_id) is None:
        raise ValueError("invalid permission profile or run ID")
    if type(exit_code) is not int or exit_code != 0:
        raise ValueError("permission probe did not exit successfully")
    source = sorted(definitions["definePermissions"], key=lambda row: row["name"])
    if not source or len({row["name"] for row in source}) != len(source):
        raise ValueError("empty or duplicate source permissions")
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(source) + 6 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("incomplete permission result list")
    if rows[0] != {"kind": "run", "runId": run_id} or rows[-1] != {
            "kind": "complete", "runId": run_id, "sourcePermissionCount": len(source)}:
        raise ValueError("stale run ID or incomplete permission probe")
    enabled = 0
    for expected, observed in zip(source, rows[1:-5]):
        types = expected.get("deviceTypes", ["general"])
        if not isinstance(types, list) or not types:
            raise ValueError("invalid source permission device types")
        allowed = "general" in types or device in types
        record = {"kind": "definition", "permissionName": expected["name"], "result": 0 if allowed else ABSENT}
        if allowed:
            enabled += 1
            record.update(grantMode=GRANT_MODE[expected["grantMode"]],
                          availableLevel=APL[expected["availableLevel"]],
                          availableType=AVAILABLE_TYPE[expected["availableType"]])
            for key in BOOL_FIELDS:
                value = expected.get(key, False)
                if type(value) is not bool:
                    raise ValueError("invalid source permission boolean policy")
                record[key] = value
        if set(observed) != set(record) or any(
                type(observed[key]) is not type(value) or observed[key] != value for key, value in record.items()):
            raise ValueError(f"permission registration/privilege differs: {expected['name']}; got {observed}")
    if rows[-5:-1] != [
        {"kind": "absent", "permissionName": "ohos.permission.QEMU_CAPABILITY_AUDIT_DOES_NOT_EXIST", "result": ABSENT},
        {"kind": "unknown-format", "permissionName": "invalid!", "result": ABSENT},
        {"kind": "invalid", "permissionName": OVERLONG_NAME, "result": INVALID},
            {"kind": "empty", "permissionName": "", "result": INVALID}]:
        raise ValueError("absent/invalid/empty permission boundaries differ")
    return {"source_permission_count": len(source), "enabled_count": enabled,
            "disabled_count": len(source) - enabled, "run_id": run_id, "boundary_count": 4}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--device", choices=("phone", "2in1"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--probe-exit-code", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {"scope": "actual AccessToken permission definitions/privilege metadata and query boundaries only",
                "status": "fail", "archive": str(args.archive.resolve()), "failures": []}
    try:
        evidence.update(archive_sha256=digest(args.archive), definitions_sha256=digest(args.definitions),
                        results_sha256=digest(args.results), device_type=args.device,
                        probe_exit_code=args.probe_exit_code)
        evidence["result"] = verify(json.loads(args.definitions.read_text()), args.results.read_text(),
                                    args.device, args.run_id, args.probe_exit_code)
        evidence["status"] = "pass"
    except (ValueError, KeyError, TypeError, OSError) as exc:
        evidence["failures"].append(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
