"""Synthetic verifier boundaries; never radio acceptance evidence."""
from copy import deepcopy
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from test_storage_stats_results import RUN, IDENTITY
from verify_wifi_scan_results import NAMES, verify
from wifi_scan_contract import PERMISSIONS


def fixture():
    values = ([1], [201], [1, 1, 0], [1, 1, 0], [1, 1], [5, 0])
    return [dict(runId=RUN, name=name, values=list(value), error='') for name, value in zip(NAMES, values)]


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class WifiScanResultTests(unittest.TestCase):
    def test_actual_builder_requests_only_normal_wifi_permissions(self):
        tree = ast.parse(Path(__file__).with_name('build_hap_probe.py').read_text())
        expressions = [value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'requestPermissions'
                       and isinstance(value, ast.IfExp)]
        self.assertEqual(len(expressions), 1)
        args = SimpleNamespace(camera_only=False, wifi_scan_only=True)
        expression = compile(ast.Expression(expressions[0]), 'actual-wifi-permissions', 'eval')
        self.assertEqual(eval(expression, {'args': args}), [{'name': name} for name in PERMISSIONS])

    def test_empty_successful_scan_callbacks_do_not_close_wlan(self):
        result = verify(text(fixture()), RUN, IDENTITY)
        self.assertEqual(result['closed'], [])
        self.assertFalse(result['association_proven'])
        self.assertFalse(result['controlled_ssid_proven'])
        self.assertEqual(result['visible_result_counts'], [0, 0])

    def test_nonempty_scan_counts_still_do_not_prove_a_controlled_ssid(self):
        rows = fixture()
        rows[2]['values'][2], rows[3]['values'][2] = 2, 3
        result = verify(text(rows), RUN, IDENTITY)
        self.assertEqual(result['visible_result_counts'], [2, 3])
        self.assertEqual(result['closed'], [])
        self.assertFalse(result['controlled_ssid_proven'])

    def test_callback_failure_wrong_types_permission_and_lifecycle_fail_closed(self):
        for index, original in enumerate(fixture()):
            for position in range(len(original['values'])):
                for value in (-1, True, str(original['values'][position])):
                    rows = fixture()
                    rows[index]['values'][position] = value
                    with self.subTest(index=index, position=position, value=value), self.assertRaises(ValueError):
                        verify(text(rows), RUN, IDENTITY)
        for index, value in ((0, [0]), (1, [0]), (2, [0, 1, 0]), (2, [1, 2, 0]),
                             (4, [2, 1]), (4, []), (5, [4, 0])):
            rows = fixture()
            rows[index]['values'] = value
            with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)

    def test_missing_duplicate_reordered_extra_and_failed_rows_rejected(self):
        rows = fixture()
        for changed in (rows[:-1], rows + rows[:1], rows[::-1], [rows[0]] + rows[:-1]):
            with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)
        for change in ({'runId': 'f' * 32}, {'error': 'backend failed'}, {'extra': True}, {'values': '1'}):
            rows = fixture()
            rows[0].update(change)
            with self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)

    def test_privileged_caller_cannot_stand_in_for_ordinary_scan(self):
        identity = json.loads(IDENTITY)
        for field, value in (('isSystemApp', True), ('appPrivilegeLevel', 'system_core'), ('uid', 0)):
            changed = deepcopy(identity)
            changed['applicationInfo'][field] = value
            with self.assertRaises(ValueError): verify(text(fixture()), RUN, json.dumps(changed))


if __name__ == '__main__':
    unittest.main()
