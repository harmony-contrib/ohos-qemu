#!/usr/bin/env python3
"""Maintainer-only: freeze the official TPC OHOS 7.0 source manifest.

Builds consume the checked-in lock, never resolve a moving branch. This command
is deliberately separate from source preparation and does not alter checkouts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
import xml.etree.ElementTree as ET

MANIFEST_REVISION = "79739ee5ae8ee71c8ef90b63e7a658ef639c5980"
RELEASE = "OpenHarmony-7.0-Release"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def manifest_projects(checkout: Path) -> tuple[list[dict], dict[str, str]]:
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != MANIFEST_REVISION:
        raise ValueError("TPC release manifest revision differs")
    records, inputs, paths = [], {}, set()
    for filename in ("developer.xml", "chromium.xml", "openharmony.xml"):
        content = subprocess.check_output(
            ["git", "-C", str(checkout), "show", f"{head}:{filename}"])
        inputs[filename] = hashlib.sha256(content).hexdigest()
        root = ET.fromstring(content)
        for project in root.findall("project"):
            attrs = project.attrib
            name, path = attrs["name"], attrs["path"]
            if (not re.fullmatch(r"[a-zA-Z0-9_.-]+", name)
                    or PurePosixPath(path).is_absolute()
                    or ".." in PurePosixPath(path).parts or path in paths):
                raise ValueError(f"unsafe or duplicate manifest project: {name}")
            if attrs.get("revision") != RELEASE:
                raise ValueError(f"non-release dependency in TPC manifest: {name}")
            paths.add(path)
            organization = "openharmony" if attrs["remote"] == "openharmony" else "OpenHarmony-TPC"
            if attrs["remote"] not in ("tpc", "openharmony"):
                raise ValueError("unknown source organization")
            records.append({"name": name, "path": path,
                            "release_ref": f"refs/heads/{RELEASE}",
                            "mirror_url": f"https://github.com/{organization}/{name}.git",
                            "upstream_url": f"https://gitcode.com/{organization.lower()}/{name}.git",
                            "links": [dict(node.attrib) for node in project.findall("linkfile")]})
    if len(records) < 100 or not any(r["name"] == "chromium_quiche" for r in records):
        raise ValueError("incomplete official ArkWeb release manifest")
    return records, inputs


def resolve(record: dict) -> dict:
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["git", "-c", "credential.helper=", "-c", "http.lowSpeedLimit=1",
                 "-c", "http.lowSpeedTime=20", "ls-remote", record["upstream_url"],
                 record["release_ref"]], capture_output=True, text=True, timeout=30, check=True)
            lines = result.stdout.strip().splitlines()
            if len(lines) != 1:
                raise ValueError(f"missing or ambiguous release ref: {record['name']}")
            revision, ref = lines[0].split()
            if ref != record["release_ref"] or not SHA.fullmatch(revision):
                raise ValueError("invalid release ref response")
            return {**record, "revision": revision}
        except (subprocess.SubprocessError, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(f"cannot freeze {record['name']}: {error}") from error
            time.sleep(attempt + 1)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-checkout", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8, choices=range(1, 17))
    args = parser.parse_args()
    records, inputs = manifest_projects(args.manifest_checkout)
    # One request per repository even when the manifest installs it twice.
    unique = {record["upstream_url"]: record for record in records}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        resolved = {record["upstream_url"]: record["revision"]
                    for record in pool.map(resolve, unique.values())}
    document = {"schema_version": 1, "release": RELEASE, "chromium_milestone": 144,
                "manifest_revision": MANIFEST_REVISION,
                "manifest_url": "https://gitcode.com/openharmony-tpc/manifest.git",
                "manifest_files_sha256": inputs,
                "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Build only exact commits; GitHub mirror first, official upstream fallback when the mirror lacks the commit.",
                "projects": [{**record, "revision": resolved[record["upstream_url"]]}
                             for record in sorted(records, key=lambda r: r["path"])]}
    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
