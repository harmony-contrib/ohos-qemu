"""Failed-boot diagnostic identity/isolation; no simulated boot success."""
import unittest

from boot_failure_snapshot import capture


class BootFailureSnapshotTests(unittest.TestCase):
    boot_id = 'a1f293cc-5726-4630-8965-2b31b25407e7'

    def test_foreign_kernel_stops_before_other_observations(self):
        calls = []
        def shell(script, label):
            calls.append((script, label))
            return self.boot_id.replace('a1f2', '0000') + '\n'
        result = capture(shell, self.boot_id)
        self.assertEqual(len(calls), 1)
        self.assertIn('identity_error', result)
        self.assertEqual(result['observations'], {})

    def test_identity_transport_failure_is_not_reported_as_same_boot(self):
        def shell(*_):
            raise ValueError('actual transport disconnected')
        result = capture(shell, self.boot_id)
        self.assertIn('identity_error', result)
        self.assertNotIn('observed_boot_id', result)
        self.assertEqual(result['observations'], {})

    def test_later_independent_diagnostics_survive_capture_errors(self):
        calls = []
        def shell(script, label):
            calls.append((script, label))
            if label == 'failure-identity': return self.boot_id + '\n'
            if label in ('failure-processes', 'failure-service-waits'):
                raise ValueError('bounded command timed out')
            return 'actual command output is recorded by the caller'
        result = capture(shell, self.boot_id)
        self.assertEqual(len(calls), 7)
        self.assertIn('capture_error', result['observations']['processes'])
        self.assertEqual(result['observations']['hilog'], {'captured': True})
        self.assertFalse(any(token in script for script, _ in calls for token in
                             ('kill ', 'param set', 'echo 0 >', 'timeout -r', 'hilog -r',
                              'force-stop', 'wakeup', 'system_powerdown')))

    def test_malformed_or_injected_identity_never_reaches_guest(self):
        for value in ('', self.boot_id + '; true', self.boot_id.upper(), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture(lambda *_: self.fail('invalid identity reached guest'), value)


if __name__ == '__main__':
    unittest.main()
