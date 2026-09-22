#!/usr/bin/env python3
"""Build one phone/2in1 usability row for every documented OHOS API entry.

This closes a gap in the SysCap ledger: a module can load while individual
class methods are device-restricted, permission-gated, or dependent on a
broken runtime backend.  The output therefore keeps declaration, permission,
surface, and behavioral evidence separate for every documented entry.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEVICES = ("phone", "2in1")
PERMISSION_RE = re.compile(r"ohos\.permission\.[A-Za-z0-9_.]+")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--capability-ledger", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def permission_index(path: Path) -> dict[str, dict[str, Any]]:
    report = read(path)
    return {row["permission"]: row for row in report["permissions"]}


def classify(
    documented_behavior: str,
    capability: dict[str, Any] | None,
    missing_permissions: list[str],
    api_surface_missing: bool,
) -> str:
    if documented_behavior == "unsupported":
        return "documented_unsupported_on_device"
    if documented_behavior.startswith("conditional_"):
        return "conditional_contract_requires_runtime_case"
    if documented_behavior == "review_required":
        return "device_contract_review_required"

    if capability is None:
        return "documentation_missing_syscap_contract"

    if missing_permissions:
        return "permission_registry_failure"
    if api_surface_missing:
        return "api_surface_missing"
    audit_status = capability["audit_status"]
    if audit_status in {"confirmed_broken", "architecture_dependent_failure"}:
        return "behavior_failure_confirmed_for_capability"
    if audit_status == "partially_broken":
        return "capability_partial_failure_method_not_individually_executed"
    if audit_status in {"invalid_declaration", "missing_capability"}:
        return "profile_or_packaging_failure"
    if audit_status == "device_restricted_methods":
        return "method_boundary_failure"
    if audit_status == "conditional_external_dependency":
        return "external_dependency_required"
    if audit_status == "role_restricted":
        return "privileged_role_required"
    if audit_status == "interactive_ui_required":
        return "interactive_ui_required"
    if audit_status == "test_harness_only":
        return "test_harness_required"
    if audit_status == "compile_time_verified":
        return "compile_time_contract"
    if not capability["contract_expected"] and documented_behavior != "supported":
        return "advertised_outside_device_contract"
    # A successful capability-level subset must not be projected onto every
    # method.  Only a method-specific probe can promote an entry to verified.
    if audit_status == "runtime_verified_subset":
        return "capability_subset_verified_method_not_individually_executed"
    return "capability_classified_method_not_individually_executed"


def main() -> int:
    args = arguments()
    entries = read(args.inventory)["entries"]
    capability_rows = read(args.capability_ledger)["capabilities"]
    capabilities = {row["syscap"]: row for row in capability_rows}
    permission_reports = {
        device: permission_index(
            args.runtime_root / f"arm64-{device}" / "permission-audit.json"
        )
        for device in DEVICES
    }

    rows: list[dict[str, Any]] = []
    missing_syscaps: set[str] = set()
    for ordinal, entry in enumerate(entries, 1):
        capability = capabilities.get(entry["syscap"])
        if entry["syscap"] is not None and capability is None:
            missing_syscaps.add(entry["syscap"])
            continue
        permissions = sorted({
            match
            for line in entry["permissions"]
            for match in PERMISSION_RE.findall(line)
        })
        row = {**entry, "api_entry_id": ordinal, "permission_names": permissions, "devices": {}}
        for device in DEVICES:
            cap_device = capability["devices"][device] if capability is not None else None
            missing_permissions = [
                permission
                for permission in permissions
                if not permission_reports[device].get(permission, {}).get("registered", False)
            ]
            documented_behavior = entry[f"{device}_documented_behavior"]
            api_text = f"{entry['heading']} {entry['signature']}"
            missing_export_names = sorted({
                item["name"] for item in (cap_device or {}).get("arkts_missing_runtime_exports", [])
            })
            api_surface_missing = any(
                re.search(rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_$])", api_text)
                for name in missing_export_names
            )
            row["devices"][device] = {
                "documented_behavior": documented_behavior,
                "contract_expected": cap_device["contract_expected"] if cap_device else None,
                "declared": cap_device["declared"] if cap_device else None,
                "can_i_use": cap_device["can_i_use"] if cap_device else None,
                "capability_audit_status": cap_device["audit_status"] if cap_device else "unmapped",
                "capability_coverage_state": cap_device["coverage_state"] if cap_device else "unmapped",
                "surface_state": cap_device["surface_state"] if cap_device else "unmapped",
                "matching_missing_exports": [
                    name for name in missing_export_names
                    if re.search(
                        rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_$])",
                        api_text,
                    )
                ],
                "missing_permissions": missing_permissions,
                "usability_status": classify(
                    documented_behavior, cap_device, missing_permissions, api_surface_missing
                ),
            }
        rows.append(row)

    if missing_syscaps:
        raise RuntimeError(
            "documented SysCaps absent from capability ledger: "
            + ", ".join(sorted(missing_syscaps))
        )

    summary: dict[str, Any] = {
        "documented_api_entry_count": len(rows),
        "callable_entry_count": sum(row["entry_kind"] == "callable" for row in rows),
        "system_api_entry_count": sum(row["system_api"] for row in rows),
        "deprecated_entry_count": sum(row["deprecated"] for row in rows),
        "permission_gated_entry_count": sum(bool(row["permission_names"]) for row in rows),
        "device_boundary_entry_count": sum(
            row.get("device_boundary_scope", "none") != "none" for row in rows
        ),
        "entry_without_syscap_contract_count": sum(row["syscap"] is None for row in rows),
        "devices": {},
    }
    for device in DEVICES:
        summary["devices"][device] = {
            "usability_status_counts": dict(sorted(Counter(
                row["devices"][device]["usability_status"] for row in rows
            ).items())),
            "documented_behavior_counts": dict(sorted(Counter(
                row["devices"][device]["documented_behavior"] for row in rows
            ).items())),
            "entries_with_missing_permission": sum(
                bool(row["devices"][device]["missing_permissions"]) for row in rows
            ),
        }

    result = {"summary": summary, "entries": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.with_name("api-usability-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    fields = [
        "api_entry_id", "syscap", "source", "line", "heading", "signature",
        "entry_kind", "start_api_version", "system_api", "deprecated",
        "device_boundary_scope", "device_boundary", "permission_names", "device",
        "documented_behavior", "contract_expected", "declared", "can_i_use",
        "capability_audit_status", "capability_coverage_state", "surface_state",
        "matching_missing_exports", "missing_permissions", "usability_status",
    ]
    with args.output.with_suffix(".csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            base = {key: row.get(key) for key in fields[:12]}
            base["permission_names"] = ";".join(row["permission_names"])
            for device in DEVICES:
                device_row = row["devices"][device]
                writer.writerow({
                    **base,
                    "device": device,
                    **device_row,
                    "matching_missing_exports": ";".join(
                        device_row["matching_missing_exports"]
                    ),
                    "missing_permissions": ";".join(device_row["missing_permissions"]),
                })

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
