"""Synthetic parser boundaries, not device acceptance evidence."""
import json
import unittest
from hitrace_kernel_contract import expected, trace_configuration, verify_restored_configuration, verify_rows, verify_trace

RUN = 'b' * 32
PID, TID, UID = 321, 456, 20010012


def fixture():
    lines = ['# tracer: nop', '# entries-in-buffer/entries-written: 36/36']
    for kind, name, value in expected(RUN):
        fields = f'{kind}|{PID}|C62' if kind == 'E' else f'{kind}|{PID}|H:{name}'
        if value is not None:
            fields += '|' + str(value)
        if kind != 'E':
            fields += '|C62'
        lines.append(f'    audit-{TID} [001] .... 123.123456: tracing_mark_write: ' + fields)
    return '\n'.join(lines) + '\n'


class HiTraceKernelTests(unittest.TestCase):
    def test_lazy_buffer_capacity_is_not_a_missing_trace_backend(self):
        actual = '0\nnop\n7 (expanded: 1408)\n[local] global mono\n0 \n-1 \n'
        expected_config = dict(on='0', tracer='nop', buffer='1408', clock='local', tags='0', pid='-1')
        self.assertEqual(trace_configuration(actual), expected_config)
        self.assertEqual(trace_configuration(actual.replace('7 (expanded: 1408)', '1408')), expected_config)
        for wrong in (actual.replace('[local]', '[local] [global]'),
                      actual.replace('1408)', '1408; touch /tmp/bad)'), actual.replace('nop', 'function')):
            with self.assertRaises(ValueError):
                trace_configuration(wrong)

    def test_complete_kernel_records_are_scoped(self):
        result = verify_trace(fixture(), RUN, PID, TID)
        self.assertEqual(result['public_api_kernel_records'], 36)
        self.assertEqual(result['closed'], [])
        self.assertEqual(verify_trace(fixture().replace('[001]', '(-------) [001]'),
                                      RUN, PID, TID)['public_api_kernel_records'], 36)
        self.assertEqual(verify_trace(fixture().replace('H:oqht', 'H:[1a,2b,0]#oqht'),
                                      RUN, PID, TID)['public_api_kernel_records'], 36)

    def test_exact_pinned_kernel_capacity_rounding(self):
        before = dict(on='0', tracer='nop', buffer='1408', clock='local', tags='0', pid='-1')
        after = dict(before, buffer='1410')
        self.assertEqual(verify_restored_configuration(before, after, 4096, 'arm64')['actual_buffer_kb'], 1410)
        for wrong in (dict(after, buffer='1411'), dict(after, tags='1'), dict(after, clock='boot')):
            with self.assertRaises(ValueError):
                verify_restored_configuration(before, wrong, 4096, 'arm64')

    def test_missing_duplicated_or_wrong_identity_fails(self):
        lines = fixture().splitlines()
        for index in range(2, len(lines)):
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify_trace('\n'.join(lines[:index] + lines[index + 1:]), RUN, PID, TID)
        for altered in (fixture().replace(f'audit-{TID}', 'audit-999'),
                        fixture().replace(f'|{PID}|', '|999|'),
                        fixture() + lines[2] + '\n', fixture().replace('2147483648', '-2147483648'),
                        fixture().replace('H:oqht', 'oqht-other'), fixture().replace('# tracer:', '# invented:')):
            with self.assertRaises(ValueError):
                verify_trace(altered, RUN, PID, TID)

    def test_actual_caller_identity_and_enabled_state(self):
        names = ['identity', 'native.0', 'arkts.0', 'native.1', 'arkts.1', 'summary']
        values = [[PID, UID, UID], [PID, UID, UID, 1, TID], [1], [PID, UID, UID, 1, TID], [1], [2]]
        rows = [dict(runId=RUN, name=name, values=value, error='') for name, value in zip(names, values)]
        self.assertEqual(verify_rows('\n'.join(map(json.dumps, rows)), RUN, UID), (PID, TID))
        rows[1]['values'][3] = 0
        with self.assertRaises(ValueError):
            verify_rows('\n'.join(map(json.dumps, rows)), RUN, UID)


if __name__ == '__main__':
    unittest.main()
