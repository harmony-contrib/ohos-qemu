"""Diagnostic setup parsing does not replace radio behavior validation."""
import unittest
from run_wifi_scan_diagnostic import active_state


class WifiScanDiagnosticTests(unittest.TestCase):
    def test_actual_service_state_is_unambiguous(self):
        self.assertFalse(active_state('\nWiFi active state: inactive\n'))
        self.assertTrue(active_state('\nWiFi active state: activated\n'))
        for value in ('', 'wifi enable success', 'WiFi active state: unknown\n',
                      'WiFi active state: inactive\nWiFi active state: activated\n'):
            with self.assertRaises(ValueError):
                active_state(value)


if __name__ == '__main__':
    unittest.main()
