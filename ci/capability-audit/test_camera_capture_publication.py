"""Publication ordering, strict predecessor composition and real-method tests."""
import subprocess
import unittest

import test_camera_capture_end as capture_end

PUBLICATION = capture_end.COMPONENT.parent / 'capture_publication'


class CameraCapturePublication(capture_end.CameraCaptureEnd):
    def apply(self):
        first = super().apply()
        if first.returncode:
            return first
        return subprocess.run(['bash', str(PUBLICATION / 'apply.sh'), '--source-root', str(self.source)],
                              capture_output=True, text=True)

    def test_actual_capture_publication_boundaries(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.source / capture_end.baseline.PROJECT / capture_end.baseline.FILES[-1][0]
        self.run_publication_case(source.read_text(), repaired=True)

    def test_prerequisite_required_without_mutation(self):
        before = self.snapshot()
        result = subprocess.run(['bash', str(PUBLICATION / 'apply.sh'), '--source-root', str(self.source)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_recipe_applies_once_before_traversal(self):
        from test_camera_capture_end import ROOT
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        call = 'bash "${QEMU_CAMERA_CAPTURE_PUBLICATION_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(call), 1)
        self.assertGreater(recipe.index(call), recipe.index('bash "${QEMU_CAMERA_CAPTURE_END_COMPONENT_SCRIPT}"'))
        self.assertLess(recipe.index(call), recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
