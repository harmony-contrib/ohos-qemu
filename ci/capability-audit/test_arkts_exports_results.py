"""Reflection completeness fixtures only; missing exports never become success."""
import json
from pathlib import Path
import tempfile
import unittest

from const_enum_contracts import LEDGER, sha256
from verify_arkts_exports_results import expected_modules, verify, settings_tts_verified, SETTINGS_TTS_VALUES

HERE = Path(__file__).resolve().parent
RUN = 'b' * 32


class ArktsExportsResultsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        template = HERE / 'arkts_exports_probe.ets'
        page = root / 'Index.ets'
        page.write_text(template.read_text().replace('__RUN__', RUN).replace('__MODULES__', json.dumps(expected_modules())))
        native = HERE / 'arkts_exports_hap_probe.cpp'
        self.inputs = {'role': 'ordinary_app', 'scope': 'actual_all_own_exports_collection_only',
            'run_id': RUN, 'arch': 'arm64', 'audit_baseline_sha256': sha256(LEDGER), 'modules': expected_modules(),
            'generated_source': str(page), 'generated_source_sha256': sha256(page),
            'native_source': str(native), 'native_source_sha256': sha256(native),
            'template': str(template), 'template_sha256': sha256(template)}
        self.report = {'runId': RUN, 'collection': 'all_own_string_properties',
            'export_collection_complete': True, 'modules': [
                {'module': name, 'load_status': 0, 'load_exception': False, 'module_type': 6,
                 'collection_status': 0, 'collection_exception': False, 'properties': []}
                for name in expected_modules()]}

    def test_full_collection_is_not_a_claim_that_empty_modules_or_backends_work(self):
        actual = verify(json.dumps(self.report), self.inputs, RUN, 'arm64')
        self.assertEqual(len(actual), len(expected_modules()))
        self.assertTrue(all(not row['properties'] for row in actual))
        self.report['modules'][0].update(load_status=1, load_exception=True, collection_status=2)
        self.assertEqual(verify(json.dumps(self.report), self.inputs, RUN, 'arm64')[0]['load_status'], 1)

    def test_missing_duplicate_stale_wrong_type_and_failed_load_claims_rejected(self):
        def reject(changed):
            with self.assertRaises(ValueError):
                verify(json.dumps(changed), self.inputs, RUN, 'arm64')
        for key, value in (('runId', 'a' * 32), ('collection', 'enumerable_only'),
                           ('export_collection_complete', 1), ('modules', self.report['modules'][:-1])):
            reject(dict(self.report, **{key: value}))
        row = self.report['modules'][0]
        row['properties'] = [{'name': 'call', 'read_status': 0, 'value_type': 7, 'read_exception': False,
                              'enum_contract_applicable': False, 'enum_contract_valid': False,
                              'settings_tts_values': [], 'settings_tts_alias_equal': False}]
        verify(json.dumps(self.report), self.inputs, RUN, 'arm64')
        row['properties'] *= 2
        reject(self.report)
        row['properties'] = row['properties'][:1]
        row['load_status'] = 1
        reject(self.report)
        row['load_status'] = 0
        row['properties'][0]['value_type'] = True
        reject(self.report)

    def test_accessibility_enum_requires_exact_native_member_contract(self):
        row = next(row for row in self.report['modules'] if row['module'] == '@ohos.accessibility')
        row['properties'] = [{'name': 'FocusMoveResultCode', 'read_status': 0, 'value_type': 6,
                              'read_exception': False, 'enum_contract_applicable': True,
                              'enum_contract_valid': True, 'settings_tts_values': [],
                              'settings_tts_alias_equal': False}]
        verify(json.dumps(self.report), self.inputs, RUN, 'arm64')
        row['properties'][0]['enum_contract_applicable'] = False
        with self.assertRaises(ValueError):
            verify(json.dumps(self.report), self.inputs, RUN, 'arm64')
        row['properties'][0]['enum_contract_applicable'] = True
        row['properties'][0]['value_type'] = 7
        with self.assertRaises(ValueError):
            verify(json.dumps(self.report), self.inputs, RUN, 'arm64')

    def test_typed_page_nonce_and_native_collector_cannot_change_under_a_report(self):
        for key, value in (('generated_source_sha256', '0' * 64), ('native_source_sha256', '0' * 64),
                           ('modules', []), ('arch', 'x86_64'), ('scope', 'all_capabilities_fixed')):
            with self.assertRaises(ValueError):
                verify(json.dumps(self.report), dict(self.inputs, **{key: value}), RUN, 'arm64')
        page = Path(self.inputs['generated_source'])
        page.write_text(page.read_text().replace('probe as NativeProbe', 'fake as NativeProbe'))
        self.inputs['generated_source_sha256'] = sha256(page)
        with self.assertRaises(ValueError):
            verify(json.dumps(self.report), self.inputs, RUN, 'arm64')

    def test_settings_namespace_requires_actual_keys_and_same_legacy_object(self):
        row = next(row for row in self.report['modules'] if row['module'] == '@ohos.settings')
        value = {'name': 'TTS', 'read_status': 0, 'value_type': 7, 'read_exception': False,
                 'enum_contract_applicable': False, 'enum_contract_valid': False,
                 'settings_tts_values': SETTINGS_TTS_VALUES, 'settings_tts_alias_equal': True}
        row['properties'] = [value]
        verify(json.dumps(self.report), self.inputs, RUN, 'arm64')
        self.assertTrue(settings_tts_verified(row['module'], value))
        for name, changed in [('settings_tts_values', []), ('settings_tts_values', SETTINGS_TTS_VALUES[:-1]),
                              ('settings_tts_values', ['wrong'] * 4), ('settings_tts_alias_equal', False),
                              ('read_exception', True), ('read_status', 1), ('value_type', 0)]:
            self.assertFalse(settings_tts_verified(row['module'], dict(value, **{name: changed})))
        self.assertFalse(settings_tts_verified('@ohos.other', value))

    def test_real_public_NAPI_collection_has_no_privilege_or_fake_export_fallback(self):
        native = (HERE / 'arkts_exports_hap_probe.cpp').read_text()
        self.assertIn('napi_load_module(env, moduleName, &module)', native)
        self.assertIn('napi_get_all_property_names(env, module, napi_key_own_only', native)
        self.assertIn('napi_key_skip_symbols', native)
        for forbidden in ('dlopen(', 'dlsym(', 'chmod(', 'setuid(', 'grantPermission', 'get_property_names(env, module'):
            self.assertNotIn(forbidden, native)
        self.assertIn("'arkts-exports'", (HERE / 'run_packaged_qemu_suite.py').read_text())


if __name__ == '__main__':
    unittest.main()
