"""Kernel diagnostic argv fixtures, never guest acceptance."""
import unittest
from qemu_kernel_diagnostic import adjust


class KernelDiagnosticTests(unittest.TestCase):
    def test_capability_queries_unchanged(self):
        for mode in ('verbose', 'idle-tick', 'power-trace'):
            self.assertEqual(adjust(['-accel', 'help'], mode), ['-accel', 'help'])

    def test_only_original_append_is_extended(self):
        argv = ['-machine', 'virt', '-append', 'console=ttyAMA0 developer_mode=1', '-kernel', 'kernel']
        result = adjust(argv, 'power-trace')
        self.assertEqual(argv[3], 'console=ttyAMA0 developer_mode=1')
        self.assertEqual(result[:3], argv[:3])
        self.assertEqual(result[4:], argv[4:])
        self.assertIn('trace_event=power:suspend_resume', result[3])
        self.assertNotIn('nohz=', result[3])
        for forbidden in ('selinux=', 'enforcing=', 'nosmp', 'mitigations=', 'init='):
            self.assertNotIn(forbidden, result[3])

    def test_bad_mode_and_missing_append_value_rejected(self):
        with self.assertRaises(ValueError):
            adjust(['-append'], 'verbose')
        with self.assertRaises(ValueError):
            adjust([], 'untrusted')
