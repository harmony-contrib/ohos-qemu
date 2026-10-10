"""Build recipe regression, not guest capture or source-assisted wait proof."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CaptureBudgetWiringTests(unittest.TestCase):
    def test_shared_patch_entry_and_shell_syntax(self):
        script = ROOT / 'scripts/build_standard_qemu_in_docker.sh'
        text = script.read_text()
        self.assertIn('QEMU_CAPTURE_BUDGET_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/'
                      'window/window_manager/capture_budget/apply.sh"', text)
        self.assertEqual(text.count('bash "${QEMU_CAPTURE_BUDGET_COMPONENT_SCRIPT}"'), 1)
        self.assertIn('logs/apply_qemu_capture_budget_component.log', text)
        subprocess.run(['bash', '-n', str(script)], check=True)


if __name__ == '__main__':
    unittest.main()
