"""Diagnostic byte preservation must not relax actual scan acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from run_wifi_scan_diagnostic import capture_hilog


class WifiHilogCaptureTests(unittest.TestCase):
    def test_opaque_bytes_are_preserved_without_becoming_behavior_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.CompletedProcess([], 0, b'actual\xf8\x00hilog\n', b'\xffstderr')
            with patch('run_wifi_scan_diagnostic.subprocess.run', return_value=result) as call:
                record = capture_hilog('/owned/hdc', '127.0.0.1:1234', directory, 'wifi-hilog')
            self.assertFalse(call.call_args.kwargs['text'])
            self.assertEqual(call.call_args.kwargs['timeout'], 30)
            self.assertEqual(Path(record['stdout_raw']).read_bytes(), result.stdout)
            self.assertEqual(Path(record['stderr_raw']).read_bytes(), result.stderr)
            self.assertEqual(record['decoded_text_scope'], 'diagnostic_only_NOT_behavior_acceptance')

    def test_transport_failure_does_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.CompletedProcess([], 0, b'[Fail] no target\xff', b'')
            with patch('run_wifi_scan_diagnostic.subprocess.run', return_value=result):
                with self.assertRaises(ValueError):
                    capture_hilog('/owned/hdc', '127.0.0.1:1234', directory, 'failure-hilog')
            self.assertEqual((Path(directory) / 'failure-hilog.stdout.bin').read_bytes(), result.stdout)

    def test_capture_cannot_be_used_as_application_result_reader(self):
        with patch('run_wifi_scan_diagnostic.subprocess.run') as call:
            with self.assertRaises(ValueError):
                capture_hilog('/owned/hdc', '127.0.0.1:1234', '/unused', 'actual-scan-result')
            with self.assertRaises(ValueError):
                capture_hilog('/owned/hdc', '', '/unused', 'wifi-hilog')
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
