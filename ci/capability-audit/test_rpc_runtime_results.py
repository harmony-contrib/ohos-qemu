"""Synthetic verifier boundaries only, never runtime evidence."""
from copy import deepcopy
import json
import unittest

from test_storage_stats_results import RUN, IDENTITY
from verify_rpc_runtime_results import expected, verify


def fixture():
    return [{'runId': RUN, 'name': name, 'values': values[:], 'text': content, 'error': ''}
            for name, (values, content) in expected(RUN).items()]


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class RpcRuntimeResultTests(unittest.TestCase):
    def test_exact_contract_remains_narrow(self):
        result = verify(text(fixture()), RUN, IDENTITY)
        self.assertEqual(result['closed'], ['arkts_export:@ohos.rpc:IRemoteObject'])
        self.assertEqual(result['observations'], 22)
        self.assertIn('NOT_remote_death_or_DBinder', result['scope'])

    def test_every_observation_and_integer_type_required(self):
        for index in range(len(expected(RUN))):
            for value in (True, '1', -99):
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
