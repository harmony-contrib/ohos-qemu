"""Lifecycle patch scope, drift protection and executable fixed-source regression."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from batch_system_child_lifecycle import COMPONENT, FIXTURE, PATCH, ROOT, prepare, run

spec = importlib.util.spec_from_file_location('batch_system_callback_guard',
                                             COMPONENT / 'verify_callback_source.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ChildLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='batch-system-lifecycle-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        prepare(self.root)

    def apply(self):
        subprocess.run(['bash', str(ROOT / 'patches/lib/apply_patch.sh'),
                        str(self.root), str(PATCH)], capture_output=True, check=True)

    def test_fixed_source_apply_idempotence_and_config_guard(self):
        self.assertFalse(guard.validate(self.root))
        pristine = self.root / 'pristine-checkout'
        prepare(pristine, pristine=True)
        installer = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(pristine)]
        subprocess.run(installer, capture_output=True, check=True)
        self.assertTrue(guard.validate(pristine, True))
        subprocess.run(installer, capture_output=True, check=True)
        self.assertTrue(guard.validate(pristine, True))
        subprocess.run(['python3', str(COMPONENT / 'verify_config_source.py'),
                        '--source-root', str(pristine), '--require-patched'], check=True)
        expected = json.loads((FIXTURE / 'expected_hashes.json').read_text())
        self.assertEqual(set(expected), set(guard.HASHES))

    def test_unknown_source_preserved(self):
        target = self.root / next(iter(guard.HASHES))
        target.write_bytes(target.read_bytes() + b'// user edit\n')
        snapshot = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unknown child callback'):
            guard.validate(self.root)
        self.assertEqual(target.read_bytes(), snapshot)

    def test_mixed_state_rejected(self):
        target = self.root / next(iter(guard.HASHES))
        original = target.read_bytes()
        self.apply()
        target.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'mixed child callback'):
            guard.validate(self.root)

    def test_symlink_refused_without_touching_external_file(self):
        target = self.root / next(iter(guard.HASHES))
        external = self.root / 'external.cpp'
        external.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(external)
        snapshot = external.read_bytes()
        with self.assertRaisesRegex(ValueError, 'symlink'):
            guard.validate(self.root)
        self.assertEqual(external.read_bytes(), snapshot)

    def test_pinned_revision_required(self):
        project = self.root / guard.PROJECT
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture',
                        '--allow-empty'], check=True)
        with self.assertRaisesRegex(ValueError, 'pinned ability_runtime'):
            guard.validate(self.root)

    def test_actual_callback_and_manager_sources_under_sanitizers(self):
        evidence = run(self.root / 'execution')
        self.assertEqual(len(evidence['scenarios']), 24)
        self.assertEqual(evidence['concurrent_repeats'], 20)
        self.assertFalse(evidence['runtime_tested'])
        self.assertFalse(evidence['first_artifact_behavior_gate_passed'])


if __name__ == '__main__':
    unittest.main()
