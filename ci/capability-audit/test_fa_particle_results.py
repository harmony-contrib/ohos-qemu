import copy
import json
from pathlib import Path
import unittest
from verify_fa_particle_results import BUNDLE, NAMES, verify

NONCE = '1234567890abcdef' * 2


class FaParticleResultTests(unittest.TestCase):
    def setUp(self):
        self.identity = json.dumps({'applicationInfo': {
            'bundleName': BUNDLE, 'uid': 20010043, 'isSystemApp': False, 'appPrivilegeLevel': 'normal'}})
        self.rows = [dict(nonce=NONCE, name=name, status='pass', value=value) for name, value in zip(NAMES, (
            {'INVALID_PARAMETER': -1}, {'bundleName': BUNDLE, 'name': BUNDLE + '.ParticleService', 'type': 2,
                                      'contextPresent': True},
            {'bundleName': BUNDLE, 'name': BUNDLE + '.ParticleService', 'type': 2}, BUNDLE + '.ParticleService', 'FA'))]

    def run_rows(self, rows, nonce=NONCE, identity=None):
        return verify('\n'.join('log QEMU_FA_PARTICLE:' + json.dumps(row) for row in rows),
                      nonce, identity or self.identity)

    def test_complete_fa_does_not_claim_stage_or_whole_gap(self):
        result = self.run_rows(self.rows)
        self.assertEqual(result['observations'], 5)
        self.assertEqual(result['closed'], [])
        self.assertIn('same-archive Stage regression', result['requires'])

    def test_missing_constant_or_false_success_rejected(self):
        for value in (None, {}, {'INVALID_PARAMETER': 401}, {'INVALID_PARAMETER': '-1'},
                      {'INVALID_PARAMETER': -1, 'EXTRA': 2}):
            with self.subTest(value=value):
                rows = copy.deepcopy(self.rows)
                rows[0]['value'] = value
                with self.assertRaises(ValueError):
                    self.run_rows(rows)

    def test_missing_duplicate_reordered_and_exception_rejected(self):
        for rows in (self.rows[:-1], self.rows + self.rows, list(reversed(self.rows)),
                     self.rows + [dict(nonce=NONCE, name='exception', status='fail', value={})]):
            with self.assertRaises(ValueError):
                self.run_rows(rows)
        for i in range(len(self.rows)):
            rows = copy.deepcopy(self.rows)
            rows[i]['status'] = 'fail'
            with self.assertRaises(ValueError):
                self.run_rows(rows)

    def test_stale_nonce_and_wrong_context_rejected(self):
        with self.assertRaises(ValueError):
            self.run_rows(self.rows, nonce='a' * 32)
        rows = copy.deepcopy(self.rows)
        rows[1]['value']['bundleName'] = 'another.application'
        with self.assertRaises(ValueError):
            self.run_rows(rows)
        rows = copy.deepcopy(self.rows)
        rows[3]['value'] = 'different.MainAbility'
        with self.assertRaises(ValueError):
            self.run_rows(rows)

    def test_builder_requires_real_legacy_tasks_and_inspects_actual_hap(self):
        source = Path(__file__).with_name('build_fa_particle_probe.py').read_text()
        for expected in ('legacyAppTasks', 'legacyHapTasks', "'apiType': 'faMode'",
                         "archive.read('config.json')", "config['module'].get('reqPermissions', [])"):
            self.assertIn(expected, source)

    def test_page_context_and_null_particle_context_cannot_substitute_for_service(self):
        for index, value in ((1, {'bundleName': BUNDLE, 'name': BUNDLE + '.MainAbility', 'type': 1}),
                             (1, {'bundleName': BUNDLE, 'name': BUNDLE + '.ParticleService', 'type': 2,
                                  'contextPresent': False}),
                             (2, None), (2, 'context'), (2, {'bundleName': BUNDLE,
                              'name': BUNDLE + '.ParticleService', 'type': True})):
            rows = copy.deepcopy(self.rows)
            rows[index]['value'] = value
            with self.assertRaises(ValueError):
                self.run_rows(rows)


if __name__ == '__main__':
    unittest.main()
