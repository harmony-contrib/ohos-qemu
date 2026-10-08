"""Cache/source mount boundaries; not Photos producer or guest acceptance."""
import errno
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/photos/source_provider'
saved_path, saved_verifier = list(sys.path), sys.modules.pop('verify_source', None)
try:
    sys.path.insert(0, str(COMPONENT))
    spec = importlib.util.spec_from_file_location('photos_dependencies', COMPONENT / 'prepare_dependencies.py')
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
finally:
    sys.path[:] = saved_path
    sys.modules.pop('verify_source', None)
    if saved_verifier is not None:
        sys.modules['verify_source'] = saved_verifier


class PhotosDependencyInstall(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='photos-cross-mount-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache, self.source = self.root / 'cache', self.root / 'source'
        self.cache.mkdir()
        self.source.mkdir()
        self.asset = self.cache / 'jsoncpp'
        self.asset.mkdir()
        (self.asset / 'actual.cpp').write_bytes(b'actual verified source fixture')

    def cross_mount(self, original):
        def action(path, target):
            if self.cache in path.parents and self.source in target.parents:
                raise OSError(errno.EXDEV, 'simulated distinct cache/source filesystems')
            return original(path, target)
        return action

    def test_source_install_uses_source_filesystem_staging(self):
        destination = self.source / 'jsoncpp'
        original = Path.rename
        with patch.object(Path, 'rename', self.cross_mount(original)):
            producer.install_tree(self.asset, destination)
        self.assertEqual(producer.tree(self.asset), producer.tree(destination))
        self.assertEqual(set(self.source.iterdir()), {destination})

    def test_existing_or_redirected_source_preserved(self):
        destination = self.source / 'jsoncpp'
        destination.mkdir()
        (destination / 'owned.cpp').write_bytes(b'user change')
        before = producer.tree(destination)
        with self.assertRaises(ValueError):
            producer.install_tree(self.asset, destination)
        self.assertEqual(before, producer.tree(destination))
        redirected = self.source / 'redirect'
        redirected.symlink_to(self.asset, target_is_directory=True)
        with self.assertRaises(ValueError):
            producer.install_tree(self.asset, redirected)

    def test_copy_failure_never_leaves_partial_managed_source(self):
        destination = self.source / 'jsoncpp'
        with patch.object(producer.shutil, 'copytree', side_effect=OSError('interrupted copy')):
            with self.assertRaises(OSError):
                producer.install_tree(self.asset, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.source.iterdir()), [])

    def test_profile_replace_staged_on_source_and_mode_preserved(self):
        signed, destination = self.cache / 'signed.p7b', self.source / 'photos.p7b'
        signed.write_bytes(b'new verified profile')
        destination.write_bytes(b'original profile fixture')
        destination.chmod(0o644)
        checksum = producer.sha(destination)
        original = Path.replace
        with patch.object(producer, 'PROFILE_SHA', checksum), patch.object(Path, 'replace', self.cross_mount(original)):
            producer.install_profile(signed, destination)
        self.assertEqual(destination.read_bytes(), signed.read_bytes())
        self.assertEqual(destination.stat().st_mode & 0o777, 0o644)
        self.assertEqual(set(self.source.iterdir()), {destination})

    def test_unknown_profile_never_overwritten(self):
        signed, destination = self.cache / 'signed.p7b', self.source / 'photos.p7b'
        signed.write_bytes(b'new profile')
        destination.write_bytes(b'user profile change')
        with self.assertRaises(ValueError):
            producer.install_profile(signed, destination)
        self.assertEqual(destination.read_bytes(), b'user profile change')
        self.assertEqual(set(self.source.iterdir()), {destination})


if __name__ == '__main__':
    unittest.main()
