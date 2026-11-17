#!/usr/bin/env python3
"""Validate the compiled permission table, without granting any permission."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TARGET_PLATFORMS = {"phone": "phone", "2in1": "pc"}
INTERNAL_NAMES = {
    "ohos.permission.KERNEL_ATM_SELF_USE", "ohos.permission.MANUAL_ATM_SELF_USE",
}
VALUE_MAP = {
    "user_grant": "USER_GRANT", "system_grant": "SYSTEM_GRANT",
    "manual_settings": "MANUAL_SETTINGS", "normal": "APL_NORMAL",
    "system_basic": "APL_SYSTEM_BASIC", "system_core": "APL_SYSTEM_CORE",
}
BOOL_FIELDS = ("provisionEnable", "distributedSceneEnable", "isKernelEffect", "hasValue")
INTERNAL_POLICY = {
    "ohos.permission.KERNEL_ATM_SELF_USE": {
        "grantMode": "SYSTEM_GRANT", "availableLevel": "APL_SYSTEM_CORE", "availableType": "SYSTEM",
        "provisionEnable": "true", "distributedSceneEnable": "true", "isKernelEffect": "true",
        "hasValue": "true", "isEnable": "true",
    },
    "ohos.permission.MANUAL_ATM_SELF_USE": {
        "grantMode": "MANUAL_SETTINGS", "availableLevel": "APL_NORMAL", "availableType": "NORMAL",
        "provisionEnable": "true", "distributedSceneEnable": "false", "isKernelEffect": "false",
        "hasValue": "false", "isEnable": "true",
    },
}


def target_platform(device: str) -> str:
    try:
        return TARGET_PLATFORMS[device]
    except KeyError:
        raise ValueError(f"unsupported permission profile: {device}") from None


def compiled_permissions(header: str) -> dict[str, dict[str, str]]:
    names: dict[str, str] = {}
    for index, name in re.findall(
            r'const static char PERMISSION_NAME_(\d+)\[\] = "([^"\n]+)";', header):
        if index in names or name in names.values():
            raise ValueError("duplicate generated permission name")
        names[index] = name
    table = re.search(r"static PermissionBriefDef g_permList\[\] = \{(.*?)\n\};", header, re.S)
    if not names or table is None:
        raise ValueError("missing generated permission table")
    rows: dict[str, dict[str, str]] = {}
    for block in re.findall(r"\{([^{}]+)\},?", table.group(1)):
        pairs = re.findall(r"\.(\w+)\s*=\s*([A-Za-z0-9_]+)\s*,?", block)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate generated permission field")
        reference = fields.pop("permissionName", "")
        index = reference.removeprefix("PERMISSION_NAME_")
        if not reference.startswith("PERMISSION_NAME_") or index not in names:
            raise ValueError("unknown generated permission name reference")
        name = names[index]
        if name in rows:
            raise ValueError("duplicate generated permission row")
        rows[name] = fields
    if set(rows) != set(names.values()):
        raise ValueError("generated permission names and rows differ")
    return rows


def validate(definitions: dict, header: str, device: str) -> dict:
    platform = target_platform(device)
    rows = compiled_permissions(header)
    source_rows = definitions.get("definePermissions")
    if not isinstance(source_rows, list) or not source_rows:
        raise ValueError("missing source permission definitions")
    expected_names = set()
    enabled = []
    disabled = []
    for source in source_rows:
        name = source["name"]
        if name in expected_names or name in INTERNAL_NAMES:
            raise ValueError(f"duplicate/reserved source permission: {name}")
        expected_names.add(name)
        types = source.get("deviceTypes", ["general"])
        if not isinstance(types, list) or not types or any(not isinstance(t, str) for t in types):
            raise ValueError(f"invalid permission device types: {name}")
        allowed = "general" in types or device in types
        expected = {
            "grantMode": VALUE_MAP[source["grantMode"]],
            "availableLevel": VALUE_MAP[source["availableLevel"]],
            "availableType": source["availableType"],
            "isEnable": "true" if allowed else "false",
        }
        for field in BOOL_FIELDS:
            value = source.get(field, False)
            if not isinstance(value, bool):
                raise ValueError(f"non-boolean source permission field: {name}.{field}")
            expected[field] = "true" if value else "false"
        if rows.get(name) != expected:
            raise ValueError(f"compiled permission differs from {device} policy: {name}; "
                             f"expected {expected}, got {rows.get(name)}")
        (enabled if allowed else disabled).append(name)
    if set(rows) != expected_names | INTERNAL_NAMES:
        raise ValueError("compiled permission set differs from source plus two ATM internal permissions")
    for name, policy in INTERNAL_POLICY.items():
        if rows[name] != policy:
            raise ValueError(f"compiled ATM internal permission policy changed: {name}")
    return {
        "schema_version": 1, "device_type": device, "target_platform": platform,
        "scope": "generated permission table and privilege policy, not runtime API behavior",
        "source_permission_count": len(source_rows),
        "enabled_permissions": sorted(enabled), "disabled_permissions": sorted(disabled),
        "runtime_validated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product", choices=("arm64_virt", "armv7a_virt", "x86_64_virt"), required=True)
    parser.add_argument("--device", choices=tuple(TARGET_PLATFORMS), required=True)
    parser.add_argument("--compiled-table", type=Path,
                        help="explicit generated table for an isolated platform-generation check")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.source_root
    source = root / "base/security/access_token/services/accesstokenmanager/permission_definitions.json"
    header = args.compiled_table or (root / "out" / args.product /
                                     "obj/base/security/access_token/frameworks/common/permission_map_constant.h")
    result = validate(json.loads(source.read_text()), header.read_text(), args.device)
    result.update(source_definitions_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  compiled_table_sha256=hashlib.sha256(header.read_bytes()).hexdigest())
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"QEMU {args.device}/{result['target_platform']} compiled permission policy validated: "
          f"{len(result['enabled_permissions'])} enabled, {len(result['disabled_permissions'])} disabled")


if __name__ == "__main__":
    main()
