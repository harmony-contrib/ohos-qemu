"""Owned test-source copy fixtures, not Rust builds or device results."""
from pathlib import Path
import tempfile
import unittest

from snapshot_native_bindings import REQUIRED, snapshot


class NativeBindingsSnapshotTests(unittest.TestCase):
    def fixture(self, source):
        source.mkdir()
        for name in REQUIRED:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture actual editable source: ' + name)
        return source

    def test_copies_actual_source_changes_but_not_old_abi_or_list_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = self.fixture(root / 'original')
            for name in ('target/old.so', 'examples-ui/entry/libs/arm64-v8a/old.so',
                         'examples-ui/node_modules/package.js',
                         'examples-ui/entry/src/ohosTest/ets/test/.List.full.bak'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('old generated payload')
            result = snapshot(source, root / 'attempt')
            copied = Path(result['snapshot'])
            self.assertEqual(result['file_count'], len(REQUIRED))
            self.assertEqual((copied / REQUIRED[-1]).read_bytes(), (source / REQUIRED[-1]).read_bytes())
            self.assertFalse((copied / 'examples-ui/entry/libs').exists())
            self.assertFalse((copied / 'target').exists())
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_owned_fresh_destination_and_no_overlap_or_symlink_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = self.fixture(root / 'original')
            for output in (source, source / 'copy', root):
                with self.assertRaises((ValueError, FileExistsError)):
                    snapshot(source, output)
            outside = root / 'outside'
            outside.write_text('must not be read as source')
            (source / 'linked.rs').symlink_to(outside)
            with self.assertRaises(ValueError):
                snapshot(source, root / 'attempt')
            self.assertFalse((root / 'attempt').exists())


if __name__ == '__main__':
    unittest.main()
