#!/usr/bin/env python3
"""Inventory the OHOS 7 static ArkTS surface and packaged ANI/ABC runtime."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SYSCAP_RE = re.compile(r"@syscap\s+(SystemCapability\.[A-Za-z0-9_.]+)")
FUNCTION_RE = re.compile(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument("--static-sdk", required=True, type=Path)
    parser.add_argument("--dynamic-sdk", required=True, type=Path)
    parser.add_argument("--installed-ets", required=True, type=Path)
    parser.add_argument("--ani-list", required=True, type=Path)
    parser.add_argument("--framework-list", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def profile_caps(root: Path, device: str) -> set[str]:
    name = "default" if device == "phone" else "2in1"
    path = root / "api/device-define" / f"{name}.json"
    return set(json.loads(path.read_text(encoding="utf-8")).get("SysCaps", []))


def debugfs_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        fields = line.split("/")
        if len(fields) > 6 and fields[2].startswith("100"):
            names.append(fields[5])
    return sorted(set(names))


def module_name(path: Path) -> str | None:
    name = path.name.removesuffix(".d.ets")
    if name.startswith(("@ohos.", "@system.", "@kit.")):
        return name
    return None


def main() -> int:
    args = arguments()
    static_root = args.static_sdk.resolve()
    caps = profile_caps(args.dynamic_sdk.resolve(), args.device)
    rows: list[dict[str, Any]] = []
    all_files = sorted(
        path
        for directory in ("api", "kits", "arkts")
        for path in (static_root / directory).rglob("*.d.ets")
    )
    for path in all_files:
        module = module_name(path)
        if module is None:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        syscaps = sorted(set(SYSCAP_RE.findall(source)))
        official = sorted(set(syscaps) & caps)
        rows.append(
            {
                "module": module,
                "source": str(path.relative_to(static_root)),
                "use_static_directive": source.lstrip().startswith("'use static'"),
                "declared_function_count": len(FUNCTION_RE.findall(source)),
                "syscaps": syscaps,
                "official_profile_syscaps": official,
                "official_profile": bool(official),
            }
        )

    ani_files = debugfs_names(args.ani_list)
    framework_files = debugfs_names(args.framework_list)
    abc_files = [name for name in framework_files if name.endswith(".abc")]
    installed_static = [
        path
        for path in args.installed_ets.resolve().rglob("*.d.ets")
        if path.read_text(encoding="utf-8", errors="ignore").lstrip().startswith("'use static'")
    ]
    result = {
        "device": args.device,
        "static_sdk": str(static_root),
        "summary": {
            "processed_static_declaration_file_count": len(all_files),
            "static_module_entry_count": len(rows),
            "official_profile_static_module_entry_count": sum(
                row["official_profile"] for row in rows
            ),
            "declared_static_function_count": sum(
                row["declared_function_count"] for row in rows
            ),
            "ani_shared_library_count": len(
                [name for name in ani_files if name.endswith(".so")]
            ),
            "framework_abc_count": len(abc_files),
            "installed_deveco_use_static_declaration_count": len(installed_static),
            "runtime_behavior_status": "static_hap_probe_required",
        },
        "runtime": {
            "ani_shared_libraries": ani_files,
            "framework_abc_files": abc_files,
        },
        "modules": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
