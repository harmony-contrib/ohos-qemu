#!/usr/bin/env python3
"""Synthetic parser counterexamples; none of these are product build evidence."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import batch_apps_contact_payload as payload


def panda(body=b'fixture-only-not-module-record-proof'):
    data = bytearray(60 + len(body))
    data[:8] = b'PANDA\0\0\0'
    data[12:16] = b'\x0c\x00\x06\x00'
    struct.pack_into('<I', data, 16, len(data))
    data[60:] = body
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
    return bytes(data)


def synthetic_elf(blobs, *, kind='dso', arch='arm64', stripped=False, duplicate=False, executable=True):
    """Serialize artificial ELF32/64 data directly; never invoke a compiler."""
    cls, machine = payload.ARCHES[arch]
    is64 = cls == 2
    header_size, ph_size, sym_size = (64, 56, 24) if is64 else (52, 32, 16)
    sh_size = 64 if is64 else 40
    data = bytearray(256)
    data[:16] = b'\x7fELF' + bytes((cls, 1, 1)) + bytes(9)
    base = 0x10000 if kind == 'dso' else 0
    sections = [(0,) * 10]

    def append(content, typ, flags=0, link=0, entsize=0):
        data.extend(bytes((-len(data)) % 8))
        offset = len(data)
        data.extend(content)
        sections.append((0, typ, flags, base + offset if flags & 2 else 0,
                         offset, len(content), link, 0, 8, entsize))
        return len(sections) - 1, offset

    _, text_offset = append(b'fixture-CFI-jump-table-ONLY', 1, 6)
    blob_data = b''.join(blobs.values())
    data_index, data_offset = append(blob_data, 1, 3)
    names = bytearray(b'\0')
    symbols = []

    def symbol(name, value, size, section, info=0x10):
        name_offset = len(names)
        names.extend(name.encode() + b'\0')
        if is64:
            return struct.pack('<IBBHQQ', name_offset, info, 0, section, value, size)
        return struct.pack('<IIIBBH', name_offset, value, size, info, 0, section)

    if kind == 'dso':
        for index, name in enumerate(payload.EXPORTS):
            symbols.append(symbol(name, base + text_offset + index * 8, 8, 1, 0x12))
    dynamic_symbols = list(symbols)
    cursor = base + data_offset if kind == 'dso' else 0
    if not stripped:
        for prefix, content in blobs.items():
            symbols.extend((symbol(prefix + 'start', cursor, 0, data_index),
                            symbol(prefix + 'end', cursor + len(content), 0, data_index),
                            symbol(prefix + 'size', len(content), 0, 0xfff1)))
            if duplicate:
                symbols.append(symbol(prefix + 'start', cursor + 1, 0, data_index))
            cursor += len(content)
    strings_index, _ = append(bytes(names), 3)
    null = bytes(sym_size)
    append(null + b''.join(symbols), 2, link=strings_index, entsize=sym_size)
    append(null + b''.join(dynamic_symbols), 11, link=strings_index, entsize=sym_size)
    _, dynamic_offset = append(bytes(32), 6, 3)
    data.extend(bytes((-len(data)) % 8))
    shoff = len(data)
    for section in sections:
        data.extend(struct.pack('<IIQQQQIIQQ' if is64 else '<IIIIIIIIII', *section))
    header = (1 if kind == 'object' else 3, machine, 1, 0, header_size if kind == 'dso' else 0,
              shoff, 0, header_size, ph_size if kind == 'dso' else 0,
              2 if kind == 'dso' else 0, sh_size, len(sections), strings_index)
    struct.pack_into('<HHIQQQIHHHHHH' if is64 else '<HHIIIIIHHHHHH', data, 16, *header)
    if kind == 'dso':
        programs = [(1, 7 if executable else 6, 0, base, base, len(data), len(data), 4096),
                    (2, 6, dynamic_offset, base + dynamic_offset, base + dynamic_offset, 32, 32, 8)]
        for index, (typ, flags, offset, addr, physical, size, memory, align) in enumerate(programs):
            values = (typ, flags, offset, addr, physical, size, memory, align) if is64 else (
                typ, offset, addr, physical, size, memory, flags, align)
            struct.pack_into('<IIQQQQQQ' if is64 else '<IIIIIIII', data, header_size + index * ph_size, *values)
    return bytes(data)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.js = b'export function selectContacts() { return realNativePicker(); }\n'
        self.abc = panda()
        self.data = self.files()
        self.paths = {}
        for name, data in self.data.items():
            self.paths[name] = self.directory / name
            self.paths[name].write_bytes(data)

    def files(self, arch='arm64'):
        blobs = dict(zip(payload.PREFIXES, (self.js, self.abc)))
        stripped = synthetic_elf(blobs, arch=arch, stripped=True)
        return {'source_js': self.js, 'abc': self.abc,
                'js_object': synthetic_elf({payload.PREFIXES[0]: self.js}, kind='object', arch=arch),
                'abc_object': synthetic_elf({payload.PREFIXES[1]: self.abc}, kind='object', arch=arch),
                'unstripped': synthetic_elf(blobs, arch=arch), 'linked': stripped,
                'staged': stripped, 'image_dso': stripped}

    def replace(self, name, data):
        self.paths[name].write_bytes(data)

    def check(self, **kwargs):
        return payload.verify_payloads(**self.paths, **kwargs)

    def test_synthetic_identity_has_explicit_limited_scope(self):
        result = self.check()
        self.assertEqual(result['status'], 'pass_payload_identity_ONLY')
        self.assertEqual(result['embedded_payloads']['abc']['sha256'], payload.digest(self.abc))
        for field in ('compiler_execution_verified', 'fresh_product_build_verified',
                      'image_extraction_uniqueness_verified', 'module_record_and_literal_binding_verified',
                      'public_runtime_execution_verified', 'first_artifact_behavior_gate_passed', 'ledger_closed'):
            self.assertIs(result[field], False)

    def test_all_three_product_ELF_classes(self):
        for arch in payload.ARCHES:
            with self.subTest(arch=arch):
                for name, data in self.files(arch).items():
                    self.replace(name, data)
                self.assertEqual(self.check(arch=arch)['architecture'], arch)

    def test_wrong_current_JS_and_old_blob_rejected(self):
        self.replace('source_js', self.js.replace(b'realNativePicker', b'oldNativePicker'))
        with self.assertRaisesRegex(ValueError, 'current source_js'):
            self.check()

    def test_valid_but_different_ABC_rejected(self):
        self.replace('abc', panda(b'another-valid-header-ABC'))
        with self.assertRaisesRegex(ValueError, 'current abc'):
            self.check()

    def test_foreign_blob_object_rejected(self):
        self.replace('abc_object', synthetic_elf({payload.PREFIXES[1]: panda(b'old')}, kind='object'))
        with self.assertRaisesRegex(ValueError, 'current abc'):
            self.check()

    def test_image_changed_after_stage_rejected(self):
        self.replace('image_dso', self.data['image_dso'] + b'changed')
        with self.assertRaisesRegex(ValueError, 'DSO bytes differ'):
            self.check()

    def test_same_wrong_image_and_linked_payload_rejected(self):
        wrong = synthetic_elf(dict(zip(payload.PREFIXES, (self.js, panda(b'wrong')))), stripped=True)
        for name in ('linked', 'staged', 'image_dso'):
            self.replace(name, wrong)
        with self.assertRaisesRegex(ValueError, 'current abc.*linked'):
            self.check()

    def test_stripped_file_cannot_supply_unstripped_boundaries(self):
        self.replace('unstripped', self.data['linked'])
        with self.assertRaisesRegex(ValueError, 'boundary symbols missing'):
            self.check()

    def test_conflicting_boundary_symbol_rejected(self):
        self.replace('unstripped', synthetic_elf(dict(zip(payload.PREFIXES, (self.js, self.abc))), duplicate=True))
        with self.assertRaisesRegex(ValueError, 'conflicting ELF symbol'):
            self.check()

    def test_nonexecutable_export_rejected(self):
        self.replace('unstripped', synthetic_elf(dict(zip(payload.PREFIXES, (self.js, self.abc))), executable=False))
        with self.assertRaisesRegex(ValueError, 'not executable'):
            self.check()

    def test_wrong_machine_rejected(self):
        with self.assertRaisesRegex(ValueError, 'product machine'):
            self.check(arch='x86_64')

    def test_truncated_ELF_and_program_header_rejected(self):
        for data in (b'\x7fELF' + bytes(60), self.data['unstripped'][:160]):
            with self.subTest(length=len(data)):
                self.replace('unstripped', data)
                with self.assertRaises(ValueError):
                    self.check()

    def test_boundary_size_and_unbacked_VA_rejected(self):
        elf = payload.Elf(self.data['unstripped'], 'arm64', 'dso')
        name = payload.PREFIXES[0]
        elf.symbols[name + 'size']['value'] += 1
        with self.assertRaisesRegex(ValueError, 'absolute-size'):
            elf.blob(name, dso=True)
        elf = payload.Elf(self.data['unstripped'], 'arm64', 'dso')
        elf.loads[0]['size'] = 1
        with self.assertRaisesRegex(ValueError, 'file-backed'):
            elf.blob(name, dso=True)

    def test_overlapping_load_mapping_rejected(self):
        elf = payload.Elf(self.data['unstripped'], 'arm64', 'dso')
        elf.loads.append(copy.copy(elf.loads[0]))
        with self.assertRaisesRegex(ValueError, 'uniquely file-backed'):
            elf.blob(payload.PREFIXES[1], dso=True)

    def test_missing_or_undefined_dynamic_exports_rejected(self):
        for undefined in (False, True):
            elf = payload.Elf(self.data['unstripped'], 'arm64', 'dso')
            if undefined:
                elf.dynamic_symbols[payload.EXPORTS[0]]['section'] = 0
            else:
                elf.dynamic_symbols.pop(payload.EXPORTS[0])
            with self.assertRaisesRegex(ValueError, 'defined public NAPI'):
                elf.exports()

    def test_ABC_header_magic_file_size_and_checksum_rejected(self):
        cases = [self.abc[:59], bytes(60)]
        wrong_size = bytearray(self.abc); struct.pack_into('<I', wrong_size, 16, len(self.abc) - 1)
        cases.append(wrong_size)
        cases.append(self.abc[:-1] + b'!')
        for data in cases:
            with self.subTest(data=bytes(data[:20])):
                with self.assertRaises(ValueError):
                    payload.abc_header(data)

    def test_CLI_preserves_failure_and_never_overwrites_report(self):
        self.replace('image_dso', b'bad')
        output = self.directory / 'result.json'
        argv = [part for name, path in self.paths.items() for part in ('--' + name.replace('_', '-'), str(path))]
        argv.extend(('--output', str(output)))
        self.assertEqual(payload.main(argv), 1)
        self.assertIn('"status": "fail"', output.read_text())
        with self.assertRaises(FileExistsError):
            payload.main(argv)


if __name__ == '__main__':
    unittest.main()
