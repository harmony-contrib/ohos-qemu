#!/usr/bin/env python3
"""Materialize every locked release project on a native Linux filesystem.

An old, differently pinned workspace is rejected, never reset. Nested directories
from the newly created parent checkout are preserved before installing their
manifest-owned project. Branches and Chromium upstream DEPS are not traversed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_m144_release_cache import load_lock
from prepare_m144_release_lfs import install as install_lfs, verify as verify_lfs


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-c", "credential.helper=", "-C", str(root), *args],
                                   env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"},
                                   text=True).strip()


def check_pins(work: Path, data: dict) -> dict[str, str]:
    pins = {}
    for project in data["projects"]:
        target = work / project["path"]
        if target.is_symlink() or not (target / ".git").is_dir():
            raise ValueError(f"missing actual manifest project: {project['path']}")
        head = git(target, "rev-parse", "HEAD")
        if head != project["revision"]:
            raise ValueError(f"release source revision differs: {project['path']}")
        pins[project["path"]] = head
    version = (work / "src/chrome/VERSION").read_text()
    if "MAJOR=144" not in version.splitlines():
        raise ValueError("actual Chromium source is not M144")
    verify_lfs(work, data)
    return pins


def materialize(work: Path, cache: Path, data: dict) -> dict[str, str]:
    marker = work / ".m144-release-source-owner.json"
    lock_identity = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if work.is_symlink():
        raise ValueError("workspace must not be a symlink")
    work.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        if json.loads(marker.read_text()) != {"source_lock_identity": lock_identity}:
            raise ValueError("workspace belongs to a different source lock")
    else:
        if any(work.iterdir()):
            raise ValueError("new release workspace must be empty; preserve the old workspace")
        marker.write_text(json.dumps({"source_lock_identity": lock_identity}) + "\n")
    # The graph is prepared only from complete exact-commit cache objects.
    for project in data["projects"]:
        repository = cache / (project["name"] + ".git")
        if repository.is_symlink() or not repository.is_dir():
            raise ValueError(f"missing pinned source cache: {project['name']}")
        if git(repository, "rev-parse", project["revision"] + "^{commit}") != project["revision"]:
            raise ValueError("source cache commit differs")
    for project in sorted(data["projects"], key=lambda p: (len(Path(p["path"]).parts), p["path"])):
        target = work / project["path"]
        if target.is_symlink():
            raise ValueError(f"unexpected source path alias: {target}")
        if (target / ".git").exists():
            if git(target, "rev-parse", "HEAD") != project["revision"]:
                raise ValueError(f"existing checkout revision differs: {target}")
            continue
        if target.exists():
            # Only the parent contents in this explicitly owned fresh workspace
            # can reach here. Keep them recoverable; never delete a subtree.
            backup = work / ".release-parent-subtrees" / project["name"] / project["path"]
            if backup.exists():
                raise ValueError("prior nested-project backup exists; inspect incomplete preparation")
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        target.mkdir(parents=True)
        git(target, "init")
        git(target, "fetch", "--no-tags", "--depth=1",
            (cache / (project["name"] + ".git")).as_uri(), project["revision"])
        git(target, "checkout", "--detach", project["revision"])
        print(f"M144 release source: {project['path']} {project['revision']}", flush=True)
    for project in data["projects"]:
        for link in project["links"]:
            destination, source = work / link["dest"], work / project["path"] / link["src"]
            if not source.exists():
                raise ValueError(f"manifest link source is missing: {source}")
            if destination.is_symlink() and destination.resolve() == source.resolve():
                continue
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"unexpected existing manifest link: {destination}")
            destination.symlink_to(os.path.relpath(source, destination.parent))
    alias, deps = work / "src/arkweb/deps_code", work / "deps_code"
    if not alias.exists() and not alias.is_symlink():
        alias.symlink_to(os.path.relpath(deps, alias.parent))
    if not alias.is_symlink() or alias.resolve() != deps.resolve():
        raise ValueError("unexpected ArkWeb interface source alias")
    # Keep Git's tracked diff as the locked pointer, while compiling the verified
    # real object. Do not allow later checkouts to download moving SDK archives.
    git(work / "src", "lfs", "install", "--local", "--skip-smudge")
    install_lfs(work, cache, data)
    return check_pins(work, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("m144_release_source_lock.json"))
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError("refusing to overwrite source preparation evidence")
    data = load_lock(args.lock)
    work = args.work_root.absolute()
    if args.verify_only:
        pins = check_pins(work, data)
    else:
        if args.cache_root is None:
            parser.error("--cache-root is required for preparation")
        pins = materialize(work, args.cache_root.absolute(), data)
    evidence = {"scope": "actual_pinned_source_graph_NOT_build_or_guest_validation",
                "source_lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(),
                "source_pins": pins, "chromium_version": (work / "src/chrome/VERSION").read_text(),
                "release_lfs_objects": [verify_lfs(work, data)],
                "first_artifact_behavior_gate_passed": False}
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
