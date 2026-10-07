#!/usr/bin/env python3
"""Fetch the locked OHOS M144 graph, preferring the official GitHub mirrors.

The cache contains complete shallow Git objects, not unverified source archives.
No branch is fetched and no existing checkout is reset or removed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import tempfile
import threading


def load_lock(path: Path) -> dict:
    data = json.loads(path.read_text())
    if (data.get("schema_version") != 1 or data.get("release") != "OpenHarmony-7.0-Release"
            or data.get("manifest_revision") != "79739ee5ae8ee71c8ef90b63e7a658ef639c5980"
            or data.get("chromium_milestone") != 144):
        raise ValueError("wrong M144 release lock")
    paths, repositories = set(), {}
    for project in data["projects"]:
        name, path, revision = project["name"], project["path"], project["revision"]
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
                or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
                or (path != "src" and not path.startswith("src/") and path != "deps_code/webview")
                or path in paths or project["release_ref"] != "refs/heads/OpenHarmony-7.0-Release"):
            raise ValueError("unsafe, moving or duplicate source lock entry")
        organization = "openharmony" if name in ("web_webview", "third_party_bounds_checking_function") else "OpenHarmony-TPC"
        if (project["mirror_url"] != f"https://github.com/{organization}/{name}.git"
                or project["upstream_url"] != f"https://gitcode.com/{organization.lower()}/{name}.git"):
            raise ValueError("unexpected source remote")
        if name in repositories and repositories[name] != revision:
            raise ValueError("same repository has inconsistent pins")
        repositories[name] = revision
        paths.add(path)
    if len(paths) != 156:
        raise ValueError("incomplete official release graph")
    return data


def git(cache: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    command = ["git", "-c", "credential.helper=", "-c", "http.lowSpeedLimit=1",
               "-c", "http.lowSpeedTime=30", "-C", str(cache), *args]
    # Killing only Git leaves remote-https/index-pack alive and stale locks.
    process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def fetch(project: dict, root: Path) -> dict:
    target = root / (project["name"] + ".git")
    if target.is_symlink():
        raise ValueError("cache target must not be a symlink")
    if not target.exists():
        target.mkdir()
        result = git(target, "init", "--bare")
        if result.returncode:
            raise RuntimeError(result.stderr)
    if git(target, "rev-parse", "--is-bare-repository").stdout.strip() != "true":
        raise ValueError("unknown non-bare cache target")
    revision = project["revision"]
    if git(target, "cat-file", "-e", revision + "^{commit}").returncode == 0:
        return {"name": project["name"], "revision": revision, "cache": str(target), "status": "reused_exact_commit"}
    attempts = []
    attempt_root = root / ".fetch-attempts"
    attempt_root.mkdir(exist_ok=True)
    for key in ("mirror_url", "upstream_url"):
        url = project[key]
        # Never let a timed-out mirror attempt corrupt/lock the usable cache.
        # Retain failed attempts, rather than recursively deleting their data.
        scratch = Path(tempfile.mkdtemp(prefix=project["name"] + "-" + key + "-", dir=attempt_root))
        if git(scratch, "init", "--bare").returncode:
            raise RuntimeError("cannot initialize isolated fetch attempt")
        try:
            result = git(scratch, "fetch", "--no-tags", "--depth=1", url,
                         revision + ":refs/ohos7/" + revision,
                         timeout=90 if key == "mirror_url" else 1800)
            attempts.append({"url": url, "scratch": str(scratch), "exit_code": result.returncode,
                             "stderr": result.stderr[-4000:]})
            if result.returncode == 0:
                imported = git(target, "fetch", "--no-tags", "--depth=1", scratch.as_uri(),
                               revision + ":refs/ohos7/" + revision, timeout=1800)
                if imported.returncode:
                    raise RuntimeError("verified fetch could not be imported into cache: " + imported.stderr)
                if git(target, "rev-parse", revision + "^{commit}").stdout.strip() != revision:
                    raise ValueError("fetched commit differs")
                return {"name": project["name"], "revision": revision, "cache": str(target),
                        "status": "fetched_exact_commit", "attempts": attempts}
        except subprocess.TimeoutExpired:
            attempts.append({"url": url, "scratch": str(scratch), "exit_code": "timeout"})
    return {"name": project["name"], "revision": revision, "status": "failed", "attempts": attempts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("m144_release_source_lock.json"))
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 17), default=8)
    args = parser.parse_args()
    data = load_lock(args.lock)
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError("refusing to overwrite cache preparation evidence")
    root = args.cache_root.absolute()
    if root.is_symlink():
        raise ValueError("cache root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    unique = {p["name"]: p for p in data["projects"]}
    records, print_lock = [], threading.Lock()

    def task(project: dict) -> dict:
        record = fetch(project, root)
        with print_lock:
            print(f"M144 release cache: {record['name']} {record['status']}", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for record in pool.map(task, unique.values()):
            records.append(record)
    result = {"schema_version": 1, "scope": "pinned_source_cache_NOT_build_or_guest_validation",
              "source_lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(),
              "repositories": records, "complete": all(r["status"] != "failed" for r in records)}
    args.evidence.write_text(json.dumps(result, indent=2) + "\n")
    if not result["complete"]:
        raise SystemExit("some locked sources could not be fetched; see preparation evidence")


if __name__ == "__main__":
    main()
