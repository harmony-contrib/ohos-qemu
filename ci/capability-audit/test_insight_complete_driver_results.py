"""Reject partial native dispatch evidence using the immutable captured diagnostic."""
import copy
import json
from pathlib import Path
import unittest
from verify_insight_complete_driver_results import verify

FIXTURE = json.loads((Path(__file__).parent /
    'fixtures/insight_complete_driver_system_diagnostic.json').read_text())


class InsightCompleteDriverResultTests(unittest.TestCase):
    def rows(self):
        return [json.loads(line) for line in FIXTURE['raw_results'].splitlines()]

    def check(self, rows=None, role='system'):
        raw = FIXTURE['raw_results'] if rows is None else '\n'.join(json.dumps(row) for row in rows) + '\n'
        return verify(raw, FIXTURE['caller_nonce'], role, FIXTURE['uid'], FIXTURE['metadata'], FIXTURE['target_nonce'])

    def test_captured_two_native_entry_and_two_static_method_dispatches(self):
        self.assertEqual(len(self.check()), 8)

    def test_prior_entry_only_metadata_or_a_single_method_cannot_close_both_decorators(self):
        rows = self.rows()
        for changed in (rows[:5] + rows[-1:], rows[:6] + rows[-1:], rows[:-1], list(reversed(rows))):
            with self.assertRaises(ValueError): self.check(changed)
        for field, value in (('runId', 'b' * 32), ('role', 'normal'), ('error', 'failed'), ('values', [True]),
                ('data', json.dumps({'methodResult': 'pretend success'}))):
            changed = self.rows(); changed[5][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.check(changed)
        changed = self.rows(); changed[6]['data'] = changed[5]['data']
        with self.assertRaises(ValueError): self.check(changed)

    def test_dispatch_return_must_be_native_zero_and_exact_boxed_json_challenge(self):
        for value in ({'methodResult': FIXTURE['caller_nonce'] + ':0:echo'},
                {'methodResult': json.dumps('old:0:echo')}, {'methodResult': json.dumps(FIXTURE['caller_nonce'] + ':1:echo')},
                {'methodResult': json.dumps(FIXTURE['caller_nonce'] + ':0:echo'), 'extra': True}):
            changed = self.rows(); changed[5]['data'] = json.dumps(value)
            with self.assertRaises(ValueError): self.check(changed)
        changed = self.rows(); changed[6]['values'] = [1]
        with self.assertRaises(ValueError): self.check(changed)

    def test_all_three_denial_methods_require_numeric_role_specific_permissions(self):
        for role, code in (('normal', 202), ('system-denied', 201)):
            rows = self.rows()[:1]; rows[0]['role'] = role
            rows += [dict(runId=FIXTURE['caller_nonce'], role=role, name='denied.' + str(method),
                values=[1, code, 1], data='', error='') for method in range(3)]
            rows.append(dict(runId=FIXTURE['caller_nonce'], role=role, name='summary', values=[1], data='', error=''))
            self.check(rows, role)
            for values in ([1, str(code), 1], [0, 0, 0], [1, code, 0], [1, 401, 1]):
                changed = copy.deepcopy(rows); changed[3]['values'] = values
                with self.assertRaises(ValueError): self.check(changed, role)


if __name__ == '__main__':
    unittest.main()
