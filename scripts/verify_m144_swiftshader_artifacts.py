#!/usr/bin/env python3
"""Verify actual ICD ABI and fixed source/patch provenance, not presentation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from verify_runtime_elf_contract import read_elf

PINS = {"chromium_revision": "a8168622b056f25c2e68d5f12fe2759bad2d9a44",
        "v8_revision": "bb352490a41083cfb4fba0fadcb0c5099f4aafa7",
        "arkweb_revision": "f3d904432cc1c57468f2b7fe01979d25e0157581"}
ARCHES = {"arm": (1, 40), "arm64": (2, 183), "x86_64": (2, 62)}
EXPORTS = {"vk_icdGetInstanceProcAddr", "vk_icdNegotiateLoaderICDInterfaceVersion"}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nodelete(data):
    is64 = data[4] == 2
    offset = struct.unpack_from("<Q" if is64 else "<I", data, 40 if is64 else 32)[0]
    size, count = struct.unpack_from("<HH", data, 58 if is64 else 46)
    section_fmt = "<IIQQQQIIQQ" if is64 else "<IIIIIIIIII"
    if not count or size < struct.calcsize(section_fmt) or offset + size * count > len(data):
        raise ValueError("invalid ICD section table")
    sections = [struct.unpack_from(section_fmt, data, offset + i * size) for i in range(count)]
    tables = [s for s in sections if s[1] == 6]
    if len(tables) != 1:
        raise ValueError("ICD must have one dynamic table")
    table = tables[0]
    entry_fmt = "<qQ" if is64 else "<iI"
    entry_size = struct.calcsize(entry_fmt)
    if (table[4] + table[5] > len(data) or table[5] % entry_size
            or table[9] != entry_size):
        raise ValueError("invalid ICD dynamic table")
    flags = 0
    for position in range(table[4], table[4] + table[5], entry_size):
        tag, value = struct.unpack_from(entry_fmt, data, position)
        if tag == 0:
            if flags & 8:
                return
            raise ValueError("ICD must retain NODELETE")
        if tag == 0x6ffffffb:
            flags |= value
    raise ValueError("unterminated ICD dynamic table")


def validate(root, arches):
    manifest = json.loads((root / "manifest.json").read_text())
    component = Path(__file__).resolve().parents[1] / "patches/common/web/arkweb/m144_swiftshader"
    patches = {p.name: checksum(p) for p in sorted(component.glob("*.patch"))}
    if (type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1
            or manifest.get("engine") != "ArkWeb M144 SwiftShader Vulkan ICD"
            or manifest.get("chromium_milestone") != 144
            or any(manifest.get(key) != value for key, value in PINS.items())
            or manifest.get("source_patches") != sorted(patches)
            or manifest.get("source_patch_sha256") != patches):
        raise ValueError("ICD source baseline or current patch provenance differs")
    records = {}
    for arch in arches:
        elf_class, machine = ARCHES[arch]
        path = root / arch / "libvk_swiftshader.so"
        if path.is_symlink():
            raise ValueError("aliased ICD artifact")
        data = path.read_bytes()
        if (len(data) < 64 or data[:7] != b"\x7fELF" + bytes((elf_class, 1, 1))
                or struct.unpack_from("<HH", data, 16) != (3, machine)):
            raise ValueError("wrong actual ICD ELF ABI: " + arch)
        record = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if manifest.get("artifacts", {}).get(arch + "/libvk_swiftshader.so") != record:
            raise ValueError("ICD checksum differs from source build: " + arch)
        if not EXPORTS <= read_elf(path).defined or b"vkCreateSurfaceOHOS\0" not in data:
            raise ValueError("ICD lacks loader entry points or the OHOS surface dispatch")
        nodelete(data)
        records[arch] = record
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--arch", choices=tuple(ARCHES), nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps({"scope": "ICD_dependency_only_NOT_guest_presentation", "first_artifact_behavior_gate_passed": False,
                      "artifacts": validate(args.artifact_root, args.arch)}))


if __name__ == "__main__":
    main()
