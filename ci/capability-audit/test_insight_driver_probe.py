"""Caller identity/permission/build provenance fixtures, never intent acceptance."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import copy
from build_always_on_vpn_probe import build_application, BUNDLE as LEGACY_BUNDLE
from build_insight_driver_probe import BUNDLE, TARGET_BUNDLE, PERMISSIONS, ROLES, TEMPLATE, build, module, page
from sign_insight_driver_probe import configure_profile

NONCE = 'a' * 32


class InsightDriverProbeTests(unittest.TestCase):
    def sdk(self, root):
        for name in ('native', 'ets'):
            directory = root / name
            directory.mkdir(parents=True)
            (directory / 'oh-uni-package.json').write_text(json.dumps(dict(
                apiVersion='26', releaseType='Release', platformVersion='26.0.0')))
        (root / 'ets/api').mkdir()
        (root / 'ets/api/@ohos.app.ability.insightIntentDriver.d.ts').write_text('// fixture NOT actual SDK')

    def test_independent_caller_cannot_overwrite_decorated_target(self):
        self.assertNotEqual(BUNDLE, TARGET_BUNDLE)
        self.assertEqual(TARGET_BUNDLE, LEGACY_BUNDLE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk = root / 'sdk'; self.sdk(sdk)
            for role in ROLES:
                project = root / role
                args = SimpleNamespace(output=project, sdk=sdk, role=role, run_id=NONCE,
                    arch='arm64', arkdown='fixture-compiler')
                with patch('build_always_on_vpn_probe.subprocess.run') as compiler:
                    build(args)
                self.assertEqual(compiler.call_count, 1)
                self.assertNotIn('--skip-checker', compiler.call_args.args[0])
                app = json.loads((project / 'AppScope/app.json5').read_text())['app']
                receipt = json.loads((project / 'insight-driver-probe-inputs.json').read_text())
                self.assertEqual(app['bundleName'], BUNDLE)
                self.assertEqual(receipt['bundle_name'], BUNDLE)
                self.assertEqual(module(role, compiled=True)['app']['bundleName'], app['bundleName'])
                self.assertEqual(receipt['request_permissions'], list(PERMISSIONS) if role == 'system' else [])
                self.assertEqual((project / 'entry/src/main/ets/pages/Index.ets').read_text(), page(NONCE, role))

    def test_unknown_bundle_and_role_rejected_before_project_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(output=root / 'project', sdk=root / 'absent-sdk',
                role='normal', run_id=NONCE)
            for value in ('', 'one', '../escape', 'org.example;command', 'org.' + 'x' * 128, False):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    build_application(args, 'fixture', TEMPLATE, 'inputs.json', 'NOT_guest',
                        '@ohos.fixture.d.ts', bundle_name=value)
            self.assertFalse(args.output.exists())
        for role in ('root', '', 'owner'):
            with self.assertRaises(ValueError): module(role)
            with self.assertRaises(ValueError): page(NONCE, role)

    def test_signer_binds_caller_role_exact_permissions_and_device(self):
        for role in ROLES:
            baseline = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
            result = configure_profile(copy.deepcopy(baseline), role, '1' * 64, module(role, compiled=True))
            self.assertEqual(result['bundle-info']['bundle-name'], BUNDLE)
            self.assertEqual(result['bundle-info']['app-feature'],
                'hos_normal_app' if role == 'normal' else 'hos_system_app')
            self.assertEqual(result['debug-info']['device-ids'], ['1' * 64])
            self.assertEqual(result['acls']['allowed-acls'], list(PERMISSIONS) if role == 'system' else [])
            self.assertEqual(result['permissions']['restricted-permissions'], result['acls']['allowed-acls'])
            for change in ('target-bundle', 'extra-permission', 'wrong-role-permission'):
                compiled = module(role, compiled=True)
                if change == 'target-bundle': compiled['app']['bundleName'] = TARGET_BUNDLE
                elif change == 'extra-permission': compiled['module']['requestPermissions'].append({'name': 'arbitrary'})
                else: compiled['module']['requestPermissions'] = module(
                    'normal' if role == 'system' else 'system')['module']['requestPermissions']
                with self.subTest(role=role, change=change), self.assertRaises(ValueError):
                    configure_profile(copy.deepcopy(baseline), role, '1' * 64, compiled)
        for role, udid in (('root', '1' * 64), ('system', 'old-device')):
            with self.assertRaises(ValueError):
                configure_profile(copy.deepcopy(baseline), role, udid, module('system', compiled=True))


if __name__ == '__main__':
    unittest.main()
