"""Archive/ELF-header fixtures only, not compiled libraries or crypto evidence."""
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from qemu_test_hap_archive import ABIS, canonical_library, normalize_archive


def header(abi):
    cls, machine = ABIS[abi]
    data = bytearray(64 if cls == 2 else 52)
    data[:7] = b'\x7fELF' + bytes((cls, 1, 1))
    struct.pack_into('<HH', data, 16, 3, machine)
    return bytes(data) + b'fixture library payload, NOT a real compiled ELF'


def nested(abi, filename='libprobe.so'):
    return (f'libs/{abi}/entry/build/default/intermediates/stripped_native_libs/default/{abi}/'
            f'entry/build/default/intermediates/libs/default/{abi}/entry/libs/{abi}/{filename}')


class QemuTestHapArchiveTests(unittest.TestCase):
    def test_only_known_native_staging_layout_is_canonicalized_for_all_three_ABIs(self):
        for abi in ABIS:
            self.assertEqual(canonical_library(nested(abi), header(abi)), f'libs/{abi}/libprobe.so')
            self.assertEqual(canonical_library(f'libs/{abi}/libc++_shared.so', header(abi)),
                             f'libs/{abi}/libc++_shared.so')
            for path in (f'libs/{abi}/other/libprobe.so', nested(abi).replace('default', 'release', 1),
                         nested(abi).replace('entry/libs', 'other/libs'), f'libs/{abi}/probe.a'):
                with self.assertRaises(ValueError): canonical_library(path, header(abi))

    def test_library_bytes_permissions_resources_unsigned_and_compression_stay_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'original.hap', root / 'normalized.hap'
            module = json.dumps({'module': {'requestPermissions': [{'name': 'ohos.permission.CAMERA'}]}}).encode()
            with zipfile.ZipFile(source, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('module.json', module)
                archive.writestr('ets/modules.abc', b'fixture application bytes')
                archive.writestr(nested('x86_64'), header('x86_64'))
            before = source.read_bytes()
            record = normalize_archive(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(record['library_bytes_changed'])
            self.assertFalse(record['permissions_changed'])
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {'module.json', 'ets/modules.abc', 'libs/x86_64/libprobe.so'})
                self.assertEqual(archive.read('module.json'), module)
                self.assertEqual(archive.read('ets/modules.abc'), b'fixture application bytes')
                self.assertEqual(archive.read('libs/x86_64/libprobe.so'), header('x86_64'))
                self.assertEqual(archive.getinfo('libs/x86_64/libprobe.so').compress_type, zipfile.ZIP_DEFLATED)
            with self.assertRaises(ValueError): normalize_archive(source, output)
            self.assertEqual(source.read_bytes(), before)

    def test_wrong_machine_class_ET_exec_truncated_and_unknown_arch_are_rejected(self):
        for abi in ABIS:
            value = header(abi)
            other = next(name for name in ABIS if name != abi)
            wrong_type = bytearray(value)
            struct.pack_into('<H', wrong_type, 16, 2)
            for data in (header(other), bytes(wrong_type), value[:30], b'not ELF'):
                with self.assertRaises(ValueError): canonical_library(f'libs/{abi}/libprobe.so', data)
        with self.assertRaises(ValueError): canonical_library('libs/unknown/libprobe.so', header('arm64-v8a'))

    def test_collision_unsafe_paths_symlink_members_and_unsigned_alias_fail_without_input_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = ((nested('x86_64'), 'libs/x86_64/libprobe.so'), ('../module.json',), ('/module.json',),
                     ('libs/x86_64/unknown/libprobe.so',))
            for index, names in enumerate(cases):
                source = root / f'source-{index}.hap'
                with zipfile.ZipFile(source, 'w') as archive:
                    for name in names: archive.writestr(name, header('x86_64'))
                before = source.read_bytes()
                with self.assertRaises(ValueError): normalize_archive(source, root / f'out-{index}.hap')
                self.assertEqual(source.read_bytes(), before)
            source = root / 'symlink-member.hap'
            with zipfile.ZipFile(source, 'w') as archive:
                info = zipfile.ZipInfo('module.json')
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, 'outside')
            with self.assertRaises(ValueError): normalize_archive(source, root / 'symlink-out.hap')
            alias = root / 'input-alias.hap'
            alias.symlink_to(source)
            with self.assertRaises(ValueError): normalize_archive(alias, root / 'alias-out.hap')

    def test_real_signing_entry_normalizes_before_both_signature_and_code_sign_verification(self):
        source = Path(__file__).with_name('sign_web_probe.py').read_text()
        self.assertLess(source.index('normalize_archive(args.unsigned.resolve(), normalized_hap)'),
                        source.index('"java", "-jar", jar, "sign-profile"'))
        self.assertIn('verify_signed_hap(jar, args.output.resolve(), temp_dir)', source)


if __name__ == '__main__': unittest.main()
