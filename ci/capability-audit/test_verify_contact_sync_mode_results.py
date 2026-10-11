"""Strict typed/native enum fixtures, not a packaged guest pass."""
import json
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from contact_sync_mode_contract import HERE, TEMPLATE, RECORD_CLASSES, PHOTO_RECORD_CLASSES, expected, expected_audio, expected_photo, inputs, sha256, verify_inputs
from verify_contact_sync_mode_results import verify

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010000}})
TS = Path(os.environ.get('OHOS_AUDIT_TYPESCRIPT',
          '/Applications/DevEco-Studio.app/Contents/plugins/openharmony/ace-server/node_modules/typescript'))


class ContactSyncModeResultTests(unittest.TestCase):
    def observed(self):
        records = []
        for name in RECORD_CLASSES:
            first, second = RUN + '-' + name + '-changed', RUN + '-second-' + name
            if name == 'ContactAttributes':
                first, second = '[1,8]', '[4]'
            elif name == 'Holder':
                first, second = 'com.ohos.contacts:17', 'com.ohos.contacts:29'
            records.append(dict(name=name, first=first, second=second, flags=[True, True, True]))
        return {'runId': RUN, 'values': [1, 2], 'native': {'values': [1, 2], 'statuses': [0] * 14,
                'types': [6, 7, 3, 3], 'own': [True, True, True], 'exception': False},
                'audioValues': [0, 1], 'audioNative': {'values': [0, 1], 'statuses': [0] * 14,
                'types': [6, 6, 3, 3], 'own': [True, True, True], 'exception': False},
                'photoValues': [0], 'photoNative': {'values': [0], 'statuses': [0] * 10,
                'types': [6, 6, 3], 'own': [True, True], 'exception': False}, 'records': records,
                'stateRecords': {'flags': [True] * 12, 'values': [RUN + suffix for suffix in
                    ('-first-changed', '-second', '-collection', '-other')]},
                'photoRecords': [dict(name=name, first=first, second=second, flags=[True] * 4)
                    for name, (first, second) in zip(PHOTO_RECORD_CLASSES, [
                        (RUN + '-cover-changed', RUN + '-cover-second'), ('image/*', 'video/*'), ('17', '29'),
                        (RUN + '-info-changed', RUN + '-info-second'),
                        (json.dumps([RUN + '-first', RUN + '-second'], separators=(',', ':')), '[]'),
                        (RUN + '-context-changed', RUN + '-context-second')])]}

    def test_record_constructor_prototypes_properties_and_isolation_cannot_be_missing(self):
        row = self.observed()
        self.assertEqual(verify(json.dumps(row), RUN, IDENTITY)['record_classes'], list(RECORD_CLASSES))
        for index in range(len(RECORD_CLASSES)):
            for field, value in (('name', 'fake'), ('first', 'wrong'), ('second', 'shared'),
                                 ('flags', [True, True, False]), ('flags', [1, 1, 1])):
                changed = copy.deepcopy(row)
                changed['records'][index][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    verify(json.dumps(changed), RUN, IDENTITY)
        for records in (row['records'][:-1], row['records'] * 2, list(reversed(row['records']))):
            with self.assertRaises(ValueError):
                verify(json.dumps(dict(row, records=records)), RUN, IDENTITY)

    def test_record_closure_rechecks_raw_evidence_and_does_not_close_provider(self):
        from verify_gap_closure import behavior_results
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = self.sdk(root / 'sdk')
            project = root / 'project'
            page = project / 'entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text(TEMPLATE.read_text().replace('__RUN__', RUN))
            child = root / 'contact-sync-mode'
            child.mkdir()
            compiled = child / 'inputs.json'
            compiled.write_text(json.dumps(inputs(project, sdk, 'arm64', RUN)))
            raw = child / 'results.log'
            raw.write_text(json.dumps(self.observed()))
            identity = child / 'application-identity.json'
            identity.write_text(IDENTITY)
            result = child / 'result.json'
            result.write_text(json.dumps(dict(status='pass', result=verify(raw.read_text(), RUN, IDENTITY),
                archive_sha256='a' * 64, run_id=RUN, arch='arm64', compiled_inputs_sha256=sha256(compiled),
                results_sha256=sha256(raw), application_identity_sha256=sha256(identity))))
            evidence = dict(status='pass', boot_id='test-boot', archive_sha256='a' * 64,
                persona='contact-sync-mode', run_id=RUN, arch='arm64', compiled_contract_inputs=str(compiled),
                compiled_contract_inputs_sha256=sha256(compiled), result=str(result), result_sha256=sha256(result),
                raw_results_sha256=sha256(raw), ordinary_identity_sha256=sha256(identity))
            path = child / 'evidence.json'
            path.write_text(json.dumps(evidence))
            closed = behavior_results(root, 'test-boot', 'a' * 64, 'phone')
            self.assertEqual(len(closed), 20)
            for name in PHOTO_RECORD_CLASSES:
                self.assertIn('arkts_export:@ohos.file.photoAccessHelper:' + name, closed)
            for name in ('ConnectOptions', 'ConnectOptionsCollections'):
                self.assertIn('arkts_export:@ohos.arkui.StateManagement:' + name, closed)
            for name in RECORD_CLASSES:
                self.assertIn('arkts_export:@ohos.contact:' + name, closed)
            self.assertFalse(any(key.startswith('behavior:') for key in closed))
            self.assertEqual(behavior_results(root, 'other-boot', 'a' * 64, 'phone'), {})
            changed = self.observed()
            changed['records'][0]['flags'] = [True, True, False]
            raw.write_text(json.dumps(changed))
            self.assertEqual(behavior_results(root, 'test-boot', 'a' * 64, 'phone'), {})
            evidence['raw_results_sha256'] = sha256(raw)
            path.write_text(json.dumps(evidence))
            with self.assertRaises(ValueError):
                behavior_results(root, 'test-boot', 'a' * 64, 'phone')

    def test_state_record_flags_and_nonce_values_are_required(self):
        for index in range(12):
            row = self.observed()
            row['stateRecords']['flags'][index] = False
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify(json.dumps(row), RUN, IDENTITY)
        for state in ({'flags': [1] * 12, 'values': self.observed()['stateRecords']['values']},
                      {'flags': [True] * 12, 'values': ['shared'] * 4}, {}, None):
            with self.assertRaises(ValueError):
                verify(json.dumps(dict(self.observed(), stateRecords=state)), RUN, IDENTITY)

    def test_photo_records_require_all_real_constructors_and_independent_fields(self):
        for index in range(len(PHOTO_RECORD_CLASSES)):
            for flag_index in range(4):
                row = self.observed()
                row['photoRecords'][index]['flags'][flag_index] = False
                with self.subTest(index=index, flag=flag_index), self.assertRaises(ValueError):
                    verify(json.dumps(row), RUN, IDENTITY)
            for field, value in (('flags', [True, True, False, True]), ('flags', [1] * 4),
                                 ('first', 'wrong'), ('second', 'shared'), ('name', 'other')):
                row = self.observed()
                row['photoRecords'][index][field] = value
                with self.assertRaises(ValueError):
                    verify(json.dumps(row), RUN, IDENTITY)

    def test_exact_values_actual_native_own_reads_and_ordinary_identity(self):
        row = self.observed()
        self.assertEqual(verify(json.dumps(row) + '\n', RUN, IDENTITY)['member_count'], 2)
        for field, value in (('values', [2, 1]), ('values', [True, 2]), ('runId', 'b' * 32),
                             ('extra', 'not evidence')):
            changed = dict(row, **{field: value})
            with self.assertRaises(ValueError):
                verify(json.dumps(changed), RUN, IDENTITY)
        for field, value in (('values', [1]), ('values', [True, 2]), ('statuses', [0] * 13),
                             ('statuses', [False] * 14), ('statuses', [1] + [0] * 13),
                             ('types', [6, 7, 0, 3]), ('own', [True, False, True]),
                             ('own', [1, 1, 1]), ('exception', True), ('exception', 0)):
            changed = self.observed()
            changed['native'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify(json.dumps(changed), RUN, IDENTITY)
        for text in ('', json.dumps(row) + '\n' + json.dumps(row), '{}'):
            with self.assertRaises(ValueError):
                verify(text, RUN, IDENTITY)
        for identity in (json.dumps({'applicationInfo': {'appPrivilegeLevel': 'system_basic',
                            'isSystemApp': True, 'uid': 20010000}}), IDENTITY.replace('20010000', '10000')):
            with self.assertRaises(ValueError):
                verify(json.dumps(row), RUN, identity)

    def sdk(self, root):
        compiler = root / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
        compiler.parent.mkdir(parents=True)
        shutil.copy2(TS / 'lib/typescript.js', compiler)
        api = root / 'ets/api'
        api.mkdir(parents=True)
        (api / '@ohos.contact.d.ts').write_text(
            'declare namespace contact { enum ContactSyncMode { MODE_INCREMENTAL=1, MODE_CLOUD_BASED=2 } }\n'
            'export default contact;\n')
        (api / '@ohos.arkui.StateManagement.d.ts').write_text('export class ConnectOptions {}\n')
        (api / '@ohos.multimedia.audio.d.ts').write_text(
            'declare namespace audio { enum DeviceBlockStatus { UNBLOCKED=0, BLOCKED=1 } }\n'
            'export default audio;\n')
        (api / '@ohos.file.photoAccessHelper.d.ts').write_text(
            'declare namespace photoAccessHelper { enum FusionAssetType { COMPATIBLE_ASSET=0 } }\n'
            'export default photoAccessHelper;\n')
        return root

    def test_actual_sdk_ast_nonconst_kind_and_both_resolved_values_required(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = self.sdk(Path(directory))
            self.assertEqual([entry['value'] for entry in expected(sdk)['members']], [1, 2])
            declaration = sdk / 'ets/api/@ohos.contact.d.ts'
            original = declaration.read_text()
            for changed in (original.replace('enum ContactSyncMode', 'const enum ContactSyncMode'),
                            original.replace('MODE_CLOUD_BASED=2', 'MODE_CLOUD_BASED=3'),
                            original.replace('MODE_CLOUD_BASED=2', 'DEFAULT_SELECT=2')):
                declaration.write_text(changed)
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    expected(sdk)

    def test_exact_compiled_input_nonce_arch_template_and_declaration_cannot_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = self.sdk(root / 'sdk')
            project = root / 'project'
            page = project / 'entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text(TEMPLATE.read_text().replace('__RUN__', RUN))
            value = inputs(project, sdk, 'arm64', RUN)
            verify_inputs(value, RUN, 'arm64')
            for key, changed in (('arch', 'armv7a'), ('run_id', 'b' * 32), ('role', 'system'),
                                 ('native_source_sha256', '0' * 64), ('resolver_sha256', '0' * 64),
                                 ('audit_baseline_sha256', '0' * 64), ('request_permissions', ['READ_CONTACTS'])):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verify_inputs(dict(value, **{key: changed}), RUN, 'arm64')
            page.write_text(page.read_text().replace('contact.ContactSyncMode.MODE_INCREMENTAL', '1'))
            with self.assertRaises(ValueError):
                verify_inputs(dict(value, generated_source_sha256=sha256(page)), RUN, 'arm64')

    def test_default_suite_uses_native_reads_not_just_an_object_or_function_export(self):
        source = (HERE / 'contact_sync_mode_hap_probe.cpp').read_text()
        self.assertIn('napi_load_module(env, moduleName, &module)', source)
        self.assertIn('InspectEnum(env, "@ohos.contact", "ContactSyncMode", names)', source)
        self.assertIn('InspectEnum(env, "@ohos.multimedia.audio", "DeviceBlockStatus", names)', source)
        self.assertIn('InspectEnum(env, "@ohos.file.photoAccessHelper", "FusionAssetType", names)', source)
        self.assertIn('napi_has_own_property', source)
        self.assertIn('napi_set_element(env, values, index, value)', source)
        suite = (HERE / 'run_packaged_qemu_suite.py').read_text()
        self.assertIn("'contact-sync-mode'", suite)
        closure = (HERE / 'verify_gap_closure.py').read_text()
        self.assertIn('typed_and_native_public_enum_own_members_and_exact_values', closure)
        self.assertNotIn("kind in ('enum', 'namespace')", closure)
        builder = (HERE / 'build_hap_probe.py').read_text()
        self.assertIn('worker_only or args.contact_sync_mode_only or args.runtime_enum_only) else [] if dedicated_contract_only else [{', builder)
        self.assertIn('libcontactsyncmodeprobe.so', builder)

    def test_audio_typed_native_values_and_actual_sdk_kind_are_separately_required(self):
        row = self.observed()
        self.assertEqual(verify(json.dumps(row), RUN, IDENTITY)['audio_member_count'], 2)
        for key, value in (('audioValues', [False, 1]), ('audioValues', [1, 0]),
                           ('audioNative', row['native'])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(json.dumps(dict(row, **{key: value})), RUN, IDENTITY)
        for key, value in (('own', [True, False, True]), ('statuses', [0] * 13), ('exception', True)):
            changed = self.observed()
            changed['audioNative'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(json.dumps(changed), RUN, IDENTITY)
        with tempfile.TemporaryDirectory() as directory:
            sdk = self.sdk(Path(directory))
            self.assertEqual([member['value'] for member in expected_audio(sdk)['members']], [0, 1])
            declaration = sdk / 'ets/api/@ohos.multimedia.audio.d.ts'
            original = declaration.read_text()
            for changed in (original.replace('enum DeviceBlockStatus', 'const enum DeviceBlockStatus'),
                            original.replace('BLOCKED=1', 'BLOCKED=2')):
                declaration.write_text(changed)
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    expected_audio(sdk)

    def test_photo_single_member_cannot_be_false_zero_missing_or_an_audio_copy(self):
        row = self.observed()
        self.assertEqual(verify(json.dumps(row), RUN, IDENTITY)['photo_member_count'], 1)
        for key, value in (('photoValues', [False]), ('photoValues', [1]), ('photoValues', []),
                           ('photoNative', row['audioNative'])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(json.dumps(dict(row, **{key: value})), RUN, IDENTITY)
        for key, value in (('values', [False]), ('types', [6, 6, 0]), ('own', [True, False]),
                           ('statuses', [0] * 14), ('statuses', [False] * 10), ('exception', True)):
            changed = self.observed()
            changed['photoNative'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(json.dumps(changed), RUN, IDENTITY)
        with tempfile.TemporaryDirectory() as directory:
            sdk = self.sdk(Path(directory))
            self.assertEqual(expected_photo(sdk)['members'], [{'name': 'COMPATIBLE_ASSET', 'value': 0}])
            declaration = sdk / 'ets/api/@ohos.file.photoAccessHelper.d.ts'
            original = declaration.read_text()
            for changed in (original.replace('enum FusionAssetType', 'const enum FusionAssetType'),
                            original.replace('COMPATIBLE_ASSET=0', 'COMPATIBLE_ASSET=1')):
                declaration.write_text(changed)
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    expected_photo(sdk)

    def test_real_parser_rejects_mixed_worker_and_contact_personas_before_writes(self):
        import sys
        for flags in (('--worker-legacy-only', '--worker-thread-only'),
                      ('--worker-legacy-only', '--contact-sync-mode-only'),
                      ('--contact-sync-mode-only', '--const-enum-only')):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'must-not-exist'
                process = subprocess.run([sys.executable, str(HERE / 'build_hap_probe.py'), *flags,
                    '--output', str(output), '--udid', 'FIXTURE_NOT_A_GUEST'], text=True, capture_output=True)
                self.assertEqual(process.returncode, 2)
                self.assertIn('mutually exclusive', process.stderr)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
