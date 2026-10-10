"""Runner guardrails; these checks do not attest a booted archive."""
import ast
from pathlib import Path
import unittest


class HiTraceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).with_name('run_hitrace_diagnostic.py').read_text()
        self.tree = ast.parse(self.source)

    def test_acceptance_boot_and_owned_transport_are_kept(self):
        namespaces = [node for node in ast.walk(self.tree) if isinstance(node, ast.Call) and
                      isinstance(node.func, ast.Attribute) and node.func.attr == 'Namespace']
        self.assertEqual(len(namespaces), 1)
        fields = {kw.arg: kw.value for kw in namespaces[0].keywords}
        self.assertEqual(ast.literal_eval(fields['purpose']), 'acceptance')
        self.assertFalse(ast.literal_eval(fields['power_diagnostic_wakeup']))
        self.assertIn('isolated_run(', self.source)
        self.assertIn('disposable_guest_closed', self.source)
        self.assertNotIn('phone-enur20', self.source)
        self.assertNotIn('first-wpa-backend-', self.source)

    def test_actual_capture_precedes_behavior_verification(self):
        self.assertLess(self.source.index("'actual-kernel-trace'"), self.source.index('verify_rows(result'))
        self.assertIn("'/status', 'actual-kernel-thread-identity'", self.source)
        self.assertIn('verify_trace(trace, nonce, pid, tid)', self.source)
        self.assertIn('verify_restored_configuration(trace_before', self.source)
        self.assertIn("'final-same-boot'", self.source)
        self.assertNotIn('chmod ', self.source)
        self.assertNotIn('grantPermission', self.source)

    def test_cli_exposes_only_single_archive_inputs(self):
        self.assertIn("('archive', 'output', 'sdk', 'hdc')", self.source)
        self.assertIn('OUTPUT.mkdir(exist_ok=False)', self.source)
        self.assertIn('first_artifact_behavior_gate_passed=False', self.source)
        self.assertIn('closed=[]', self.source)
        self.assertNotIn('run_2in1_full_build_docker', self.source)


if __name__ == '__main__':
    unittest.main()
