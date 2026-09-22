#!/usr/bin/env python3
"""Compare packaged System Ability profiles with the registered runtime set."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument("--profile-dir", required=True, type=Path)
    parser.add_argument("--system-ability-list", required=True, type=Path)
    parser.add_argument("--definition-header", required=True, type=Path)
    parser.add_argument("--dump-utils", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def definition_index(path: Path) -> tuple[dict[str, int], dict[int, str]]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    names = {
        name: int(value, 0)
        for name, value in re.findall(
            r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*,",
            source,
            re.MULTILINE,
        )
    }
    # Prefer semantic constants over SUBSYS_* range markers for duplicate IDs.
    by_id: dict[int, str] = {}
    for name, value in names.items():
        previous = by_id.get(value)
        if previous is None or (previous.startswith("SUBSYS_") and not name.startswith("SUBSYS_")):
            by_id[value] = name
    return names, by_id


def display_name_index(path: Path, constants: dict[str, int]) -> dict[str, int]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    result: dict[str, int] = {}
    for key, display in re.findall(
        r'\{\s*([A-Z][A-Z0-9_]*|\d+)\s*,\s*"([^"]+)"\s*\}', source
    ):
        value = int(key) if key.isdigit() else constants.get(key)
        if value is not None:
            result[display] = value
    return result


def packaged_profiles(root: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get("systemability", []):
            if not isinstance(item, dict) or not isinstance(item.get("name"), int):
                continue
            rows[item["name"]] = {
                **item,
                "profile": path.name,
                "process": data.get("process"),
            }
    return rows


def registered_ids(path: Path, aliases: dict[str, int]) -> tuple[set[int], list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    marker = "System ability list:"
    body = text.partition(marker)[2] if marker in text else text
    tokens = re.findall(r"[A-Za-z0-9_.-]+", body)
    ids: set[int] = set()
    unknown: list[str] = []
    for token in tokens:
        if token.isdigit():
            ids.add(int(token))
        elif token in aliases:
            ids.add(aliases[token])
        else:
            unknown.append(token)
    return ids, sorted(set(unknown)), tokens


def main() -> int:
    args = arguments()
    constants, constants_by_id = definition_index(args.definition_header)
    aliases = display_name_index(args.dump_utils, constants)
    aliases_by_id = {value: name for name, value in aliases.items()}
    expected = packaged_profiles(args.profile_dir)
    registered, unknown_names, raw_names = registered_ids(args.system_ability_list, aliases)

    rows = []
    for sa_id, profile in sorted(expected.items()):
        eager = profile.get("run-on-create") is True
        rows.append(
            {
                "sa_id": sa_id,
                "constant": constants_by_id.get(sa_id),
                "display_name": aliases_by_id.get(sa_id),
                "profile": profile["profile"],
                "process": profile.get("process"),
                "library": profile.get("libpath"),
                "run_on_create": eager,
                "start_on_demand": profile.get("start-on-demand") is True,
                "registered": sa_id in registered,
                "status": (
                    "registered"
                    if sa_id in registered
                    else ("eager_not_registered" if eager else "inactive_on_demand")
                ),
            }
        )

    eager = [row for row in rows if row["run_on_create"]]
    result = {
        "device": args.device,
        "profile_dir": str(args.profile_dir.resolve()),
        "system_ability_list": str(args.system_ability_list.resolve()),
        "summary": {
            "packaged_profile_count": len(rows),
            "eager_profile_count": len(eager),
            "registered_id_count": len(registered),
            "eager_not_registered_count": sum(not row["registered"] for row in eager),
            "inactive_on_demand_count": sum(
                row["status"] == "inactive_on_demand" for row in rows
            ),
            "unknown_registered_display_name_count": len(unknown_names),
        },
        "unknown_registered_display_names": unknown_names,
        "raw_registered_names": raw_names,
        "abilities": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    for row in rows:
        if row["status"] == "eager_not_registered":
            print(
                f"missing eager SA {row['sa_id']} "
                f"({row['constant'] or row['display_name'] or 'unknown'}): "
                f"{row['profile']} -> {row['library']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
