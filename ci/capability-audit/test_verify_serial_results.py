"""Verifier fixtures only: never guest/runtime acceptance evidence."""
import copy
import hashlib
import json
import unittest

from serial_host_echo import expected_frame, FRAME_SIZES
from verify_serial_results import verify, EXPECTED_CASE_ORDER, EXPECTED_CODES

RUN = '98623ef520f448c3b573047d1752f864'
BUNDLE = 'org.harmonycontrib.serialaudit'


def fixture():
    rows = [{'kind': 'serial_case', 'run_id': RUN, 'bundle': BUNDLE, 'case': name,
             'passed': True, 'code_type': 'number', 'code': EXPECTED_CODES.get(name, 0), 'details': ''}
            for name in EXPECTED_CASE_ORDER]
    acl = {'passed': True, 'port_name': 'ttyUSB0', 'stat_errno': 0, 'open_errno': 13,
           'mode': 0o660, 'node_uid': 1025, 'node_gid': 1025, 'app_uid': 20010001}
    for row in rows:
        if row['case'].startswith('raw_node_'):
            row['details'] = json.dumps(acl)
        if row['case'] == 'enumerate':
            row['details'] = json.dumps([{'portName': 'ttyUSB0', 'vendorId': 0x0403, 'productId': 0x6001}])
    host = []
    for phase, size in FRAME_SIZES.items():
        digest = hashlib.sha256(expected_frame(RUN, phase)).hexdigest()
        host.append({'kind': 'serial_host_frame', 'run_id': RUN, 'phase': phase,
                     'frame_size': size, 'frame_sha256': digest, 'expected_sha256': digest,
                     'challenge_matched': True, 'echo_bytes': size, 'echo_completed': True})
    return rows, host


class VerifySerialFixtureTest(unittest.TestCase):
    def setUp(self):
        self.guest, self.host = fixture()

    def errors(self):
        return verify(self.guest, self.host, RUN, BUNDLE)

    def test_fixture_sanity_not_runtime(self):
        self.assertEqual(self.errors(), [])

    def test_stale_guest(self):
        self.guest[0]['run_id'] = '0' * 32
        self.assertTrue(self.errors())

    def test_wrong_bundle(self):
        self.guest[0]['bundle'] = 'com.usb.right'
        self.assertTrue(self.errors())

    def test_stale_host(self):
        self.host[0]['run_id'] = '0' * 32
        self.assertTrue(self.errors())

    def test_missing_allow(self):
        self.guest = [row for row in self.guest if row['case'] != 'allow_open']
        self.assertTrue(self.errors())

    def test_numeric_error_is_required(self):
        self.guest[3]['code'] = str(self.guest[3]['code'])
        self.guest[3]['code_type'] = 'string'
        self.assertTrue(self.errors())

    def test_boolean_is_not_numeric_code(self):
        self.guest[0]['code'] = False
        self.assertTrue(self.errors())

    def test_partial_host_write(self):
        self.host[1]['echo_bytes'] = 1024
        self.assertTrue(self.errors())

    def test_failed_host_send_not_pass(self):
        self.host[1]['echo_completed'] = False
        self.assertTrue(self.errors())

    def test_host_byte_hash(self):
        self.host[0]['frame_sha256'] = '0' * 64
        self.assertTrue(self.errors())

    def test_raw_world_writable_rejected(self):
        row = next(row for row in self.guest if row['case'] == 'raw_node_denied_before_grant')
        acl = json.loads(row['details'])
        acl['mode'] = 0o666
        row['details'] = json.dumps(acl)
        self.assertTrue(self.errors())

    def test_missing_hardware_not_raw_permission_pass(self):
        row = next(row for row in self.guest if row['case'] == 'raw_node_denied_before_grant')
        acl = json.loads(row['details'])
        acl['stat_errno'] = 2
        acl['open_errno'] = 2
        row['details'] = json.dumps(acl)
        self.assertTrue(self.errors())

    def test_other_port_rejected(self):
        row = next(row for row in self.guest if row['case'] == 'raw_node_denied_after_grant')
        acl = json.loads(row['details'])
        acl['port_name'] = 'ttyAMA0'
        row['details'] = json.dumps(acl)
        self.assertTrue(self.errors())

    def test_root_result_not_app_acceptance(self):
        row = next(row for row in self.guest if row['case'] == 'raw_node_denied_before_grant')
        acl = json.loads(row['details'])
        acl['app_uid'] = 0
        row['details'] = json.dumps(acl)
        self.assertTrue(self.errors())

    def test_duplicate_case(self):
        self.guest.append(copy.deepcopy(self.guest[-1]))
        self.assertTrue(self.errors())

    def test_guest_order(self):
        self.guest[-1], self.guest[-2] = self.guest[-2], self.guest[-1]
        self.assertTrue(self.errors())

    def test_host_order(self):
        self.host.reverse()
        self.assertTrue(self.errors())

    def test_non_integer_host_phase_and_counts(self):
        original = copy.deepcopy(self.host[0])
        for field, value in (('phase', True), ('phase', 1.0),
                             ('frame_size', 64.0), ('echo_bytes', 64.0)):
            with self.subTest(field=field, value=value):
                self.host[0] = dict(original, **{field: value})
                self.assertTrue(self.errors())

    def test_late_host_transport_error_rejected(self):
        self.host.append({'kind': 'serial_host_error', 'run_id': RUN, 'error': 'unexpected extra bytes'})
        self.assertTrue(self.errors())

    def test_binary_frame_has_challenge_and_non_text_bytes(self):
        frame = expected_frame(RUN, 2)
        self.assertEqual(len(frame), 4096)
        self.assertEqual(frame[5:21], bytes.fromhex(RUN))
        self.assertIn(0, frame[21:])
        self.assertIn(255, frame[21:])


if __name__ == '__main__':
    unittest.main()
