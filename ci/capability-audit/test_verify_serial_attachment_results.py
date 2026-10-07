"""Synthetic transcript verifier units, never guest/device acceptance."""
import copy
import json
import unittest
from verify_serial_attachment_results import ORDER, CODES, verify


class SerialAttachmentTranscriptTest(unittest.TestCase):
    def setUp(self):
        self.run = 'a' * 32
        self.bundle = 'org.example.ordinary'
        self.port = 'ttyUSB0'
        self.rows = [{'kind': 'serial_attachment_case', 'run_id': self.run, 'bundle': self.bundle,
                      'case': name, 'passed': True, 'code_type': 'number',
                      'code': CODES.get(name, 0), 'details': ''} for name in ORDER]
        info = {'portName': self.port, 'vendorId': 1027, 'productId': 24577, 'manufacturer': 'fixture'}
        for name in ('enumerate_original', 'enumerate_replacement', 'enumerate_replug'):
            self.case(name)['details'] = json.dumps([info])
        self.case('enumerate_absent')['details'] = '[]'
        self.case('on_off_disconnect')['details'] = '{"removed":0,"retained":1}'
        self.case('raw_node_denied_after_grant')['details'] = json.dumps(
            {'passed': True, 'port_name': self.port, 'app_uid': 20000, 'stat_errno': 0,
             'open_errno': 13, 'mode': 0o660, 'node_uid': 1025, 'node_gid': 1025})

    def case(self, name):
        return next(row for row in self.rows if row['case'] == name)

    def errors(self):
        return verify(self.rows, self.run, self.bundle, self.port)

    def test_consistent_fixture_only(self):
        self.assertEqual(self.errors(), [])

    def test_numeric_code_must_not_be_bool_float_or_string(self):
        for code in (True, 35700003.0, '35700003'):
            self.case('unplug_pending_open')['code'] = code
            self.assertTrue(self.errors())

    def test_cannot_omit_new_permission_refusal(self):
        self.case('deny_replug')['code'] = 0
        self.assertTrue(self.errors())

    def test_rejects_missing_duplicate_or_reordered_cases(self):
        original = copy.deepcopy(self.rows)
        self.rows.pop()
        self.assertTrue(self.errors())
        self.rows = original + [original[0]]
        self.assertTrue(self.errors())
        self.rows = list(reversed(original))
        self.assertTrue(self.errors())

    def test_identical_tty_tuple_is_required(self):
        info = json.loads(self.case('enumerate_replug')['details'])
        info[0]['productId'] += 1
        self.case('enumerate_replug')['details'] = json.dumps(info)
        self.assertTrue(self.errors())

    def test_rejects_root_raw_access_and_world_writable_node(self):
        original = json.loads(self.case('raw_node_denied_after_grant')['details'])
        for field, value in (('app_uid', 0), ('open_errno', 0), ('mode', 0o666), ('node_uid', 0)):
            modified = dict(original, **{field: value})
            self.case('raw_node_denied_after_grant')['details'] = json.dumps(modified)
            self.assertTrue(self.errors())

    def test_selective_callback_counts_are_strict_integers(self):
        for details in ('{"removed":0,"retained":true}', '{"removed":0,"retained":1.0}',
                        '{"removed":1,"retained":1}', '{"removed":0,"retained":2}'):
            self.case('on_off_disconnect')['details'] = details
            self.assertTrue(self.errors())

    def test_rejects_stale_bundle_run_and_device_presence(self):
        self.rows[0]['run_id'] = 'old-run'
        self.assertTrue(self.errors())
        self.rows[0]['run_id'] = self.run
        self.rows[0]['bundle'] = 'system-dialog'
        self.assertTrue(self.errors())
        self.rows[0]['bundle'] = self.bundle
        self.case('enumerate_absent')['details'] = self.case('enumerate_original')['details']
        self.assertTrue(self.errors())


if __name__ == '__main__':
    unittest.main()
