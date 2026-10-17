#!/usr/bin/env python3
"""Host contract/counterexample tests; no Java, SDK, compiler or guest execution."""
import json
from pathlib import Path
import tempfile
import time
import struct
import unittest
from unittest.mock import patch
import warnings
import zipfile

import batch_apps_contact_picker_coordinator as c


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.bundle = c.driver.CALLER

    def tearDown(self):
        self.temp.cleanup()

    def json(self, name, value):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value)); return path

    def hap(self, path=None, *, permissions=(), bundle=None, duplicate=False):
        path = path or self.root / 'unsigned.hap'
        module = {'app': {'bundleName': bundle or self.bundle, 'debug': False},
            'module': {'name': 'entry', 'type': 'entry', 'requestPermissions': [{'name': p} for p in permissions],
                       'abilities': [{'name': 'EntryAbility'}]}}
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('module.json', json.dumps(module)); z.writestr('ets/modules.abc', b'compiled-ABC')
            z.writestr('resources.index', b'compiled-resources')
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore'); z.writestr('module.json', json.dumps(module))
        return path

    def sdk(self, *, nested=False, fixture=False):
        source = self.root / 'project'; source.mkdir()
        module = source / 'entry/src/main/module.json5'; module.parent.mkdir(parents=True)
        module.write_text('{"module": {}}')
        rows = {'entry/src/main/module.json5': c.verifier.sha(module)}
        spec = {'source_project': str(source), 'sdk_project': 'contacts-seed'}
        if fixture:
            fix = self.root / 'fixture'; fix.mkdir(); (fix / 'Index.ets').write_text('actual ETS')
            target = module.parent / 'ets/pages/Index.ets'; target.parent.mkdir(parents=True); target.write_text('actual ETS')
            rows['entry/src/main/ets/pages/Index.ets'] = c.verifier.sha(target)
            manifest = source / 'seed-source-manifest.json'
            manifest.write_text(json.dumps({'fixture_hashes': {'Index.ets': c.verifier.sha(fix / 'Index.ets')}}))
            rows['seed-source-manifest.json'] = c.verifier.sha(manifest)
            spec['source_manifest'] = c.descriptor(manifest)
        hap = self.hap(source / 'unsigned.hap')
        compile_log = self.root / 'compile.log'; compile_log.write_text('Hvigor BUILD SUCCESSFUL in 2s\n')
        deps_log = self.root / 'deps.log'; deps_log.write_text('dependencies installed\n')
        commands = [{'project': 'contacts-seed', 'label': label, 'argv': argv, 'exit_code': 0,
                     'log': str(log), 'sha256': c.verifier.sha(log)}
                    for label, argv, log in [('dependencies', ['node', 'ohpm', 'install'], deps_log),
                                            ('compile', ['node', 'hvigor', 'assembleHap'], compile_log)]]
        commands.append({'project': 'unrelated-failed-project', 'exit_code': 255})
        report = {'exit_code': 1, 'source_commit': 'a' * 40, 'runner_sha256': 'b' * 64,
                  'source_files': {'contacts-seed': rows} if nested else {'contacts-seed/' + k: v for k, v in rows.items()},
                  'commands': commands, 'haps': [{'project': 'contacts-seed', **c.descriptor(hap), 'bytes': hap.stat().st_size}]}
        evidence = self.json('sdk-evidence.json', report)
        spec.update(sdk_evidence=c.descriptor(evidence), unsigned_hap=c.descriptor(hap))
        return spec, report, evidence

    def rewrite(self, spec, report, evidence):
        evidence.write_text(json.dumps(report)); spec['sdk_evidence'] = c.descriptor(evidence)

    def test_partial_project_success_preserves_failed_batch(self):
        spec, report, evidence = self.sdk()
        result = c.verify_sdk_project(spec)
        self.assertEqual(result['batch_exit_code'], 1)
        self.assertEqual(json.loads(evidence.read_text())['exit_code'], 1)
        self.assertEqual(result['project_commands_verified'], 2)

    def test_nested_provider_format_without_hap_project(self):
        spec, report, evidence = self.sdk(nested=True)
        del report['haps'][0]['project']; self.rewrite(spec, report, evidence)
        self.assertEqual(c.verify_sdk_project(spec)['source_files_verified'], 1)

    def test_failed_own_project_cannot_borrow_other_success(self):
        spec, report, evidence = self.sdk(); report['commands'][1]['exit_code'] = 1
        self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'failed or incomplete'): c.verify_sdk_project(spec)

    def test_missing_own_compile_rejected(self):
        spec, report, evidence = self.sdk(); report['commands'][1]['argv'] = ['node', 'other']
        self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'assembleHap'): c.verify_sdk_project(spec)

    def test_actual_log_tamper_rejected(self):
        spec, _, _ = self.sdk(); (self.root / 'compile.log').write_text('fake pass')
        with self.assertRaisesRegex(ValueError, 'artifact hash'): c.verify_sdk_project(spec)

    def test_self_reported_exit_zero_without_hvigor_success_rejected(self):
        spec, report, evidence = self.sdk(); log = self.root / 'compile.log'; log.write_text('BUILD FAILED')
        report['commands'][1]['sha256'] = c.verifier.sha(log); self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'Hvigor success'): c.verify_sdk_project(spec)

    def test_current_source_tamper_rejected(self):
        spec, _, _ = self.sdk(); (Path(spec['source_project']) / 'entry/src/main/module.json5').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'source changed'): c.verify_sdk_project(spec)

    def test_source_traversal_rejected(self):
        spec, report, evidence = self.sdk(nested=True)
        report['source_files']['contacts-seed']['../escape'] = 'a' * 64; self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'unsafe SDK source'): c.verify_sdk_project(spec)

    def test_wrong_project_hap_rejected(self):
        spec, report, evidence = self.sdk(); report['haps'][0]['project'] = 'other'
        self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'HAP artifact/project'): c.verify_sdk_project(spec)

    def test_compiled_fixture_and_manifest_bound(self):
        spec, report, evidence = self.sdk(fixture=True)
        fix = self.root / 'fixture'
        c.verify_sdk_project(spec, fixture=fix, source_manifest='seed-source-manifest.json')
        source = Path(spec['source_project']) / 'entry/src/main/ets/pages/Index.ets'; source.write_text('different ETS')
        report['source_files']['contacts-seed/entry/src/main/ets/pages/Index.ets'] = c.verifier.sha(source)
        self.rewrite(spec, report, evidence)
        with self.assertRaisesRegex(ValueError, 'compiled ETS differs'):
            c.verify_sdk_project(spec, fixture=fix, source_manifest='seed-source-manifest.json')

    def test_signed_payload_comparison_detects_abc_change(self):
        unsigned = self.hap(); before = c.hap_contents(unsigned)[1]
        modified = self.hap(self.root / 'modified.hap')
        with zipfile.ZipFile(modified, 'a') as archive: archive.writestr('ets/new.abc', 'injected')
        self.assertNotEqual(before, c.hap_contents(modified)[1])

    def test_duplicate_hap_member_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate HAP'): c.hap_contents(self.hap(duplicate=True))

    def test_ordinary_caller_extra_permission_rejected(self):
        with self.assertRaisesRegex(ValueError, 'permission surface'):
            c.ordinary_hap(self.hap(permissions=c.driver.PERMISSIONS), self.bundle, [])

    def profile(self):
        now = int(time.time())
        return {'type': 'debug', 'bundle-info': {'bundle-name': self.bundle, 'apl': 'normal', 'app-feature': 'hos_normal_app'},
                'debug-info': {'device-ids': ['a' * 64]}, 'acls': {'allowed-acls': []},
                'permissions': {'restricted-permissions': []}, 'validity': {'not-before': now - 1, 'not-after': now + 3600}}

    def test_wrong_udid_apl_acl_and_expired_profile_rejected(self):
        for field in ('udid', 'apl', 'acl', 'expired'):
            with self.subTest(field=field):
                value = self.profile()
                if field == 'udid': value['debug-info']['device-ids'] = ['b' * 64]
                if field == 'apl': value['bundle-info']['apl'] = 'system_basic'
                if field == 'acl': value['acls']['allowed-acls'] = ['ohos.permission.READ_CONTACTS']
                if field == 'expired': value['validity']['not-after'] = 0
                with self.assertRaises(ValueError): c.verify_profile(value, self.bundle, [], 'a' * 64)

    def test_system_basic_query_needs_exact_feature_empty_acl(self):
        value = self.profile(); value['bundle-info'].update(apl='system_basic', **{'app-feature': 'hos_system_app'})
        c.verify_profile(value, self.bundle, ['ohos.permission.READ_IMAGEVIDEO'], 'a' * 64, apl='system_basic', system_app=True)
        value['permissions']['restricted-permissions'] = ['ohos.permission.READ_IMAGEVIDEO']
        with self.assertRaises(ValueError):
            c.verify_profile(value, self.bundle, ['ohos.permission.READ_IMAGEVIDEO'], 'a' * 64, apl='system_basic', system_app=True)

    def test_contacts_seed_profile_flag_is_narrow_and_normal_default_unchanged(self):
        args = ('/unsigned.hap', self.bundle, [], 'a' * 64, '/dist', '/dist/tool.jar', '/signed.hap')
        ordinary = c.normal_sign_argv(*args)
        self.assertNotIn('--contacts-seed-profile', ordinary)
        seed = c.normal_sign_argv(args[0], c.driver.SEED, c.driver.PERMISSIONS, *args[3:], contacts_seed=True)
        self.assertEqual(seed[-1], '--contacts-seed-profile')
        for bundle, permissions in [(self.bundle, c.driver.PERMISSIONS), (c.driver.SEED, []),
                                    (c.driver.SEED, c.driver.PERMISSIONS + ['ohos.permission.GET_BUNDLE_INFO'])]:
            with self.subTest(bundle=bundle, permissions=permissions), self.assertRaises(ValueError):
                c.normal_sign_argv(args[0], bundle, permissions, *args[3:], contacts_seed=True)
        with self.assertRaises(ValueError): c.normal_sign_argv(*args, contacts_seed=1)

    def test_identity_raw_command_cannot_substitute_another_script(self):
        item = self.json('0001-BMS.log', {'host': 'only'}); desc = c.descriptor(item)
        marker = '__QEMU_CHILD_EXIT_' + 'a' * 32 + '__='; script = 'bm dump -n ' + self.bundle
        log = self.root / 'guest-0001-BMS.log'; log.write_text(item.read_text() + '\n' + marker + '0\n')
        argv = ['hdc', '-t', 'owned', 'shell', '(' + script + '); task_child_rc=$?; printf "\\n' + marker + '%s\\n" "$task_child_rc"']
        report = {'guest_commands': [{'argv': argv, 'exit_code': 0, 'log': str(log), 'sha256': c.verifier.sha(log)}]}
        self.assertEqual(c.runtime_raw_bound(report, desc, script, 'owned')[0], item.read_text())
        with self.assertRaises(ValueError): c.runtime_raw_bound(report, desc, 'cat /unrelated', 'owned')
        with self.assertRaises(ValueError): c.runtime_raw_bound(report, desc, script, 'other-guest')

    def test_contacts_token_replay_rejects_reinstall_and_missing_bms_join(self):
        target = 'owned'; run = 'contacts_host'; bundle = c.driver.SEED
        app = {'bundleName': bundle, 'uid': 20010001, 'accessTokenId': 123, 'isSystemApp': True, 'appPrivilegeLevel': 'system_basic'}
        report = {'run_id': run, 'observer_remote': '/data/local/tmp/' + run + '_observer', 'guest_commands': []}
        def raw(number, script, text):
            label = str(number).zfill(4) + '-identity.log'
            path = self.root / label; path.write_text(text)
            marker = '__QEMU_CHILD_EXIT_' + str(number) * 32 + '__='
            log = self.root / ('guest-' + label); log.write_text(text + '\n' + marker + '0\n')
            report['guest_commands'].append({'argv': ['hdc', '-t', target, 'shell', '(' + script + '); task_child_rc=$?; printf "\\n' + marker + '%s\\n" "$task_child_rc"'], 'exit_code': 0, 'log': str(log), 'sha256': c.verifier.sha(log)})
            return c.descriptor(path)
        bms = json.dumps({'applicationInfo': app})
        before = raw(1, 'bm dump -n ' + bundle, bms)
        token = raw(2, c.shlex.join([report['observer_remote'], 'permissions', bundle, '123']), json.dumps({
            'api': 'AccessTokenKit::VerifyAccessToken', 'bundle_name': bundle, 'token_id': 123, 'READ_CONTACTS': -1, 'WRITE_CONTACTS': -1}))
        after = raw(3, 'bm dump -n ' + bundle, bms)
        report['permission_bms_bindings'] = [{'bundle': bundle, 'token': token, 'before': before, 'after': after}]
        self.assertEqual(c.runtime_token_bound(report, token, bundle, app, target)['READ_CONTACTS'], -1)
        with self.assertRaises(ValueError): c.runtime_token_bound(report, token, bundle, dict(app, accessTokenId=124), target)
        report['permission_bms_bindings'] = []
        with self.assertRaises(ValueError): c.runtime_token_bound(report, token, bundle, app, target)

    def test_wrong_actual_application_leaf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'signer leaf'):
            c.application_leaf('certificate #0\nSHA256: ' + '0' * 64 + '\ncertificate #1\nSHA256: ' + c.APP_LEAF)

    def crypto_stub(self, failure=None):
        """Models tool outputs to test parser rejection, not crypto execution."""
        dist = self.root / 'dist'; dist.mkdir(); jar = dist / 'hap-sign-tool.jar'; jar.write_text('unit-only')
        (dist / 'OpenHarmonyProfileDebug.pem').write_text(('-----BEGIN CERTIFICATE-----\nunit-only\n-----END CERTIFICATE-----\n') * 3)
        value = self.profile()
        if failure == 'udid': value['debug-info']['device-ids'] = ['b' * 64]
        calls = []
        def command(argv, label):
            calls.append((argv, label))
            if label == 'verify-app':
                Path(argv[argv.index('-outCertChain') + 1]).write_text('unit chain')
                Path(argv[argv.index('-outProfile') + 1]).write_text('unit p7b')
                markers = ['verify codesign success', 'Digest verify result: true', 'verify permission sign success', 'verify-app success']
                if failure == 'codesign': markers.pop(0)
                return '\n'.join(markers) + '\ncertificate #0\nSHA256: ' + c.APP_LEAF + '\ncertificate #1\n'
            if label == 'verify-profile':
                Path(argv[-1]).write_text(json.dumps({'verifiedPassed': failure != 'java-profile', 'content': value}))
                return 'verify-profile success'
            if label == 'profile-leaf-fingerprint': return 'sha256 Fingerprint=' + c.PROFILE_LEAF
            if label == 'profile-CMS-signature':
                self.assertIn('-nointern', argv); self.assertIn('-certfile', argv)
                Path(argv[-1]).write_text(json.dumps({**value, 'changed': True} if failure == 'CMS' else value))
                return 'CMS Verification successful'
            raise AssertionError(label)
        return dist, jar, calls, command

    def test_signature_parser_requires_all_four_checks_and_fixed_CMS_identity(self):
        dist, jar, calls, command = self.crypto_stub()
        with patch.object(c, 'signer_inputs', return_value=(dist, jar, {})):
            proof = c.verify_signed_hap_artifacts(self.hap(), self.bundle, [], 'a' * 64, dist, jar, self.root / 'verification', command)
        self.assertEqual(len(calls), 4)
        self.assertEqual(c.load(c.checked_artifact(proof['decoded_profile']))['bundle-info']['apl'], 'normal')

    def test_signature_parser_rejects_missing_codesign(self):
        dist, jar, _, command = self.crypto_stub('codesign')
        with patch.object(c, 'signer_inputs', return_value=(dist, jar, {})), self.assertRaisesRegex(ValueError, 'code-sign'):
            c.verify_signed_hap_artifacts(self.hap(), self.bundle, [], 'a' * 64, dist, jar, self.root / 'verification', command)

    def test_signature_parser_rejects_unverified_java_profile(self):
        dist, jar, _, command = self.crypto_stub('java-profile')
        with patch.object(c, 'signer_inputs', return_value=(dist, jar, {})), self.assertRaisesRegex(ValueError, 'not verified'):
            c.verify_signed_hap_artifacts(self.hap(), self.bundle, [], 'a' * 64, dist, jar, self.root / 'verification', command)

    def test_signature_parser_rejects_CMS_mismatch(self):
        dist, jar, _, command = self.crypto_stub('CMS')
        with patch.object(c, 'signer_inputs', return_value=(dist, jar, {})), self.assertRaisesRegex(ValueError, 'CMS decoded'):
            c.verify_signed_hap_artifacts(self.hap(), self.bundle, [], 'a' * 64, dist, jar, self.root / 'verification', command)

    def test_signature_parser_rejects_wrong_actual_udid(self):
        dist, jar, _, command = self.crypto_stub('udid')
        with patch.object(c, 'signer_inputs', return_value=(dist, jar, {})), self.assertRaisesRegex(ValueError, 'UDID'):
            c.verify_signed_hap_artifacts(self.hap(), self.bundle, [], 'a' * 64, dist, jar, self.root / 'verification', command)

    def test_driver_pass_does_not_replace_raw_verifier(self):
        self.json('driver-report.json', {'run_id': 'nonce', 'status': 'pass', 'failures': [], 'test_environment': {'boot_id': 'boot'}})
        with patch.object(c.verifier, 'verify_runtime', side_effect=ValueError('bad raw AMS')) as raw:
            with self.assertRaisesRegex(ValueError, 'bad raw AMS'): c.independent_result(self.root, 'nonce', 'boot')
        raw.assert_called_once()

    def test_missing_matrix_case_or_dual_slot_rejected(self):
        self.json('driver-report.json', {'run_id': 'nonce', 'status': 'pass', 'failures': [], 'test_environment': {'boot_id': 'boot'}})
        rows = [{'case_id': row['id'], 'invocation_id': row['id'] + '/' + slot} for row in c.verifier.MATRIX.values()
                if row['required'] for slot in row['slots']]
        value = {'raw_results_verified': True, 'scope': 'required_caller_matrix', 'run_id': 'nonce', 'observations': rows}
        with patch.object(c.verifier, 'verify_runtime', return_value=value):
            self.assertEqual(len(c.independent_result(self.root, 'nonce', 'boot')['observations']), 16)
            value['observations'] = rows[:-1]
            with self.assertRaisesRegex(ValueError, 'complete matrix'): c.independent_result(self.root, 'nonce', 'boot')

    def test_driver_foreign_boot_rejected_before_raw_verification(self):
        self.json('driver-report.json', {'run_id': 'nonce', 'status': 'pass', 'failures': [], 'test_environment': {'boot_id': 'other'}})
        with patch.object(c.verifier, 'verify_runtime') as raw:
            with self.assertRaisesRegex(ValueError, 'different guest'): c.independent_result(self.root, 'nonce', 'boot')
        raw.assert_not_called()

    def test_full_boundary_scope_requires_both_extra_raw_invocations(self):
        marker = '__UITEST_EXIT_' + 'a' * 32 + '__='
        log = self.root / 'transport-actual-home.log'; log.write_text('actual unit input result\n' + marker + '0\n')
        home = {**c.descriptor(log), 'exit_code': 0,
                'argv': ['hdc', '-t', '127.0.0.1:5555', 'shell', 'uitest uiInput keyEvent Home; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"']}
        report = {'run_id': 'nonce', 'status': 'pass', 'failures': [],
                  'test_environment': {'boot_id': 'boot', 'target': '127.0.0.1:5555'}, 'commands': [home]}
        self.json('driver-report.json', report)
        rows = [{'case_id': row['id'], 'invocation_id': row['id'] + '/' + slot} for row in c.verifier.MATRIX.values()
                if row['required'] for slot in row['slots']]
        value = {'raw_results_verified': True, 'scope': 'required_caller_matrix', 'run_id': 'nonce', 'observations': rows}
        with patch.object(c.verifier, 'verify_runtime', return_value=value):
            self.assertFalse(c.independent_result(self.root, 'nonce', 'boot')['full_boundaries_verified'])
            with self.assertRaisesRegex(ValueError, 'complete matrix'): c.independent_result(self.root, 'nonce', 'boot', True)
            value['observations'] = rows + [{'case_id': name, 'invocation_id': name + '/a'} for name in c.FULL_BOUNDARY_CASES]
            result = c.independent_result(self.root, 'nonce', 'boot', True)
            self.assertTrue(result['full_boundaries_verified']); self.assertEqual(len(result['observations']), 18)
            report['commands'] = []; self.json('driver-report.json', report)
            with self.assertRaisesRegex(ValueError, 'actual Home command'): c.independent_result(self.root, 'nonce', 'boot', True)
            report['commands'] = [home]; self.json('driver-report.json', report)
            value['observations'].pop()
            with self.assertRaisesRegex(ValueError, 'complete matrix'): c.independent_result(self.root, 'nonce', 'boot', True)

    def test_real_raw_verifier_rejects_shortened_native_deadline(self):
        import test_batch_apps_contact_picker_runtime as synthetic
        fixture = synthetic.RuntimeVerifier('test_complete_synthetic_verifier_fixture_does_not_close_runtime_gate')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.make_case('deadline')
        action = next(event for event in fixture.ui['events'] if event['kind'] == 'done'); action['kind'] = 'deadline_wait'
        result = next(row for row in fixture.rows if row['event'] == 'reject')
        result['timestamp_ms'] = 600100
        self.assertTrue(fixture.verify('deadline')['raw_results_verified'])
        result['timestamp_ms'] = 600099
        with self.assertRaisesRegex(ValueError, 'native deadline'): fixture.verify('deadline')

    def test_real_raw_navigation_requires_home_action_and_provider_closure(self):
        import test_batch_apps_contact_picker_runtime as synthetic
        fixture = synthetic.RuntimeVerifier('test_complete_synthetic_verifier_fixture_does_not_close_runtime_gate')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.make_case('navigation-dismiss')
        action = next(event for event in fixture.ui['events'] if event['kind'] == 'done'); action['kind'] = 'home'
        self.assertTrue(fixture.verify('navigation-dismiss')['raw_results_verified'])
        action['kind'] = 'done'
        with self.assertRaisesRegex(ValueError, 'terminal UI action'): fixture.verify('navigation-dismiss')

    def test_real_installed_path_must_be_unique_and_own_bundle(self):
        path = '/data/app/el1/bundle/public/' + self.bundle + '/entry.hap'
        self.assertEqual(c.installed_path(json.dumps({'hapPath': path}), self.bundle), path)
        with self.assertRaises(ValueError): c.installed_path(json.dumps({'hapPath': '/system/app/provider.hap'}), self.bundle)
        with self.assertRaises(ValueError):
            c.installed_path(json.dumps({'a': {'hapPath': path}, 'b': {'hapPath': path.replace('entry.hap', 'other.hap')}}), self.bundle)

    def test_observer_receipt_is_not_optional(self):
        binary = self.root / 'observer'; binary.write_bytes(b'\x7fELF' + b'\0' * 60)
        with self.assertRaises(ValueError): c.verify_observer(binary, self.root / 'missing.json')

    def test_plan_only_helper_cannot_be_used(self):
        binary = self.root / 'observer'; binary.write_bytes(b'\x7fELF' + b'\0' * 60)
        receipt = self.json('builder.json', {'plan_only': True, 'product': 'arm64_virt', 'changed_inputs': []})
        with self.assertRaisesRegex(ValueError, 'actual immutable product'): c.verify_observer(binary, receipt)

    def test_actual_public_cleanup_not_a_summary_pass(self):
        raw_delete = self.json('delete.json', {'run_id': 'nonce', 'api': 'contact.deleteContact', 'error': None, 'keys': ['nonce-key']})
        raw_read = self.json('read.json', {'run_id': 'nonce', 'api': 'contact.queryContacts', 'error': None, 'contacts': []})
        receipt = self.json('cleanup.json', {'run_id': 'nonce', 'delete_api': 'contact.deleteContact', 'read_api': 'contact.queryContacts',
            'deleted_keys': ['nonce-key'], 'remaining_contacts': [], 'raw_delete': c.descriptor(raw_delete), 'raw_readback': c.descriptor(raw_read)})
        c.verify_public_cleanup(receipt, 'nonce')
        read = json.loads(raw_read.read_text()); read['contacts'] = [{'key': 'nonce-key'}]; raw_read.write_text(json.dumps(read))
        value = json.loads(receipt.read_text()); value['raw_readback'] = c.descriptor(raw_read); receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'read-back cleanup failed'): c.verify_public_cleanup(receipt, 'nonce')

    def cleanup_fixture(self, *, with_ams=False):
        nonce, target = 'nonce', '127.0.0.1:5555'
        remote = '/data/local/tmp/nonce_observer'
        cleanup = {'public_CRUD_required': False, 'installed_bundles': [self.bundle], 'target': target,
                   'processes': {}, 'observer_removed': True, 'captures': {}}
        def capture(name, script, text):
            path = self.root / name; path.write_text(text)
            log = self.root / (name + '.transport'); log.write_text(text + '\n__QEMU_CHILD_EXIT_' + 'a' * 32 + '__=0\n')
            desc = c.descriptor(path)
            cleanup['captures'][desc['path']] = {'artifact': desc, 'script': script, 'command': {'exit_code': 0,
                'argv': ['hdc', '-t', target, 'shell', '(' + script + '); task_child_rc=$?; ...'], 'log': str(log), 'sha256': c.verifier.sha(log)}}
            return desc
        cleanup['processes'][self.bundle] = capture('process.json', ' '.join([remote, 'processes', self.bundle]),
            json.dumps({'api': 'AppMgrClient::GetAllRunningProcesses', 'error_code': 0, 'bundle_name': self.bundle, 'processes': []}))
        cleanup['BMS_after'] = capture('BMS.log', 'bm dump -a', 'com.ohos.contacts\ncom.ohos.settings\n')
        if with_ams:
            from test_batch_apps_contact_picker_runtime import ams_fixture, provider_fixture
            cleanup.update(provider_uid=10004, caller_uid=20000100)
            cleanup['provider_bms'] = capture('provider-BMS.log', 'bm dump -n ' + c.driver.PROVIDER,
                c.driver.PROVIDER + ':\n' + json.dumps(provider_fixture()))
            cleanup['AMS_after'] = capture('AMS.log', 'aa dump -a -u 100', ams_fixture([]))
        cleanup['observer_removal'] = capture('observer.log', 'rm -f ' + remote + ' && test ! -e ' + remote, '')
        return cleanup

    def test_cleanup_consumes_actual_transport_and_guest_exit(self):
        cleanup = self.cleanup_fixture(); c.verify_resources_cleanup(cleanup, 'nonce', cleanup['target'])
        row = cleanup['captures'][cleanup['BMS_after']['path']]['command']
        log = Path(row['log']); log.write_text('different raw output\n__QEMU_CHILD_EXIT_' + 'a' * 32 + '__=0\n')
        row['sha256'] = c.verifier.sha(log)
        with self.assertRaisesRegex(ValueError, 'actual successful guest output'): c.verify_resources_cleanup(cleanup, 'nonce')

    def test_cleanup_singleton_binding_requires_actual_bms_transport_and_not_claimed_uid(self):
        cleanup = self.cleanup_fixture(with_ams=True)
        c.verify_resources_cleanup(cleanup, 'nonce', cleanup['target'])
        bound = cleanup.pop('provider_bms')
        with self.assertRaisesRegex(ValueError, 'singleton cleanup BMS binding'):
            c.verify_resources_cleanup(cleanup, 'nonce')
        cleanup['provider_bms'] = bound; cleanup['provider_uid'] = 20010004
        with self.assertRaisesRegex(ValueError, 'differs from actual BMS'):
            c.verify_resources_cleanup(cleanup, 'nonce')
        cleanup['provider_uid'] = 10004
        cleanup['captures'][bound['path']]['script'] = 'bm dump -n foreign.bundle'
        with self.assertRaises(ValueError): c.verify_resources_cleanup(cleanup, 'nonce')

    def test_cleanup_rejects_wrong_guest(self):
        cleanup = self.cleanup_fixture()
        with self.assertRaisesRegex(ValueError, 'different guest'): c.verify_resources_cleanup(cleanup, 'nonce', '127.0.0.1:5556')

    def test_cleanup_rejects_nonzero_guest_exit_despite_host_exit_zero(self):
        cleanup = self.cleanup_fixture(); row = cleanup['captures'][cleanup['observer_removal']['path']]['command']
        log = Path(row['log']); log.write_text('\n__QEMU_CHILD_EXIT_' + 'a' * 32 + '__=1\n'); row['sha256'] = c.verifier.sha(log)
        with self.assertRaisesRegex(ValueError, 'actual successful guest output'): c.verify_resources_cleanup(cleanup, 'nonce')

    def test_cleanup_rejects_deleted_summary_without_removal_observation(self):
        cleanup = self.cleanup_fixture(); del cleanup['observer_removal']
        with self.assertRaisesRegex(ValueError, 'removal proof'): c.verify_resources_cleanup(cleanup, 'nonce')

    def observer_fixture(self, *, recheck=False, truncated=False):
        # Synthetic ELF/command-receipt parser fixture, never native evidence.
        fixture = c.driver.FIX / 'observer.cpp'; source = self.root / 'observer.cpp'; source.write_bytes(fixture.read_bytes())
        builder = self.root / 'batch_system_build_runtime_helpers.py'; builder.write_text('unit builder identity')
        binary = self.root / 'contact_picker_observer'
        data = bytearray(256); data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HH', data, 16, 3, 183); struct.pack_into('<Q', data, 32, 64); struct.pack_into('<HH', data, 54, 56, 2)
        interpreter = b'/lib/ld-musl-aarch64.so.1\0'; data[192:192 + len(interpreter)] = interpreter
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), 4096)
        struct.pack_into('<IIQQQQQQ', data, 120, 3, 4, 192, 0, 0, len(interpreter), len(interpreter), 1)
        binary.write_bytes(data[:64] if truncated else data)
        compile_cmd = ['clang++', '--target=aarch64-linux-ohos', '-fno-exceptions', '-fsanitize-cfi-cross-dso', '-fsanitize=cfi', '-c', str(source), '-o', 'unit.o']
        link_cmd = ['clang++', '-pie', '-o', str(binary), 'unit.o']
        commands = []
        for kind, argv in [('compile', compile_cmd), ('link', link_cmd), ('actual-ELF-ABI', ['llvm-readelf', '-h', str(binary)])]:
            log = self.root / (kind + '.log'); log.write_text('__cfi_check std::__h::basic_string' if kind == 'actual-ELF-ABI' else 'unit command output')
            commands.append({'label': 'contact_picker_observer-' + kind, 'argv': argv, 'exit_code': 0, 'log': str(log), 'sha256': c.verifier.sha(log)})
        row = {'status': 'pass_compile_link_ONLY', 'fixture': 'batch_apps/contact_picker_seed/observer.cpp',
               'private_source_sha256': c.verifier.sha(fixture), 'source': c.descriptor(fixture), 'binary': str(binary),
               'binary_sha256': c.verifier.sha(binary), 'CFI_preserved': True, 'anchors': [{'unit': True}],
               'actual_compiler_dependencies': [{'unit': True}], 'actual_link_inputs': [{'unit': True}],
               'DT_NEEDED': ['libapp_manager.z.so', 'libaccesstoken_sdk.z.so'], 'compile_command': compile_cmd, 'link_command': link_cmd}
        report = {'plan_only': False, 'product': 'arm64_virt', 'changed_inputs': [], 'builder_sha256': c.verifier.sha(builder),
                  'commands': commands, 'helpers': {'contact_picker_observer': row}, 'status': 'pass_compile_link_ONLY'}
        if recheck:
            old = self.json('original.json', report)
            report = {**report, 'verify_existing': True, 'original_report': {**c.descriptor(old), 'rewritten': False,
                'status': report['status'], 'builder_sha256': report['builder_sha256']},
                'commands': [commands[-1]], 'original_commands': [dict(command, verified_log={'path': command['log'], 'sha256': command['sha256']}) for command in commands]}
            report['helpers']['contact_picker_observer'] = {key: value for key, value in row.items()
                if key not in ('source', 'fixture', 'private_source_sha256', 'anchors')}
            report['helpers']['contact_picker_observer']['reused_artifacts'] = {'source': c.descriptor(source), 'binary': c.descriptor(binary)}
        receipt = self.json('builder.json', report)
        return binary, receipt

    def test_legacy_helper_recheck_cannot_claim_installed_runtime_bindings(self):
        binary, receipt = self.observer_fixture(recheck=True)
        with patch.object(c, 'HERE', self.root), self.assertRaisesRegex(ValueError, 'actual product musl dynamic'):
            c.verify_observer(binary, receipt)

    def test_truncated_elf_still_rejected_with_matching_receipt_hash(self):
        binary, receipt = self.observer_fixture(truncated=True)
        with patch.object(c, 'HERE', self.root), self.assertRaisesRegex(ValueError, 'program headers'):
            c.verify_observer(binary, receipt)

    def test_missing_actual_readelf_cannot_borrow_compile_success(self):
        binary, receipt = self.observer_fixture()
        value = c.load(receipt); value['commands'].pop(); receipt.write_text(json.dumps(value))
        with patch.object(c, 'HERE', self.root), self.assertRaisesRegex(ValueError, 'ELF recheck missing'):
            c.verify_observer(binary, receipt)


if __name__ == '__main__': unittest.main()
