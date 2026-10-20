#!/usr/bin/env python3
"""Verify dynamic-symbol contracts required by QEMU runtime components."""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


SHT_DYNSYM = 11
SHN_UNDEF = 0


@dataclass(frozen=True)
class ElfInfo:
    machine: int
    defined: frozenset[str]
    undefined: frozenset[str]


def _unpack(fmt: str, data: bytes, offset: int) -> tuple[int, ...]:
    return struct.unpack_from(fmt, data, offset)


def read_elf(path: Path) -> ElfInfo:
    data = path.read_bytes()
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ValueError(f"not an ELF file: {path}")
    elf_class = data[4]
    byte_order = {1: "<", 2: ">"}.get(data[5])
    if byte_order is None:
        raise ValueError(f"unsupported ELF byte order: {path}")

    machine = _unpack(byte_order + "H", data, 18)[0]
    if elf_class == 2:
        section_offset = _unpack(byte_order + "Q", data, 40)[0]
        section_size, section_count = _unpack(byte_order + "HH", data, 58)
        section_format = byte_order + "IIQQQQIIQQ"
        symbol_format = byte_order + "IBBHQQ"
    elif elf_class == 1:
        section_offset = _unpack(byte_order + "I", data, 32)[0]
        section_size, section_count = _unpack(byte_order + "HH", data, 46)
        section_format = byte_order + "IIIIIIIIII"
        symbol_format = byte_order + "IIIBBH"
    else:
        raise ValueError(f"unsupported ELF class: {path}")

    expected_section_size = struct.calcsize(section_format)
    if section_size < expected_section_size:
        raise ValueError(f"invalid ELF section table: {path}")
    sections = []
    for index in range(section_count):
        offset = section_offset + index * section_size
        if offset + expected_section_size > len(data):
            raise ValueError(f"truncated ELF section table: {path}")
        sections.append(_unpack(section_format, data, offset))

    defined: set[str] = set()
    undefined: set[str] = set()
    symbol_size = struct.calcsize(symbol_format)
    for section in sections:
        section_type = section[1]
        if section_type != SHT_DYNSYM:
            continue
        table_offset, table_size = section[4], section[5]
        string_index, entry_size = section[6], section[9]
        if string_index >= len(sections):
            raise ValueError(f"invalid ELF dynamic string table: {path}")
        string_section = sections[string_index]
        strings_offset, strings_size = string_section[4], string_section[5]
        strings = data[strings_offset : strings_offset + strings_size]
        entry_size = entry_size or symbol_size
        if entry_size < symbol_size:
            raise ValueError(f"invalid ELF dynamic symbol entries: {path}")
        for offset in range(table_offset, table_offset + table_size, entry_size):
            fields = _unpack(symbol_format, data, offset)
            if elf_class == 2:
                name_offset, section_index = fields[0], fields[3]
            else:
                name_offset, section_index = fields[0], fields[5]
            if name_offset == 0 or name_offset >= len(strings):
                continue
            end = strings.find(b"\0", name_offset)
            if end < 0:
                continue
            name = strings[name_offset:end].decode("utf-8", errors="replace")
            (undefined if section_index == SHN_UNDEF else defined).add(name)
    return ElfInfo(machine, frozenset(defined), frozenset(undefined))


def is_v8_api_symbol(name: str) -> bool:
    return name.startswith(("_ZN2v8", "_ZNK2v8", "_ZTIN2v8", "_ZTVN2v8"))


def verify_machine(info: ElfInfo, expected: int, path: Path) -> None:
    if info.machine != expected:
        raise ValueError(
            f"wrong ELF machine for {path}: expected {expected}, got {info.machine}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", type=int, required=True)
    parser.add_argument("--elf", type=Path)
    parser.add_argument("--require-defined", action="append", default=[])
    parser.add_argument("--jsvm", type=Path)
    parser.add_argument("--v8", type=Path)
    args = parser.parse_args()

    if args.elf:
        info = read_elf(args.elf)
        verify_machine(info, args.machine, args.elf)
        missing = sorted(set(args.require_defined) - info.defined)
        if missing:
            raise SystemExit(
                f"{args.elf} lacks required dynamic symbol(s): {', '.join(missing)}"
            )
        return

    if not args.jsvm or not args.v8:
        parser.error("use --elf, or provide both --jsvm and --v8")
    jsvm = read_elf(args.jsvm)
    v8 = read_elf(args.v8)
    verify_machine(jsvm, args.machine, args.jsvm)
    verify_machine(v8, args.machine, args.v8)

    missing_dfx = sorted(
        symbol
        for symbol in jsvm.undefined
        if "jsvm8jitparse17JsSymbolExtractor" in symbol
    )
    if missing_dfx:
        raise SystemExit(
            "JSVM contains unresolved internal DFX symbol(s): "
            + ", ".join(missing_dfx)
        )

    required_v8 = {symbol for symbol in jsvm.undefined if is_v8_api_symbol(symbol)}
    if not required_v8:
        raise SystemExit("JSVM does not declare any dynamic V8 API dependencies")
    missing_v8 = sorted(required_v8 - v8.defined)
    if missing_v8:
        preview = "\n  ".join(missing_v8[:20])
        raise SystemExit(
            f"v8_shared does not satisfy {len(missing_v8)} JSVM V8 symbol(s):\n  {preview}"
        )
    v8_api = {symbol for symbol in v8.defined if is_v8_api_symbol(symbol)}
    if not any("NSt3__h" in symbol for symbol in v8_api):
        raise SystemExit("v8_shared does not expose the OpenHarmony std::__h ABI")
    incompatible = sorted(
        symbol
        for symbol in v8_api
        if "NSt4__Cr" in symbol or "NSt3__n1" in symbol
    )
    if incompatible:
        raise SystemExit("v8_shared exposes a non-OpenHarmony libc++ ABI namespace")


if __name__ == "__main__":
    main()
