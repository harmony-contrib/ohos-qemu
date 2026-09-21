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
    parser.add_argument("--api-dir", required=True, type=Path)
    parser.add_argument("--kits-dir", required=True, type=Path)
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
    require(len(matrix_rows) == len(expected_syscaps), "matrix has duplicate SysCaps", failures := [])

    ledger = read(args.ledger)
    ledger_rows = ledger["capabilities"]
    ledger_syscaps = {row["syscap"] for row in ledger_rows}
    require(ledger_syscaps == expected_syscaps, "ledger SysCap set differs from matrix", failures)
    require(len(ledger_rows) == len(ledger_syscaps), "ledger has duplicate SysCaps", failures)

    result: dict[str, object] = {
        "public_syscap_count": len(expected_syscaps),
        "public_module_count": len(expected_modules),
        "ledger_capability_count": len(ledger_rows),
        "devices": {},
    }
    for device in DEVICES:
        root = args.runtime_root / f"arm64-{device}"
        probe_log = (root / "hap-probe/results-ohos7-latest.log").read_text(encoding="utf-8")
        static_exports = {}
        for line in probe_log.splitlines():
            if line.startswith("arkts.static_export.") and "=" in line:
                name, value = line.split("=", 1)
                static_exports[name] = value
        require(
            len(static_exports) == 10,
            f"{device}: direct ArkTS export probes are incomplete",
            failures,
        )
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
            "direct_arkts_exports_probed": len(static_exports),
            "direct_arkts_exports_undefined": sum(
                value == "undefined" for value in static_exports.values()
            ),
            "official_callable_load_failures": arkts["summary"]["official_callable_load_failure"],
        }

    if failures:
        result["failures"] = failures
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    result["status"] = "complete_inventory"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
