"""Reject incomplete routing/receiver/pixel proofs using captured diagnostic data."""
import copy
import json
from pathlib import Path
import unittest
from verify_insight_navigation_results import verify, verify_receiver, verify_views

DIRECTORY = Path(__file__).parent / 'fixtures'
FIXTURE = json.loads((DIRECTORY / 'insight_navigation_diagnostic.json').read_text())


class InsightNavigationResultTests(unittest.TestCase):
    def check(self, role='system', rows=None):
        item = FIXTURE['roles'][role]
        text = item['raw_results'] if rows is None else '\n'.join(json.dumps(row) for row in rows) + '\n'
        return verify(text, item['run_id'], role, item['uid'], FIXTURE['metadata'], FIXTURE['target_nonce'])

    def rows(self):
        return [json.loads(line) for line in FIXTURE['roles']['system']['raw_results'].splitlines()]

    def receiver(self, targets=None, pages=None):
        item = FIXTURE['roles']['system']
        target_text = FIXTURE['target_results'] if targets is None else '\n'.join(json.dumps(row) for row in targets) + '\n'
        page_text = FIXTURE['page_results'] if pages is None else '\n'.join(json.dumps(row) for row in pages) + '\n'
        return verify_receiver(target_text, page_text, FIXTURE['target_nonce'], item['run_id'],
            item['uid'], FIXTURE['target_uid'], self.rows()[0]['values'][2])

    def views(self, phases=None):
        phases = copy.deepcopy(FIXTURE['phases']) if phases is None else phases
        for phase in phases:
            phase['layout'] = str(DIRECTORY / phase['layout'])
            phase['screenshot'] = str(DIRECTORY / phase['screenshot'])
        return verify_views(phases, FIXTURE['target_nonce'], FIXTURE['roles']['system']['run_id'])

    def test_actual_cold_page_warm_page_two_links_receiver_data_and_changed_pixels(self):
        for role in FIXTURE['roles']: self.check(role)
        self.assertEqual(len(self.receiver()['receiver_callbacks']), 4)
        metrics = self.views()
        self.assertGreaterEqual(metrics[1]['changed_text_pixels'], 10)
        self.assertGreaterEqual(metrics[3]['changed_text_pixels'], 10)

    def test_return_zero_and_metadata_alone_do_not_close_incomplete_dispatch(self):
        rows = self.rows()
        for changed in (rows[:-1], rows[:7] + rows[-1:], list(reversed(rows)), rows + rows[-1:]):
            with self.assertRaises(ValueError): self.check(rows=changed)
        for field, value in (('runId', 'b' * 32), ('role', 'normal'), ('values', [True]), ('error', 'failed')):
            changed = self.rows(); changed[4][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.check(rows=changed)
        for field, value in (('executeMode', 1), ('abilityName', 'absent'), ('insightIntentName', 'AuditEntry')):
            changed = self.rows(); parameter = json.loads(changed[3]['data']); parameter[field] = value
            changed[3]['data'] = json.dumps(parameter)
            with self.assertRaises(ValueError): self.check(rows=changed)
        changed = self.rows(); parameter = json.loads(changed[7]['data']); parameter['uris'] = ['audit://intent/old']
        changed[7]['data'] = json.dumps(parameter)
        with self.assertRaises(ValueError): self.check(rows=changed)

    def test_both_api_denials_must_be_native_numeric_role_specific_values(self):
        for role in ('normal', 'system-denied'):
            original = [json.loads(line) for line in FIXTURE['roles'][role]['raw_results'].splitlines()]
            for values in ([1, '202', 1], [1, 401, 1], [0, 0, 0], [1, 202 if role == 'system-denied' else 201, 1]):
                rows = copy.deepcopy(original); rows[2]['values'] = values
                with self.assertRaises(ValueError): self.check(role, rows)

    def test_receiver_challenge_requires_real_native_caller_and_page_lifecycle_data(self):
        original = [json.loads(line) for line in FIXTURE['target_results'].splitlines()]
        for field, value in (('ohos.aafwk.param.callerUid', 0), ('ohos.aafwk.param.callerPid', 1),
                ('ohos.aafwk.param.callerBundleName', 'another.bundle'), ('isShellCall', True),
                ('ohos.insightIntent.executeParam.mode', 1)):
            targets = copy.deepcopy(original)
            for row in targets:
                if row['want'].get('parameters', {}).get('ohos.insightIntent.executeParam.name') == 'AuditPage':
                    row['want']['parameters'][field] = value; break
            with self.subTest(field=field), self.assertRaises(ValueError): self.receiver(targets=targets)
        for changed in (original[:-1], original + [original[-1]]):
            with self.assertRaises(ValueError): self.receiver(targets=changed)
        pages = [json.loads(line) for line in FIXTURE['page_results'].splitlines()]
        pages[-1]['value'] = pages[-2]['value']
        with self.assertRaises(ValueError): self.receiver(pages=pages)

    def test_old_reused_pixel_or_missing_navigation_phase_is_rejected(self):
        phases = copy.deepcopy(FIXTURE['phases']); phases[1]['screenshot'] = phases[0]['screenshot']
        with self.assertRaises(ValueError): self.views(phases)
        phases = copy.deepcopy(FIXTURE['phases']); phases[3]['screenshot'] = phases[2]['screenshot']
        with self.assertRaises(ValueError): self.views(phases)
        with self.assertRaises(ValueError): self.views(copy.deepcopy(FIXTURE['phases'][:-1]))


if __name__ == '__main__':
    unittest.main()
