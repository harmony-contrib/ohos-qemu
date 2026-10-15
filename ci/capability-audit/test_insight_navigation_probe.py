"""Check navigation caller/target isolation and signing bounds, never guest routing."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from build_insight_navigation_probe import BUNDLE, PERMISSIONS, ROLES, build, module, page
from sign_insight_navigation_probe import configure_profile
from build_insight_decorator_probe import sources, build as build_target
from run_root_probe import digest

NONCE = 'a' * 32
TARGET = 'b' * 32


class InsightNavigationProbeTests(unittest.TestCase):
    def sdk(self, root):
        for part in ('ets', 'native'):
            directory = root / part; directory.mkdir(parents=True)
            (directory / 'oh-uni-package.json').write_text(json.dumps(dict(
                apiVersion='26', releaseType='Release', platformVersion='26.0.0')))
        (root / 'ets/api').mkdir()
        for name in ('insightIntentDriver', 'InsightIntentDecorator'):
            (root / ('ets/api/@ohos.app.ability.' + name + '.d.ts')).write_text('// fixture NOT SDK compile')

    def test_three_roles_keep_caller_distinct_and_bind_the_target_nonce(self):
        self.assertNotEqual(BUNDLE, 'org.harmonycontrib.capabilityaudit')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk = root / 'sdk'; self.sdk(sdk)
            for role in ROLES:
                args = SimpleNamespace(sdk=sdk, output=root / role, role=role, run_id=NONCE,
                    target_run_id=TARGET, arch='arm64', arkdown='fixture-compiler')
                with patch('build_always_on_vpn_probe.subprocess.run') as compiler: build(args)
                self.assertEqual(compiler.call_count, 1)
                self.assertNotIn('--skip-checker', compiler.call_args.args[0])
                receipt = json.loads((args.output / 'insight-navigation-probe-inputs.json').read_text())
                self.assertEqual(receipt['bundle_name'], BUNDLE)
                self.assertEqual(receipt['request_permissions'], list(PERMISSIONS) if role == 'system' else [])
                text = (args.output / 'entry/src/main/ets/pages/Index.ets').read_text()
                self.assertEqual(text, page(NONCE, role, TARGET))
                self.assertIn('audit://intent/' + TARGET, text)
            for bad_nonce in ('old', 'C' * 32, ''):
                args.output = root / ('bad-' + str(len(bad_nonce))); args.target_run_id = bad_nonce
                with self.assertRaises(ValueError): build(args)
                self.assertFalse(args.output.exists())

    def test_target_ability_want_journal_is_an_explicit_hashed_build_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk = root / 'sdk'; self.sdk(sdk)
            args = SimpleNamespace(sdk=sdk, output=root / 'target', role='normal', run_id=TARGET,
                case='valid', arch='arm64', arkdown='fixture-compiler')
            with patch('build_always_on_vpn_probe.subprocess.run'): build_target(args)
            relative = 'entry/src/main/ets/entryability/EntryAbility.ets'
            actual = args.output / relative
            self.assertEqual(actual.read_text(), sources(TARGET, 'valid')[relative])
            receipt = json.loads((args.output / 'insight-decorator-probe-inputs.json').read_text())
            self.assertEqual(receipt['additional_input_sha256'][relative], digest(actual))
            skills = json.loads((args.output / 'entry/src/main/module.json5').read_text())['module']['abilities'][0]['skills']
            self.assertEqual(skills, [{'actions': ['ohos.want.action.viewData'],
                'entities': ['entity.system.browsable'], 'uris': [{'scheme': 'audit', 'host': 'intent'}]}])

    def test_signing_rejects_target_bundle_wrong_role_and_unbounded_permissions(self):
        original = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
        for role in ROLES:
            result = configure_profile(copy.deepcopy(original), role, '1' * 64, module(role, compiled=True))
            self.assertEqual(result['bundle-info']['bundle-name'], BUNDLE)
            expected = list(PERMISSIONS) if role == 'system' else []
            self.assertEqual(result['acls']['allowed-acls'], expected)
            for changed in ('target', 'extra-permission', 'another-role'):
                value = module(role, compiled=True)
                if changed == 'target': value['app']['bundleName'] = 'org.harmonycontrib.capabilityaudit'
                elif changed == 'extra-permission': value['module']['requestPermissions'].append({'name': 'unknown'})
                else: value['module']['requestPermissions'] = module('normal' if role == 'system' else 'system')['module']['requestPermissions']
                with self.subTest(role=role, changed=changed), self.assertRaises(ValueError):
                    configure_profile(copy.deepcopy(original), role, '1' * 64, value)


if __name__ == '__main__':
    unittest.main()
