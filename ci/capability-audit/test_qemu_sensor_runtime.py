"""Check shared init/GN ownership, rollback and resolved real-sensor features."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
from sceneboard_profile import configure_boot_unlock_publisher
from sensor_features import EXPECTED, validate
SPEC = importlib.util.spec_from_file_location('sensor_runtime', ROOT / 'scripts/prepare_qemu_sensor_runtime.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class SensorRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        path = self.root / M.BUILD
        path.parent.mkdir(parents=True)
        path.write_bytes((ROOT / 'ci/capability-audit/fixtures/core/qemu_sensor/BUILD.gn').read_bytes())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), M.BUILD_SHA)

    def test_reapply_and_profile_disable_enable_preserve_shared_gn(self):
        result = M.apply(self.root)
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        first = (self.root / M.BUILD).read_bytes()
        M.apply(self.root)
        configure_boot_unlock_publisher(self.root, False)
        configure_boot_unlock_publisher(self.root, True)
        M.apply(self.root)
        self.assertEqual(first, (self.root / M.BUILD).read_bytes())
        self.assertIn(b'qemu_sceneboard_unlock_cfg', first)
        self.assertEqual(first.count(M.DEPENDENCY.encode()), 1)

    def test_unknown_partial_and_symlink_do_not_modify_other_inputs(self):
        path = self.root / next(iter(M.FILES))
        path.write_text('caller edit')
        before = (self.root / M.BUILD).read_bytes()
        with self.assertRaisesRegex(ValueError, 'partial'):
            M.apply(self.root)
        self.assertEqual(before, (self.root / M.BUILD).read_bytes())
        path.unlink()
        path.symlink_to(self.root / M.BUILD)
        with self.assertRaisesRegex(ValueError, 'linked'):
            M.apply(self.root)
        self.assertEqual(before, (self.root / M.BUILD).read_bytes())

    def test_failed_publication_rolls_back_only_owned_files(self):
        original = M.replace
        before = (self.root / M.BUILD).read_bytes()
        calls = 0

        def fail_third(path, data):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('injected publication failure')
            original(path, data)

        with patch.object(M, 'replace', side_effect=fail_third), self.assertRaises(OSError):
            M.apply(self.root)
        self.assertEqual(before, (self.root / M.BUILD).read_bytes())
        self.assertTrue(all(not (self.root / name).exists() for name in M.FILES))

    def test_resolved_transport_and_no_mock_flags_are_mandatory(self):
        for device in ('phone', '2in1'):
            validate(EXPECTED, device)
            for feature in EXPECTED:
                changed = {**EXPECTED, feature: not EXPECTED[feature]}
                with self.subTest(device=device, feature=feature), self.assertRaises(ValueError):
                    validate(changed, device)


if __name__ == '__main__':
    unittest.main()
