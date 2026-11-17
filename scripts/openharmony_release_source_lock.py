#!/usr/bin/env python3
"""Pin/verify prepared main-system project commits, without resetting edits."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

DEFAULT_LOCK = Path(__file__).with_name("openharmony_7_0_release_source_lock.json")
MANIFEST_REVISION = "f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549"


def load_lock(path):
    document = json.loads(path.read_text())
    if (document.get("schema_version") != 1 or document.get("manifest_branch") != "OpenHarmony-7.0-Release"
            or document.get("manifest_revision") != MANIFEST_REVISION):
        raise ValueError("not the fixed main-system 7.0 release lock")
    projects = document.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("empty main-system project lock")
    paths = set()
    for project in projects:
        if not isinstance(project, dict) or set(project) != {"name", "path", "revision"}:
            raise ValueError("invalid locked project record")
        name, relative, revision = (project[k] for k in ("name", "path", "revision"))
        if not all(isinstance(value, str) for value in (name, relative, revision)):
            raise ValueError("locked project fields must be strings")
        parts = PurePosixPath(relative)
        if (not name or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None or not relative
                or parts.is_absolute() or any(part in (".", "..") for part in relative.split("/"))
                or str(parts) != relative or relative in paths or re.fullmatch(r"[0-9a-f]{40}", revision) is None):
            raise ValueError("unsafe, duplicate or unpinned release project")
        paths.add(relative)
    return document


def payload(document):
    manifest = ET.Element("manifest")
    for project in document["projects"]:
        # Retain the remote and existing tag/branch fetch hints. Those hints
        # locate objects, while this exact commit fixes the actual build input.
        ET.SubElement(manifest, "extend-project", **project)
    ET.indent(manifest, space="  ")
    return ET.tostring(manifest, encoding="utf-8", xml_declaration=True) + b"\n"


def install(source, document):
    parent = source / ".repo/local_manifests"
    target = parent / "ohos-qemu-7.0-source-lock.xml"
    if (source / ".repo").is_symlink() or parent.is_symlink() or target.is_symlink():
        raise ValueError("unexpected manifest alias; preserving it")
    content = payload(document)
    if target.exists():
        if not target.is_file() or target.read_bytes() != content:
            raise ValueError("existing source-lock manifest differs; preserve and review it")
        return
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".ohos-qemu-source-lock-", dir=parent)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
    os.replace(name, target)


def verify(source, document, resolved=None):
    manifest_head = subprocess.check_output(["git", "-C", str(source / ".repo/manifests"),
                                            "rev-parse", "HEAD"], text=True).strip()
    if manifest_head != document["manifest_revision"]:
        raise ValueError("main manifest HEAD differs from locked Release")
    if resolved is not None:
        actual = [{"name": p.attrib["name"], "path": p.attrib.get("path", p.attrib["name"]),
                   "revision": p.attrib["revision"]} for p in ET.parse(resolved).findall("project")]
        if sorted(actual, key=lambda p: p["path"]) != document["projects"]:
            raise ValueError("resolved system project graph differs from the exact source lock")

    def check(project):
        checkout = source / project["path"]
        # Repo's internal .git link is expected; project directory aliases are not.
        if checkout.is_symlink() or not checkout.is_dir():
            raise ValueError("missing or aliased locked checkout: " + project["path"])
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual != project["revision"]:
            raise ValueError("locked project HEAD differs: " + project["path"] + " " + actual)
        return {**project, "observed_head": actual}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(check, document["projects"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--resolved-manifest", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    document = load_lock(args.lock)
    if args.install:
        install(args.source_root, document)
    else:
        records = verify(args.source_root, document, args.resolved_manifest)
        if args.evidence:
            with args.evidence.open("x") as stream:
                json.dump({"schema_version": 1, "status": "pass", "scope": "actual_main_Release_project_HEADs_NOT_guest_behavior",
                    "source_lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(), "projects": records,
                    "first_artifact_behavior_gate_passed": False}, stream, indent=2)
                stream.write("\n")
    print("installed fixed main-system project graph" if args.install else "PASS: exact main-system project HEAD graph")


if __name__ == "__main__":
    main()
