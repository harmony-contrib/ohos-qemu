"""Isolated source-only tests; no SDK, native compiler, guest, or source volume."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
COMPONENT_PATHS = (
    'patches/common/base/telephony/number_identity/native_manifest',
    'patches/common/foundation/ability/ability_runtime/number_identity_loader',
    'patches/common/base/telephony/number_identity/native_package_identity',
)


def component_inputs():
    result = []
    for component in COMPONENT_PATHS:
        state = json.loads((ROOT / component / 'source_states.json').read_text())
        if len(state['files']) != 1:
            raise ValueError('one exact target required per NumberIdentity component')
        relative, before_sha256, after_sha256 = state['files'][0]
        result.append(dict(component=component, project=state['project'],
                           revision=state['revision'],
                           target=state['project'] + '/' + relative,
                           before_sha256=before_sha256,
                           after_sha256=after_sha256, patch=state['patch']))
    return result


COMPONENTS = component_inputs()
SUPPORT = ROOT / 'patches/lib'
sys.path.insert(0, str(SUPPORT))


class NumberIdentityNativeComponentsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='number-identity-native-components-')
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name).resolve()

    def fixture(self, index, state='original'):
        item = COMPONENTS[index]
        component = self.work / 'components' / item['component']
        shutil.copytree(ROOT / item['component'], component)
        root = self.work / 'source'
        shutil.copytree(component / 'fixtures' / state, root)
        return item, component, root, root / item['target']

    def run_helper(self, component, root):
        env = dict(os.environ, PYTHONPATH=str(SUPPORT),
                   PYTHONDONTWRITEBYTECODE='1',
                   GIT_CEILING_DIRECTORIES=str(self.work),
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   TMPDIR=str(self.work))
        # git apply changes only the generated scratch source bytes. No index,
        # commit, branch, checkout, or external source directory is involved.
        return subprocess.run(
            [sys.executable, str(SUPPORT / 'apply_exact_component.py'),
             '--component-dir', str(component), '--source-root', str(root)],
            env=env, cwd=self.work, capture_output=True, text=True, timeout=20)

    def load(self, component):
        spec = importlib.util.spec_from_file_location('number_identity_component', component / 'verify_source.py')
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value

    def assert_unknown_preserved(self, index):
        item, component, root, target = self.fixture(index)
        unknown = target.read_bytes() + b'\n// unrelated external edit\n'
        target.write_bytes(unknown)
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown/incomplete', result.stderr)
        self.assertEqual(target.read_bytes(), unknown)
        self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_official_manifest_is_already_final_and_idempotent(self):
        item, component, root, target = self.fixture(0, 'final')
        before = target.read_bytes()
        for _ in range(2):
            result = self.run_helper(component, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), before)
        self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_installed_invalid_manifest_migrates_and_replays(self):
        item, component, root, target = self.fixture(0)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), item['before_sha256'])
        for _ in range(2):
            result = self.run_helper(component, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), item['after_sha256'])
        self.assertEqual(target.read_bytes(), (ROOT / item['component'] / 'fixtures/final' / item['target']).read_bytes())

    def test_loader_pristine_applies_once_then_is_idempotent(self):
        item, component, root, target = self.fixture(1)
        for _ in range(2):
            result = self.run_helper(component, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), item['after_sha256'])

    def test_unknown_manifest_preserved(self):
        self.assert_unknown_preserved(0)

    def test_unknown_loader_preserved(self):
        self.assert_unknown_preserved(1)

    def test_partial_manifest_reversion_is_unknown(self):
        item, component, root, target = self.fixture(0)
        mixed = target.read_bytes().replace(b',\n        "srcLanguage": "c++"', b'', 1)
        target.write_bytes(mixed)
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), mixed)

    def test_wrong_case_bundle_is_unknown(self):
        item, component, root, target = self.fixture(1, 'final')
        mixed = target.read_bytes().replace(b'com.ohos.numberidentity', b'com.ohos.NumberIdentity')
        target.write_bytes(mixed)
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), mixed)

    def test_source_symlink_rejected_without_mutating_target(self):
        for index in range(3):
            with self.subTest(component=index):
                nested = self.work / str(index)
                nested.mkdir()
                old_work, self.work = self.work, nested
                try:
                    item, component, root, target = self.fixture(index)
                    original = target.read_bytes()
                    outside = self.work / 'outside'
                    outside.write_bytes(original)
                    target.unlink()
                    target.symlink_to(outside)
                    result = self.run_helper(component, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('symlink', result.stderr)
                    self.assertEqual(outside.read_bytes(), original)
                    self.assertTrue(target.is_symlink())
                finally:
                    self.work = old_work

    def test_wrong_project_revision_rejected(self):
        for index in range(3):
            with self.subTest(component=index):
                nested = self.work / str(index)
                nested.mkdir()
                old_work, self.work = self.work, nested
                try:
                    item, component, root, target = self.fixture(index)
                    baseline = self.load(component)
                    (root / item['project'] / '.git').mkdir()
                    original = target.read_bytes()
                    with mock.patch('exact_source_states.subprocess.check_output', return_value='0' * 40 + '\n') as command:
                        with self.assertRaisesRegex(ValueError, 'pinned OpenHarmony'):
                            baseline.validate(root)
                    command.assert_called_once_with(['git', '-C', str(root / item['project']), 'rev-parse', 'HEAD'], text=True)
                    self.assertEqual(target.read_bytes(), original)
                finally:
                    self.work = old_work

    def test_patched_required_rejects_unapplied_loader(self):
        item, component, root, target = self.fixture(1)
        with self.assertRaisesRegex(ValueError, 'unknown/incomplete'):
            self.load(component).validate(root, require_patched=True)

    def test_patch_bytes_tamper_rejected_before_source_change(self):
        item, component, root, target = self.fixture(0)
        original = target.read_bytes()
        patch = component / item['patch']
        patch.write_bytes(patch.read_bytes() + b'\n')
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('patch stack', result.stderr)
        self.assertEqual(target.read_bytes(), original)

    def test_metadata_tamper_rejected_even_for_final_source(self):
        item, component, root, target = self.fixture(1, 'final')
        original = target.read_bytes()
        state = component / 'source_states.json'
        metadata = json.loads(state.read_text())
        metadata['revision'] = '4d07de8461a051729a1a3f8cc61a93066f62369a'
        state.write_text(json.dumps(metadata))
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('metadata differs', result.stderr)
        self.assertEqual(target.read_bytes(), original)

    def test_duplicate_metadata_key_rejected(self):
        item, component, root, target = self.fixture(0, 'final')
        state = component / 'source_states.json'
        state.write_text(state.read_text().replace('{', '{"source_only": true,', 1))
        result = self.run_helper(component, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('duplicate', result.stderr)

    def test_only_three_schema_fields_reversed(self):
        item = COMPONENTS[0]
        component = ROOT / item['component']
        before = (component / 'fixtures/original' / item['target']).read_bytes()
        after = (component / 'fixtures/final' / item['target']).read_bytes()
        self.assertEqual(before.count(b'"srcLanguage": "c++"'), 3)
        self.assertNotIn(b'srcLanguage', after)
        self.assertEqual(before.replace(b',\n        "srcLanguage": "c++"', b''), after)

    def test_loader_only_adds_exact_bundle_to_existing_allowlist(self):
        item = COMPONENTS[1]
        component = ROOT / item['component']
        before = (component / 'fixtures/original' / item['target']).read_bytes()
        after = (component / 'fixtures/final' / item['target']).read_bytes()
        new_entry = b'        "com.ohos.numberidentity",\n'
        self.assertNotIn(new_entry, before)
        self.assertEqual(after.count(new_entry), 1)
        self.assertEqual(after.replace(new_entry, b''), before)

    def test_package_identity_applies_once_then_is_idempotent(self):
        item, component, root, target = self.fixture(2)
        for _ in range(2):
            result = self.run_helper(component, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), item['after_sha256'])

    def test_unknown_package_identity_preserved(self):
        self.assert_unknown_preserved(2)

    def test_package_option_changes_only_project_native_strip(self):
        item = COMPONENTS[2]
        component = ROOT / item['component']
        before = (component / 'fixtures/original' / item['target']).read_bytes()
        after = (component / 'fixtures/final' / item['target']).read_bytes()
        block = b'    "nativeLib": {\n      "debugSymbol": {\n        "strip": false\n      }\n    },\n'
        self.assertEqual(after.count(block), 1)
        self.assertNotIn(b'nativeLib', before)
        self.assertEqual(after.replace(block, b''), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
