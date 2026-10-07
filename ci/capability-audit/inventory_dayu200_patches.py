#!/usr/bin/env python3
"""Inventory current QEMU patch inputs with reviewed DAYU200 cause annotations.

Read-only: classifications come from an existing audit JSON. New or removed
leaf components require review instead of silently inheriting a guessed cause.
Print to stdout; use a separate output path to preserve the annotation input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--annotations", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    patch_root = root / "patches"
    annotations = json.loads(args.annotations.read_text())
    reviewed = {row["component"]: row for row in annotations["components"]}
    entries = sorted(patch_root.rglob("apply.sh"))
    leaves = [entry.parent for entry in entries
              if not any(other != entry and other.is_relative_to(entry.parent)
                         for other in entries)]
    current = {str(directory.relative_to(patch_root)) for directory in leaves}
    if current != reviewed.keys():
        raise ValueError(f"Review new/removed components first: "
                         f"new={sorted(current - reviewed.keys())}, "
                         f"removed={sorted(reviewed.keys() - current)}")
    rows = []
    for directory in leaves:
        component = str(directory.relative_to(patch_root))
        patches = []
        for path in sorted(directory.rglob("*.patch")):
            content = path.read_text()
            targets = set(re.findall(r"^diff --git a/(.+?) b/", content, re.M))
            targets.update(re.findall(r"^--- a/(.+)$", content, re.M))
            patches.append({"path": str(path.relative_to(root)), "sha256": digest(path),
                            "numbered_source_patch": bool(re.match(r"^\d+", path.name)),
                            "targets": sorted(targets)})
        rows.append({"component": component,
                     **{field: reviewed[component][field]
                        for field in ("category", "dayu_relation", "reason")},
                     "numbered_patch_count": sum(p["numbered_source_patch"] for p in patches),
                     "patches": patches})
    all_patches = {str(path.relative_to(root)) for path in patch_root.rglob("*.patch")}
    recorded = {patch["path"] for row in rows for patch in row["patches"]}
    if all_patches != recorded:
        raise ValueError(f"Unowned patch files: {sorted(all_patches - recorded)}")
    non_patch_files = {str(path.relative_to(root)): digest(path)
                       for path in sorted(patch_root.rglob("*"))
                       if path.is_file() and path.suffix not in (".patch", ".pyc")
                       and "__pycache__" not in path.parts and path.name != ".DS_Store"}
    output = {"scope": annotations["scope"],
              "collected_at_utc": datetime.now(timezone.utc).isoformat(),
              "leaf_component_count": len(rows),
              "numbered_patch_count": sum(row["numbered_patch_count"] for row in rows),
              "all_patch_count": len(all_patches), "components": rows,
              "non_patch_file_sha256": non_patch_files,
              "notes": annotations["notes"]}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
