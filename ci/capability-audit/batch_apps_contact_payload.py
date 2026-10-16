#!/usr/bin/env python3
"""Check embedded Contacts JS/ABC bytes, without executing ELF or build tools.

This is a payload identity check, not an ABC semantic decoder, build witness,
image extractor or runtime test. The enclosing package verifier must supply an
independently extracted, unique image inode and bind all inputs to the actual
fresh product build. In particular, byte identity does not prove moduleRecordIdx
or literal-array binding, nor that a caller executed NAPI_contact_GetABCCode.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


ARCHES = {'arm64': (2, 183), 'x86_64': (2, 62), 'armv7a': (1, 40)}
EXPORTS = ('NAPI_contact_GetJSCode', 'NAPI_contact_GetABCCode')
PREFIXES = ('_binary_contact_js_', '_binary_contact_abc_')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_slice(data, offset, size, reason):
    require(type(offset) is int and type(size) is int and offset >= 0 and size >= 0 and
            offset <= len(data) and size <= len(data) - offset, reason)
    return data[offset:offset + size]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Elf:
    """Small bounded reader for the ELF sections/symbols and PT_LOAD file bytes."""

    def __init__(self, data, arch, kind):
        require(arch in ARCHES, 'unsupported product architecture')
        self.data = data
        require(len(data) >= 16 and data[:4] == b'\x7fELF', 'ELF header missing')
        cls, machine = ARCHES[arch]
        require(data[4:7] == bytes((cls, 1, 1)), 'wrong ELF class, endianness or version')
        if cls == 2:
            header_format, section_format, program_format, symbol_format = (
                '<HHIQQQIHHHHHH', '<IIQQQQIIQQ', '<IIQQQQQQ', '<IBBHQQ')
        else:
            header_format, section_format, program_format, symbol_format = (
                '<HHIIIIIHHHHHH', '<IIIIIIIIII', '<IIIIIIII', '<IIIBBH')
        self.cls = cls
        header_size = 16 + struct.calcsize(header_format)
        header = struct.unpack(header_format, checked_slice(data, 16, header_size - 16, 'truncated ELF header'))
        (elf_type, actual_machine, version, _, phoff, shoff, _, ehsize, phentsize,
         phnum, shentsize, shnum, shstrndx) = header
        require(elf_type == (1 if kind == 'object' else 3) and actual_machine == machine and version == 1 and
                ehsize == header_size, 'wrong ELF product machine, file type or header size')
        require(0 < shnum < 65535 and shstrndx < shnum and shentsize == struct.calcsize(section_format),
                'ELF section table absent, extended or malformed')
        checked_slice(data, shoff, shnum * shentsize, 'ELF section table outside file')
        self.sections = []
        for index in range(shnum):
            values = struct.unpack_from(section_format, data, shoff + index * shentsize)
            section = dict(zip(('name', 'type', 'flags', 'address', 'offset', 'size', 'link', 'info', 'align', 'entsize'), values))
            if section['type'] != 8:  # SHT_NOBITS has no file bytes.
                checked_slice(data, section['offset'], section['size'], 'ELF section outside file')
            self.sections.append(section)
        require(self.sections[0]['type'] == 0, 'ELF null section malformed')
        self.loads = []
        dynamic = 0
        if phnum:
            require(phentsize == struct.calcsize(program_format), 'ELF program entry size mismatch')
            checked_slice(data, phoff, phnum * phentsize, 'ELF program table outside file')
            for index in range(phnum):
                values = struct.unpack_from(program_format, data, phoff + index * phentsize)
                if cls == 2:
                    typ, flags, offset, address, _, filesz, memsz, align = values
                else:
                    typ, offset, address, _, filesz, memsz, flags, align = values
                checked_slice(data, offset, filesz, 'ELF program segment outside file')
                if typ in (1, 2):
                    require(filesz <= memsz, 'ELF program file size exceeds memory size')
                if typ == 1:
                    require(align in (0, 1) or (align & (align - 1) == 0 and address % align == offset % align),
                            'ELF PT_LOAD alignment malformed')
                    self.loads.append({'offset': offset, 'address': address, 'size': filesz, 'flags': flags})
                elif typ == 2:
                    require(filesz > 0, 'empty ELF PT_DYNAMIC')
                    dynamic += 1
        if kind == 'dso':
            require(self.loads and dynamic == 1, 'real DSO PT_LOAD/PT_DYNAMIC required')
        else:
            require(phnum == 0, 'blob object unexpectedly has program segments')
        self.symbols = {}
        self.dynamic_symbols = {}
        symbol_size = struct.calcsize(symbol_format)
        for section in self.sections:
            if section['type'] not in (2, 11):
                continue
            require(section['entsize'] == symbol_size and section['size'] % symbol_size == 0 and
                    section['link'] < len(self.sections), 'ELF symbol table malformed')
            strings = self.sections[section['link']]
            require(strings['type'] == 3, 'ELF symbol string table has wrong type')
            names = checked_slice(data, strings['offset'], strings['size'], 'ELF symbol strings outside file')
            for offset in range(section['offset'], section['offset'] + section['size'], symbol_size):
                values = struct.unpack_from(symbol_format, data, offset)
                if cls == 2:
                    name_offset, info, other, shindex, value, size = values
                else:
                    name_offset, value, size, info, other, shindex = values
                require(name_offset < len(names), 'ELF symbol name outside string table')
                end = names.find(b'\0', name_offset)
                require(end >= 0, 'unterminated ELF symbol name')
                name_bytes = names[name_offset:end]
                if not (name_bytes.startswith(tuple(prefix.encode() for prefix in PREFIXES)) or
                        name_bytes in tuple(name.encode() for name in EXPORTS)):
                    continue
                name = name_bytes.decode('ascii')
                symbol = {'value': value, 'size': size, 'section': shindex, 'binding': info >> 4,
                          'type': info & 15, 'visibility': other & 3}
                require(name not in self.symbols or self.symbols[name] == symbol, 'conflicting ELF symbol: ' + name)
                self.symbols[name] = symbol
                if section['type'] == 11:
                    require(name not in self.dynamic_symbols or self.dynamic_symbols[name] == symbol,
                            'conflicting dynamic ELF symbol: ' + name)
                    self.dynamic_symbols[name] = symbol

    def mapped(self, address, size, executable=False):
        require(size > 0, 'empty mapped ELF range')
        matches = [row for row in self.loads if address >= row['address'] and
                   address - row['address'] <= row['size'] and size <= row['size'] - (address - row['address'])]
        require(len(matches) == 1, 'ELF virtual range is not uniquely file-backed by PT_LOAD')
        row = matches[0]
        require(not executable or row['flags'] & 1, 'NAPI export is not executable')
        return checked_slice(self.data, row['offset'] + address - row['address'], size, 'ELF mapped range outside file')

    def blob(self, prefix, dso=False):
        names = [prefix + suffix for suffix in ('start', 'end', 'size')]
        require(all(name in self.symbols for name in names), 'actual blob boundary symbols missing: ' + prefix)
        start, end, length = [self.symbols[name] for name in names]
        index = start['section']
        require(0 < index < len(self.sections) and end['section'] == index and length['section'] == 0xfff1 and
                end['value'] > start['value'] and length['value'] == end['value'] - start['value'],
                'invalid blob start/end/absolute-size symbols: ' + prefix)
        section = self.sections[index]
        require(section['type'] == 1 and (not dso or section['flags'] & 2), 'blob is not file-backed allocated data')
        offset = start['value'] - (section['address'] if dso else 0)
        size = length['value']
        payload = checked_slice(checked_slice(self.data, section['offset'], section['size'], 'blob section outside file'),
                                offset, size, 'blob symbols outside actual section')
        if dso:
            require(payload == self.mapped(start['value'], size), 'blob symbol section differs from loaded file bytes')
        return payload, {'address': start['value'], 'size': size, 'sha256': digest(payload)}

    def exports(self):
        result = {}
        for name in EXPORTS:
            symbol = self.dynamic_symbols.get(name)
            require(symbol and symbol['binding'] == 1 and symbol['type'] == 2 and symbol['visibility'] == 0 and
                    0 < symbol['section'] < len(self.sections) and symbol['size'] > 0,
                    'defined public NAPI function export missing: ' + name)
            code = self.mapped(symbol['value'], symbol['size'], executable=True)
            # CFI builds legitimately export short jump-table entries. Their
            # implementation is bound by the actual full-build source witness,
            # not guessed from a stub length or a disassembler heuristic here.
            result[name] = {'address': symbol['value'], 'size': symbol['size'], 'sha256': digest(code)}
        return result


def abc_header(data):
    require(len(data) >= 60 and data[:8] == b'PANDA\0\0\0', 'ABC Panda header missing or truncated')
    checksum, = struct.unpack_from('<I', data, 8)
    size, = struct.unpack_from('<I', data, 16)
    require(size == len(data), 'ABC header file size differs from actual bytes')
    require(checksum == zlib.adler32(data[12:]) & 0xffffffff, 'ABC header Adler32 checksum mismatch')
    return {'version_bytes': list(data[12:16]), 'file_size': size, 'checksum': checksum,
            'module_record_and_literal_binding_verified': False}


def verify_payloads(*, source_js, abc, js_object, abc_object, unstripped, linked, staged, image_dso, arch='arm64'):
    """Re-read all files; caller supplies independent fresh build/image receipts."""
    paths = {name: Path(path) for name, path in locals().copy().items() if name != 'arch'}
    data = {name: path.read_bytes() for name, path in paths.items()}
    require(data['source_js'], 'empty contact.js')
    data['source_js'].decode('utf-8')
    header = abc_header(data['abc'])
    require(data['linked'] == data['staged'] == data['image_dso'],
            'linked, staged and independently extracted image DSO bytes differ')
    objects = {name: Elf(data[name], arch, 'object') for name in ('js_object', 'abc_object')}
    dsos = {name: Elf(data[name], arch, 'dso') for name in ('unstripped', 'linked', 'staged', 'image_dso')}
    exports = {name: value.exports() for name, value in dsos.items()}
    require(all(value == exports['unstripped'] for value in exports.values()),
            'unstripped and installed NAPI function addresses/code differ')
    blobs = {}
    for key, prefix, object_name in (('source_js', PREFIXES[0], 'js_object'), ('abc', PREFIXES[1], 'abc_object')):
        expected = data[key]
        object_data, _ = objects[object_name].blob(prefix)
        actual, location = dsos['unstripped'].blob(prefix, dso=True)
        require(expected == object_data == actual, 'current ' + key + ' differs from object or unstripped embedded bytes')
        for name in ('linked', 'staged', 'image_dso'):
            require(dsos[name].mapped(location['address'], location['size']) == expected,
                    'current ' + key + ' differs from loaded ' + name + ' bytes')
        blobs[key] = location
    artifacts = {name: {'path': str(path.resolve()), 'sha256': digest(data[name]), 'size': len(data[name])}
                 for name, path in paths.items()}
    return {'schema_version': 1, 'status': 'pass_payload_identity_ONLY', 'architecture': arch,
            'scope': 'contact_JS_ABC_blob_objects_unstripped_and_installed_ELF_bytes_ONLY',
            'artifacts': artifacts, 'embedded_payloads': blobs, 'ABC_header': header,
            'NAPI_exports': exports['unstripped'], 'compiler_execution_verified': False,
            'fresh_product_build_verified': False, 'image_extraction_uniqueness_verified': False,
            'module_record_and_literal_binding_verified': False, 'public_runtime_execution_verified': False,
            'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('source-js', 'abc', 'js-object', 'abc-object', 'unstripped', 'linked', 'staged', 'image-dso'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--arch', choices=tuple(ARCHES), default='arm64')
    parser.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args(argv))
    output = args.pop('output')
    try:
        result = verify_payloads(**args)
        code = 0
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        result = {'schema_version': 1, 'status': 'fail', 'error': str(error),
                  'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}
        code = 1
    with output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
