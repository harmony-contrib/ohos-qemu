#!/usr/bin/env python3
"""Fail when a phone/2in1 audit silently omits public capabilities or modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEVICES = ("phone", "2in1")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--api-ledger", required=True, type=Path)
    parser.add_argument("--backend-audit", required=True, type=Path)
    parser.add_argument("--api-dir", required=True, type=Path)
    parser.add_argument("--kits-dir", required=True, type=Path)
    parser.add_argument("--static-sdk", required=True, type=Path)
    return parser.parse_args()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    args = arguments()
    matrix_rows = read(args.matrix)["capabilities"]
    expected_syscaps = {row["syscap"] for row in matrix_rows}
    expected_modules = {
        path.name.removesuffix(".d.ts")
        for pattern in ("@ohos*.d.ts", "@system*.d.ts")
        for path in args.api_dir.glob(pattern)
    }
    expected_modules.update(
        path.name.removesuffix(".d.ts")
        for path in args.kits_dir.glob("@kit*.d.ts")
    )
    expected_static_modules = {
        path.name.removesuffix(".d.ets")
        for directory in (args.static_sdk / "api", args.static_sdk / "kits")
        for path in directory.glob("@*.d.ets")
        if path.name.startswith(("@ohos.", "@system.", "@kit."))
    }
    require(len(matrix_rows) == len(expected_syscaps), "matrix has duplicate SysCaps", failures := [])

    ledger = read(args.ledger)
    ledger_rows = ledger["capabilities"]
    ledger_syscaps = {row["syscap"] for row in ledger_rows}
    require(ledger_syscaps == expected_syscaps, "ledger SysCap set differs from matrix", failures)
    require(len(ledger_rows) == len(ledger_syscaps), "ledger has duplicate SysCaps", failures)
    unresolved_capability_states = {
        "behavior_validation_pending",
        "surface_failure_unclassified",
        "permission_registry_gap",
    }
    for device in DEVICES:
        unresolved = [
            row["syscap"] for row in ledger_rows
            if row["devices"][device]["contract_expected"] and
            row["devices"][device]["coverage_state"] in unresolved_capability_states
        ]
        require(
            not unresolved,
            f"{device}: contract capabilities remain unclassified: {', '.join(unresolved)}",
            failures,
        )

    api_inventory = read(args.matrix.parent / "public-api-inventory.json")["entries"]
    api_ledger = read(args.api_ledger)
    api_rows = api_ledger["entries"]
    api_ids = [row["api_entry_id"] for row in api_rows]
    require(
        len(api_rows) == len(api_inventory),
        "API usability ledger does not cover every documented API entry",
        failures,
    )
    require(len(api_ids) == len(set(api_ids)), "API usability ledger has duplicate IDs", failures)
    require(
        all(set(row.get("devices", {})) == set(DEVICES) for row in api_rows),
        "API usability ledger has entries without both device outcomes",
        failures,
    )
    require(
        all(row["devices"][device].get("usability_status") for row in api_rows for device in DEVICES),
        "API usability ledger has an unclassified device outcome",
        failures,
    )

    backend_audit = read(args.backend_audit)
    backend_ids: dict[str, set[str]] = {}
    for device in DEVICES:
        backend_rows = backend_audit.get("devices", {}).get(device, {}).get("backends", [])
        backend_ids[device] = {row["id"] for row in backend_rows}
        require(
            len(backend_rows) == len(backend_ids[device]),
            f"{device}: runtime backend audit has duplicate IDs",
            failures,
        )
        require(
            all(row.get("evidence_required_count", 0) > 0 for row in backend_rows),
            f"{device}: runtime backend audit contains an evidence-free classification",
            failures,
        )
        require(
            all(row.get("evidence_complete") for row in backend_rows),
            f"{device}: runtime backend audit has unmatched required evidence",
            failures,
        )
    require(
        backend_ids.get("phone") == backend_ids.get("2in1") and bool(backend_ids.get("phone")),
        "runtime backend audit sets differ between phone and 2in1",
        failures,
    )

    provider_audit = read(args.matrix.parent / "system-bundle-provider-audit.json")
    provider_rows = provider_audit.get("provider_rules", [])
    provider_source_rows = provider_audit.get("source_bundle_references", [])
    provider_ids = [row.get("id") for row in provider_rows]
    require(provider_rows and len(provider_ids) == len(set(provider_ids)),
            "system bundle-provider audit is empty or has duplicate IDs", failures)
    require(
        provider_audit.get("summary", {}).get("provider_rule_count") == len(provider_rows),
        "system bundle-provider audit summary is incomplete",
        failures,
    )
    require(
        provider_audit.get("summary", {}).get("production_bundle_token_count", 0) > 0,
        "production source bundle-reference scan is empty",
        failures,
    )
    require(
        provider_audit.get("schema_version", 0) >= 2
        and provider_audit.get("summary", {}).get("production_bundle_token_unique_count")
        == len(provider_source_rows)
        and len({row.get("token") for row in provider_source_rows}) == len(provider_source_rows),
        "production source bundle-reference inventory drops or duplicates tokens",
        failures,
    )
    require(
        all(
            row.get("classification")
            and set(row.get("devices", {})) == set(DEVICES)
            and all(row["devices"][device] for device in DEVICES)
            for row in provider_source_rows
        ),
        "production source bundle-reference inventory has unclassified device state",
        failures,
    )
    require(
        {
            "permission-manager-dialogs",
            "accessibility-screen-reader",
            "accessibility-caption-assistant",
            "media-control-ui",
            "ability-share-picker",
        }.issubset(set(provider_ids)),
        "system bundle-provider audit omits critical framework-delegated UI flows",
        failures,
    )
    require(
        all(
            set(row.get("devices", {})) == set(DEVICES)
            and all(row["devices"][device].get("status") for device in DEVICES)
            for row in provider_rows
        ),
        "system bundle-provider rules do not classify both devices",
        failures,
    )

    result: dict[str, object] = {
        "public_syscap_count": len(expected_syscaps),
        "public_module_count": len(expected_modules),
        "ledger_capability_count": len(ledger_rows),
        "devices": {},
    }
    for device in DEVICES:
        root = args.runtime_root / f"arm64-{device}"
        syscap_report = read(root / "syscap-runtime.json")
        syscap_rows = syscap_report["capabilities"]
        probed_syscaps = {row["syscap"] for row in syscap_rows}
        require(len(syscap_rows) == len(probed_syscaps), f"{device}: duplicate SysCap probes", failures)
        require(
            probed_syscaps == expected_syscaps,
            f"{device}: SysCap probe set differs from the public registry",
            failures,
        )
        require(
            syscap_report["summary"]["probed_count"] == len(expected_syscaps),
            f"{device}: summary probed_count is incomplete",
            failures,
        )

        arkts_path = root / "arkts-module-load-latest.json"
        arkts = read(arkts_path)
        modules = [row["module"] for row in arkts["modules"]]
        require(len(modules) == len(set(modules)), f"{device}: duplicate ArkTS modules", failures)
        require(
            set(modules) == expected_modules,
            f"{device}: module probe set differs from api/@ohos+@system and kits/@kit",
            failures,
        )
        require(
            arkts["summary"]["module_count"] == len(modules),
            f"{device}: ArkTS module summary does not match its rows",
            failures,
        )
        require(
            arkts["summary"]["loaded"] + arkts["summary"]["load_failed"] == len(modules),
            f"{device}: ArkTS load outcomes do not cover every module",
            failures,
        )
        loaded_rows = [row for row in arkts["modules"] if row["loaded"]]
        require(
            all(row.get("export_probe_status") == 0 for row in loaded_rows),
            f"{device}: loaded ArkTS modules are missing export-surface probes",
            failures,
        )
        require(
            arkts["summary"]["loaded_with_export_probe"] == len(loaded_rows),
            f"{device}: ArkTS export-probe summary is incomplete",
            failures,
        )

        export_surface = read(root / "arkts-export-surface-latest.json")
        export_rows = export_surface["modules"]
        export_by_module = {row["module"]: row for row in export_rows}
        require(
            len(export_rows) == len(export_by_module) and set(export_by_module) == set(modules),
            f"{device}: ArkTS export-surface set differs from the module probe",
            failures,
        )
        for row in arkts["modules"]:
            surface_row = export_by_module.get(row["module"], {})
            require(
                surface_row.get("loaded") == row["loaded"] and
                surface_row.get("actual_runtime_exports") == sorted(row.get("exports", [])),
                f"{device}: stale ArkTS export surface for {row['module']}",
                failures,
            )
        require(
            export_surface["summary"]["module_count"] == len(export_rows),
            f"{device}: ArkTS export-surface summary is incomplete",
            failures,
        )

        static_surface = read(root / "arkts-static-surface.json")
        static_modules = {row["module"] for row in static_surface["modules"]}
        require(
            static_modules == expected_static_modules,
            f"{device}: static ArkTS module set differs from generated OHOS 7 SDK",
            failures,
        )
        require(
            static_surface["summary"]["ani_shared_library_count"] > 0 and
            static_surface["summary"]["framework_abc_count"] > 0,
            f"{device}: static ArkTS ANI/ABC runtime inventory is empty",
            failures,
        )

        c_abi = read(root / "c-api-abi-latest.json")
        require(
            c_abi.get("contract_source") == "interface_sdk_c_ndk_manifests",
            f"{device}: C ABI report does not use latest interface_sdk_c manifests",
            failures,
        )
        require(
            c_abi["summary"].get("header_backed_manifest_function_count", 0) > 0,
            f"{device}: latest C ABI callable inventory is empty",
            failures,
        )

        sa_profiles = read(root / "system-ability-profile-audit.json")
        require(
            sa_profiles["summary"]["packaged_profile_count"] == len(sa_profiles["abilities"]),
            f"{device}: System Ability profile audit is incomplete",
            failures,
        )

        permission_audit = read(root / "permission-audit.json")
        require(
            permission_audit["summary"]["api_permission_count"] == len(permission_audit["permissions"]),
            f"{device}: permission registry audit is incomplete",
            failures,
        )

        config_bundle_audit = read(root / "config-bundle-reference-audit.json")
        require(
            config_bundle_audit["summary"]["referenced_bundle_count"] ==
            len(config_bundle_audit["references"]),
            f"{device}: config bundle-reference audit is incomplete",
            failures,
        )

        preinstall_audit = read(root / "preinstalled-hap-audit.json")
        hap_rows = preinstall_audit.get("haps", [])
        preinstall_rows = preinstall_audit.get("preinstall_entries", [])
        require(
            preinstall_audit.get("schema_version", 0) >= 2
            and preinstall_audit["summary"]["hap_count"] == len(hap_rows)
            and preinstall_audit["summary"]["preinstall_entry_count"] == len(preinstall_rows),
            f"{device}: preinstalled HAP activation audit is incomplete",
            failures,
        )
        require(
            all(
                "listed_for_preinstall" in row
                and "abilities" in row
                and "extensions" in row
                and "configured_in_capability_list" in row
                for row in hap_rows
            ),
            f"{device}: preinstalled HAP audit omits bundle entrypoints or activation state",
            failures,
        )
        require(
            preinstall_audit["summary"]["unlisted_hap_count"] ==
            len(preinstall_audit.get("unlisted_haps", [])),
            f"{device}: unlisted preinstalled HAP count is stale",
            failures,
        )

        result["devices"][device] = {
            "syscaps_probed": len(probed_syscaps),
            "can_i_use_enabled": syscap_report["summary"]["enabled_count"],
            "arkts_modules_probed": len(modules),
            "arkts_modules_loaded": arkts["summary"]["loaded"],
            "arkts_loaded_with_empty_exports": arkts["summary"]["loaded_with_empty_exports"],
            "arkts_official_modules_with_missing_exports": export_surface["summary"][
                "official_export_surface_missing"
            ],
            "arkts_missing_official_public_functions": export_surface["summary"][
                "missing_official_public_function_count"
            ],
            "arkts_missing_official_system_functions": export_surface["summary"][
                "missing_official_system_function_count"
            ],
            "static_arkts_modules_inventoried": len(static_modules),
            "static_arkts_behavior_status": static_surface["summary"]["runtime_behavior_status"],
            "latest_c_abi_functions_inventoried": c_abi["summary"][
                "header_backed_manifest_function_count"
            ],
            "eager_system_abilities_not_registered": sa_profiles["summary"][
                "eager_not_registered_count"
            ],
            "official_callable_load_failures": arkts["summary"]["official_callable_load_failure"],
            "permissions_audited": permission_audit["summary"]["api_permission_count"],
            "missing_config_bundle_references": config_bundle_audit["summary"][
                "missing_referenced_bundle_count"
            ],
            "runtime_backends_audited": len(backend_ids[device]),
            "preinstalled_haps_audited": len(hap_rows),
            "unlisted_preinstalled_haps": preinstall_audit["summary"]["unlisted_hap_count"],
            "provider_rules_audited": len(provider_rows),
            "production_bundle_tokens_audited": len(provider_source_rows),
            "non_usable_contract_provider_rules": provider_audit["summary"][
                f"{device}_non_usable_provider_rule_count"
            ],
        }

    if failures:
        result["failures"] = failures
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    result["status"] = "complete_capability_classification_method_sampling_full_provider_inventory"
    result["documented_api_entries_classified"] = len(api_rows)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
