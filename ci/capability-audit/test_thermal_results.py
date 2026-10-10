"""Synthetic verifier boundaries, never actual guest observations."""
from copy import deepcopy
import json
import unittest

from test_storage_stats_results import RUN, IDENTITY
from verify_thermal_results import EXPECTED, verify


def fixture():
    return [{'runId': RUN, 'name': name, 'values': values[:], 'error': ''}
            for name, values in EXPECTED.items()]


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class ThermalResultTests(unittest.TestCase):
    def test_callbacks_do_not_alone_close_the_backend(self):
        actual = verify(text(fixture()), RUN, IDENTITY)
        self.assertEqual(actual['closed'], [])
        self.assertFalse(actual['hot_transitions_proven'])
        self.assertEqual(actual['generations'], 4)

    def test_every_observation_and_integer_type_required(self):
        for index, original in enumerate(fixture()):
            for position in range(len(original['values'])):
                for value in (99, True, str(original['values'][position])):
                    rows = fixture()
                    rows[index]['values'][position] = value
                    with self.subTest(index=index, position=position, value=value), self.assertRaises(ValueError):
                        verify(text(rows), RUN, IDENTITY)

    def test_missing_duplicate_reordered_and_extra_results_rejected(self):
        rows = fixture()
        for changed in (rows[:-1], rows + rows[:1], rows[::-1], [rows[0]] + rows[:-1]):
            with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)

    def test_nonce_errors_and_unexpected_fields_rejected(self):
        for change in ({'runId': 'f' * 32}, {'error': 'service error'}, {'extra': True}):
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
