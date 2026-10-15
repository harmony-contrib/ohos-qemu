"""Fixed-source guard and true loader boundary regression; no package closure."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from batch_system_graphics3d_startup import COMPONENT, FIXTURE, prepare, run

spec = importlib.util.spec_from_file_location('batch_system_scene_guard', COMPONENT / 'verify_source.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GraphicsStartupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='batch-system-scene-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        prepare(self.root)

    def install(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_full_installer_idempotent(self):
        self.assertFalse(guard.validate(self.root))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(guard.validate(self.root, True))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(guard.validate(self.root, True))
        expected = json.loads((FIXTURE / 'expected_hashes.json').read_text())
        self.assertEqual(set(expected), set(guard.HASHES))

    def test_unknown_source_preserved(self):
        target = self.root / next(iter(guard.HASHES))
        target.write_bytes(target.read_bytes() + b'// unrelated edit\n')
        before = target.read_bytes()
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(target.read_bytes(), before)

    def test_mixed_state_preserved(self):
        target = self.root / next(iter(guard.HASHES))
        original = target.read_bytes()
        self.assertEqual(self.install().returncode, 0)
        target.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'mixed'):
            guard.validate(self.root)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(target.read_bytes(), original)

    def test_symlink_preserved(self):
        target = self.root / next(iter(guard.HASHES))
        external = self.root / 'external.cpp'
        external.write_bytes(target.read_bytes())
        before = external.read_bytes()
        target.unlink()
        target.symlink_to(external)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(external.read_bytes(), before)

    def test_pinned_revision_required(self):
        project = self.root / guard.PROJECT
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture',
                        '--allow-empty'], check=True)
        with self.assertRaisesRegex(ValueError, 'fixed graphic_3d revision'):
            guard.validate(self.root)

    def test_actual_loader_and_initializer_under_sanitizers(self):
        result = run(self.root / 'execution')
        self.assertEqual(len(result['scenarios']), 37)
        self.assertFalse(result['runtime_tested'])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])


if __name__ == '__main__':
    unittest.main()
