import copy
import json
import unittest

from verify_graphics_memory_results import verify

NONCE = 'a' * 32
UID = 20010038


def fixture():
    rows = []
    for phase, graph in enumerate((4096, 20480, 36864, 20480, 4096)):
        sizes = [0, 0] if phase == 0 else [16384, 0] if phase == 1 else [16384, 16384]
        values = [2134, UID, UID, 0, graph + 128, 0, 128, graph, 401, 401,
                  phase, [0, 1, 2, 1, 0][phase], *sizes]
        rows.append(dict(runId=NONCE, phase=phase, native=values, gl=128, graph=graph,
                         total=graph + 128, publicTypes=['number'] * 3,
                         publicValues=['128', str(graph), str(graph + 128)], error=''))
    rows.append(dict(runId=NONCE, phase=5, native=[], gl=0, graph=0, total=0,
                     publicTypes=[], publicValues=[], error=''))
    return rows


def check(rows):
    return verify('\n'.join(json.dumps(row) for row in rows), NONCE, UID)


class GraphicsMemoryResultTests(unittest.TestCase):
    def test_fixture_is_narrow_not_kernel_closure(self):
        result = check(fixture())
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['allocation_kib'], [16384, 16384])

    def test_false_success_constant_zero_or_unchanged_counters_rejected(self):
        for constant in (0, 4096):
            rows = fixture()
            for row in rows[:5]:
                row.update(gl=0, graph=constant, total=constant)
                row['publicValues'] = ['0', str(constant), str(constant)]
                row['native'][4], row['native'][6], row['native'][7] = constant, 0, constant
            with self.assertRaises(ValueError):
                check(rows)

    def test_identity_boundaries_and_accounting_fail_closed(self):
        for index, value in ((0, 1), (1, 0), (2, 0), (3, 1), (4, 0), (5, 1),
                             (8, 0), (9, 0), (10, 3), (11, 0), (12, 0)):
            rows = fixture()
            rows[1]['native'][index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                check(rows)

    def test_missing_duplicate_foreign_and_incomplete_runs_rejected(self):
        original = fixture()
        variants = [original[:-1], original + [original[-1]], original[1:]]
        for key, value in (('runId', 'b' * 32), ('phase', -1), ('error', 'allocation failed')):
            rows = copy.deepcopy(original)
            rows[2][key] = value
            variants.append(rows)
        for rows in variants:
            with self.assertRaises(ValueError):
                check(rows)

    def test_leaked_buffer_is_not_restored_accounting(self):
        rows = fixture()
        rows[4].update(graph=20480, total=20608)
        rows[4]['publicValues'] = ['128', '20480', '20608']
        rows[4]['native'][4], rows[4]['native'][7] = 20608, 20480
        with self.assertRaises(ValueError):
            check(rows)

    def test_observed_bigint_is_never_coerced_to_success(self):
        rows = fixture()
        rows[0]['publicTypes'][1] = 'bigint'
        with self.assertRaisesRegex(ValueError, 'must remain numbers'):
            check(rows)
