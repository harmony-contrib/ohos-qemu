"""Synthetic collector fixtures are never guest or provider evidence."""
import copy
import json
import unittest

from runtime_enum_contracts import generate, requested
from verify_runtime_enum_results import verify

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}})
CONTRACTS = [dict(module='@ohos.net.ethernet', name='DeviceConnectionType', import_kind='default_namespace',
                  members=[{'name': 'BUILT_IN', 'value': 0}, {'name': 'EXTERNAL', 'value': 1}]),
             dict(module='@ohos.app.cli.cliManager', name='SessionStatus', import_kind='default_namespace',
                  members=[{'name': 'RUNNING', 'value': 'running'}])]


def records():
    rows = []
    for contract in CONTRACTS:
        values = [member['value'] for member in contract['members']]
        count = len(values)
        rows.append(dict(runId=RUN, module=contract['module'], name=contract['name'], values=values,
            typedException=False, native=dict(values=values[:], statuses=[0] * (10 + 4 * count),
                types=[6, 6] + [3 if type(value) is int else 4 for value in values], own=[True] * (1 + count),
                exception=False)))
    rows.append({'runId': RUN, 'summary': len(CONTRACTS)})
    return rows


def render(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class RuntimeEnumTests(unittest.TestCase):
    def test_exact_independent_reads_only_close_their_enum_contract(self):
        result = verify(render(records()), CONTRACTS, RUN, IDENTITY)
        self.assertEqual(len(result['closed']), 2)
        self.assertEqual(result['unresolved'], [])
        self.assertIn('associated_hardware', result['not_claimed'])

    def test_absence_or_undefined_is_truthfully_unresolved_not_collection_failure(self):
        rows = records()
        rows[0]['typedException'] = True
        rows[0]['values'] = []
        rows[0]['native'].update(values=[], statuses=[0] * 10, types=[6, 0], own=[False])
        result = verify(render(rows), CONTRACTS, RUN, IDENTITY)
        self.assertEqual(len(result['closed']), 1)
        self.assertEqual(result['unresolved'], ['arkts_export:@ohos.net.ethernet:DeviceConnectionType'])

    def test_every_member_native_type_read_status_and_ownership_matter(self):
        for path, bad in ((('values', 0), True), (('values', 0), '0'), (('values', 1), 2),
                          (('native', 'values', 0), 99), (('native', 'types', 2), 4),
                          (('native', 'statuses', 2), 1), (('native', 'own', 0), False),
                          (('native', 'exception'), True), (('typedException',), True)):
            rows = records()
            destination = rows[0]
            for part in path[:-1]: destination = destination[part]
            destination[path[-1]] = bad
            with self.subTest(path=path, bad=bad):
                self.assertEqual(len(verify(render(rows), CONTRACTS, RUN, IDENTITY)['closed']), 1)

    def test_missing_duplicate_reordered_wrong_nonce_summary_are_rejected(self):
        variants = [records()[:-1], records()[1:], list(reversed(records()))]
        duplicate = records(); duplicate[1] = copy.deepcopy(duplicate[0]); variants.append(duplicate)
        wrong = records(); wrong[0]['runId'] = 'b' * 32; variants.append(wrong)
        count = records(); count[-1]['summary'] = True; variants.append(count)
        for rows in variants:
            with self.assertRaises(ValueError): verify(render(rows), CONTRACTS, RUN, IDENTITY)

    def test_system_identity_malformed_native_types_and_numeric_booleans_rejected(self):
        identity = json.loads(IDENTITY); identity['applicationInfo']['isSystemApp'] = True
        with self.assertRaises(ValueError): verify(render(records()), CONTRACTS, RUN, json.dumps(identity))
        for field, value in (('statuses', [True]), ('types', [10]), ('own', [1]), ('exception', 0)):
            rows = records(); rows[0]['native'][field] = value
            with self.assertRaises(ValueError): verify(render(rows), CONTRACTS, RUN, IDENTITY)

    def test_generator_reads_typed_and_actual_native_not_sdk_expected_values(self):
        source = generate(CONTRACTS, RUN)
        self.assertIn('EnumModule0.DeviceConnectionType.BUILT_IN', source)
        self.assertIn('probe.inspect("@ohos.net.ethernet", "DeviceConnectionType", ["BUILT_IN", "EXTERNAL"])', source)
        self.assertNotIn('"running"', source)  # Only a typed SDK read; no expected-value injection.
        self.assertIn('catch (_) { typedException = true; }', source)
        self.assertIn('summary: 2', source)
        with self.assertRaises(ValueError): generate(CONTRACTS * 2, RUN)
        with self.assertRaises(ValueError): generate(CONTRACTS, 'old')

    def test_complete_profile_keeps_unresolved_ambient_curve_in_requirements(self):
        for device in ('phone', '2in1'):
            identifiers = [(row['module'], item['name']) for row in requested(device) for item in row['contracts']]
            self.assertIn(('@ohos.curves', 'Curve'), identifiers)
            self.assertIn(('@ohos.net.ethernet', 'DeviceConnectionType'), identifiers)
            self.assertEqual(len(identifiers), len(set(identifiers)))
        with self.assertRaises(ValueError): requested('watch')


if __name__ == '__main__':
    unittest.main()
