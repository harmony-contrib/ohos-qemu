"""Strict discovery/profile fixtures are not fresh-image behavior evidence."""
from copy import deepcopy
import json
import unittest
from verify_optional_phone_profile_results import OPTIONAL, POSITIVE, verify

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010000}})


def fixture():
    policy = {'required_official_syscaps': list(POSITIVE),
        'explicit_qemu_requirements': [], 'enabled_required_syscaps': list(POSITIVE),
        'excluded_unsupported_syscaps': list(OPTIONAL)}
    profile = {'device_type': 'phone', 'qemu_adaptations': policy}
    syscap = {'components': [{'syscap': list(POSITIVE)}]}
    names = [*OPTIONAL, *POSITIVE, 'SystemCapability.QemuOwned.' + RUN, '']
    values = [False] * 4 + [True] * 2 + [False] * 2
    rows = [{'runId': RUN, 'syscap': name, 'observed': value, 'error': ''}
        for repeat in range(33) for name, value in zip(names, values)]
    rows.append({'runId': RUN, 'syscap': 'summary', 'observed': True, 'error': ''})
    return rows, profile, syscap


class OptionalPhoneProfileTests(unittest.TestCase):
    def test_only_four_outside_official_phone_declarations_can_close(self):
        rows, profile, syscap = fixture()
        result = verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY, profile, syscap)
        self.assertEqual(result['closed'], list(OPTIONAL.values()))
        self.assertIn('any_official_capability', result['not_claimed'])

    def test_official_requested_2in1_false_stale_or_incomplete_results_are_rejected(self):
        for case in ('official', 'requested', 'enabled', 'not-excluded', 'still-declared', '2in1',
                     'missing-positive', 'wrong-runtime', 'zero-not-bool', 'error', 'stale',
                     'missing', 'reordered', 'duplicate', 'summary'):
            with self.subTest(case=case):
                rows, profile, syscap = deepcopy(fixture())
                cap = next(iter(OPTIONAL))
                if case == 'official': profile['qemu_adaptations']['required_official_syscaps'].append(cap)
                elif case == 'requested': profile['qemu_adaptations']['explicit_qemu_requirements'].append(cap)
                elif case == 'enabled': profile['qemu_adaptations']['enabled_required_syscaps'].append(cap)
                elif case == 'not-excluded': profile['qemu_adaptations']['excluded_unsupported_syscaps'].remove(cap)
                elif case == 'still-declared': syscap['components'][0]['syscap'].append(cap)
                elif case == '2in1': profile['device_type'] = '2in1'
                elif case == 'missing-positive': syscap['components'][0]['syscap'].pop()
                elif case == 'wrong-runtime': rows[0]['observed'] = True
                elif case == 'zero-not-bool': rows[0]['observed'] = 0
                elif case == 'error': rows[0]['error'] = 'actual error'
                elif case == 'stale': rows[0]['runId'] = 'b' * 32
                elif case == 'missing': rows.pop(0)
                elif case == 'reordered': rows[0], rows[1] = rows[1], rows[0]
                elif case == 'duplicate': rows.insert(0, rows[0])
                elif case == 'summary': rows[-1]['observed'] = False
                with self.assertRaises(ValueError):
                    verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY, profile, syscap)


if __name__ == '__main__':
    unittest.main()
