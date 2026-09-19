#!/usr/bin/env python3
"""Patch the OpenHarmony 7.0 SceneBoard unlock common-event name.

The pinned SceneBoard HAP was compiled with the legacy
``common.event.UNLOCK_SCREEN`` event.  AbilityManager 7.0 subscribes to
``usual.event.SCREEN_UNLOCKED`` and keeps its first-boot interceptor installed
when it never receives that event.  The replacement string already exists in
the method's sorted ABC index, so this tool changes only the ``lda.str``
operand and refreshes the ABC Adler-32 checksum without rebuilding SceneBoard.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import tempfile
import zipfile
import zlib
from pathlib import Path


MODULES_ABC = "ets/modules.abc"
ORIGINAL_ABC_SHA256 = "4866846a48fa6247ce48edf449fc306c5ce1a2f19f7338f6377621c5130b1549"
PATCHED_ABC_SHA256 = "f1ceb224f8ffa56181c5de199db9bcf7e3c25a84d4dd538f8600330019d63759"

METHOD_ENTITY_OFFSET = 0x3724D9
METHOD_STRING_INDEX = 0x7C9F
NEW_METHOD_STRING_INDEX = 0x847B
INSTRUCTION_OFFSET = 0x155A98A
OLD_STRING_ENTITY_OFFSET = 0x7623E6
NEW_STRING_ENTITY_OFFSET = 0x7E87CA
OLD_EVENT = b"common.event.UNLOCK_SCREEN\0"
NEW_EVENT = b"usual.event.SCREEN_UNLOCKED\0"

HEADER_SIZE = 60
CHECKSUM_OFFSET = 8
FILE_CONTENT_OFFSET = 12
INDEX_HEADER_SIZE = 40


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def read_panda_string(data: bytes | bytearray, offset: int) -> bytes:
    cursor = offset
    encoded_length = 0
    shift = 0
    while True:
        value = data[cursor]
        cursor += 1
        encoded_length |= (value & 0x7F) << shift
        if value & 0x80 == 0:
            break
        shift += 7
        if shift > 28:
            raise ValueError(f"invalid Panda string length at 0x{offset:x}")
    if encoded_length & 1 == 0:
        raise ValueError(f"expected an ASCII Panda string at 0x{offset:x}")
    end = data.index(0, cursor) + 1
    return bytes(data[cursor:end])


def patch_modules_abc(original: bytes) -> bytes:
    original_hash = sha256(original)
    if PATCHED_ABC_SHA256 and original_hash == PATCHED_ABC_SHA256:
        return original
    if original_hash != ORIGINAL_ABC_SHA256:
        raise ValueError(
            "unexpected SceneBoard modules.abc SHA-256: "
            f"{original_hash} (expected {ORIGINAL_ABC_SHA256})"
        )
    if len(original) < HEADER_SIZE or original[:8] != b"PANDA\0\0\0":
        raise ValueError("input is not a supported Panda ABC file")

    data = bytearray(original)
    file_size, = struct.unpack_from("<I", data, 16)
    num_indexes, index_section_offset = struct.unpack_from("<II", data, 52)
    if file_size != len(data):
        raise ValueError(f"ABC size mismatch: header={file_size}, actual={len(data)}")

    method_index_offset = None
    method_index_size = None
    for index in range(num_indexes):
        header_offset = index_section_offset + index * INDEX_HEADER_SIZE
        values = struct.unpack_from("<10I", data, header_offset)
        start, end = values[:2]
        if start <= METHOD_ENTITY_OFFSET < end:
            method_index_size, method_index_offset = values[4:6]
            break
    if method_index_offset is None or method_index_size is None:
        raise ValueError("SceneBoard unlock method index header was not found")
    if max(METHOD_STRING_INDEX, NEW_METHOD_STRING_INDEX) >= method_index_size:
        raise ValueError("SceneBoard unlock string index is outside its method index")

    old_table_entry_offset = method_index_offset + METHOD_STRING_INDEX * 4
    new_table_entry_offset = method_index_offset + NEW_METHOD_STRING_INDEX * 4
    old_entity, = struct.unpack_from("<I", data, old_table_entry_offset)
    new_entity, = struct.unpack_from("<I", data, new_table_entry_offset)
    if old_entity != OLD_STRING_ENTITY_OFFSET:
        raise ValueError(
            f"unexpected legacy unlock string entity 0x{old_entity:x} at "
            f"0x{old_table_entry_offset:x}"
        )
    if new_entity != NEW_STRING_ENTITY_OFFSET:
        raise ValueError(
            f"unexpected 7.0 unlock string entity 0x{new_entity:x} at "
            f"0x{new_table_entry_offset:x}"
        )
    if data[INSTRUCTION_OFFSET:INSTRUCTION_OFFSET + 3] != b"\x3e\x9f\x7c":
        raise ValueError("SceneBoard unlock lda.str instruction does not match")
    if read_panda_string(data, OLD_STRING_ENTITY_OFFSET) != OLD_EVENT:
        raise ValueError("legacy unlock event string does not match")
    if read_panda_string(data, NEW_STRING_ENTITY_OFFSET) != NEW_EVENT:
        raise ValueError("7.0 unlock event string does not match")

    struct.pack_into("<H", data, INSTRUCTION_OFFSET + 1, NEW_METHOD_STRING_INDEX)
    checksum = zlib.adler32(data[FILE_CONTENT_OFFSET:]) & 0xFFFFFFFF
    struct.pack_into("<I", data, CHECKSUM_OFFSET, checksum)
    return bytes(data)


def rewrite_hap(input_hap: Path, output_hap: Path) -> str:
    output_hap.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_hap, "r") as source:
        names = source.namelist()
        if names.count(MODULES_ABC) != 1:
            raise ValueError(f"{input_hap} must contain exactly one {MODULES_ABC}")
        patched_abc = patch_modules_abc(source.read(MODULES_ABC))

        with tempfile.NamedTemporaryFile(
            prefix=f".{output_hap.name}.", suffix=".tmp", dir=output_hap.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, "w", allowZip64=True) as target:
                for info in source.infolist():
                    payload = patched_abc if info.filename == MODULES_ABC else source.read(info)
                    target.writestr(info, payload)
            shutil.move(temporary_path, output_hap)
        finally:
            temporary_path.unlink(missing_ok=True)
    return sha256(patched_abc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_hap", type=Path, help="unsigned SceneBoard HAP")
    parser.add_argument("output_hap", type=Path, help="patched unsigned HAP")
    args = parser.parse_args()
    patched_hash = rewrite_hap(args.input_hap, args.output_hap)
    print(f"patched {MODULES_ABC} SHA-256: {patched_hash}")
    print(f"patched unsigned HAP: {args.output_hap}")


if __name__ == "__main__":
    main()
