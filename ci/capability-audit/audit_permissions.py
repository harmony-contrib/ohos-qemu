#!/usr/bin/env python3
"""Compare API permission requirements with a device permission registry."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path


COMMENT_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)
PERMISSION_RE = re.compile(r"ohos\.permission\.[A-Za-z0-9_.]*[A-Za-z0-9_]")
SYSCAP_RE = re.compile(r"SystemCapability\.[A-Za-z0-9_.]+")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-dir", type=Path, required=True)
    parser.add_argument("--kits-dir", type=Path, required=True)
    parser.add_argument("--sdk-c-root", type=Path, required=True)
    parser.add_argument("--runtime-definitions", type=Path, required=True)
    parser.add_argument("--profile", choices=("phone", "2in1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def scan_file(path: Path, source_root: Path, output: dict[str, dict]) -> None:
    source = path.read_text(encoding="utf-8", errors="ignore")
    for comment in COMMENT_RE.findall(source):
        if "@permission" not in comment:
            continue
        permissions = set(PERMISSION_RE.findall(comment))
        if not permissions:
            continue
        syscaps = set(SYSCAP_RE.findall(comment))
        system_api = "@systemapi" in comment
        for permission in permissions:
            row = output.setdefault(
                permission,
                {
                    "permission": permission,
                    "sources": set(),
                    "syscaps": set(),
                    "public_api": False,
                    "system_api": False,
                },
            )
            row["sources"].add(str(path.relative_to(source_root)))
            row["syscaps"].update(syscaps)
            row["system_api"] = row["system_api"] or system_api
            row["public_api"] = row["public_api"] or not system_api


def main() -> int:
    args = arguments()
    profile_file = "default.json" if args.profile == "phone" else "2in1.json"
    official = set(
        json.loads(
            (args.api_dir / "device-define" / profile_file).read_text(encoding="utf-8")
        )["SysCaps"]
    )
    required: dict[str, dict] = {}
    source_root = args.api_dir.parent
    for root in (args.api_dir, args.kits_dir):
        for path in root.rglob("*"):
            if path.is_file() and (
                path.name.endswith(".d.ts") or path.name.endswith(".d.ets")
            ):
                scan_file(path, source_root, required)
    for path in args.sdk_c_root.rglob("*.h"):
        scan_file(path, args.sdk_c_root, required)

    definitions = {
        row["permissionName"]: row
        for row in json.loads(args.runtime_definitions.read_text(encoding="utf-8"))
    }
    rows = []
    for permission, row in sorted(required.items()):
        syscaps = sorted(row["syscaps"])
        official_syscaps = sorted(set(syscaps) & official)
        definition = definitions.get(permission)
        if definition is not None:
            status = "registered"
        elif official_syscaps and row["public_api"]:
            status = "missing_official_public_permission"
        elif official_syscaps:
            status = "missing_official_system_permission"
        elif row["public_api"]:
            status = "missing_public_permission_outside_profile"
        else:
            status = "missing_system_permission_outside_profile"
        rows.append(
            {
                **{key: value for key, value in row.items() if key not in {"sources", "syscaps"}},
                "sources": sorted(row["sources"]),
                "syscaps": syscaps,
                "official_profile_syscaps": official_syscaps,
                "registered": definition is not None,
                "runtime_definition": definition,
                "status": status,
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    result = {
        "profile": args.profile,
        "summary": {
            "api_permission_count": len(rows),
            "runtime_definition_count": len(definitions),
            "registered_api_permission_count": sum(row["registered"] for row in rows),
            "missing_api_permission_count": sum(not row["registered"] for row in rows),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "permissions": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
