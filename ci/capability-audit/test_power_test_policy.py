"""The nested bindings suite can restore an owned timeout before the outer cleanup."""
import unittest

from power_test_policy import verify_restoration


class PowerTestPolicyTests(unittest.TestCase):
    def setUp(self):
        self.before = {'base_ms': 9000000, 'override_ms': None}
        self.setup = {'base_ms': 9000000, 'override_ms': 86400000}

    def test_suite_owned_restoration(self):
        self.assertEqual(verify_restoration('Restore screen off time\n', self.before, self.setup,
                                            self.before), 'restored_by_suite')

    def test_nested_suite_already_restored_same_policy(self):
        self.assertEqual(verify_restoration('Restore screen off time failed\n', self.before, self.setup,
                                            self.before), 'already_restored_by_nested_test')

    def test_rejected_restore_requires_actual_original_state(self):
        with self.assertRaises(ValueError):
            verify_restoration('Restore screen off time failed', self.before, self.setup, self.setup)
        with self.assertRaises(ValueError):
            verify_restoration('unexpected reply', self.before, self.setup, self.before)


if __name__ == '__main__':
    unittest.main()
