#!/usr/bin/env python3
"""Merge profile, package, ABI and runtime evidence into one row per SysCap.

The ledger deliberately distinguishes surface checks (a module loads or an ELF
exports a symbol) from behavioral checks.  A surface check is useful coverage,
but it never upgrades an uncalled API to "usable".
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEVICES = ("phone", "2in1")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def validation_environment(syscap: str) -> str:
    lower = syscap.lower()
    hardware_tokens = (
        "bluetooth", "wifi", "wlan", "camera", "sensor", "vibrator", "infrared",
        "usb", "serial", "nfc", "nearlink", "telephony", "location", "gnss",
        "battery", "audio", "microphone", "input", "biometric", "faceauth",
        "pinauth", "companion", "deviceauth", "ddk", "scsi", "hid.", "print",
        "motion", "devicestatus", "multimodalawareness", "wearable",
    )
    peer_tokens = (
        "distributed", "softbus", "continuation", "collaboration", "cloud",
        "datatransit", "fusionconnectivity", "remotedevice", "cast",
    )
    account_tokens = ("account", "enterprise", "payment", "ads", "oaid")
    kernel_tokens = (
        "kernel", "memory", "storage", "filesystem", "filemanagement", "qos",
        "hiviewdfx", "hidebug", "hitrace", "vulkan", "codesign", "accesstoken",
    )
    if any(token in lower for token in hardware_tokens):
        return "hardware_or_virtual_backend"
    if any(token in lower for token in peer_tokens):
        return "peer_device_or_network"
    if any(token in lower for token in account_tokens):
        return "account_policy_or_cloud"
    if any(token in lower for token in kernel_tokens):
        return "kernel_or_filesystem_backend"
    return "local_or_system_integration"


def arkts_index(path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for module in json.loads(path.read_text(encoding="utf-8"))["modules"]:
        for syscap in module["syscaps"]:
            result.setdefault(syscap, []).append(module)
    return result


def c_index(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["syscap"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))["capabilities"]
    }


def arkts_export_index(path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    report = json.loads(path.read_text(encoding="utf-8"))
    for module in report["modules"]:
        for detail in module["missing_official_runtime_exports"]:
            syscaps = detail["syscaps"] or module["official_profile_syscaps"]
            for syscap in syscaps:
                result.setdefault(syscap, []).append({"module": module["module"], **detail})
    return result


def syscap_runtime_index(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["syscap"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))["capabilities"]
    }


def missing_permission_index(path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    report = json.loads(path.read_text(encoding="utf-8"))
    for permission in report["permissions"]:
        if permission["registered"]:
            continue
        for syscap in permission["official_profile_syscaps"]:
            result.setdefault(syscap, []).append({
                "permission": permission["permission"],
                "public_api": permission["public_api"],
                "system_api": permission["system_api"],
                "status": permission["status"],
            })
    return result


def preferred_arkts_report(device_root: Path) -> Path:
    latest = device_root / "arkts-module-load-latest.json"
    return latest if latest.exists() else device_root / "arkts-module-load.json"


def preferred_c_abi_report(device_root: Path) -> Path:
    latest = device_root / "c-api-abi-latest.json"
    return latest if latest.exists() else device_root / "c-api-abi.json"


def surface_state(
    modules: list[dict[str, Any]], c_contract: dict[str, Any] | None,
    missing_exports: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    problems: list[str] = []
    runtime_modules = [row for row in modules if row["has_runtime_callable"]]
    failed_modules = [row["module"] for row in runtime_modules if not row["loaded"]]
    if failed_modules:
        problems.extend(f"arkts_module_missing:{name}" for name in failed_modules)
    problems.extend(
        f"arkts_export_missing:{row['module']}:{row['name']}"
        for row in missing_exports
    )
    if c_contract:
        for library in c_contract["libraries"]:
            if library["status"] != "symbols_match":
                problems.append(f"c_abi_{library['status']}:{library['library']}")
    if problems:
        return "surface_failure", problems
    if runtime_modules or c_contract:
        return "surface_present", []
    if modules:
        return "compile_time_only", []
    return "no_public_runtime_surface", []


def coverage_state(audit_status: str, surface: str) -> str:
    if audit_status in {"confirmed_broken", "partially_broken", "architecture_dependent_failure"}:
        return "behavior_failure_confirmed"
    if audit_status in {"invalid_declaration", "missing_capability"}:
        return "profile_or_packaging_failure"
    if audit_status == "device_restricted_methods":
        return "method_boundary_failure"
    if audit_status == "not_applicable":
        return "not_applicable"
    if surface == "surface_failure":
        return "surface_failure_unclassified"
    if audit_status == "runtime_verified_subset":
        return "behavior_verified_subset"
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
    return "behavior_validation_pending"


def main() -> int:
    args = arguments()
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))["capabilities"]
    device_roots = {
        device: args.runtime_root / f"arm64-{device}"
        for device in DEVICES
    }
    arkts_reports = {
        device: preferred_arkts_report(device_roots[device])
        for device in DEVICES
    }
    arkts = {device: arkts_index(arkts_reports[device]) for device in DEVICES}
    arkts_export_reports = {
        device: device_roots[device] / "arkts-export-surface-latest.json"
        for device in DEVICES
    }
    arkts_exports = {
        device: arkts_export_index(arkts_export_reports[device])
        for device in DEVICES
    }
    c_abi = {
        device: c_index(preferred_c_abi_report(device_roots[device]))
        for device in DEVICES
    }
    syscap_runtime = {
        device: syscap_runtime_index(device_roots[device] / "syscap-runtime.json")
        for device in DEVICES
    }
    missing_permissions = {
        device: missing_permission_index(device_roots[device] / "permission-audit.json")
        for device in DEVICES
    }

    rows: list[dict[str, Any]] = []
    for capability in matrix:
        syscap = capability["syscap"]
        row: dict[str, Any] = {
            "syscap": syscap,
            "validation_environment": validation_environment(syscap),
            "documented_api_entries": capability["documented_api"]["entry_count"],
            "arkts_annotation_count": capability["arkts"]["annotation_count"],
            "c_annotation_count": capability["c_api"]["annotation_count"],
            "xts_source_count": capability["xts"]["source_count"],
            "devices": {},
        }
        for device in DEVICES:
            profile = capability["devices"][device]
            modules = arkts[device].get(syscap, [])
            missing_exports = arkts_exports[device].get(syscap, [])
            contract = c_abi[device].get(syscap)
            syscap_probe = syscap_runtime[device].get(syscap, {})
            surface, surface_problems = surface_state(modules, contract, missing_exports)
            runtime_modules = [module for module in modules if module["has_runtime_callable"]]
            permission_gaps = missing_permissions[device].get(syscap, [])
            coverage = coverage_state(profile["audit_status"], surface)
            if permission_gaps and coverage in {
                "behavior_validation_pending", "behavior_verified_subset"
            }:
                coverage = "permission_registry_gap"
            row["devices"][device] = {
                "official_sdk_profile": profile["official_sdk_profile"],
                "documented_minimum_profile": profile["documented_minimum_profile"],
                "documented_profile_is_reference_only": profile["documented_profile_is_reference_only"],
                "contract_expected": profile["contract_expected"],
                "profile_source_status": profile["profile_source_status"],
                "declared": profile["declared"],
                "declaration_status": profile["declaration_status"],
                "contract_declaration_status": profile["contract_declaration_status"],
                "audit_status": profile["audit_status"],
                "coverage_state": coverage,
                "can_i_use": syscap_probe.get("can_i_use"),
                "syscap_runtime_status": syscap_probe.get("status", "not_probed"),
                "surface_state": surface,
                "surface_problems": surface_problems,
                "missing_runtime_permissions": permission_gaps,
                "arkts_modules": [module["module"] for module in modules],
                "arkts_runtime_module_count": len(runtime_modules),
                "arkts_loaded_runtime_module_count": sum(module["loaded"] for module in runtime_modules),
                "arkts_missing_runtime_exports": missing_exports,
                "arkts_missing_public_function_count": sum(
                    item["kind"] == "function" and not item["system_api"]
                    for item in missing_exports
                ),
                "arkts_missing_system_function_count": sum(
                    item["kind"] == "function" and item["system_api"]
                    for item in missing_exports
                ),
                "c_library_contract_count": len(contract["libraries"]) if contract else 0,
                "c_abi_ok": (
                    all(library["status"] == "symbols_match" for library in contract["libraries"])
                    if contract else None
                ),
                "image_components": capability["image_components"][device],
                "findings": profile["findings"],
            }
        rows.append(row)

    summary: dict[str, Any] = {
        "capability_count": len(rows),
        "arkts_reports": {device: str(path) for device, path in arkts_reports.items()},
        "arkts_export_reports": {
            device: str(path) for device, path in arkts_export_reports.items()
        },
        "devices": {},
    }
    for device in DEVICES:
        official = [row for row in rows if row["devices"][device]["official_sdk_profile"]]
        contract = [row for row in rows if row["devices"][device]["contract_expected"]]
        declared = [row for row in rows if row["devices"][device]["declared"]]
        summary["devices"][device] = {
            "official_profile_count": len(official),
            "documented_profile_count": sum(
                row["devices"][device]["documented_minimum_profile"] for row in rows
            ),
            "contract_expected_count": len(contract),
            "declared_count": len(declared),
            "contract_coverage_state_counts": dict(sorted(Counter(
                row["devices"][device]["coverage_state"] for row in contract
            ).items())),
            "contract_surface_state_counts": dict(sorted(Counter(
                row["devices"][device]["surface_state"] for row in contract
            ).items())),
            "contract_can_i_use_counts": dict(sorted(Counter(
                str(row["devices"][device]["can_i_use"]).lower() for row in contract
            ).items())),
            "all_public_coverage_state_counts": dict(sorted(Counter(
                row["devices"][device]["coverage_state"] for row in rows
            ).items())),
            "declared_outside_official_profile": sum(
                row["devices"][device]["declaration_status"] == "declared_outside_official_profile"
                for row in rows
            ),
            "missing_from_official_profile": sum(
                row["devices"][device]["declaration_status"] == "missing_from_image"
                for row in rows
            ),
        }

    result = {"summary": summary, "capabilities": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fields = [
        "syscap", "validation_environment", "documented_api_entries",
        "arkts_annotation_count", "c_annotation_count", "xts_source_count",
        "device", "official_sdk_profile", "documented_minimum_profile",
        "documented_profile_is_reference_only", "contract_expected", "profile_source_status",
        "declared", "declaration_status", "contract_declaration_status",
        "audit_status", "coverage_state", "can_i_use", "syscap_runtime_status",
        "surface_state", "surface_problems",
        "missing_runtime_permissions",
        "arkts_modules", "arkts_runtime_module_count", "arkts_loaded_runtime_module_count",
        "arkts_missing_runtime_exports", "arkts_missing_public_function_count",
        "arkts_missing_system_function_count",
        "c_library_contract_count", "c_abi_ok", "image_components", "findings",
    ]
    with args.output.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            for device in DEVICES:
                device_row = row["devices"][device]
                writer.writerow({
                    **{key: row[key] for key in fields[:6]},
                    "device": device,
                    **{key: device_row[key] for key in fields[7:20]},
                    "surface_problems": ";".join(device_row["surface_problems"]),
                    "missing_runtime_permissions": ";".join(
                        item["permission"] for item in device_row["missing_runtime_permissions"]
                    ),
                    "arkts_modules": ";".join(device_row["arkts_modules"]),
                    "arkts_runtime_module_count": device_row["arkts_runtime_module_count"],
                    "arkts_loaded_runtime_module_count": device_row["arkts_loaded_runtime_module_count"],
                    "arkts_missing_runtime_exports": ";".join(
                        f"{item['module']}:{item['name']}" for item in
                        device_row["arkts_missing_runtime_exports"]
                    ),
                    "arkts_missing_public_function_count": device_row[
                        "arkts_missing_public_function_count"
                    ],
                    "arkts_missing_system_function_count": device_row[
                        "arkts_missing_system_function_count"
                    ],
                    "c_library_contract_count": device_row["c_library_contract_count"],
                    "c_abi_ok": device_row["c_abi_ok"],
                    "image_components": ";".join(device_row["image_components"]),
                    "findings": ";".join(
                        f"{finding['id']}:{finding['status']}:{finding['evidence']}"
                        for finding in device_row["findings"]
                    ),
                })

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
