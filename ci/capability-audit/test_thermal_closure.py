"""Outer thermal closure binding only; actual parsers have separate negative tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verify_gap_closure import behavior_results

IDENTIFIER = 'behavior:thermal-backend-zero-data'


class ThermalClosureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='thermal-closure-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'boot').mkdir()
        (self.root / 'thermal').mkdir()
        self.boot = {'status': 'pass', 'purpose': 'acceptance',
            'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate', 'archive_sha256': 'a' * 64,
            'test_environment': {'boot_id': 'fixture-boot', 'guest_arch': 'arm64',
                'device_type': 'phone', 'external_keepalive': False}}
        self.document = {'status': 'pass', 'archive_sha256': 'a' * 64, 'boot_id': 'fixture-boot'}
        self.save()

    def save(self):
        (self.root / 'boot/boot.json').write_text(json.dumps(self.boot))
        (self.root / 'thermal/evidence.json').write_text(json.dumps(self.document))

    def check(self):
        return behavior_results(self.root, 'fixture-boot', 'a' * 64, 'phone')

    def test_only_real_sensor_gap_closes_and_strict_inner_replay_required(self):
        with patch('verify_thermal_results.verify_evidence') as inner:
            result = self.check()
            self.assertEqual(set(result), {IDENTIFIER})
            inner.assert_called_once_with(self.document, 'a' * 64, 'fixture-boot', 'arm64')
            self.assertIn('hot_transitions', result[IDENTIFIER]['not_claimed'])
        with patch('verify_thermal_results.verify_evidence', side_effect=ValueError('raw failed')):
            with self.assertRaisesRegex(ValueError, 'raw failed'): self.check()

    def test_assisted_diagnostic_or_wrong_boot_cannot_close(self):
        original = deepcopy(self.boot)
        for change in ({'purpose': 'diagnostic'}, {'status': 'fail'}, {'archive_sha256': 'b' * 64},
                       {'scope': 'other'}, {'candidate_kernel': 'replacement'}, {'diagnostic_assistance': True},
                       {'diagnostic_power_button': True}, {'kernel_command_line_diagnostic': ['extra']}):
            self.boot = dict(original, **change)
            self.save()
            with self.assertRaises(ValueError): self.check()
        for change in ({'external_keepalive': True}, {'boot_id': 'old'}, {'device_type': '2in1'}):
            self.boot = deepcopy(original)
            self.boot['test_environment'].update(change)
            self.save()
            with self.assertRaises(ValueError): self.check()

    def test_missing_or_wrong_child_stays_unresolved(self):
        for change in ({'status': 'fail'}, {'archive_sha256': 'b' * 64}, {'boot_id': 'old'}):
            original = self.document.copy()
            self.document.update(change)
            self.save()
            self.assertNotIn(IDENTIFIER, self.check())
            self.document = original
        (self.root / 'thermal/evidence.json').unlink()
        self.assertNotIn(IDENTIFIER, self.check())


if __name__ == '__main__':
    unittest.main()
