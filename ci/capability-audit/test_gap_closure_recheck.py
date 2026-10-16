"""Synthetic serial/ledger fixtures exercise raw rechecking, never a real guest."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_gap_closure as closure
from run_backup_init_probe import run as backup_run
from run_root_probe import digest
from test_backup_init_results import GOOD


class ClosureRecheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / 'synthetic.tar.gz'; self.archive.write_bytes(b'structure-only unit archive')
        self.boot = self.root / 'boot/boot.json'; self.boot.parent.mkdir()
        self.boot.write_text(json.dumps({'status': 'pass', 'purpose': 'acceptance',
            'archive_sha256': digest(self.archive), 'test_environment': {
                'device_type': 'phone', 'boot_id': 'fresh', 'external_keepalive': False}}))
        (self.boot.parent / 'qemu.log').write_text(GOOD)
        backup_run(self.archive, self.boot, self.root / 'backup-init')
        # Restrict the synthetic requirement set to the real serial verifier.
        # No behavior function, raw parser or digest is mocked.
        p = patch.object(closure, 'requirements', return_value={
            'behavior:backup-init-invalid-linux-capability': {'id': 'backup-init-invalid-linux-capability'}})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(closure, 'exclusion_record', return_value={'ids': []})
        p.start(); self.addCleanup(p.stop)
        self.summary = closure.collect(self.archive, self.boot, self.root, 'phone')
        self.assertEqual(self.summary['status'], 'pass')

    def verify(self, value=None):
        return closure.verify_evidence(self.summary if value is None else value,
                                       self.archive, self.boot, self.root, 'phone')

    def test_current_raw_serial_is_required_even_when_summary_does_not_change(self):
        self.assertEqual(self.verify(), self.summary)
        serial = self.root / 'backup-init/serial.log'
        serial.write_text(GOOD.replace('1480', '1481'))
        with self.assertRaisesRegex(ValueError, 'raw proofs'):
            self.verify()
        serial.unlink()
        with self.assertRaisesRegex(ValueError, 'raw proofs'):
            self.verify()

    def test_deleted_or_old_guest_child_does_not_close_retained_summary(self):
        path = self.root / 'backup-init/evidence.json'
        value = json.loads(path.read_text()); value['boot_id'] = 'old-guest'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'raw proofs'):
            self.verify()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'raw proofs'):
            self.verify()

    def test_all_closure_records_are_recomputed_not_just_closed_identifiers(self):
        value = deepcopy(self.summary)
        value['closed'][next(iter(value['closed']))]['verifier'] = 'invented-verifier'
        with self.assertRaisesRegex(ValueError, 'raw proofs'):
            self.verify(value)

    def test_wrong_archive_or_boot_root_is_refused(self):
        self.archive.write_bytes(b'changed archive')
        with self.assertRaisesRegex(ValueError, 'actual new unassisted'):
            self.verify()
        other = self.root / 'other-boot.json'; other.write_bytes(self.boot.read_bytes())
        with self.assertRaisesRegex(ValueError, 'exact runtime'):
            closure.collect(self.archive, other, self.root, 'phone')


if __name__ == '__main__': unittest.main()
