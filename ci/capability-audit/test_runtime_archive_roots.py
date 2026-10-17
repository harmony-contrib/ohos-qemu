"""Small real tar fixtures; no package gate, image tools, SDK or guest execution."""
import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import run_root_probe as root_probe
import run_native_bindings_e2e as bindings
from batch_system_calendar_runtime_archive import archive_inputs


class RuntimeArchiveRoots(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / 'package.tar.gz'
        self.image = self.root / 'system.img'
        self.image.write_bytes(b'exact packaged system image')
        self.manifest = dict(guest_arch='arm64', device_type='phone',
                             device_type_profile='qemu_phone_full_source')
        self.inputs = dict(revision='package-B', files_sha256={}, tree_sha256='b' * 64)

    def entries(self):
        return [('qemu/manifest.json', json.dumps(self.manifest).encode(), tarfile.REGTYPE),
                ('qemu/build-inputs.json', json.dumps(self.inputs).encode(), tarfile.REGTYPE),
                ('qemu/images/system.img', self.image.read_bytes(), tarfile.REGTYPE)]

    def nested(self):
        return [('qemu/native-frozen-inputs/build-inputs.json', b'{"revision":"native-A"}', tarfile.REGTYPE),
                ('qemu/native-frozen-inputs/manifest.json', b'{"guest_arch":"x86_64"}', tarfile.REGTYPE),
                ('qemu/native-frozen-inputs/patches/gnss/manifest.json', b'{"component":"GNSS"}', tarfile.REGTYPE),
                ('qemu/native-frozen-inputs/images/system.img', b'native provenance, not the selected image', tarfile.REGTYPE)]

    def write(self, entries, damaged_tail=None):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as package:
            for name, payload, kind in entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    member.linkname = 'qemu/manifest.json'
                member.size = len(payload) if kind == tarfile.REGTYPE else 0
                package.addfile(member, io.BytesIO(payload) if member.size else None)
            end = raw.tell()
        content = raw.getvalue()
        if damaged_tail is not None:
            content = content[:end] + damaged_tail
        self.archive.write_bytes(gzip.compress(content))

    def reject_both(self, entries):
        self.write(entries)
        with self.assertRaises((ValueError, tarfile.TarError)):
            root_probe.validate_archive(self.archive, 'arm64', 'phone')
        with self.assertRaises((ValueError, tarfile.TarError)):
            archive_inputs(self.archive, self.image)

    def test_top_B_metadata_wins_over_nested_A_in_either_order(self):
        for entries in (self.entries() + self.nested(), self.nested() + self.entries()):
            with self.subTest(first=entries[0][0]):
                self.write(entries)
                self.assertEqual(root_probe.validate_archive(self.archive, 'arm64', 'phone'), self.manifest)
                system, inputs_raw, manifest_raw, inputs, manifest = archive_inputs(self.archive, self.image)
                self.assertEqual(system.name, 'qemu/images/system.img')
                self.assertEqual(inputs, self.inputs)
                self.assertEqual(manifest, self.manifest)
                self.assertEqual(json.loads(inputs_raw)['revision'], 'package-B')
                self.assertEqual(json.loads(manifest_raw), self.manifest)

    def test_native_bindings_final_runner_uses_the_same_checked_reader(self):
        self.assertIs(bindings.validate_archive, root_probe.validate_archive)
        self.write(self.nested() + self.entries())
        self.assertEqual(bindings.validate_archive(self.archive, 'arm64', 'phone'), self.manifest)
        self.write(self.entries() + [('other/readme', b'late second root', tarfile.REGTYPE)])
        with self.assertRaises(ValueError):
            bindings.validate_archive(self.archive, 'arm64', 'phone')

    def test_nested_metadata_cannot_replace_missing_top_metadata_or_image(self):
        for missing in ('manifest.json', 'build-inputs.json', 'images/system.img'):
            entries = [row for row in self.entries() if row[0] != 'qemu/' + missing]
            self.write(entries + self.nested())
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                archive_inputs(self.archive, self.image)
            if missing == 'manifest.json':
                with self.assertRaises(ValueError):
                    root_probe.validate_archive(self.archive, 'arm64', 'phone')

    def test_duplicates_and_normalization_aliases_anywhere_are_rejected(self):
        for row in (self.entries()[0], self.nested()[0]):
            with self.subTest(duplicate=row[0]):
                self.reject_both(self.entries() + self.nested() + [row])
        for name in ('./qemu/extra', 'qemu//extra', 'qemu/./extra', 'qemu/a/../extra',
                     '/qemu/extra', 'qemu\\extra', 'qemu/line\nbreak', 'other/extra'):
            with self.subTest(alias=name):
                self.reject_both(self.entries() + [(name, b'late unsafe member', tarfile.REGTYPE)])

    def test_links_special_files_and_non_directory_roots_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE):
            with self.subTest(kind=kind):
                self.reject_both(self.entries() + [('qemu/late-entry', b'', kind)])
        self.reject_both([('qemu', b'not a directory', tarfile.REGTYPE)] + self.entries())
        self.reject_both(self.entries() + [('qemu/alias//', b'', tarfile.DIRTYPE)])

    def test_file_directory_collisions_in_both_orders_are_rejected(self):
        child = ('qemu/conflict/child', b'child', tarfile.REGTYPE)
        parent = ('qemu/conflict', b'file', tarfile.REGTYPE)
        for collision in ([parent, child], [child, parent]):
            self.reject_both(self.entries() + collision)
        self.write([('qemu', b'', tarfile.DIRTYPE)] + self.entries() +
                   [('qemu/images', b'', tarfile.DIRTYPE)])
        self.assertEqual(root_probe.validate_archive(self.archive, 'arm64', 'phone'), self.manifest)
        self.assertEqual(archive_inputs(self.archive, self.image)[3], self.inputs)

    def test_pax_path_alias_cannot_be_hidden_by_directory_normalization(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as package:
            for name, payload, kind in self.entries():
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                package.addfile(member, io.BytesIO(payload))
            member = tarfile.TarInfo('qemu/placeholder')
            member.type = tarfile.DIRTYPE
            member.pax_headers = {'path': 'qemu/alias//'}
            package.addfile(member)
        self.archive.write_bytes(gzip.compress(raw.getvalue()))
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            root_probe.validate_archive(self.archive, 'arm64', 'phone')
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            archive_inputs(self.archive, self.image)

    def test_valid_early_metadata_cannot_hide_a_later_bad_or_truncated_header(self):
        for tail in (b'not a tar header'.ljust(512, b'x') + b'\0' * 1024, b'partial header'):
            self.write(self.entries(), damaged_tail=tail)
            with self.subTest(tail_length=len(tail)), self.assertRaises(ValueError):
                root_probe.validate_archive(self.archive, 'arm64', 'phone')
            with self.assertRaises(ValueError):
                archive_inputs(self.archive, self.image)

    def test_metadata_size_and_entry_count_limits_remain_strict(self):
        for name, size in (('manifest.json', 1024**2 + 1), ('build-inputs.json', 16777216 + 1)):
            entries = [row for row in self.entries() if row[0] != 'qemu/' + name]
            entries.append(('qemu/' + name, b' ' * size, tarfile.REGTYPE))
            self.write(entries)
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive_inputs(self.archive, self.image)
            if name == 'manifest.json':
                with self.assertRaises(ValueError):
                    root_probe.validate_archive(self.archive, 'arm64', 'phone')
        self.write(self.entries() + self.nested())
        with patch.object(root_probe, 'MAX_PACKAGE_MEMBERS', 3):
            with self.assertRaises(ValueError):
                root_probe.validate_archive(self.archive, 'arm64', 'phone')
            with self.assertRaises(ValueError):
                archive_inputs(self.archive, self.image)
        header = tarfile.TarInfo('qemu/oversized')
        header.size = root_probe.MAX_PACKAGE_MEMBER_BYTES + 1
        self.write(self.entries(), damaged_tail=header.tobuf(format=tarfile.GNU_FORMAT))
        with self.assertRaisesRegex(ValueError, 'oversized'):
            root_probe.validate_archive(self.archive, 'arm64', 'phone')
        with self.assertRaisesRegex(ValueError, 'oversized'):
            archive_inputs(self.archive, self.image)

    def test_wrong_profile_or_image_cannot_borrow_nested_valid_metadata(self):
        for key, value in (('guest_arch', 'x86_64'), ('device_type', '2in1'),
                           ('device_type_profile', 'qemu_phone_minimal')):
            wrong = dict(self.manifest, **{key: value})
            entries = self.entries()
            entries[0] = ('qemu/manifest.json', json.dumps(wrong).encode(), tarfile.REGTYPE)
            with self.subTest(key=key):
                self.reject_both(entries + self.nested())
        self.write(self.entries() + self.nested())
        self.image.write_bytes(b'x' * self.image.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'system.img differs'):
            archive_inputs(self.archive, self.image)
        self.image.write_bytes(b'wrong length')
        with self.assertRaisesRegex(ValueError, 'length differs'):
            archive_inputs(self.archive, self.image)


if __name__ == '__main__':
    unittest.main()
