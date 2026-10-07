#!/usr/bin/env python3
"""Require fresh complete HDI behavior results; CAPI/JSON/app tests are separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re

CASES = ("connect", "time_capacity_only", "info_local", "oneshot_running", "oneshot_cancel",
         "oneshot_expiry", "preset_known", "preset_unknown_no_change", "upstream_stop_marker",
         "timeline_no_double_count", "invalid_sequence_no_change",
         "wrong_device_no_change", "unsupported_modulation", "cleaned")


def verify(log, arch, run_id, exit_code):
    if arch not in ("arm64", "armv7a", "x86_64") or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise ValueError("invalid architecture/run ID")
    if type(exit_code) is not int or exit_code != 0:
        raise ValueError("actual probe exit code is not zero")
    rows = [json.loads(line) for line in log.splitlines()]
    expected = [{"kind": "run", "run_id": run_id, "arch": arch, "uid": 0, "euid": 0},
                *[{"kind": "case", "name": name, "pass": True} for name in CASES],
                {"kind": "complete", "run_id": run_id}]
    if len(rows) != len(expected):
        raise ValueError("incomplete or repeated result records")
    for observed, wanted in zip(rows, expected):
        if not isinstance(observed, dict) or set(observed) != set(wanted) or any(
                type(observed[key]) is not type(value) or observed[key] != value for key, value in wanted.items()):
            raise ValueError(f"unexpected/stale/failed HDI result: {observed}")
    return {"case_count": len(CASES), "run_id": run_id, "arch": arch}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--probe-exit-code", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {"scope": "root real HDI IPC/virtual time backend only, not ordinary-app CAPI/JSON decoding",
                "status": "fail", "failures": []}
    try:
        evidence.update(archive=str(args.archive.resolve()), archive_sha256=digest(args.archive),
                        probe_sha256=digest(args.probe), log_sha256=digest(args.log), probe_exit_code=args.probe_exit_code)
        evidence["result"] = verify(args.log.read_text(), args.arch, args.run_id, args.probe_exit_code)
        evidence["status"] = "pass"
    except (ValueError, TypeError, KeyError, OSError) as exc:
        evidence["failures"].append(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
