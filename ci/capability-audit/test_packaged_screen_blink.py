"""Owned-VM cleanup wiring only, never real package evidence."""
import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import run_packaged_screen_blink_probe as runner
import run_screen_blink_probe as child_runner


class PackagedBlinkTests(unittest.TestCase):
    def test_failed_probe_can_only_continue_after_real_state_and_caller_cleanup(self):
        for restored, stop_error, boot_error, expected in (
                (True, None, None, True), (False, None, None, False),
                (True, ValueError('caller still alive'), None, False),
                (True, None, ValueError('boot changed'), False)):
            with self.subTest(restored=restored, stop_error=stop_error, boot_error=boot_error):
                report = dict(status='fail', failures=['original pixel failure'])
                health = MagicMock(side_effect=boot_error)
                with patch.object(child_runner, 'stop_previous_probe', side_effect=stop_error,
                                  return_value={'kernel_process_absent': True}) as stop:
                    child_runner.finish_cleanup(report, MagicMock(), health, True, restored)
                    stop.assert_called_once()
                self.assertEqual(report['cleanup_verified'], expected)
                self.assertEqual(report['status'], 'fail')
                self.assertIn('original pixel failure', report['failures'])

    def test_preinstall_failure_does_not_stop_an_unrelated_previous_caller(self):
        report = dict(status='fail', failures=['build failed'])
        health = MagicMock()
        with patch.object(child_runner, 'stop_previous_probe') as stop:
            child_runner.finish_cleanup(report, MagicMock(), health, False, True)
            stop.assert_not_called()
        health.assert_called_once()
        self.assertTrue(report['cleanup_verified'])
        self.assertEqual(report['status'], 'fail')

    def execute(self, directory, *, failed_probe=False, failed_restore=False):
        guest = MagicMock()
        guest.arch, guest.device, guest.target, guest.udid = 'arm64', 'phone', 'owned', 'a' * 64
        guest.report = {'test_environment': {'boot_id': 'boot'}}

        def shell(command, label):
            return {'power-shell timeout -o 86400000': 'Override screen off time to 86400000',
                    'power-shell timeout -r': 'failed' if failed_restore else 'Restore screen off time',
                    'cat /proc/sys/kernel/random/boot_id': 'boot'}.get(command, 'policy')

        guest.shell.side_effect = shell
        args = argparse.Namespace(output=Path(directory) / 'result', archive=Path(directory) / 'package',
                                  sdk=Path(directory) / 'sdk', hdc='hdc')
        before = dict(base_ms=30000, override_ms=None)
        with patch.object(runner, 'QemuGuest') as constructor, \
                patch.object(runner, 'run_home', return_value={'status': 'pass'}), \
                patch.object(runner, 'power_timeout', side_effect=[before, dict(before, override_ms=86400000), before]), \
                patch.object(runner, 'run_blink', return_value={'status': 'fail' if failed_probe else 'pass',
                    'boot_id': 'boot', 'failures': ['actual pixel failure'] if failed_probe else []}):
            constructor.return_value.start.return_value = guest
            result = runner.run(args)
        guest.close.assert_called_once()
        self.assertIn('power-shell timeout -r', [call.args[0] for call in guest.shell.call_args_list])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        return result

    def test_success_still_never_opens_full_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.execute(directory)['status'], 'pass')

    def test_probe_failure_restores_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.execute(directory, failed_probe=True)['status'], 'fail')

    def test_power_restore_failure_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.execute(directory, failed_restore=True)['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
