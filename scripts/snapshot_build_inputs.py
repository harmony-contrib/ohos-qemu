#!/usr/bin/env python3
"""Freeze build and runtime-validation recipes, including uncommitted edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

INPUT_DIRECTORIES = ("scripts", "patches", "ci/capability-audit", "ci/qemu-smoke")
INPUT_FILES = (
    'docs/capability-audit/parallel/apps/round375-provider-research/result.json',
    'docs/capability-audit/parallel/apps/round375-provider-research/REPORT.md',
    'docs/capability-audit/parallel/apps/round375-provider-research/source-pins.json',
    'docs/capability-audit/execution-20261019/unsupported-public-providers.json',
    'docs/capability-audit/parallel/network/round375-provider-research/result.json',
    'docs/capability-audit/parallel/media/round375/OFFICIAL-IMPLEMENTATION-BOUNDARY.md',
    "docs/capability-audit/native-arkts11-gap-ledger.json",
    # Runtime and diagnostic helpers read these fixed-source contracts. Freeze
    # their exact bytes with the scripts that consume them.
    "docs/capability-audit/parallel/network/audio-observation-20261016.json",
    "docs/capability-audit/parallel/location/round7-communication-build-map.json",
    "docs/capability-audit/parallel/location/round8-registry-api-link-map.json",
)


def digest_files(root: Path) -> dict[str, str]:
    files = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in INPUT_DIRECTORIES
        for path in sorted((root / directory).rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
    }
    files.update({name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                  for name in INPUT_FILES if (root / name).is_file()})
    return dict(sorted(files.items()))


def snapshot(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("build input snapshot must be outside the source repository")
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("snapshot destination must be an existing empty directory")
    before = digest_files(source)
    for directory in INPUT_DIRECTORIES:
        if (source / directory).is_dir():
            shutil.copytree(source / directory, destination / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    for name in INPUT_FILES:
        if (source / name).is_file():
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, destination / name)
    copied = digest_files(destination)
    if before != copied or copied != digest_files(source):
        raise ValueError("build/validation scripts or patches changed while snapshotting; retry")
    git = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=False)
    document = {
        "schema_version": 1,
        "source_git_revision": git.stdout.strip() if git.returncode == 0 else None,
        "note": "Exact file hashes include uncommitted edits; the git revision alone is not the build input identity.",
        "tree_sha256": hashlib.sha256(json.dumps(copied, sort_keys=True).encode()).hexdigest(),
        "files_sha256": copied,
    }
    (destination / "build-inputs.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = snapshot(args.source, args.destination)
    print(f"frozen build inputs: {args.destination} sha256={result['tree_sha256']}")
