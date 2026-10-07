"""Actual-loader verifier fixtures; these do not attest any guest."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_native_gap_abi_probe import generate
from const_enum_contracts import sha256
from verify_native_gap_abi_results import SOURCE_LOCK, runtime_path, validate_definitions, verify

RUN = 'b' * 32


class NativeGapAbiResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ledger = Path(self.temp.name) / 'ledger.json'
        original = [{'syscap': 'SystemCapability.Test.Required', 'library': 'libtest.so',
                     'missing_symbols': ['OH_Test'], 'public_function_count': 1},
                    {'syscap': 'SystemCapability.Test.Optional', 'library': 'liboptional.so',
                     'missing_symbols': [], 'public_function_count': 1}]
        ledger.write_text(json.dumps({'devices': {'phone': {'native_abi_gaps': original}}}))
        self.replacement = patch('verify_native_gap_abi_results.LEDGER', ledger)
        self.replacement.start()
        self.addCleanup(self.replacement.stop)
        self.inputs = {'status': 'pass', 'arch': 'arm64', 'device': 'phone',
            'scope': 'offline_actual_final_image_complete_original_Native_gap_ABI_NOT_behavior',
            'audit_baseline_sha256': sha256(ledger), 'actual_syscap_sha256': '1' * 64,
            'device_profile_sha256': '2' * 64, 'contracts': []}
        self.inputs.update(source_lock_sha256=sha256(SOURCE_LOCK), sdk_c_revision=next(
            row['revision'] for row in json.loads(SOURCE_LOCK.read_text())['projects'] if row['path'] == 'interface/sdk_c'))
        self.rows = []
        for index, original_row in enumerate(original):
            required = index == 0
            identifier = 'native:' + original_row['syscap'] + ':' + original_row['library']
            spec = dict(original_requirement=original_row, id=identifier, syscap=original_row['syscap'],
                library=original_row['library'], functions=['OH_Test'], source_inputs_sha256={'test.h': '3' * 64},
                needs_library=required, declared_by_final_image=required, required_by_active_contract=required,
                status='all_source_contract_symbols_present' if required else 'optional_undeclared',
                scope='required_actual_native_ABI' if required else 'optional_undeclared_NOT_implemented')
            if required:
                spec.update(library_sha256='4' * 64, image_entry={'image_path': '/lib64/ndk/libtest.so'})
            else:
                spec['implemented'] = False
            self.inputs['contracts'].append(spec)
            self.rows.append({'kind': 'library', 'id': identifier, 'runId': RUN, 'required': required,
                              'loaded': required, 'path': '/system/lib64/ndk/libtest.so' if required else ''})
            if required:
                self.rows.append({'kind': 'symbol', 'id': identifier, 'runId': RUN, 'name': 'OH_Test',
                                  'resolved': True, 'origin': '/system/lib64/ndk/libtest.so'})
        self.rows.append({'kind': 'summary', 'runId': RUN, 'loaded_libraries': 1,
                          'optional_undeclared': 1, 'checked_symbols': 1, 'pass': True})

    def verify(self, rows=None, **kwargs):
        return verify('\n'.join(map(json.dumps, self.rows if rows is None else rows)),
                      kwargs.get('inputs', self.inputs), kwargs.get('arch', 'arm64'), 'phone',
                      kwargs.get('run_id', RUN), kwargs.get('code', 0))

    def test_complete_loader_observations_keep_optional_undeclared_unimplemented(self):
        actual = self.verify()
        self.assertEqual(actual['contract_count'], 2)
        self.assertEqual(actual['checked_symbols'], 1)
        self.assertEqual(len(actual['optional_undeclared_not_implemented']), 1)
        header = generate(self.inputs['contracts'], 'arm64')
        self.assertIn('FUNCTIONS_0', header)
        self.assertIn('"/system/lib64/ndk/libtest.so",true,1,FUNCTIONS_0', header)
        self.assertIn('"liboptional.so","",false,1,FUNCTIONS_1', header)

    def test_missing_stale_failed_nonboolean_wrong_owner_or_extra_results_rejected(self):
        for rows in (self.rows[:-1], self.rows + self.rows[-1:]):
            with self.assertRaises(ValueError):
                self.verify(rows)
        for index, key, value in ((0, 'loaded', 1), (1, 'resolved', False),
                                  (1, 'origin', '/data/local/tmp/libtest.so'),
                                  (1, 'runId', 'a' * 32), (3, 'pass', 1)):
            changed = json.loads(json.dumps(self.rows))
            changed[index][key] = value
            with self.assertRaises(ValueError):
                self.verify(changed)
        for kwargs in ({'code': 1}, {'code': True}, {'run_id': 'a' * 32}, {'arch': 'x86_64'}):
            with self.assertRaises(ValueError):
                self.verify(**kwargs)

    def test_no_symbol_omission_or_required_feature_optional_exemption(self):
        for key, value in (('source_lock_sha256', '0' * 64), ('sdk_c_revision', 'master')):
            with self.assertRaises(ValueError):
                validate_definitions(dict(self.inputs, **{key: value}), 'phone', 'arm64')
        for index, key, value in ((0, 'functions', []), (0, 'declared_by_final_image', False),
                                  (1, 'needs_library', True), (1, 'implemented', True),
                                  (0, 'id', 'invented'), (0, 'source_inputs_sha256', {})):
            changed = json.loads(json.dumps(self.inputs))
            changed['contracts'][index][key] = value
            if key == 'declared_by_final_image':
                changed['contracts'][index]['required_by_active_contract'] = False
            with self.assertRaises(ValueError):
                validate_definitions(changed, 'phone', 'arm64')

    def test_verified_path_cannot_escape_or_switch_abi(self):
        spec = self.inputs['contracts'][0]
        self.assertEqual(runtime_path(spec, 'arm64'), '/system/lib64/ndk/libtest.so')
        for path in ('/data/libtest.so', '/lib/ndk/libtest.so', '/lib64/../libtest.so',
                     '/lib64/ndk/libother.so'):
            changed = dict(spec, image_entry={'image_path': path})
            with self.assertRaises(ValueError):
                runtime_path(changed, 'arm64')


if __name__ == '__main__':
    unittest.main()
