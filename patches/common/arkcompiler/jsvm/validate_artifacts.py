#!/usr/bin/env python3
"""Validate the reproducible ArkWeb M144 V8 artifact contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


ELF_MACHINES = {
    "arm": 40,
    "arm64": 183,
    "x86_64": 62,
}

PINNED_REVISIONS = {
    "chromium_revision": "a8168622b056f25c2e68d5f12fe2759bad2d9a44",
    "v8_revision": "bb352490a41083cfb4fba0fadcb0c5099f4aafa7",
    "arkweb_revision": "f3d904432cc1c57468f2b7fe01979d25e0157581",
    "cef_revision": "6153d21e9a5d6f0a6718757dcf9c5cadf60fe595",
    "webview_revision": "4237e061441ea9392e83a353c0d52cb1c44404b3",
}


def elf_machine(path: Path) -> int:
    if path.is_symlink():
        raise SystemExit(f"unexpected aliased V8 shared library: {path}")
    with path.open("rb") as stream:
        data = stream.read(64)
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise SystemExit(f"not an ELF shared library: {path}")
    if data[4] not in (1, 2) or data[5:7] != b"\x01\x01" or struct.unpack_from("<H", data, 16)[0] != 3:
        raise SystemExit(f"not an actual little-endian V8 shared ELF: {path}")
    machine = struct.unpack_from("<H", data, 18)[0]
    if (machine == 40 and data[4] != 1) or (machine in (62, 183) and data[4] != 2):
        raise SystemExit(f"V8 ELF class/machine mismatch: {path}")
    return machine


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
    if manifest.get("libcxx_abi_namespace") != "__h":
        raise SystemExit("artifact libc++ ABI namespace is not OpenHarmony __h")
    if manifest.get("libcxx_abi_version") != 1:
        raise SystemExit("artifact libc++ ABI version is not OpenHarmony version 1")
    configuration = {"v8_enable_i18n_support": True, "icu_use_data_file": False,
                     "v8_use_external_startup_data": False}
    actual_configuration = manifest.get("runtime_configuration")
    if (actual_configuration != configuration or not isinstance(actual_configuration, dict)
            or any(type(value) is not bool for value in actual_configuration.values())):
        raise SystemExit("JSVM V8 must retain Intl with embedded ICU/startup data")
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
    if manifest.get("source_patch_sha256") != {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in patch_root.glob("*.patch")}:
        raise SystemExit("artifact source patch content differs; rebuild M144 V8")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit("artifact manifest lacks per-file SHA-256 records")

    header = root / "v8-include/v8-include/v8.h"
    if not header.is_file():
        raise SystemExit(f"missing public V8 headers: {header}")
    headers = root / "v8-include/v8-include"
    header_digest = hashlib.sha256()
    for path in sorted(path for path in headers.rglob("*") if path.is_file()):
        if path.is_symlink():
            raise SystemExit("unexpected aliased V8 header")
        header_digest.update(path.relative_to(headers).as_posix().encode())
        header_digest.update(b"\0")
        header_digest.update(path.read_bytes())
    if manifest.get("headers_sha256") != header_digest.hexdigest():
        raise SystemExit("actual V8 public header content differs from source build")

    for arch in arches:
        expected = ELF_MACHINES[arch]
        arguments = root / "v8" / arch / "args.gn"
        if (arguments.is_symlink() or not arguments.is_file()
                or manifest.get("build_args_sha256", {}).get("v8/" + arch + "/args.gn") !=
                hashlib.sha256(arguments.read_bytes()).hexdigest()):
            raise SystemExit("missing or changed actual V8 GN arguments: " + arch)
        for name, value in configuration.items():
            matches = re.findall(r"^" + re.escape(name) + r"\s*=\s*(true|false)\s*$", arguments.read_text(), re.M)
            if matches != ["true" if value else "false"]:
                raise SystemExit("actual V8 feature/data configuration differs: " + name)
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
            data = library.read_bytes()
            if b"NSt3__h" not in data:
                raise SystemExit(
                    f"V8 artifact does not expose OpenHarmony std::__h ABI: {library}"
                )
            for foreign_namespace in (b"NSt4__Cr", b"NSt3__n1"):
                if foreign_namespace in data:
                    namespace = foreign_namespace.decode("ascii")[3:]
                    raise SystemExit(
                        f"V8 artifact exposes incompatible std::{namespace} ABI: {library}"
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
