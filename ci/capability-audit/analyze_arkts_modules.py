#!/usr/bin/env python3
"""Classify runtime load and export-surface results for every public ArkTS module."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


SYSCAP_RE = re.compile(r"@syscap\s+(SystemCapability\.[A-Za-z0-9_.]+)")
LOAD_RE = re.compile(
    r"^module\.load=(.*?)\|status:(\d+)\|exception:(\d+)\|type:(\d+)$"
)
EXPORTS_RE = re.compile(r"^module\.exports=(.*?)\|status:(\d+)\|count:(\d+)$")
COLLECTION_RE = re.compile(r"^module\.export\.collection=(.*?)\|(all_own_string_properties)$")
EXPORT_RE = re.compile(
    r"^module\.export=(.*?)\|index:(\d+)\|key:(.*?)(?:\|type:(\d+)\|status:(\d+))?$"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--api-dir", type=Path)
    parser.add_argument("--kits-dir", type=Path)
    parser.add_argument("--profile", choices=("phone", "2in1"), required=True)
    parser.add_argument("--probe-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def has_runtime_callable(source: str) -> bool:
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    # Methods/getters inside ``declare class`` files describe objects injected
    # by an Ability runtime; they do not prove that the d.ts filename is a
    # standalone NAPI module.  Count only namespace/top-level functions here.
    return bool(re.search(r"\bfunction\s+[A-Za-z_$]", code))


def main() -> int:
    args = arguments()
    api = (args.api_dir or (args.sdk / "ets/api")).resolve()
    kits = (args.kits_dir or (api.parent / "kits")).resolve()
    profile_name = "default.json" if args.profile == "phone" else "2in1.json"
    official = set(
        json.loads((api / "device-define" / profile_name).read_text(encoding="utf-8"))["SysCaps"]
    )
    loads = {}
    export_summaries = {}
    collections = {}
    exports: dict[str, list[tuple[int, str, int | None, int | None]]] = {}
    for line in args.probe_log.read_text(encoding="utf-8").splitlines():
        match = COLLECTION_RE.match(line)
        if match:
            collections[match.group(1)] = match.group(2)
            continue
        match = LOAD_RE.match(line)
        if match:
            loads[match.group(1)] = {
                "load_status": int(match.group(2)),
                "exception_pending": bool(int(match.group(3))),
                "value_type": int(match.group(4)),
            }
            continue
        match = EXPORTS_RE.match(line)
        if match:
            export_summaries[match.group(1)] = {
                "export_probe_status": int(match.group(2)),
                "export_count": int(match.group(3)),
            }
            continue
        match = EXPORT_RE.match(line)
        if match:
            exports.setdefault(match.group(1), []).append(
                (
                    int(match.group(2)),
                    match.group(3),
                    int(match.group(4)) if match.group(4) is not None else None,
                    int(match.group(5)) if match.group(5) is not None else None,
                )
            )

    rows = []
    for module in sorted(loads):
        source_path = (kits if module.startswith("@kit.") else api) / f"{module}.d.ts"
        if not source_path.is_file():
            raise FileNotFoundError(f"probe reported an unknown public module: {module}")
        source = source_path.read_text(encoding="utf-8", errors="ignore")
        syscaps = sorted(set(SYSCAP_RE.findall(source)))
        official_syscaps = sorted(set(syscaps) & official)
        callable_module = has_runtime_callable(source)
        loaded = loads[module]["load_status"] == 0
        export_summary = export_summaries.get(module, {})
        export_values = [
            {"name": name, "value_type": value_type, "read_status": read_status}
            for _, name, value_type, read_status in sorted(exports.get(module, []))
        ]
        # napi_undefined is 0. Old logs have no value type and remain usable as
        # name-only evidence; new logs exclude properties whose value is
        # actually undefined or unreadable.
        export_names = [
            value["name"] for value in export_values
            if value["value_type"] is None or
            (value["read_status"] == 0 and value["value_type"] != 0)
        ]
        undefined_exports = [
            value["name"] for value in export_values
            if value["value_type"] == 0
        ]
        if loaded:
            audit_status = "loaded"
        elif not callable_module:
            audit_status = "compile_time_declaration"
        elif official_syscaps:
            audit_status = "official_callable_load_failure"
        else:
            audit_status = "callable_load_failure_outside_profile"
        rows.append(
            {
                "module": module,
                "source": str(source_path.relative_to(api.parent)),
                "has_runtime_callable": callable_module,
                "syscaps": syscaps,
                "official_profile_syscaps": official_syscaps,
                "loaded": loaded,
                "export_probe_status": export_summary.get("export_probe_status"),
                "export_collection": collections.get(module, "unknown_legacy_probe"),
                "export_count": export_summary.get("export_count"),
                "exports": export_names,
                "export_values": export_values,
                "undefined_exports": undefined_exports,
                **loads[module],
                "audit_status": audit_status,
            }
        )

    summary = {
        "module_count": len(rows),
        "loaded": sum(row["loaded"] for row in rows),
        "load_failed": sum(not row["loaded"] for row in rows),
        "loaded_with_export_probe": sum(
            row["loaded"] and row["export_probe_status"] == 0 for row in rows
        ),
        "loaded_with_empty_exports": sum(
            row["loaded"] and row["export_probe_status"] == 0 and row["export_count"] == 0
            for row in rows
        ),
        "compile_time_declaration": sum(
            row["audit_status"] == "compile_time_declaration" for row in rows
        ),
        "official_callable_load_failure": sum(
            row["audit_status"] == "official_callable_load_failure" for row in rows
        ),
        "callable_load_failure_outside_profile": sum(
            row["audit_status"] == "callable_load_failure_outside_profile" for row in rows
        ),
    }
    result = {"profile": args.profile, "summary": summary, "modules": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.output.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        fields = [
            "module",
            "has_runtime_callable",
            "loaded",
            "load_status",
            "exception_pending",
            "value_type",
            "export_probe_status",
            "export_collection",
            "export_count",
            "exports",
            "audit_status",
            "syscaps",
            "official_profile_syscaps",
            "source",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row.pop("export_values")
            csv_row.pop("undefined_exports")
            csv_row["exports"] = ";".join(row["exports"])
            csv_row["syscaps"] = ";".join(row["syscaps"])
            csv_row["official_profile_syscaps"] = ";".join(row["official_profile_syscaps"])
            writer.writerow(csv_row)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
