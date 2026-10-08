"""Whole fixed-release JS regression and exact-state patch boundary checks."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/image_model_callbacks'
spec = importlib.util.spec_from_file_location('image_model_callback_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class ImageModelCallbacks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='actual-image-model-callbacks-')
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'source'
        self.source.mkdir()
        names = ('AIGenerateImpl.js', 'AIGenerateImpl.ets', 'BUILD.gn')
        for name, (relative, original, _) in zip(names, baseline.FILES):
            fixture = HERE / 'fixtures/image_model_callbacks' / name
            self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), original)
            destination = self.source / baseline.PROJECT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture, destination)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.source)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {relative: (self.source / baseline.PROJECT / relative).read_bytes()
                for relative, _, _ in baseline.FILES}

    def test_whole_callback_stream_and_lifecycle(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.source, require_patched=True))
        patched = self.source / baseline.PROJECT / baseline.FILES[0][0]
        original = HERE / 'fixtures/image_model_callbacks/AIGenerateImpl.js'
        result = subprocess.run(['node', str(HERE / 'image_model_callbacks_host.js'), str(original), str(patched)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status":"pass"', result.stdout)
        self.assertIn('"original_failure_reproduced":true', result.stdout)

    def test_full_stack_idempotent(self):
        self.assertEqual(self.apply().returncode, 0)
        before = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_each_unknown_sibling_is_rejected_before_any_write(self):
        pristine = self.snapshot()
        for relative, _, _ in baseline.FILES:
            with self.subTest(relative=relative):
                path = self.source / baseline.PROJECT / relative
                path.write_bytes(pristine[relative] + b'\n// unknown future source\n')
                before = self.snapshot()
                self.assertNotEqual(self.apply().returncode, 0)
                self.assertEqual(before, self.snapshot())
                path.write_bytes(pristine[relative])

    def test_partial_stack_preserves_all_source(self):
        original = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        relative = baseline.FILES[1][0]
        (self.source / baseline.PROJECT / relative).write_bytes(original[relative])
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_symlink_alias_rejected(self):
        path = self.source / baseline.PROJECT / baseline.FILES[0][0]
        preserved = path.with_suffix('.preserved')
        path.rename(preserved)
        path.symlink_to(preserved)
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_recipe_applies_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${IMAGE_MODEL_CALLBACKS_COMPONENT_SCRIPT}"'), 1)
        self.assertLess(recipe.index('bash "${IMAGE_MODEL_CALLBACKS_COMPONENT_SCRIPT}"'),
                        recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
