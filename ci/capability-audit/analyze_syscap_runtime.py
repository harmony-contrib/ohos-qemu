#!/usr/bin/env python3
"""Compare app-visible canIUse() results with every public OHOS 7 SysCap."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


PREFIX = "syscap.canIUse."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument("--probe-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    values: dict[str, bool] = {}
    for line in args.probe_log.read_text(encoding="utf-8").splitlines():
        if not line.startswith(PREFIX) or line.startswith(PREFIX + "summary="):
            continue
        name, value = line[len(PREFIX):].rsplit("=", 1)
        if value in {"true", "false"}:
            values[name] = value == "true"

    rows = []
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))["capabilities"]
    for capability in matrix:
        syscap = capability["syscap"]
        profile = capability["devices"][args.device]
        enabled = values.get(syscap)
        if enabled is None:
            status = "not_probed"
        elif enabled != profile["declared"]:
            status = "declaration_runtime_mismatch"
        elif enabled and profile["contract_expected"]:
            status = "enabled_contract_capability"
        elif enabled:
            status = "enabled_outside_contract"
        elif profile["contract_expected"]:
            status = "disabled_contract_capability"
        else:
            status = "disabled_outside_contract"
        rows.append({
            "syscap": syscap,
            "can_i_use": enabled,
            "declared": profile["declared"],
            "official_sdk_profile": profile["official_sdk_profile"],
            "documented_minimum_profile": profile["documented_minimum_profile"],
            "documented_profile_is_reference_only": profile["documented_profile_is_reference_only"],
            "contract_expected": profile["contract_expected"],
            "profile_source_status": profile["profile_source_status"],
            "status": status,
        })

    summary = {
        "device": args.device,
        "public_syscap_count": len(rows),
        "probed_count": sum(row["can_i_use"] is not None for row in rows),
        "enabled_count": sum(row["can_i_use"] is True for row in rows),
        "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
    }
    result = {"summary": summary, "capabilities": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.output.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
