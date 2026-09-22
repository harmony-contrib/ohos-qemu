#!/usr/bin/env python3
"""Compare bundle names referenced by packaged JSON configuration with BM state."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BUNDLE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")
CONFIG_SUFFIXES = {".json", ".cfg", ".conf"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", required=True, type=Path)
    parser.add_argument("--bundle-dump", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def installed_bundles(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if BUNDLE_RE.fullmatch(line.strip())
    }


def bundle_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return "bundle" in normalized and (
        "name" in normalized or normalized in {"bundle", "bundles"}
    )


def collect(value: Any, path: str, source: str, rows: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if bundle_key(key):
                candidates = child if isinstance(child, list) else [child]
                for candidate in candidates:
                    if isinstance(candidate, str) and BUNDLE_RE.fullmatch(candidate):
                        rows.append({
                            "bundle": candidate,
                            "source": source,
                            "json_path": child_path,
                        })
            collect(child, child_path, source, rows)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            collect(child, f"{path}[{index}]", source, rows)


def main() -> int:
    args = arguments()
    installed = installed_bundles(args.bundle_dump)
    rows: list[dict[str, str]] = []
    parsed_files = 0
    invalid_files: list[str] = []
    for path in sorted(args.config_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in CONFIG_SUFFIXES:
            continue
        source = str(path.relative_to(args.config_root))
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            invalid_files.append(source)
            continue
        parsed_files += 1
        collect(value, "", source, rows)

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["bundle"], []).append({
            "source": row["source"],
            "json_path": row["json_path"],
        })
    references = [
        {
            "bundle": bundle,
            "installed": bundle in installed,
            "locations": sorted(
                grouped[bundle], key=lambda item: (item["source"], item["json_path"])
            ),
        }
        for bundle in sorted(grouped)
    ]
    missing = [row for row in references if not row["installed"]]
    result = {
        "summary": {
            "config_file_count": sum(1 for path in args.config_root.rglob("*") if path.is_file()),
            "json_config_parsed_count": parsed_files,
            "json_config_skipped_count": len(invalid_files),
            "installed_bundle_count": len(installed),
            "referenced_bundle_count": len(references),
            "missing_referenced_bundle_count": len(missing),
        },
        "missing_references": missing,
        "references": references,
        "skipped_non_json_files": invalid_files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
