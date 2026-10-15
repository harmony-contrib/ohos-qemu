"""Fail closed on tampered or unsafe external backend source archives."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('openvpn_builder', ROOT / 'scripts/build_openvpn_ohos.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class OpenvpnSourceArchiveTests(unittest.TestCase):
    def archive(self, directory, entries):
        path = directory / 'source.tar.gz'
        with tarfile.open(path, 'w:gz') as target:
            for name, content, kind in entries:
                member = tarfile.TarInfo(name)
                member.mode = 0o755
                if kind == 'symlink':
                    member.type = tarfile.SYMTYPE
                    member.linkname = '../../outside'
                    target.addfile(member)
                else:
                    member.size = len(content)
                    target.addfile(member, io.BytesIO(content))
        return path

    def lock(self, archive):
        return {'archive_bytes': archive.stat().st_size,
                'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'commit': 'fixed', 'license_file': 'COPYING',
                'license_file_sha256': hashlib.sha256(b'actual-license').hexdigest()}

    def test_exact_archive_license_and_executable_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [('openvpn-fixed/COPYING', b'actual-license', 'file'),
                                          ('openvpn-fixed/tool', b'executable-source', 'file')])
            result = BUILDER.extract_source(archive, root / 'out', self.lock(archive))
            self.assertEqual((result / 'tool').read_bytes(), b'executable-source')
            self.assertEqual((result / 'tool').stat().st_mode & 0o777, 0o755)

    def test_archive_tampering_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [('openvpn-fixed/COPYING', b'actual-license', 'file')])
            lock = self.lock(archive)
            archive.write_bytes(archive.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'exact pinned'):
                BUILDER.extract_source(archive, root / 'out', lock)
            self.assertFalse((root / 'out').exists())

    def test_unsafe_paths_links_and_foreign_roots_are_rejected(self):
        for name, kind in [('openvpn-fixed/../../outside', 'file'), ('/outside', 'file'),
                           ('other/COPYING', 'file'), ('openvpn-fixed/link', 'symlink')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self.archive(root, [(name, b'payload', kind)])
                with self.assertRaisesRegex(ValueError, 'unexpected paths'):
                    BUILDER.extract_source(archive, root / 'out', self.lock(archive))
                self.assertFalse((root / 'outside').exists())

    def test_existing_files_and_changed_license_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [('openvpn-fixed/COPYING', b'changed-license', 'file')])
            with self.assertRaisesRegex(ValueError, 'license identity'):
                BUILDER.extract_source(archive, root / 'out', self.lock(archive))
            with self.assertRaises(FileExistsError):
                BUILDER.extract_source(archive, root / 'out', self.lock(archive))

    def test_invalid_later_member_does_not_leave_an_extracted_prefix(self):
        for entries in ([('openvpn-fixed/COPYING', b'actual-license', 'file'),
                         ('openvpn-fixed/../../outside', b'bad', 'file')],
                        [('openvpn-fixed/COPYING', b'actual-license', 'file'),
                         ('openvpn-fixed/COPYING', b'duplicate', 'file')]):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self.archive(root, entries)
                with self.assertRaisesRegex(ValueError, 'unexpected paths'):
                    BUILDER.extract_source(archive, root / 'out', self.lock(archive))
                self.assertFalse((root / 'out').exists())
