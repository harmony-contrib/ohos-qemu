"""Default suite wiring/completeness safety fixtures, not guest passes."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from verify_gap_closure import (behavior_results, requirements, optional_profile_resolutions,
                                NETFIREWALL_OPTIONAL, VIDEO_PROCESSING_OPTIONAL)
from run_root_probe import digest

ROOT = Path(__file__).resolve().parents[2]


class PackagedSuiteTests(unittest.TestCase):
    def test_all_gap_dimensions_and_duplicate_rejection(self):
        data = {'native_abi_gaps': [{'syscap': 'cap', 'library': 'lib.so'}],
            'arkts11_module_load_gaps': [{'module': 'load'}],
            'arkts11_runtime_export_gaps': [{'module': 'export', 'missing': [{'name': 'method'}]}],
            'arkts11_compiled_constant_enum_contracts': [{'module': 'enum', 'contracts': [{'name': 'Inline'}]}],
            'permission_registry_gaps': [{'permission': 'permission'}],
            'runtime_behavior_gaps': [{'id': 'actual'}]}
        self.assertEqual(set(requirements(data)), {'native:cap:lib.so', 'arkts_load:load',
            'arkts_export:export:method', 'const_enum:enum:Inline', 'permission:permission', 'behavior:actual'})
        data['runtime_behavior_gaps'] *= 2
        with self.assertRaises(ValueError):
            requirements(data)

    def test_old_checked_in_audit_and_missing_new_results_never_close_gaps(self):
        self.assertEqual(behavior_results(ROOT / 'docs/capability-audit', 'fixture', '0' * 64), {})

    def test_optional_profile_closure_keeps_official_2in1_firewall_and_partial_video_open(self):
        self.assertEqual(optional_profile_resolutions([], 'phone'), set())
        self.assertEqual(optional_profile_resolutions([NETFIREWALL_OPTIONAL], 'phone'),
                         {'behavior:netfirewall-feature-disabled'})
        self.assertEqual(optional_profile_resolutions([NETFIREWALL_OPTIONAL], '2in1'), set())
        self.assertEqual(optional_profile_resolutions(list(VIDEO_PROCESSING_OPTIONAL)[:1], 'phone'), set())
        self.assertEqual(optional_profile_resolutions(VIDEO_PROCESSING_OPTIONAL, '2in1'),
                         {'behavior:video-processing-libraries-not-packaged'})

    def test_permission_iteration_does_not_replace_package_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / 'ledger.json'
            ledger.write_text(json.dumps({'devices': {
                'phone': {'permission_registry_gaps': [{'permission': 'P'}]},
                '2in1': {'permission_registry_gaps': [{'permission': 'other'}]},
            }}))
            permissions = root / 'permission-registry'
            permissions.mkdir()
            permission_definitions = permissions / 'definitions.json'
            permission_definitions.write_text('[]')
            permission_raw = permissions / 'stdout.jsonl'
            permission_raw.write_text(json.dumps({'kind': 'definition', 'result': 0,
                                                  'permissionName': 'P'}) + '\n')
            (permissions / 'result.json').write_text(json.dumps({
                'status': 'pass', 'boot_id': 'boot', 'archive_sha256': 'archive',
                'kind': 'permission-registry', 'device': 'phone', 'run_id': 'run',
                'probe_exit_code': 0, 'kernel_boot_id_unchanged': True,
                'definitions': str(permission_definitions),
                'definitions_sha256': digest(permission_definitions),
                'log_sha256': digest(permission_raw), 'result': {'verified': True},
            }))
            native = root / 'native-gap-abi'
            native.mkdir()
            native_definitions = native / 'definitions.json'
            native_definitions.write_text(json.dumps({'actual_syscap_sha256': 'guest-caps'}))
            native_raw = native / 'stdout.jsonl'
            native_raw.write_text('{}\n')
            native_result = {'resolved_original_contracts': [NETFIREWALL_OPTIONAL],
                             'optional_undeclared_not_implemented': [NETFIREWALL_OPTIONAL]}
            (native / 'result.json').write_text(json.dumps({
                'status': 'pass', 'boot_id': 'boot', 'archive_sha256': 'archive',
                'kind': 'native-gap-abi', 'device': 'phone', 'arch': 'arm64',
                'run_id': 'run', 'probe_exit_code': 0,
                'kernel_boot_id_unchanged': True,
                'definitions': str(native_definitions),
                'definitions_sha256': digest(native_definitions),
                'log_sha256': digest(native_raw),
                'actual_guest_syscap_sha256': 'guest-caps', 'result': native_result,
            }))
            with patch('verify_gap_closure.LEDGER', ledger), \
                    patch('verify_permission_results.verify', return_value={'verified': True}), \
                    patch('verify_native_gap_abi_results.verify', return_value=native_result):
                closed = behavior_results(root, 'boot', 'archive', 'phone')
            self.assertIn('behavior:api26-permission-registry-gaps-phone', closed)
            self.assertIn('behavior:netfirewall-feature-disabled', closed)
            self.assertNotIn('behavior:api26-permission-registry-gaps-2in1', closed)

    def test_default_is_repository_runner_and_suite_retains_private_VM_ownership(self):
        matrix = (ROOT / 'scripts/run_device_type_matrix_build_docker.sh').read_text()
        self.assertIn('MATRIX_FIRST_VALIDATOR:-${SCRIPT_DIR}/validate_packaged_qemu.sh', matrix)
        text = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn('QemuGuest(boot_args).start()', text)
        self.assertIn('guest.close()', text)
        self.assertIn("'verify_gap_closure.py'", text)
        self.assertIn("'run_native_bindings_e2e.py'", text)
        self.assertIn("'run_service_init_contract_probe.py'", text)
        self.assertIn("'run_huks_compatibility_probe.py'", text)
        self.assertLess(text.index("'actual-HUKS-init-and-owned-legacy-migration'"),
                        text.index("for persona in ('web'"))
        for forbidden in ('--candidate-surface', '--candidate-fence', 'setenforce', 'server -k', 'system_wakeup'):
            self.assertNotIn(forbidden, text)

    def test_fresh_suite_checks_actual_kernel_and_hdi_not_compile_only(self):
        text = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        for builder in ('build_access_token_probe.sh', 'build_audio_suite_probe.sh', 'build_vibrator_hdi_probe.py',
                        'build_binder_sender_probe.py'):
            self.assertIn(builder, text)
        for kind in ('bitmap', 'userid', 'bpf', 'audio-suite', 'vibrator-hdi', 'binder-sender'):
            self.assertIn("'" + kind + "'", text)
        self.assertIn("'--boot-id', environment['boot_id']", text)
        self.assertLess(text.index("'actual-virtual-Vibrator-HDI-boundaries'"),
                        text.index("'complete-Cxx-ArkTS11-gap-closure'"))


if __name__ == '__main__':
    unittest.main()
