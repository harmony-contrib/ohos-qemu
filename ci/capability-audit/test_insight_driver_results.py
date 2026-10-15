"""Strict rejection tests from captured diagnostic records, not guest acceptance."""
import copy
import json
from pathlib import Path
import unittest
from verify_insight_driver_results import verify

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/insight_driver_system_diagnostic.json').read_text())


class InsightDriverResultTests(unittest.TestCase):
    def check(self, rows=None, role='system'):
        raw = FIXTURE['raw_results'] if rows is None else '\n'.join(json.dumps(row) for row in rows) + '\n'
        return verify(raw, FIXTURE['caller_nonce'], role, FIXTURE['uid'],
                      FIXTURE['metadata'], FIXTURE['target_nonce'])

    def rows(self):
        return [json.loads(line) for line in FIXTURE['raw_results'].splitlines()]

    def test_actual_diagnostic_five_records_and_two_distinct_executions(self):
        self.assertEqual(len(self.check()), 6)

    def test_partial_reordered_foreign_and_self_reported_success_rejected(self):
        rows = self.rows()
        for changed in (rows[:-1], rows + [rows[-1]], rows[:2] + rows[3:], list(reversed(rows))):
            with self.assertRaises(ValueError): self.check(changed)
        for field, value in (('runId', 'b' * 32), ('role', 'normal'), ('error', 'failed'), ('values', [True])):
            changed = self.rows(); changed[2][field] = value
            with self.assertRaises(ValueError): self.check(changed)
        changed = self.rows(); changed[3]['data'] = changed[2]['data']
        with self.assertRaises(ValueError): self.check(changed)

    def test_count_alone_does_not_close_missing_or_wrong_registered_metadata(self):
        for mutation in ('missing', 'duplicate', 'bundle', 'entity', 'link', 'form', 'entry-mode', 'function-schema'):
            rows = self.rows(); infos = json.loads(rows[1]['data'])
            mapping = {row['intentName']: row for row in infos}
            if mutation == 'missing': infos.pop()
            elif mutation == 'duplicate': infos[-1] = copy.deepcopy(infos[0])
            elif mutation == 'bundle': infos[0]['bundleName'] = 'another.bundle'
            elif mutation == 'entity': mapping['AuditEntry']['entities'] = []
            elif mutation == 'link': mapping['AuditLink']['subIntentInfo']['uri'] = 'audit://intent/old'
            elif mutation == 'form': mapping['AuditForm']['subIntentInfo']['formName'] = 'unregistered'
            elif mutation == 'entry-mode': mapping['AuditEntry']['subIntentInfo']['executeMode'] = [0]
            else: mapping['AuditFunction']['parameters']['required'] = []
            rows[1]['data'] = json.dumps(infos)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check(rows)

    def test_both_denial_roles_require_exact_numeric_errors_and_actual_identity(self):
        for role, code in (('normal', 202), ('system-denied', 201)):
            rows = self.rows()[:1]
            rows[0]['role'] = role
            for method in range(2):
                rows.append(dict(runId=FIXTURE['caller_nonce'], role=role, name='denied.' + str(method),
                    values=[1, code, 1], data='', error=''))
            rows.append(dict(runId=FIXTURE['caller_nonce'], role=role, name='summary', values=[1], data='', error=''))
            self.check(rows, role)
            for values in ([0, 0, 0], [1, str(code), 1], [1, code, 0], [1, 201 if code == 202 else 202, 1]):
                changed = copy.deepcopy(rows); changed[1]['values'] = values
                with self.assertRaises(ValueError): self.check(changed, role)


if __name__ == '__main__':
    unittest.main()
