#!/usr/bin/env python3
"""Compare API permission requirements with a device permission registry."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import hashlib
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
    parser.add_argument("--source-definitions", type=Path, required=True,
                        help="pinned AccessToken permission_definitions.json; retains device restrictions")
    parser.add_argument("--profile", choices=("phone", "2in1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def source_support(definition: dict | None, profile: str) -> bool | None:
    if profile not in ("phone", "2in1"):
        raise ValueError(f"unsupported permission profile: {profile}")
    if definition is None:
        return None
    types = definition.get("deviceTypes", ["general"])
    if not isinstance(types, list) or not types or any(not isinstance(item, str) for item in types):
        raise ValueError("invalid source permission device types")
    return "general" in types or profile in types


def classify(row: dict, official_syscaps: list, definition: dict | None,
             source_definition: dict | None, profile: str) -> str:
    if definition is not None:
        return "registered"
    # A broad SysCap shared with phone does not make every PC-only property
    # available on phone (e.g. deviceInfo.diskSN). Do not add or globally enable
    # privileges based solely on a SysCap intersection. This is not an API pass.
    if source_support(source_definition, profile) is False:
        return "permission_disabled_by_device_policy_requires_api_boundary_validation"
    if official_syscaps and row["public_api"]:
        return "missing_official_public_permission"
    if official_syscaps:
        return "missing_official_system_permission"
    if row["public_api"]:
        return "missing_public_permission_outside_profile"
    return "missing_system_permission_outside_profile"


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
    source_rows = json.loads(args.source_definitions.read_text(encoding="utf-8"))["definePermissions"]
    source_definitions = {row["name"]: row for row in source_rows}
    if not source_definitions or len(source_definitions) != len(source_rows):
        raise ValueError("empty or duplicate source permission definitions")
    rows = []
    for permission, row in sorted(required.items()):
        syscaps = sorted(row["syscaps"])
        official_syscaps = sorted(set(syscaps) & official)
        definition = definitions.get(permission)
        source_definition = source_definitions.get(permission)
        status = classify(row, official_syscaps, definition, source_definition, args.profile)
        rows.append(
            {
                **{key: value for key, value in row.items() if key not in {"sources", "syscaps"}},
                "sources": sorted(row["sources"]),
                "syscaps": syscaps,
                "official_profile_syscaps": official_syscaps,
                "registered": definition is not None,
                "runtime_definition": definition,
                "source_definition": source_definition,
                "source_supports_profile": source_support(source_definition, args.profile),
                "api_behavior_validated": False,
                "status": status,
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    result = {
        "profile": args.profile,
        "source_definitions_sha256": hashlib.sha256(args.source_definitions.read_bytes()).hexdigest(),
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
