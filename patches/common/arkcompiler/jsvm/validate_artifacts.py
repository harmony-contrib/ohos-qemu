#!/usr/bin/env python3
"""Validate the reproducible ArkWeb M144 V8 artifact contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ELF_MACHINES = {
    "arm": 40,
    "arm64": 183,
    "x86_64": 62,
}

PINNED_REVISIONS = {
    "chromium_revision": "4ae5a7f106cdf9d3f42acd1c6ab007140dcd249f",
    "v8_revision": "1170083e0a717f67cead0abe20900f273ae01fb5",
    "arkweb_revision": "eff888fcd48ce0aa4dc4bf7b2474ed77f0353fa2",
    "cef_revision": "d154063ab448260480a75a4e755a18aaf0baf7c4",
    "webview_revision": "93dce838eea694887c707c28b3f4f0fa85f87326",
}


def elf_machine(path: Path) -> int:
    data = path.read_bytes()[:20]
    if len(data) < 20 or data[:4] != b"\x7fELF":
        raise SystemExit(f"not an ELF shared library: {path}")
    if data[5] == 1:
        byte_order = "<"
    elif data[5] == 2:
        byte_order = ">"
    else:
        raise SystemExit(f"unsupported ELF byte order: {path}")
    return struct.unpack(byte_order + "H", data[18:20])[0]


def validate(root: Path, arches: list[str]) -> None:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing V8 artifact manifest: {manifest_path}") from exc
    if manifest.get("schema_version") != 1:
        raise SystemExit("unsupported V8 artifact manifest schema")
    if manifest.get("engine") != "ArkWeb M144 V8":
        raise SystemExit("artifact is not marked as ArkWeb M144 V8")
    if manifest.get("chromium_milestone") != 144:
        raise SystemExit("artifact manifest is not Chromium milestone 144")
    for key, expected_revision in PINNED_REVISIONS.items():
        value = manifest.get(key, "")
        if value != expected_revision:
            raise SystemExit(
                f"artifact {key} is not pinned to {expected_revision}: {value}"
            )
    patch_root = (
        Path(__file__).resolve().parents[2] / "web/arkweb/m144_v8_shared"
    )
    expected_patches = sorted(path.name for path in patch_root.glob("*.patch"))
    if manifest.get("source_patches") != expected_patches:
        raise SystemExit(
            "artifact source patch set does not match the current M144 component"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit("artifact manifest lacks per-file SHA-256 records")

    header = root / "v8-include/v8-include/v8.h"
    if not header.is_file():
        raise SystemExit(f"missing public V8 headers: {header}")

    for arch in arches:
        expected = ELF_MACHINES[arch]
        libraries = (
            root / f"v8/{arch}/libv8_shared.so",
            root / f"v8/{arch}/lib.unstripped_v8/lib.unstripped/libv8_shared.so",
        )
        for library in libraries:
            if not library.is_file():
                raise SystemExit(f"missing {arch} V8 artifact: {library}")
            actual = elf_machine(library)
            if actual != expected:
                raise SystemExit(
                    f"wrong ELF machine for {library}: expected {expected}, got {actual}"
                )
            relative = library.relative_to(root).as_posix()
            record = artifacts.get(relative)
            if not isinstance(record, dict):
                raise SystemExit(f"manifest lacks artifact record: {relative}")
            digest = hashlib.sha256(library.read_bytes()).hexdigest()
            if record.get("sha256") != digest:
                raise SystemExit(f"artifact checksum mismatch: {relative}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--arch", action="append", choices=sorted(ELF_MACHINES))
    args = parser.parse_args()
    validate(args.artifact_root.resolve(), args.arch or sorted(ELF_MACHINES))


if __name__ == "__main__":
    main()
