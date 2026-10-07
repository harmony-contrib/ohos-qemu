import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = load('camera_jpeg_check', REPO / 'patches/common/drivers/peripheral/camera/jpeg_rotation/check.py')
COMPILER = load('camera_jpeg_compile', HERE / 'check_camera_jpeg_rotation.py')


class CameraJpegSafetyTest(unittest.TestCase):
    def test_builder_applies_before_profile_generation_and_traversal(self):
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        apply_at = builder.index('  bash "${QEMU_CAMERA_JPEG_COMPONENT_SCRIPT}" --source-root')
        self.assertLess(apply_at, builder.index('  configure_qemu_device_profile', apply_at))
        self.assertLess(apply_at, builder.index('  write_source_preparation_metadata', apply_at))

    def test_exported_command_preserves_matching_flags_and_headers(self):
        original = ['clang++', '-Igen/real/armv7', '--target=arm-linux-ohos', '-ftrivial-auto-var-init=zero',
                    '-MF', 'old.o.d', '-c', 'original.cpp', '-o', 'old.o']
        updated = COMPILER.candidate_command(original, Path('/tmp/candidate.cpp'), Path('/tmp/candidate.o'))
        self.assertEqual(updated[:4], original[:4])
        self.assertEqual(updated[4:], ['-MF', '/tmp/candidate.o.d', '-c', '/tmp/candidate.cpp',
                                       '-o', '/tmp/candidate.o'])
        self.assertEqual(original[-1], 'old.o')

    def test_unknown_or_multi_compile_commands_are_rejected(self):
        for command in (['clang++', '-c', 'a.cpp', '-o', 'a.o'],
                        ['clang++', '-MF', 'a.d', '-c', 'a.cpp', '-c', 'b.cpp', '-o', 'a.o'],
                        ['clang++', '-MF', 'a.d', '-c', 'a.cpp', '-o', 'a.o', '&&', 'touch', 'seed']):
            with self.assertRaises(ValueError):
                COMPILER.candidate_command(command, '/tmp/a.cpp', '/tmp/a.o')

    def test_repair_guard_rejects_drift_without_guessing(self):
        for data in (b'', b'jpeg_transform_info transformoption;\n', b'unknown changed source'):
            with self.assertRaises(ValueError):
                CHECK.repaired(data)


if __name__ == '__main__':
    unittest.main()
