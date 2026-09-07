#!/usr/bin/env python3
"""Create a minimal ELF dynamic-symbol fixture for shell integration tests."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", type=int, required=True)
    parser.add_argument("--defined", action="append", default=[])
    parser.add_argument("--undefined", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    strings = bytearray(b"\0")
    entries = [b"\0" * 24]
    for name, defined in (
        [(name, True) for name in args.defined]
        + [(name, False) for name in args.undefined]
    ):
        name_offset = len(strings)
        strings.extend(name.encode() + b"\0")
        entries.append(
            struct.pack("<IBBHQQ", name_offset, 0x12, 0, 1 if defined else 0, 0, 0)
        )

    dynstr_offset = 64
    dynsym_offset = (dynstr_offset + len(strings) + 7) & ~7
    dynsym = b"".join(entries)
    section_offset = (dynsym_offset + len(dynsym) + 7) & ~7
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01" + b"\0" * 9,
        3,
        args.machine,
        1,
        0,
        0,
        section_offset,
        0,
        64,
        0,
        0,
        64,
        3,
        0,
    )
    null = b"\0" * 64
    dynstr_section = struct.pack(
        "<IIQQQQIIQQ", 0, 3, 0, 0, dynstr_offset, len(strings), 0, 0, 1, 0
    )
    dynsym_section = struct.pack(
        "<IIQQQQIIQQ", 0, 11, 0, 0, dynsym_offset, len(dynsym), 1, 1, 8, 24
    )
    data = bytearray(header)
    data.extend(strings)
    data.extend(b"\0" * (dynsym_offset - len(data)))
    data.extend(dynsym)
    data.extend(b"\0" * (section_offset - len(data)))
    data.extend(null + dynstr_section + dynsym_section)
    data.extend(b"\0" * (8192 - len(data)))
    args.output.write_bytes(data)


if __name__ == "__main__":
    main()
