"""Synthetic verifier boundaries only, never runtime evidence."""
from copy import deepcopy
import json
import unittest

from test_storage_stats_results import RUN, IDENTITY
from verify_completion_handler_results import EXPECTED, verify


def fixture():
    return [{'runId': RUN, 'name': name, 'values': values[:], 'error': ''}
            for name, values in EXPECTED.items()]


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class CompletionHandlerResultTests(unittest.TestCase):
    def test_exact_contract_remains_narrow(self):
        result = verify(text(fixture()), RUN, IDENTITY)
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['observations'], 8)
        self.assertIn('NOT_service_start_or_IPC', result['scope'])

    def test_every_observation_and_integer_type_required(self):
        for index in range(len(EXPECTED)):
            for value in (0, True, '1'):
                rows = fixture()
                rows[index]['values'][0] = value
                with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                    verify(text(rows), RUN, IDENTITY)

    def test_missing_duplicate_reordered_and_extra_results_rejected(self):
        rows = fixture()
        for changed in (rows[:-1], rows + rows[:1], rows[::-1], [rows[0]] + rows[:-1]):
            with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)

    def test_nonce_errors_and_unexpected_fields_rejected(self):
        for change in ({'runId': 'f' * 32}, {'error': 'actual error'}, {'extra': True}):
            rows = fixture()
            rows[0].update(change)
            with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)

    def test_system_or_root_caller_cannot_close_ordinary_contract(self):
        identity = json.loads(IDENTITY)
        for field, value in (('isSystemApp', True), ('appPrivilegeLevel', 'system_core'), ('uid', 0)):
            changed = deepcopy(identity)
            changed['applicationInfo'][field] = value
            with self.assertRaises(ValueError): verify(text(fixture()), RUN, json.dumps(changed))


if __name__ == '__main__':
    unittest.main()
