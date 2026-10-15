"""Rejection tests from captured native journals and compositor images, not a gate."""
import copy
import json
from pathlib import Path
import unittest
from verify_insight_form_host_results import verify, verify_provider, verify_pixels, verify_layout

DIRECTORY = Path(__file__).parent / 'fixtures'
FIXTURE = json.loads((DIRECTORY / 'insight_form_diagnostic.json').read_text())


class InsightFormHostResultTests(unittest.TestCase):
    def check(self, role='system', observations=None):
        item = FIXTURE['roles'][role]
        text = item['raw_results'] if observations is None else '\n'.join(json.dumps(row) for row in observations) + '\n'
        return verify(text, item['caller_nonce'], role, item['uid'])

    def observations(self):
        return [json.loads(line) for line in FIXTURE['roles']['system']['raw_results'].splitlines()]

    def pixels(self, phase=None, initial=None, updated=None):
        phase = phase or FIXTURE['phases'][0]
        return verify_pixels(initial or DIRECTORY / phase['acquired_image'],
            updated or DIRECTORY / phase['updated_image'], phase['acquired_layout'], phase['updated_layout'],
            FIXTURE['target_nonce'], phase['form_id'])

    def test_captured_two_distinct_native_lifecycles_and_real_compositor_data_changes(self):
        identifiers = self.check()
        self.assertEqual(identifiers, [phase['form_id'] for phase in FIXTURE['phases']])
        verify_provider(FIXTURE['roles']['system']['provider_results'], FIXTURE['target_nonce'], identifiers)
        for phase in FIXTURE['phases']:
            self.assertGreaterEqual(self.pixels(phase)['changed_text_pixels'], 10)

    def test_partial_duplicate_foreign_wrong_id_or_missing_delete_boundary_rejected(self):
        rows = self.observations()
        for changed in (rows[:-1], rows[:9], rows + [rows[-1]], list(reversed(rows))):
            with self.assertRaises(ValueError): self.check(observations=changed)
        for field, value in (('runId', 'b' * 32), ('role', 'normal'), ('values', [True]),
                ('data', 'old-id'), ('error', 'failed'), ('cycle', True)):
            changed = self.observations(); changed[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.check(observations=changed)
        changed = self.observations(); next(row for row in changed if row['name'] == 'deleted.reject')['values'] = [1, 401, 1]
        with self.assertRaises(ValueError): self.check(observations=changed)
        changed = self.observations()
        old_id = changed[1]['data']
        for row in changed:
            if row['cycle'] == 1 and row['data']: row['data'] = old_id
        with self.assertRaises(ValueError): self.check(observations=changed)

    def test_permission_roles_must_be_native_numeric_and_cannot_create_provider_callbacks(self):
        for role, code in (('normal', 202), ('system-denied', 201)):
            self.assertEqual(self.check(role), [])
            self.assertEqual(FIXTURE['roles'][role]['provider_results'], '')
            for values in ([1, str(code), 1], [1, 401, 1], [0, 0, 0], [1, code, 0]):
                rows = [json.loads(line) for line in FIXTURE['roles'][role]['raw_results'].splitlines()]
                rows[1]['values'] = values
                with self.assertRaises(ValueError): self.check(role, rows)

    def test_provider_completion_and_removal_are_required_for_each_actual_created_id(self):
        original = [json.loads(line) for line in FIXTURE['roles']['system']['provider_results'].splitlines()]
        for changed in (original[:-1], original[:4], original + original[-1:], list(reversed(original))):
            with self.assertRaises(ValueError):
                verify_provider('\n'.join(json.dumps(row) for row in changed) + '\n',
                    FIXTURE['target_nonce'], self.check())
        changed = copy.deepcopy(original); changed[2]['name'] = 'update.failed.201'
        with self.assertRaises(ValueError):
            verify_provider('\n'.join(json.dumps(row) for row in changed) + '\n', FIXTURE['target_nonce'], self.check())

    def test_hierarchy_success_with_white_or_unchanged_pixels_is_rejected(self):
        with self.assertRaises(ValueError):
            self.pixels(initial=DIRECTORY / 'insight_form_diagnostic_unpresented_white.png')
        phase = FIXTURE['phases'][0]
        with self.assertRaises(ValueError): self.pixels(updated=DIRECTORY / phase['acquired_image'])
        with self.assertRaises(ValueError):
            verify_layout(phase['updated_layout'], 'b' * 32, phase['form_id'], 'updated')
        with self.assertRaises(ValueError):
            verify_layout(phase['acquired_layout'], FIXTURE['target_nonce'], phase['form_id'], 'updated')


if __name__ == '__main__':
    unittest.main()
