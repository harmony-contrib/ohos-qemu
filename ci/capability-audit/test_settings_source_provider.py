"""Pinned Settings packaging/profile candidates; never guest acceptance."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/source_provider'
spec = importlib.util.spec_from_file_location('settings_source_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
spec = importlib.util.spec_from_file_location('settings_source_preparation', COMPONENT / 'prepare_dependencies.py')
preparation = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'verify_source': baseline}):
    spec.loader.exec_module(preparation)


class SettingsSourceProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-source-contract-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / baseline.PROJECT
        fixtures = Path(__file__).parent / 'fixtures/settings_source_provider'
        for relative, original, _ in baseline.FILES:
            if original is not None:
                fixture = fixtures / relative
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), original)
                target = self.project / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fixture, target)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {name: (self.project / name).read_bytes() if (self.project / name).exists() else None
                for name, _, _ in baseline.FILES}

    def test_exact_apply_and_repeated_complete_state(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))

    def test_unknown_file_fails_before_any_source_mutation(self):
        target = self.project / 'build-profile.json5'
        target.write_text(target.read_text() + '\n// user edit\n')
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_partial_patch_stack_is_not_silently_accepted(self):
        self.assertEqual(self.apply().returncode, 0)
        (self.project / 'BUILD.gn').unlink()
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_all_ABIs_and_real_source_target_are_retained(self):
        self.assertEqual(self.apply().returncode, 0)
        target = (self.project / 'BUILD.gn').read_text()
        self.assertIn('ohos_app("settings_hap")', target)
        self.assertIn('certificate_profile = "signature/settings.p7b"', target)
        self.assertIn('build_modules = [ "phone" ]', target)
        self.assertNotIn('ohos_prebuilt', target)
        native = (self.project / 'native_api/build-profile.json5').read_text()
        for abi in ('arm64-v8a', 'armeabi-v7a', 'x86_64'):
            self.assertEqual(native.count('"'+abi+'"'), 1)
        self.assertIn('"//applications/standard/settings:settings_hap"',
                      (self.project / 'bundle.json').read_text())
        self.assertNotIn('"signingConfig"', (self.project / 'build-profile.json5').read_text())

    def test_only_certificate_and_finite_expiry_change(self):
        original = {'bundle-info': {'bundle-name': 'com.ohos.settings', 'apl': 'system_basic',
                    'app-feature': 'hos_system_app', 'distribution-certificate': 'original'},
                    'validity': {'not-before': 1594865258, 'not-after': 1689473258},
                    'type': 'release', 'app-distribution-type': 'os_integration',
                    'acls': {'allowed-acls': ['owned-ACL']}, 'permissions': {'restricted-permissions': []},
                    'uuid': 'fixed-identity'}
        before = copy.deepcopy(original)
        with patch.object(preparation, 'fingerprint', return_value=preparation.SIGNATURE):
            desired = preparation.release_profile(original, b'new OS certificate')
        self.assertEqual(original, before)
        desired['bundle-info']['distribution-certificate'] = original['bundle-info']['distribution-certificate']
        desired['validity']['not-after'] = original['validity']['not-after']
        self.assertEqual(desired, original)
        for key, value in (('bundle-name', 'other.app'), ('apl', 'system_core'), ('app-feature', 'normal')):
            changed = copy.deepcopy(original)
            changed['bundle-info'][key] = value
            with patch.object(preparation, 'fingerprint', return_value=preparation.SIGNATURE), self.assertRaises(ValueError):
                preparation.release_profile(changed, b'new')
        with patch.object(preparation, 'fingerprint', return_value='unknown'), self.assertRaises(ValueError):
            preparation.release_profile(original, b'new')

    def test_unknown_cached_asset_and_symlink_are_preserved(self):
        name = next(iter(preparation.ASSETS))
        target = self.root / name
        target.write_bytes(b'unknown cache')
        with patch.object(preparation.subprocess, 'run') as invoked, self.assertRaises(ValueError):
            preparation.fetch(self.root, name)
        invoked.assert_not_called()
        self.assertEqual(target.read_bytes(), b'unknown cache')
        link = self.root / 'redirected'
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            preparation.sha(link)

    def test_duplicate_signed_policy_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            preparation.document('{"apl":"system_basic","apl":"system_core"}')


if __name__ == '__main__':
    unittest.main()
