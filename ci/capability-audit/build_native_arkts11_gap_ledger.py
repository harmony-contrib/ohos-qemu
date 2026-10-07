#!/usr/bin/env python3
"""Build the focused OHOS 7 Native and ArkTS 1.1 gap ledger.

The broad capability audit also inventories ArkTS Static declarations.  This
tool deliberately excludes that surface and keeps four independent failure
layers visible:

* Native C/C++ library and symbol contracts;
* ArkTS 1.1 dynamic module loading and runtime exports;
* permissions required by the dynamic or Native contracts; and
* behavior findings below the API surface (service, provider, kernel, or
  virtual-hardware backends).

It consumes checked-in audit evidence and does not infer that a loadable
module, a present library, or a passing lifecycle smoke test is usable.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEVICES = ("phone", "2in1")
GAP_STATUSES = {
    "architecture_dependent_failure",
    "confirmed_broken",
    "invalid_declaration",
    "missing_capability",
    "partially_broken",
}


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def native_gaps(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for capability in report["capabilities"]:
        for library in capability["libraries"]:
            if library["status"] == "symbols_match":
                continue
            rows.append(
                {
                    "syscap": capability["syscap"],
                    "scope": capability["declaration_status"],
                    "official_sdk_profile": capability["official_sdk_profile"],
                    "declared_by_image": capability["declared"],
                    "library": library["library"],
                    "status": library["status"],
                    "public_function_count": library["public_function_count"],
                    "missing_symbols": library["missing_symbols"],
                    "runtime_paths": library["runtime_paths"],
                }
            )
    return rows


def arkts_load_gaps(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "module": module["module"],
            "syscaps": module["official_profile_syscaps"],
            "status": module["audit_status"],
        }
        for module in report["modules"]
        if module["audit_status"] == "official_callable_load_failure"
    ]


def arkts_export_gaps(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in report["modules"]:
        missing = module["missing_official_runtime_exports"]
        if not missing or module["audit_status"] == "compile_time_declaration":
            continue
        rows.append(
            {
                "module": module["module"],
                "syscaps": module["official_profile_syscaps"],
                "loaded": module["loaded"],
                "audit_status": module["audit_status"],
                "missing_count": len(missing),
                "missing": missing,
            }
        )
    return rows


def permission_gaps(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "permission": permission["permission"],
            "status": permission["status"],
            "public_api": permission["public_api"],
            "system_api": permission["system_api"],
            "syscaps": permission["syscaps"],
            "sources": [
                source
                for source in permission["sources"]
                if not source.endswith(".static.d.ets")
            ],
        }
        for permission in report["permissions"]
        if permission["status"].startswith("missing_official_")
        and any(
            not source.endswith(".static.d.ets")
            for source in permission["sources"]
        )
    ]


def compiled_constant_contracts(report: dict[str, Any]) -> list[dict[str, Any]]:
    if any("compiled_constant_enum_contracts" not in module for module in report["modules"]):
        raise ValueError("regenerate ArkTS export evidence with the const-enum-aware analyzer")
    return [
        {"module": module["module"], "contracts": module["compiled_constant_enum_contracts"]}
        for module in report["modules"]
        if module["compiled_constant_enum_contracts"]
    ]


def behavior_gaps(
    findings: dict[str, Any], device: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings["findings"]:
        device_result = finding.get("devices", {}).get(device)
        if not device_result or device_result.get("status") not in GAP_STATUSES:
            continue
        rows.append(
            {
                "id": finding["id"],
                "status": device_result["status"],
                "syscap_match": finding.get("match", {}),
                "evidence": device_result["evidence"],
            }
        )
    return rows


def summarize_exports(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: Counter[str] = Counter()
    public_functions = 0
    system_functions = 0
    for row in rows:
        for export in row["missing"]:
            kinds[export["kind"]] += 1
            if export["kind"] != "function":
                continue
            if export["system_api"]:
                system_functions += 1
            else:
                public_functions += 1
    return {
        "module_count": len(rows),
        "loaded_module_count": sum(row["loaded"] for row in rows),
        "unloadable_module_count": sum(not row["loaded"] for row in rows),
        "export_count": sum(kinds.values()),
        "by_kind": dict(sorted(kinds.items())),
        "public_function_count": public_functions,
        "system_function_count": system_functions,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = args.runtime_root
    findings = load(args.findings)
    result: dict[str, Any] = {
        "schema_version": 1,
        "scope": {
            "included": [
                "Native C/C++ public ABI",
                "ArkTS 1.1 dynamic modules and runtime exports",
                "permissions used by those contracts",
                "runtime service/provider/kernel/virtual-hardware behavior",
            ],
            "excluded": ["ArkTS Static"],
            "passing_smoke_test_is_not_full_capability_proof": True,
        },
        "devices": {},
    }

    for device in DEVICES:
        prefix = runtime_root / f"arm64-{device}"
        native_report = load(prefix / "c-api-abi-latest.json")
        load_report = load(prefix / "arkts-module-load-latest.json")
        export_report = load(prefix / "arkts-export-surface-latest.json")
        permission_report = load(prefix / "permission-audit.json")

        native = native_gaps(native_report)
        loads = arkts_load_gaps(load_report)
        exports = arkts_export_gaps(export_report)
        constants = compiled_constant_contracts(export_report)
        permissions = permission_gaps(permission_report)
        behaviors = behavior_gaps(findings, device)

        result["devices"][device] = {
            "summary": {
                "native_library_or_symbol_gap_count": len(native),
                "native_official_contract_gap_count": sum(
                    row["official_sdk_profile"] for row in native
                ),
                "arkts11_official_callable_module_load_failure_count": len(loads),
                "arkts11_missing_runtime_exports": summarize_exports(exports),
                "arkts11_compiled_constant_enum_contract_count": sum(
                    len(row["contracts"]) for row in constants
                ),
                "missing_official_permission_count": len(permissions),
                "behavior_gap_count": len(behaviors),
                "behavior_status_counts": dict(
                    sorted(Counter(row["status"] for row in behaviors).items())
                ),
            },
            "native_abi_gaps": native,
            "arkts11_module_load_gaps": loads,
            "arkts11_runtime_export_gaps": exports,
            "arkts11_compiled_constant_enum_contracts": constants,
            "permission_registry_gaps": permissions,
            "runtime_behavior_gaps": behaviors,
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
