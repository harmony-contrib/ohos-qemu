"""Exact-source and actual-extension request boundaries, not guest UI acceptance."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/external_input'
spec = importlib.util.spec_from_file_location('settings_external_input_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class SettingsExternalInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-external-input-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / baseline.PROJECT
        fixtures = Path(__file__).parent / 'fixtures/settings_external_input'
        for name, original, _ in baseline.FILES:
            if original:
                fixture = fixtures / name
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), original)
                target = self.project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fixture, target)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {name: (self.project / name).read_bytes() if (self.project / name).exists() else None
                for name, _, _ in baseline.FILES}

    def test_exact_and_idempotent(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))

    def test_unknown_config_preserved(self):
        target = self.project / baseline.FILES[0][0]
        target.write_text(target.read_text() + '\n// user change\n')
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_entire_share_successor_replays_but_partial_or_unknown_successor_is_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        share = ROOT / 'patches/common/applications/standard/settings/share_picker/apply.sh'
        argv = ['bash', str(share), '--source-root', str(self.root)]
        self.assertEqual(subprocess.run(argv, capture_output=True).returncode, 0)
        for _ in range(2):
            self.assertEqual(self.apply().returncode, 0)
            self.assertEqual(subprocess.run(argv, capture_output=True).returncode, 0)
            self.assertTrue(baseline.validate(self.root, require_patched=True))
        target = self.project / 'product/phone/src/main/ets/pages/SharePicker.ets'
        original = target.read_bytes();target.unlink()
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot());self.assertFalse(target.exists())
        target.write_bytes(original + b'\n// unknown successor\n')
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_partial_state_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        (self.project / baseline.FILES[-1][0]).unlink()
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_real_pages_session_local_storage_and_no_permission_change(self):
        self.assertEqual(self.apply().returncode, 0)
        page = (self.project / baseline.FILES[-1][0]).read_text()
        for name in ('InputSettings', 'OtherInputDetailSettings', 'UiExtensionList'):
            self.assertIn('import { ' + name + ' }', page)
        self.assertIn('@Entry({ useSharedStorage: true })', page)
        self.assertIn('getSharedLocalStorage()', page)
        self.assertNotIn('AppStorage', page)
        source = (self.project / baseline.FILES[-2][0]).read_text()
        self.assertNotIn('enableInputMethod(', source)
        self.assertNotIn('switchInputMethod(', source)
        self.assertIn('getAllInputMethodsSync()', source)
        patch = next(COMPONENT.glob('*.patch')).read_text()
        self.assertNotIn('allowAppUsePrivilegeExtension', patch)
        self.assertNotIn('requestPermissions', patch)

    def test_actual_extension_request_and_session_boundaries(self):
        sdk = Path(os.environ.get('QEMU_TEST_SDK_HOME',
            '/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0'))
        typescript = sdk / 'ets/build-tools/ets-loader/node_modules/typescript'
        node = shutil.which('node')
        if not node or not (typescript / 'package.json').is_file():
            self.skipTest('requires Node and the OHOS 26 SDK TypeScript compiler')
        self.assertEqual(self.apply().returncode, 0)
        result = subprocess.run([node, str(Path(__file__).with_name('settings_external_input_boundary.cjs')),
                                 str(self.project / baseline.FILES[-2][0]), str(typescript)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['cases'], 31)


if __name__ == '__main__':
    unittest.main()
