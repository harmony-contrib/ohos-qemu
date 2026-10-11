"""Whole pinned HCS fixture application, not actual codec/provider proof."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/vendor/ohemu/codec_hardware_profile'
FIXTURES = Path(__file__).parent / 'fixtures/codec_hardware_profile'
spec = importlib.util.spec_from_file_location('codec_hardware_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def fixture(root):
    for relative, original, _ in baseline.FILES:
        source = FIXTURES / Path(relative).name
        data = source.read_bytes()
        assert hashlib.sha256(data).hexdigest() == original
        target = root / baseline.PROJECT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def apply(root, success=True):
    result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                            capture_output=True, text=True)
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout + result.stderr)


class CodecHardwareProfileTests(unittest.TestCase):
    def test_whole_exact_stack_twice_preserves_all_nonhardware_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            self.assertFalse(baseline.validate(root))
            apply(root)
            self.assertTrue(baseline.validate(root, True))
            after = {relative: (root / baseline.PROJECT / relative).read_bytes()
                     for relative, _, _ in baseline.FILES}
            apply(root)
            for relative, _, _ in baseline.FILES:
                data = (root / baseline.PROJECT / relative).read_bytes()
                self.assertEqual(data, after[relative])
                original = (FIXTURES / Path(relative).name).read_bytes()
                self.assertEqual(data.split(b'        VideoSwEncoders {')[1],
                                 original.split(b'        VideoSwEncoders {')[1])
                self.assertEqual(data.split(b'        // QEMU has')[0],
                                 original.split(b'        VideoHwEncoders {')[0])
                self.assertNotIn(b'OMX.rk', data)
                self.assertNotIn(b'HDF_video_hw_', data)
                self.assertNotIn(b'codec.avc.hardware', data)
                self.assertIn(b'VideoHwEncoders {\n        }', data)
                self.assertIn(b'VideoHwDecoders {\n        }', data)

    def test_unknown_edit_or_partial_stack_fails_without_changing_any_file(self):
        for partial in (False, True):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture(root)
                if partial:
                    patch = sorted(COMPONENT.glob('0001-*.patch'))[0]
                    subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True,
                                   capture_output=True)
                else:
                    target = root / baseline.PROJECT / baseline.FILES[0][0]
                    target.write_bytes(target.read_bytes() + b'// unknown user edit\n')
                before = {relative: (root / baseline.PROJECT / relative).read_bytes()
                          for relative, _, _ in baseline.FILES}
                apply(root, False)
                self.assertEqual(before, {relative: (root / baseline.PROJECT / relative).read_bytes()
                                          for relative, _, _ in baseline.FILES})

    def test_link_and_wrong_revision_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            target = root / baseline.PROJECT / baseline.FILES[0][0]
            saved = root / 'owned-fixture.hcs'
            shutil.move(target, saved)
            target.symlink_to(saved)
            original = saved.read_bytes()
            apply(root, False)
            self.assertEqual(saved.read_bytes(), original)
            target.unlink()
            shutil.move(saved, target)
            subprocess.run(['git', 'init', '-q', str(root / baseline.PROJECT)], check=True)
            apply(root, False)
            self.assertEqual(target.read_bytes(), original)

    def test_both_profiles_and_all_products_apply_before_traversal(self):
        source = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        declaration = 'CODEC_HARDWARE_PROFILE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/codec_hardware_profile/apply.sh"'
        self.assertIn(declaration, source)
        invocation = '  bash "${CODEC_HARDWARE_PROFILE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(source.count(invocation), 1)
        self.assertLess(source.index(invocation), source.index('  write_source_preparation_metadata'))
        self.assertLess(source.index(invocation), source.index('\nmain() {'))


if __name__ == '__main__':
    unittest.main()
