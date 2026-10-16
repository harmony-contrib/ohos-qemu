"""Real shared GN ownership, optional source provenance and atomic rollback."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_qemu_sensor_runtime as S
import prepare_qemu_knowledge_resource as M


class KnowledgeResourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        path = self.root / S.BUILD
        path.parent.mkdir(parents=True)
        path.write_bytes((ROOT / 'ci/capability-audit/fixtures/core/qemu_sensor/BUILD.gn').read_bytes())
        S.apply(self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_absence_creates_real_config_directory_without_dates_and_both_reapply(self):
        M.apply(self.root)
        self.assertFalse((self.root / M.ASSET).exists())
        value = json.loads((self.root / M.CONTRACT).read_text())
        self.assertIsNone(value['asset_sha256'])
        first = self.snapshot()
        S.apply(self.root)
        M.apply(self.root)
        self.assertEqual(first, self.snapshot())

    def test_explicit_external_bytes_bound_and_retained_with_complete_shared_GN(self):
        # A labeled synthetic configuration tests the importer, not a real-world holiday date.
        asset = self.root / 'synthetic-input.ics'
        data = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n'
        asset.write_bytes(data)
        result = M.apply(self.root, asset)
        self.assertEqual((self.root / M.ASSET).read_bytes(), data)
        self.assertEqual(result['asset']['asset_sha256'], hashlib.sha256(data).hexdigest())
        first = self.snapshot()
        S.apply(self.root)
        M.apply(self.root)
        self.assertEqual(first, self.snapshot())
        (self.root / M.ASSET).write_bytes(data + b'edited')
        broken = self.snapshot()
        with self.assertRaises(ValueError):
            M.apply(self.root)
        self.assertEqual(broken, self.snapshot())

    def test_symlink_partial_and_publication_failure_preserve_all_prior_inputs(self):
        first = self.snapshot()
        original = S.replace
        count = 0
        def fail_second(path, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected atomic publication failure')
            original(path, data)
        with patch.object(S, 'replace', side_effect=fail_second), self.assertRaises(OSError):
            M.apply(self.root)
        self.assertEqual(first, self.snapshot())
        path = self.root / M.CONTRACT
        path.symlink_to(self.root / S.BUILD)
        with self.assertRaises(ValueError):
            M.apply(self.root)
        path.unlink()
        path.write_text('unmanaged caller data')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            M.apply(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
