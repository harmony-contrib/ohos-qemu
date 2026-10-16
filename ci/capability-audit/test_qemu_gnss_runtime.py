"""Strict GNSS runtime installation transactions; no hardware/runtime claims."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_qemu_gnss_runtime as M


class GnssRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.build = self.root / M.BUILD
        self.build.parent.mkdir(parents=True)
        self.build.write_bytes((ROOT / 'ci/capability-audit/fixtures/gnss_runtime/BUILD.gn').read_bytes())

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_exact_target_mode_init_identity_and_complete_reapply(self):
        value = M.apply(self.root)
        self.assertFalse(value['first_artifact_behavior_gate_passed'])
        first = self.snapshot()
        self.assertEqual(self.build.read_text().count(M.DEPENDENCY), 1)
        cfg = (self.root / M.DIRECTORY / 'qemu_gnss_input.cfg').read_text()
        self.assertIn('0700 location_host location_host', cfg)
        self.assertEqual((self.root / M.DIRECTORY / 'qemu_gnss.para').read_text(), 'const.location.supl_mode=1\n')
        self.assertIn('qemu_external_gnss', (self.root / M.DIRECTORY / 'BUILD.gn').read_text())
        M.apply(self.root)
        self.assertEqual(first, self.snapshot())

    def test_unknown_or_partial_edits_are_preserved_before_any_writes(self):
        M.apply(self.root)
        for name in [M.BUILD, *M.FILES]:
            path = self.root / name
            saved = path.read_bytes()
            path.write_bytes(saved + b'caller change')
            before = self.snapshot()
            with self.assertRaises(ValueError): M.apply(self.root)
            self.assertEqual(before, self.snapshot())
            path.write_bytes(saved)

    def test_publish_failure_restores_all_previous_sources(self):
        before = self.snapshot()
        real = M.replace
        count = 0
        def fail_once(path, value):
            nonlocal count
            count += 1
            if count == 4: raise OSError('injected write failure')
            real(path, value)
        with patch.object(M, 'replace', fail_once), self.assertRaises(OSError): M.apply(self.root)
        self.assertEqual(before, self.snapshot())

    def test_alias_rejected_without_changing_external_files(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.root / M.DIRECTORY).symlink_to(outside, target_is_directory=True)
        before = self.snapshot()
        with self.assertRaises(ValueError): M.apply(self.root)
        self.assertEqual(before, self.snapshot())
        self.assertEqual([], list(outside.iterdir()))


if __name__ == '__main__': unittest.main()
