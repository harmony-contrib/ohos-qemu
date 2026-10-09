"""Strict observations and independent process/UI evidence, never fixture closure."""
import copy
import json
from pathlib import Path
import unittest

from run_normal_hap_probe import PERSONAS, verifier_arguments
from verify_settings_navigation_results import settings_identity, verify_rows

NONCE = '1234567890abcdef' * 2


class SettingsResultsTests(unittest.TestCase):
    def setUp(self):
        self.methods = [{'name': 'real.ime', 'id': 'ServiceExtAbility', 'label': 'real input'}]
        names = ['installed-input-methods', 'empty-identity.0', 'empty-identity.1', 'ready']
        names += ['input.request-returned', 'detail.request-returned'] * 2
        values = [json.dumps(self.methods), '{"code":16900010}', '{"code":16900010}', 'UI required']
        values += ['void-return-only-not-render-proof', json.dumps(self.methods[0])] * 2
        self.rows = [dict(runId=NONCE, sequence=i + 1, name=name, value=value, **{'pass': True})
                     for i, (name, value) in enumerate(zip(names, values))]

    def verify(self, rows, **kwargs):
        return verify_rows('\n'.join(map(json.dumps, rows)), NONCE, **kwargs)

    def test_complete_calls_do_not_claim_ui_or_whole_settings(self):
        result = self.verify(self.rows)
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['observations'], 8)
        self.assertNotIn('ui', result)
        self.assertEqual(self.verify(self.rows[:4], startup=True)['observations'], 4)

    def test_stale_incomplete_duplicate_failure_rejected(self):
        for rows in (self.rows[:-1], self.rows + self.rows, list(reversed(self.rows))):
            with self.assertRaises(ValueError):
                self.verify(rows)
        for key, value in (('runId', 'a' * 32), ('pass', False), ('sequence', True)):
            rows = copy.deepcopy(self.rows)
            rows[0][key] = value
            with self.assertRaises(ValueError):
                self.verify(rows)

    def test_actual_ime_and_exact_error_required(self):
        for index, value in ((0, '[]'), (0, '[{}]'), (1, '{"code":401}'), (1, 'null'),
                             (2, '{"code":"16900010"}'), (5, '{"name":"other"}')):
            rows = copy.deepcopy(self.rows)
            rows[index]['value'] = value
            with self.assertRaises(ValueError):
                self.verify(rows)

    def test_settings_identity_never_accepts_elevated_test_caller(self):
        info = {'name': 'com.ohos.settings', 'uid': 20010011,
                'isSystemApp': True, 'appPrivilegeLevel': 'system_basic'}
        self.assertEqual(settings_identity(json.dumps({'applicationInfo': info})), 20010011)
        for key, value in (('name', 'other'), ('uid', 10011), ('isSystemApp', False),
                           ('appPrivilegeLevel', 'system_core')):
            with self.assertRaises(ValueError):
                settings_identity(json.dumps({'applicationInfo': dict(info, **{key: value})}))

    def test_repository_runner_builds_fresh_caller_and_requires_ui(self):
        self.assertEqual(PERSONAS['settings-navigation'][0], '--settings-navigation-only')
        args = verifier_arguments('settings-navigation', Path('/package'), Path('/results'),
                                  Path('/identity'), NONCE, 'arm64', Path('/output'))
        self.assertIn('--application-identity', args)
        self.assertIn('--arch', args)
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn('from settings_navigation_ui import exercise', source)
        self.assertIn("'--sdk', str(args.sdk)", source)

    def test_both_profiles_and_independent_gate_require_settings(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('settings-navigation', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("'camera', 'settings-navigation', 'photos-recent'", suite)
        self.assertIn("check('settings-navigation', path, [record])", suite)
        gate = Path(__file__).resolve().parents[2] / 'scripts/verify_first_artifact_gate.py'
        self.assertIn('from verify_settings_navigation_results import verify_evidence', gate.read_text())


if __name__ == '__main__':
    unittest.main()
