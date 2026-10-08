"""Whole-file Photos source patch safety; not HAP/guest acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/photos/source_provider'
FIXTURE = Path(__file__).parent / 'fixtures/photos_source_provider'
spec = importlib.util.spec_from_file_location('photos_source_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class PhotosSourceProvider(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='actual-photos-source-provider-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / baseline.PROJECT
        shutil.copytree(FIXTURE, self.source)
        for name, original, _ in baseline.FILES:
            if original is not None:
                self.assertEqual(hashlib.sha256((self.source / name).read_bytes()).hexdigest(), original)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {name: (self.source / name).read_bytes() if (self.source / name).exists() else None
                for name, _, _ in baseline.FILES}

    def test_whole_stack_and_idempotence(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.root, require_patched=True))
        before = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_every_unknown_sibling_preserved(self):
        pristine = self.snapshot()
        for name, _, _ in baseline.FILES:
            with self.subTest(name=name):
                target = self.source / name
                target.write_bytes((pristine[name] or b'') + b'\n// unrelated edit\n')
                before = self.snapshot()
                self.assertNotEqual(self.apply().returncode, 0)
                self.assertEqual(before, self.snapshot())
                if pristine[name] is None:
                    target.unlink()
                else:
                    target.write_bytes(pristine[name])

    def test_partial_stack_preserved(self):
        pristine = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        name = baseline.FILES[0][0]
        (self.source / name).write_bytes(pristine[name])
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_symlink_rejected(self):
        target = self.source / baseline.FILES[0][0]
        preserved = target.with_suffix('.preserved')
        target.rename(preserved)
        target.symlink_to(preserved)
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_real_hvigor_native_and_part_graph(self):
        self.assertEqual(self.apply().returncode, 0)
        build = (self.source / 'BUILD.gn').read_text()
        self.assertIn('ohos_app("photos_hap")', build)
        self.assertIn('build_modules = [ "phone_photos" ]', build)
        self.assertIn('part_name = "photos"', build)
        self.assertIn('certificate_profile = "signature/photos.p7b"', build)
        self.assertNotIn('ohos_prebuilt_etc', build)
        cmake = (self.source / 'imageEditor/common/src/main/cpp/sdk/projects/ohos/CMakeLists.txt').read_text()
        self.assertIn('add_library(JsonCpp STATIC', cmake)
        self.assertNotIn('JsonCpp/lib', cmake)
        abi = (self.source / 'imageEditor/common/build-profile.json5').read_text()
        for name in ('armeabi-v7a', 'arm64-v8a', 'x86_64'):
            self.assertIn('"' + name + '"', abi)
        duration = (self.source / 'imageEditor/common/src/main/cpp/sdk/src/Service/Asset/HmcAsset.cpp').read_text()
        self.assertIn('Json::Value::Int64 complexDuration', duration)
        for name in ('common/src/main/ets/default/model/browser/photo/pipeline/ImagePipeline.ets',
                     'common/src/main/ets/default/view/dialog/NetworkConnectionSwitchDialog.ets',
                     'imageEditor/common/src/main/ets/common/util/BreakPointSystem.ets'):
            self.assertNotIn('@ohos/hypium', (self.source / name).read_text())
        callback = (self.source / 'feature/faCard/src/main/ets/formability/FACardServiceStub.ets').read_text()
        self.assertIn('if (this.initialized) {', callback)
        self.assertNotIn('if (!this.initialized) {', callback)


if __name__ == '__main__':
    unittest.main()
