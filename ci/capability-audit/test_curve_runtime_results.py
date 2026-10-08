"""Verifier boundary fixtures are NOT actual guest or first-package passes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from curve_contract import HERE, PRESETS, TEMPLATE, TIMES, inputs, verify_inputs
from verify_curve_results import bezier, verify

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {
    'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010000}})
SDK = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')


def fixture():
    rows = []
    def row(name, **kwargs):
        value = {'name': name, 'runId': RUN, 'typed': [], 'native': None, 'values': [], 'reference': [],
                 'isolated': False, 'repeats': 0, 'repeatError': 0, 'error': ''}
        value.update(kwargs)
        return value
    strings = [preset[1] for preset in PRESETS]
    native = {'values': strings[:], 'types': [6, 6] + [4] * 13, 'statuses': [0] * 62,
              'own': [True] * 14, 'exception': False}
    rows.append(row('members', typed=strings, native=native))
    for generation in range(2):
        for name, _, points in PRESETS:
            values = [bezier(points, min(1, max(0, time))) if points else min(1, max(0, time))
                      for time in TIMES]
            rows.append(row('generation.' + str(generation) + '.' + name, values=values,
                            reference=values[:], isolated=True, repeats=32))
    rows.append(row('summary', values=[26, 0]))
    return rows


class CurveRuntimeTests(unittest.TestCase):
    def test_complete_host_fixture_and_independent_bounds_not_guest(self):
        result = verify('\n'.join(map(json.dumps, fixture())), RUN, IDENTITY)
        self.assertEqual(result['closed'], ['arkts_export:@ohos.curves:Curve'])
        self.assertIn('exact_mathematical_Cubic_endpoints', result['not_claimed'])
        self.assertEqual(result['preset_generations'], 26)

    def test_missing_duplicate_stale_privileged_fabricated_or_nonfinite_results_fail(self):
        cases = ('missing', 'duplicate', 'order', 'stale', 'numeric-enum', 'native-enum',
            'own', 'status', 'native-exception', 'native-types', 'linear-fallback', 'different-reference',
            'bad-clamp', 'nan', 'infinity', 'boolean', 'aliased', 'repeat', 'drift',
            'summary-count', 'summary-error', 'caught-error', 'extra-key')
        for case in cases:
            with self.subTest(case=case):
                rows = deepcopy(fixture())
                if case == 'missing': rows.pop(2)
                elif case == 'duplicate': rows.insert(2, rows[2])
                elif case == 'order': rows[1], rows[2] = rows[2], rows[1]
                elif case == 'stale': rows[4]['runId'] = 'b' * 32
                elif case == 'numeric-enum': rows[0]['typed'] = list(range(13))
                elif case == 'native-enum': rows[0]['native']['values'][4] = 'linear'
                elif case == 'own': rows[0]['native']['own'][1] = False
                elif case == 'status': rows[0]['native']['statuses'][40] = 9
                elif case == 'native-exception': rows[0]['native']['exception'] = True
                elif case == 'native-types': rows[0]['native']['types'][2] = 3
                elif case == 'linear-fallback':
                    rows[2]['values'] = [min(1, max(0, time)) for time in TIMES]
                    rows[2]['reference'] = rows[2]['values'][:]
                elif case == 'different-reference': rows[2]['reference'][4] += .1
                elif case == 'bad-clamp': rows[2]['values'][0] += .1
                elif case == 'nan': rows[2]['values'][4] = float('nan')
                elif case == 'infinity': rows[2]['values'][4] = float('inf')
                elif case == 'boolean': rows[2]['values'][4] = True
                elif case == 'aliased': rows[4]['isolated'] = False
                elif case == 'repeat': rows[4]['repeats'] = 31
                elif case == 'drift': rows[4]['repeatError'] = .1
                elif case == 'summary-count': rows[-1]['values'][0] = 25
                elif case == 'summary-error': rows[-1]['values'][1] = 1
                elif case == 'caught-error': rows[4]['error'] = 'actual failure'
                elif case == 'extra-key': rows[4]['injected'] = True
                with self.assertRaises(ValueError): verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY)
        for identity in ('{}', json.dumps({'applicationInfo': {
                'appPrivilegeLevel': 'system_basic', 'isSystemApp': True, 'uid': 0}})):
            with self.assertRaises((ValueError, KeyError)):
                verify('\n'.join(map(json.dumps, fixture())), RUN, identity)

    def test_actual_sdk_generated_caller_inputs_and_edits_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            page = project / 'entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text(TEMPLATE.read_text().replace('__CURVE_RUN_ID__', RUN))
            module = project / 'entry/src/main/module.json5'
            module.write_text(json.dumps({'module': {'requestPermissions': []}}))
            value = inputs(project, SDK, 'arm64', RUN)
            verify_inputs(value, RUN, 'arm64')
            for field, changed in (('run_id', 'b' * 32), ('arch', 'x86_64'),
                    ('request_permissions', ['ohos.permission.INTERNET']), ('native_source_sha256', 'stale'),
                    ('schema_version', True), ('generations', True), ('repeats', 1)):
                candidate = deepcopy(value); candidate[field] = changed
                with self.subTest(field=field), self.assertRaises(ValueError):
                    verify_inputs(candidate, RUN, 'arm64')
            page.write_text(page.read_text() + '// altered actual caller\n')
            with self.assertRaises(ValueError): verify_inputs(value, RUN, 'arm64')
            page.write_text(TEMPLATE.read_text().replace('__CURVE_RUN_ID__', RUN))
            module.write_text(json.dumps({'module': {'requestPermissions': [{'name': 'ohos.permission.INTERNET'}]}}))
            with self.assertRaises(ValueError): verify_inputs(value, RUN, 'arm64')


if __name__ == '__main__':
    unittest.main()
