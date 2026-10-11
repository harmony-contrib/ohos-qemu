"""Diagnostic setup parsing does not replace radio behavior validation."""
import unittest
import argparse
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import run_wifi_scan_diagnostic as runner
from run_wifi_scan_diagnostic import active_state


class WifiScanDiagnosticTests(unittest.TestCase):
    def test_enclosing_failure_preserves_owner_vm_and_power(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, boot = root / 'archive', root / 'boot.json'
            archive.write_bytes(b'synthetic host fixture, not package evidence')
            boot.write_text('{}')
            guest = MagicMock()
            guest.report = {'test_environment': {'boot_id': 'boot'}}
            guest.target = '127.0.0.1:12345'
            def shell(script, label):
                if script == 'hidumper -s 1120': return 'WiFi active state: inactive\n'
                if script == 'cat /proc/sys/kernel/random/boot_id': return 'boot\n'
                if script.startswith('sha256sum '): return 'wrong deliberately rejected asset\n'
                return 'power'
            guest.shell.side_effect = shell
            args = argparse.Namespace(archive=archive, boot=boot, output=root / 'result', hdc='hdc')
            with patch.object(runner, 'EnclosingAcceptanceGuest') as borrowed, \
                    patch.object(runner, 'QemuGuest') as owned, \
                    patch.object(runner, 'power_timeout', return_value=dict(base_ms=30000, override_ms=86400000)), \
                    patch.object(runner, 'capture_hilog', return_value={}), \
                    patch.object(runner, 'stop_previous_probe', return_value=dict(kernel_process_absent=True,
                        ability_process_records_absent=True, consecutive_absent_observations=2)):
                borrowed.return_value.start.return_value = guest
                result = runner.run(args)
            owned.assert_not_called()
            guest.close.assert_not_called()
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['cleanup_verified'])
            self.assertTrue(result['radio_restored'])
            self.assertEqual(result['power_restoration'], 'unchanged_enclosing_policy')
            self.assertFalse(any(call.args[0].startswith(('power-shell', 'svc wifi')) for call in guest.shell.call_args_list))

    def test_actual_service_state_is_unambiguous(self):
        self.assertFalse(active_state('\nWiFi active state: inactive\n'))
        self.assertTrue(active_state('\nWiFi active state: activated\n'))
        for value in ('', 'wifi enable success', 'WiFi active state: unknown\n',
                      'WiFi active state: inactive\nWiFi active state: activated\n'):
            with self.assertRaises(ValueError):
                active_state(value)


if __name__ == '__main__':
    unittest.main()
