"""SDK preparation and signed caller identity tests; no guest success is mocked."""
import base64
import copy
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from build_insight_form_host_probe import (BUNDLE, COMPONENT_DECLARATION, COMPONENT_SHA256,
    LOADER_DECLARATION, PERMISSIONS, ROLES, build, module, page)
from prepare_form_component_sdk import prepare
from sign_insight_form_host_probe import configure_profile

NONCE = 'a' * 32
SOURCE = gzip.decompress(base64.decodebytes((Path(__file__).parent /
    'fixtures/form_component_api26.d.ts.gz.b64').read_bytes()))


class InsightFormHostProbeTests(unittest.TestCase):
    def sdk(self, root):
        for part in ('ets', 'native'):
            directory = root / part
            directory.mkdir(parents=True)
            (directory / 'oh-uni-package.json').write_text(json.dumps(dict(
                apiVersion='26', releaseType='Release', platformVersion='26.0.0')))
        (root / 'ets/api').mkdir()
        (root / 'ets/api/@ohos.app.form.formHost.d.ts').write_text('// fixture NOT actual compile')
        declaration = root.parent / 'pinned-source.d.ts'
        declaration.write_bytes(SOURCE)
        return declaration

    def test_actual_system_declaration_is_idempotent_and_preserves_other_sdk_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk = root / 'sdk'; source = self.sdk(sdk)
            first = prepare(sdk, source)
            self.assertFalse(first['first_artifact_behavior_gate_passed'])
            self.assertEqual(first['source_sha256'], COMPONENT_SHA256)
            self.assertEqual(prepare(sdk, source), first)
            self.assertEqual((sdk / COMPONENT_DECLARATION).read_bytes(), SOURCE)
            self.assertEqual((sdk / LOADER_DECLARATION).read_bytes(),
                SOURCE.replace(b"import('../api/", b"import('../../../api/"))
            self.assertEqual((sdk / 'ets/api/@ohos.app.form.formHost.d.ts').read_text(),
                '// fixture NOT actual compile')

    def test_unknown_or_linked_declaration_rejected_before_any_overwrite(self):
        for changed in ('unknown-loader', 'linked-source', 'bad-source'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); sdk = root / 'sdk'; source = self.sdk(sdk)
                if changed == 'unknown-loader':
                    path = sdk / LOADER_DECLARATION; path.parent.mkdir(parents=True)
                    path.write_text('unknown original'); selected = source
                elif changed == 'linked-source':
                    selected = root / 'linked.d.ts'; selected.symlink_to(source)
                else:
                    source.write_bytes(SOURCE + b'\n'); selected = source
                with self.subTest(changed=changed), self.assertRaises(ValueError): prepare(sdk, selected)
                self.assertFalse((sdk / COMPONENT_DECLARATION).exists())
                if changed == 'unknown-loader': self.assertEqual(path.read_text(), 'unknown original')

    def test_all_caller_roles_bind_actual_component_declarations_and_exact_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk = root / 'sdk'; source = self.sdk(sdk); prepare(sdk, source)
            for role in ROLES:
                args = SimpleNamespace(sdk=sdk, output=root / role, role=role, run_id=NONCE,
                    arch='arm64', arkdown='fixture-compiler')
                with patch('build_always_on_vpn_probe.subprocess.run') as compiler: build(args)
                self.assertEqual(compiler.call_count, 1)
                self.assertNotIn('--skip-checker', compiler.call_args.args[0])
                receipt = json.loads((args.output / 'insight-form-host-probe-inputs.json').read_text())
                self.assertEqual(receipt['bundle_name'], BUNDLE)
                self.assertEqual(receipt['additional_sdk_declarations'][COMPONENT_DECLARATION], COMPONENT_SHA256)
                self.assertEqual(set(receipt['additional_sdk_declarations']),
                    {COMPONENT_DECLARATION, LOADER_DECLARATION})
                self.assertEqual(receipt['request_permissions'], list(PERMISSIONS) if role == 'system' else [])
                self.assertEqual((args.output / 'entry/src/main/ets/pages/Index.ets').read_text(), page(NONCE, role))
            (sdk / LOADER_DECLARATION).write_text('modified signature')
            args.output = root / 'bad'
            with self.assertRaises(ValueError): build(args)
            self.assertFalse(args.output.exists())

    def test_signature_roles_cannot_grant_extra_permissions_or_target_another_bundle(self):
        for role in ROLES:
            original = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
            result = configure_profile(copy.deepcopy(original), role, '1' * 64, module(role, compiled=True))
            self.assertEqual(result['bundle-info']['bundle-name'], BUNDLE)
            expected = list(PERMISSIONS) if role == 'system' else []
            self.assertEqual(result['acls']['allowed-acls'], expected)
            self.assertEqual(result['permissions']['restricted-permissions'], expected)
            for field in ('bundle', 'permissions'):
                compiled = module(role, compiled=True)
                if field == 'bundle': compiled['app']['bundleName'] = 'org.harmonycontrib.capabilityaudit'
                else: compiled['module']['requestPermissions'].append({'name': 'unknown'})
                with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                    configure_profile(copy.deepcopy(original), role, '1' * 64, compiled)


if __name__ == '__main__':
    unittest.main()
