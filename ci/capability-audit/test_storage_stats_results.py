"""Synthetic verifier boundaries only; no guest success is implied."""
from copy import deepcopy
import json
import unittest
from verify_storage_stats_results import verify
from run_normal_hap_probe import PERSONAS, verifier_arguments

RUN = '1234567890abcdef1234567890abcdef'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010000}})


def fixture():
    rows = []
    for generation in range(2):
        data, cache = (generation + 1) * 4 * 1024**2, (generation + 1) * 2 * 1024**2
        for name, values in (
            ('before', [900000, 4096, 16384]), ('written', [data, cache]),
            ('occupied', [900000, 4096 + cache, 16384 + data + cache]),
            ('restored', [900000, 4096, 20480])):
            rows.append({'runId': RUN, 'name': name + '.' + str(generation),
                         'values': values, 'error': ''})
    for name, values in (('other-bundle-denial', [202]), ('summary', [1, 1])):
        rows.append({'runId': RUN, 'name': name, 'values': values, 'error': ''})
    return rows


def text(rows):
    return '\n'.join(map(json.dumps, rows))


class StorageStatisticsTests(unittest.TestCase):
    def test_exact_deltas_never_claim_complete_quota_closure(self):
        result = verify(text(fixture()), RUN, IDENTITY)
        self.assertEqual(result['closed'], [])
        self.assertTrue(result['data_cache_growth_and_release'])
        self.assertTrue(result['cache_is_subset_of_data'])

    def test_data_must_include_cache_once_not_omit_or_double_count_it(self):
        for generation in range(2):
            cache = (generation + 1) * 2 * 1024**2
            for delta in (-cache, cache):
                rows = fixture()
                rows[generation * 4 + 2]['values'][2] += delta
                with self.subTest(generation=generation, delta=delta), self.assertRaises(ValueError):
                    verify(text(rows), RUN, IDENTITY)

    def test_every_row_identity_order_and_error_is_required(self):
        for index in range(10):
            for field, replacement in (('name', 'wrong'), ('runId', 'b' * 32), ('error', 'actual error')):
                rows = fixture()
                rows[index][field] = replacement
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    verify(text(rows), RUN, IDENTITY)

    def test_zero_success_stale_accounting_and_wrong_cache_mapping_reject(self):
        for index in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
            rows = fixture()
            rows[index]['values'] = [0] * len(rows[index]['values'])
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify(text(rows), RUN, IDENTITY)
        rows = fixture()
        rows[2]['values'] = rows[0]['values']
        with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)
        rows = fixture()
        rows[3]['values'] = rows[2]['values']
        with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)

    def test_short_extra_reordered_boolean_privileged_and_bad_denial_reject(self):
        cases = []
        rows = fixture(); rows.pop(); cases.append(rows)
        rows = fixture(); rows.append(deepcopy(rows[-1])); cases.append(rows)
        rows = fixture(); rows[0], rows[1] = rows[1], rows[0]; cases.append(rows)
        rows = fixture(); rows[-1]['values'][0] = True; cases.append(rows)
        rows = fixture(); rows[-2]['values'] = [201]; cases.append(rows)
        rows = fixture(); rows[0]['extra'] = 0; cases.append(rows)
        for rows in cases:
            with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)
        with self.assertRaises(ValueError):
            verify(text(fixture()), RUN, IDENTITY.replace('normal', 'system_basic'))

    def test_runner_binds_actual_arch_identity_and_nonce(self):
        self.assertEqual(PERSONAS['storage-stats'][0], '--storage-stats-only')
        args = verifier_arguments('storage-stats', 'archive', 'rows', 'identity', RUN, 'arm64', 'output')
        for flag, value in (('--arch', 'arm64'), ('--application-identity', 'identity'), ('--run-id', RUN)):
            self.assertEqual(args[args.index(flag) + 1], value)


if __name__ == '__main__':
    unittest.main()
