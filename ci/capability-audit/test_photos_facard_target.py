"""Native event target/unchanged protocol and exact-source patch boundaries."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/photos_facard'
FIXTURE = Path(__file__).parent / 'fixtures/photos_facard_operations.cpp'
spec = importlib.util.spec_from_file_location('photos_facard_target_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class PhotosFaCardTarget(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='photos-native-facard-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.file = self.root / baseline.PROJECT / baseline.FILES[0][0]
        self.file.parent.mkdir(parents=True)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), baseline.FILES[0][1])
        shutil.copy2(FIXTURE, self.file)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_only_two_bundle_targets_change(self):
        before = self.file.read_bytes()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.root, require_patched=True))
        self.assertEqual(self.file.read_bytes(), before.replace(
            b'SetElementName("com.huawei.hmos.photos", "FACardServiceAbility")',
            b'SetElementName("com.ohos.photos", "FACardServiceAbility")'))
        self.assertEqual(self.file.read_text().count('SetParam("assetChangeUris", assetChangeUris)'), 2)
        self.assertEqual(self.file.read_text().count('SetParam("assetChangeTypes", assetChangeTypes)'), 2)

    def test_idempotence(self):
        self.assertEqual(self.apply().returncode, 0)
        before = self.file.read_bytes()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.file.read_bytes())

    def test_unknown_source_preserved(self):
        self.file.write_bytes(self.file.read_bytes() + b'\n// unrelated edit\n')
        before = self.file.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.file.read_bytes())

    def test_partial_target_change_preserved(self):
        self.file.write_bytes(self.file.read_bytes().replace(b'"com.huawei.hmos.photos"', b'"com.ohos.photos"', 1))
        before = self.file.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.file.read_bytes())

    def test_symlink_rejected(self):
        preserved = self.file.with_suffix('.preserved')
        self.file.rename(preserved)
        self.file.symlink_to(preserved)
        self.assertNotEqual(self.apply().returncode, 0)

    def test_recipe_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        call = 'bash "${PHOTOS_FACARD_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(call), 1)
        self.assertLess(recipe.index(call), recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
