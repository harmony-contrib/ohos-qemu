#!/usr/bin/env python3
"""Prepare the real release PGO input before generating or compiling targets.

The SDK/toolchains come from the verified private API-26 SDK and the locked
toolchain projects, not the obsolete SDK archives in Chromium's ohos_sdk/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from prepare_m144_release_cache import git, load_lock

PGO_PATH = "build/pgo/ohos/arkweb.profdata"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pointer_record(content: str) -> dict:
    match = re.fullmatch(r"version https://git-lfs.github.com/spec/v1\n"
                         r"oid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n", content)
    if not match or int(match[2]) <= 0:
        raise ValueError("invalid locked PGO LFS pointer")
    return {"sha256": match[1], "size": int(match[2]), "pointer": content}


def cached_object(repository: Path, record: dict) -> Path:
    oid = record["sha256"]
    path = repository / "lfs/objects" / oid[:2] / oid[2:4] / oid
    if path.is_symlink() or not path.is_file():
        raise ValueError("required release PGO LFS object is not cached")
    if path.stat().st_size != record["size"] or sha256(path) != oid:
        raise ValueError("cached release PGO object size/checksum differs")
    return path


def prepare_cache(cache: Path, data: dict, fetch: bool) -> dict:
    project = next(p for p in data["projects"] if p["name"] == "chromium_src")
    repository = cache / "chromium_src.git"
    result = git(repository, "show", project["revision"] + ":" + PGO_PATH)
    if result.returncode:
        raise ValueError("locked PGO pointer is missing from exact source commit")
    record = pointer_record(result.stdout)
    attempts = []
    try:
        path = cached_object(repository, record)
    except ValueError:
        if not fetch:
            raise
        for key in ("mirror_url", "upstream_url"):
            try:
                result = git(repository, "-c", "lfs.fetchrecentalways=false", "lfs", "fetch",
                             "--include=" + PGO_PATH, "--exclude=", project[key],
                             project["revision"], timeout=1800)
            except subprocess.TimeoutExpired:
                attempts.append({"remote": project[key], "exit_code": "timeout"})
                continue
            attempts.append({"remote": project[key], "exit_code": result.returncode,
                             "stderr": result.stderr[-4000:]})
            if result.returncode == 0:
                break
        path = cached_object(repository, record)
    return {"path": PGO_PATH, **record, "cached_object": str(path),
            "source_revision": project["revision"], "attempts": attempts}


def install(work: Path, cache: Path, data: dict) -> dict:
    record = prepare_cache(cache, data, fetch=False)
    target = work / "src" / PGO_PATH
    if any(path.is_symlink() for path in (target, *target.parents) if path.is_relative_to(work)) or not target.is_file():
        raise ValueError("unexpected release PGO source path")
    if target.stat().st_size == record["size"] and sha256(target) == record["sha256"]:
        return {**record, "status": "reused_verified_object"}
    if target.stat().st_size > 512 or target.read_text() != record["pointer"]:
        raise ValueError("unknown PGO source content; preserving it")
    descriptor, temporary = tempfile.mkstemp(prefix=".qemu-pgo-", dir=target.parent)
    os.close(descriptor)
    staged = Path(temporary)
    shutil.copyfile(record["cached_object"], staged)
    if sha256(staged) != record["sha256"]:
        raise ValueError("PGO cache changed while copying; staged input retained")
    os.replace(staged, target)
    return {**record, "status": "installed_verified_object"}


def verify(work: Path, data: dict) -> dict:
    project = next(p for p in data["projects"] if p["name"] == "chromium_src")
    result = git(work / "src", "show", project["revision"] + ":" + PGO_PATH)
    if result.returncode:
        raise ValueError("locked PGO pointer is missing")
    record = pointer_record(result.stdout)
    target = work / "src" / PGO_PATH
    if (any(path.is_symlink() for path in (target, *target.parents) if path.is_relative_to(work))
            or not target.is_file() or target.stat().st_size != record["size"]
            or sha256(target) != record["sha256"]):
        raise ValueError("PGO is absent, still a LFS pointer, or has changed")
    return {"path": PGO_PATH, "sha256": record["sha256"], "size": record["size"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("m144_release_source_lock.json"))
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError("refusing to replace LFS preparation evidence")
    record = prepare_cache(args.cache_root, load_lock(args.lock), fetch=not args.no_fetch)
    args.evidence.write_text(json.dumps({"scope": "verified_release_PGO_NOT_runtime_acceptance",
        "source_lock_sha256": sha256(args.lock), "objects": [record],
        "first_artifact_behavior_gate_passed": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
