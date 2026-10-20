"""Synthetic oracle rejection checks; never SDK/device/package acceptance."""
import copy
import json
import unittest

from verify_usb_manager_results import (OWNER_ORDER, PEER_ORDER, DENIED, RIGHTS,
                                       SOCKET_ORDER, UI_ORDER, verify, rows)


def fixture():
    run_id = 'c' * 32
    owner_bundle = 'org.example.usbowner'
    peer_bundle = 'org.example.usbpeer'
    raw = [18, 1, 0, 2, 0, 0, 0, 8, 3, 4, 1, 96, 0, 1, 1, 2, 3, 1,
           9, 2, 9, 0, 1, 1, 0, 128, 50]

    def device(address):
        return {'busNum': 1, 'devAddress': address, 'vendorId': 1027,
                'productId': 24577, 'name': '1-' + str(address), 'serial': '', 'configs': [{}]}

    original, replacement = device(2), device(3)
    actors = []
    for actor, order, bundle in (('owner', OWNER_ORDER, owner_bundle), ('peer', PEER_ORDER, peer_bundle)):
        records = []
        for name in order:
            code = 14400001 if name in DENIED else -1 if name == 'stale_control_transfer' else 22 if name == 'stale_pipe_close_rejected' else 0
            row = {'kind': 'usb_manager_case', 'run_id': run_id, 'bundle': bundle, 'actor': actor,
                   'case': name, 'passed': True, 'code': code, 'code_type': 'number', 'details': 'unit fixture only'}
            target = replacement if 'replug' in name or name == 'right_removed_final' else original
            if name.startswith('query_'):
                absent = name in ('query_absent_initial', 'query_detached', 'query_absent_final')
                row['details'] = json.dumps({'devices': [] if absent else [target], 'matching_count': 0 if absent else 1})
            elif name in DENIED:
                row['details'] = json.dumps({'name': target['name'], 'result': False, 'has_right': False})
            elif name in RIGHTS:
                result, right = RIGHTS[name]
                row['details'] = json.dumps({'name': target['name'], 'result': result, 'has_right': right})
            elif name == 'right_retained_after_other_bundle':
                row['details'] = original['name']
            elif name in ('descriptors_original', 'descriptors_live', 'descriptors_replug'):
                serial = list('QEMUAPI26'.encode('utf-16-le'))
                serial = [len(serial) + 2, 3] + serial
                row['details'] = json.dumps({'name': target['name'],
                    'pipe': {'busNum': 1, 'devAddress': target['devAddress']},
                    'control_count': 18, 'control_bytes': raw[:18], 'raw_bytes': raw,
                    'language_count': 4, 'language_bytes': [4, 3, 9, 4],
                    'serial_count': len(serial), 'serial_bytes': serial})
            records.append(row)
        actors.append(records)

    def sysfs(address):
        return '/sys/devices/unit-fixture/usb1/1-1\n1\n' + str(address) + '\n0403\n6001\nQEMUAPI26\n1\n' + ' '.join(f'{item:02x}' for item in raw)

    witnesses = [{'label': label, 'raw': 'ABSENT' if label in ('initial', 'detached', 'final') else
                  sysfs(3 if label == 'replug' else 2)}
                 for label in ('initial', 'original', 'live', 'detached', 'replug', 'final')]
    host = {'witnesses': witnesses, 'normal_uids': {owner_bundle: 20001, peer_bundle: 20002},
            'socket_journal': [{'kind': 'serial_host_attachment', 'run_id': run_id, 'sequence': index,
                                'operation': op, 'host_operation_completed': True,
                                'host_socket_connected': op == 'attach'}
                               for index, op in enumerate(SOCKET_ORDER, 1)],
            'ui_actions': [{'label': label, 'trusted_bundle': 'com.usb.right',
                            'decision': 'notAllowButton' if index in (0, 3) else 'allowButton',
                            'clicked': True, 'selected_node': {'bundle': 'com.usb.right'}}
                           for index, label in enumerate(UI_ORDER)],
            'cleanup': {bundle: {'stop_reply': 'force stop process successfully.', 'pidof': '',
                                'absence_observations': 2, 'uninstall_reply': 'Success'}
                        for bundle in (owner_bundle, peer_bundle)}}
    return actors[0], actors[1], host, run_id, owner_bundle, peer_bundle


class UsbManagerRawOracleTests(unittest.TestCase):
    def test_consistent_fixture_and_parser_only(self):
        values = fixture()
        self.assertEqual(verify(*values), [])
        self.assertEqual(rows('{"case":"unit fixture"}\n'), [{'case': 'unit fixture'}])
        for raw in ('{"case":', 'PASS', '{"case":"a"}\n\n', ''):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                rows(raw)

    def test_failed_or_incomplete_physical_and_permission_contracts_are_rejected(self):
        def changed_case(values, name, field, value):
            next(row for row in values[0] if row['case'] == name)[field] = value

        def altered_descriptor(values):
            row = next(row for row in values[0] if row['case'] == 'descriptors_original')
            value = json.loads(row['details']); value['control_bytes'][8] ^= 1
            row['details'] = json.dumps(value)

        def leaked_serial(values):
            row = next(row for row in values[0] if row['case'] == 'query_original')
            value = json.loads(row['details']); value['devices'][0]['serial'] = 'QEMUAPI26'
            row['details'] = json.dumps(value)

        mutations = [
            lambda v: changed_case(v, 'connect_denied_original', 'code', True),
            lambda v: changed_case(v, 'connect_denied_original', 'code', '14400001'),
            lambda v: changed_case(v, 'stale_control_transfer', 'code', 18),
            lambda v: changed_case(v, 'stale_pipe_close_rejected', 'code', 0),
            lambda v: v[0].pop(),
            lambda v: v[0].reverse(),
            lambda v: v[2]['normal_uids'].__setitem__(v[5], v[2]['normal_uids'][v[4]]),
            lambda v: v[2]['witnesses'][1].__setitem__('raw', v[2]['witnesses'][1]['raw'].replace('QEMUAPI26', 'foreign-device')),
            lambda v: v[2]['socket_journal'][2].__setitem__('host_socket_connected', True),
            lambda v: v[2]['ui_actions'][0].__setitem__('trusted_bundle', 'untrusted.dialog'),
            lambda v: v[2]['cleanup'][v[5]].__setitem__('pidof', '1234'),
            lambda v: v[2]['cleanup'].pop(v[5]),
            altered_descriptor, leaked_serial,
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                values = copy.deepcopy(fixture()); mutate(values)
                self.assertTrue(verify(*values))


if __name__ == '__main__':
    unittest.main()
