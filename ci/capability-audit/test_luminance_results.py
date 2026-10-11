"""Synthetic verifier and signing-boundary fixtures, not rendering evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_luminance_probe import TEMPLATE, module, page
from run_root_probe import digest
from sign_luminance_probe import configure_profile
from verify_luminance_results import SCOPE, verify, verify_evidence
from run_luminance_probe import observations_complete, click_when_ready


class LuminanceTests(unittest.TestCase):
    nonce = 'a' * 32
    identity = json.dumps({'applicationInfo': dict(appPrivilegeLevel='system_core', isSystemApp=True, uid=20000001)})

    def test_actual_control_attachment_wait_never_retries_duplicates_or_transport_failures(self):
        from unittest.mock import MagicMock
        from guest_ui import GuestUiCommandError, LayoutNotReady
        from test_guest_ui import node
        from build_luminance_probe import BUNDLE
        with tempfile.TemporaryDirectory() as directory:
            empty = {'attributes': {}, 'children': []}
            actual = node('luminance-run', bundle=BUNDLE)
            paths = [Path(directory) / str(index) for index in range(2)]
            for path, layout in zip(paths, (empty, actual)): path.write_text(json.dumps(layout))
            ui = MagicMock(); ui.layout.side_effect = [LayoutNotReady('window not attached'),
                (empty, paths[0]), (actual, paths[1])]
            attempts = []; ticks = iter(range(10))
            selection = click_when_ready(ui, attempts, 10, clock=lambda: next(ticks), sleep=lambda _: None)
            self.assertEqual(len(attempts), 3)
            self.assertEqual(selection['selected_node']['rect'], [20, 30, 320, 180])
            ui.shell.assert_called_once_with('uitest uiInput click 180 120', 'actual-luminance-ready-node-center')
            for error in (GuestUiCommandError('connection lost', None, '[Fail]'), ValueError('malformed hierarchy')):
                ui = MagicMock(); ui.layout.side_effect = error
                with self.assertRaises(type(error)): click_when_ready(ui, [], 10)
                ui.shell.assert_not_called()
            ui = MagicMock(); ui.layout.return_value = ([actual, actual], paths[1])
            with self.assertRaises(ValueError): click_when_ready(ui, [], 10)
            ui.shell.assert_not_called()
            ui = MagicMock(); ui.layout.return_value = (empty, paths[0]); ticks = iter(range(10))
            with self.assertRaises(ValueError):
                click_when_ready(ui, [], 2, clock=lambda: next(ticks), sleep=lambda _: None)
            ui.shell.assert_not_called()

    def test_real_jsonl_termination_not_literal_backslash_n(self):
        row = dict(runId=self.nonce, name='summary', values=[1], error='')
        raw = json.dumps(row)
        self.assertTrue(observations_complete(raw + '\n', self.nonce))
        self.assertTrue(observations_complete(raw + '\r\n', self.nonce))
        for incomplete in (raw, raw + '\\n', raw[:-1] + '\n', '\n', 'null\n'):
            self.assertFalse(observations_complete(incomplete, self.nonce))
        self.assertFalse(observations_complete(raw + '\n', 'b' * 32))
        row.update(name='failed', error='summary')
        self.assertFalse(observations_complete(json.dumps(row) + '\n', self.nonce))
        row.update(name='summary', values=[0], error='')
        self.assertTrue(observations_complete(json.dumps(row) + '\n', self.nonce))
        with self.assertRaises(ValueError):
            verify(json.dumps(row) + '\n', self.nonce, self.identity)

    def observations(self):
        data = [('identity', [20000001, 20000001, 123]), ('factory', [1, 1, 1]),
                ('invalid.bright.256', [100001, 1]), ('invalid.bright.-1', [100001, 1])]
        for cycle in range(2):
            data += [(f'sample.dark.{cycle}', [0, 1]), (f'dark.{cycle}', [1]),
                     (f'sample.bright.{cycle}', [255, 1]), (f'bright.{cycle}', [2]),
                     (f'off.{cycle}', [2, 2])]
        data += [('cleanup', [1]), ('summary', [1])]
        return [dict(runId=self.nonce, name=name, values=values, error='') for name, values in data]

    def encoded(self, rows):
        return '\n'.join(json.dumps(row) for row in rows) + '\n'

    def test_complete_callbacks_and_rejections(self):
        rows = self.observations()
        verify(self.encoded(rows), self.nonce, self.identity)
        for change in ('nonce', 'no-light', 'boolean', 'count', 'missing', 'extra', 'nan', 'uid'):
            bad = copy.deepcopy(rows)
            if change == 'nonce': bad[0]['runId'] = 'b' * 32
            elif change == 'no-light': bad[6]['values'][0] = 0
            elif change == 'boolean': bad[-1]['values'] = [True]
            elif change == 'count': bad[8]['values'] = [2, 3]
            elif change == 'missing': bad.pop(4)
            elif change == 'extra': bad.append(bad[-1])
            elif change == 'nan': bad[4]['values'][0] = float('nan')
            else: bad[0]['values'][0] += 1
            with self.assertRaises(ValueError, msg=change):
                verify(self.encoded(bad), self.nonce, self.identity)

    def test_system_factory_caller_adds_no_permissions_or_constructor_shim(self):
        profile = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
        configured = configure_profile(profile, 'system', 'b' * 64, module('system', compiled=True))
        self.assertEqual(configured['permissions']['restricted-permissions'], [])
        self.assertEqual(configured['acls']['allowed-acls'], [])
        text = page(self.nonce, 'system')
        self.assertIn('context.getLuminanceSampler', text)
        self.assertNotIn('new LuminanceSampler', text)
        self.assertIn('complete = boundariesOk;', text)
        self.assertIn('boundariesOk = false;', text)
        self.assertNotIn("throw new Error('threshold boundary differs')", text)
        bad = module('system', compiled=True)
        bad['module']['requestPermissions'].append({'name': 'ohos.permission.MANAGE_SECURE_SETTINGS'})
        with self.assertRaises(ValueError):
            configure_profile(profile, 'system', 'b' * 64, bad)
        with self.assertRaises(ValueError): page(self.nonce, 'normal')

    def test_evidence_rechecks_files_raw_calls_and_exact_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, sdk = root / 'Index.ets', root / '@ohos.arkui.UIContext.d.ts'
            source.write_text(page(self.nonce, 'system'))
            sdk.write_text('// synthetic verifier fixture, not an actual SDK\n')
            inputs = dict(schema_version=1, run_id=self.nonce, arch='arm64', role='system', scope=SCOPE,
                request_permissions=[], template_sha256=digest(TEMPLATE), generated_source=str(source),
                generated_source_sha256=digest(source), sdk_declaration=str(sdk), sdk_declaration_sha256=digest(sdk))
            compiled = module('system', compiled=True)
            paths = {name: root / name for name in ('inputs', 'application_identity', 'signed_hap',
                                                   'unsigned_hap', 'signing_receipt', 'raw_results')}
            paths['inputs'].write_text(json.dumps(inputs))
            paths['application_identity'].write_text(self.identity)
            paths['raw_results'].write_text(self.encoded(self.observations()))
            for field in ('signed_hap', 'unsigned_hap'):
                with zipfile.ZipFile(paths[field], 'w') as archive:
                    archive.writestr('module.json', json.dumps(compiled))
            profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                        'system', 'b' * 64, compiled)
            paths['signing_receipt'].write_text(json.dumps(dict(status='pass', role='system',
                scope='actual_signature_profile_and_codesign_NOT_guest', verified_profile=profile,
                signed_sha256=digest(paths['signed_hap']), unsigned_sha256=digest(paths['unsigned_hap']))))
            record = dict(run_id=self.nonce, uid=20000001, status='pass', results=self.observations())
            for name, path in paths.items():
                record.update({name: str(path), name + '_sha256': digest(path)})
            document = dict(status='pass', scope='real_factory_RS_callbacks_and_unsubscription_NOT_full_gate',
                archive_sha256='archive', boot_id='boot', arch='arm64', device='phone', failures=[],
                udid='b' * 64, roles={'system': record}, cleanup_verified=True,
                caller_cleanup=dict(kernel_process_absent=True, ability_process_records_absent=True,
                                    consecutive_absent_observations=2))
            self.assertEqual(verify_evidence(document, 'archive', 'boot', 'arm64', 'phone'),
                             ['arkts_export:@ohos.arkui.UIContext:LuminanceSampler'])
            bad = copy.deepcopy(document)
            bad['roles']['system']['results'][-1]['values'] = [0]
            with self.assertRaises(ValueError): verify_evidence(bad, 'archive', 'boot', 'arm64', 'phone')
            with self.assertRaises(ValueError): verify_evidence(document, 'older', 'boot', 'arm64', 'phone')
            with self.assertRaises(ValueError): verify_evidence(document, 'archive', 'older', 'arm64', 'phone')
            bad = copy.deepcopy(document)
            bad['cleanup_verified'] = False
            with self.assertRaises(ValueError): verify_evidence(bad, 'archive', 'boot', 'arm64', 'phone')
            bad = copy.deepcopy(document)
            bad['caller_cleanup']['consecutive_absent_observations'] = 0
            with self.assertRaises(ValueError): verify_evidence(bad, 'archive', 'boot', 'arm64', 'phone')
            paths['raw_results'].write_text('unverified')
            with self.assertRaises(ValueError): verify_evidence(document, 'archive', 'boot', 'arm64', 'phone')


if __name__ == '__main__':
    unittest.main()
