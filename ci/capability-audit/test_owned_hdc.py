import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import run_with_owned_hdc as runner


class OwnedHdcTests(unittest.TestCase):
    def test_terminates_only_owned_process(self):
        process = MagicMock()
        process.poll.return_value = None
        runner.stop_owned(process)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_not_called()

    def test_kills_only_owned_stuck_process(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('owned', 5), 0]
        runner.stop_owned(process)
        process.kill.assert_called_once_with()

    def test_exited_process_not_signalled(self):
        process = MagicMock()
        process.poll.return_value = 1
        runner.stop_owned(process)
        process.terminate.assert_not_called()

    def exercise(self, child_code=0, handshake='server version: Ver: 3.2.0a\n', stderr='', owns_lock=True):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            private = root / 'private'
            private.mkdir()
            (private / '.hdc.pid').write_text('123' if owns_lock else '999')
            process = MagicMock(pid=123, returncode=-15)
            process.poll.return_value = None
            before = dict(os.environ)
            with patch.object(runner.tempfile, 'mkdtemp', return_value=str(private)), \
                    patch.object(runner.subprocess, 'Popen', return_value=process) as launch, \
                    patch.object(runner.socket, 'create_connection'), \
                    patch.object(runner.subprocess, 'run', side_effect=[
                        subprocess.CompletedProcess([], 0, handshake, stderr),
                        subprocess.CompletedProcess([], child_code)]) as run:
                result = runner.run(['actual-suite', '--no-retry'], root / 'output', Path('/test/hdc'))
                report = json.loads((root / 'output/transport.json').read_text())
                environment = launch.call_args.kwargs['env']
                self.assertEqual(environment['TMPDIR'], str(private))
                self.assertNotEqual(environment['OHOS_HDC_SERVER_PORT'], '8710')
                self.assertEqual(dict(os.environ), before)
                self.assertFalse(report['commands_retried'])
                self.assertFalse(report['shared_server_restarted'])
                process.terminate.assert_called_once_with()
                return result, report, run.call_count

    def test_private_environment_and_success(self):
        result, report, calls = self.exercise()
        self.assertEqual((result, report['status'], calls), (0, 'pass', 2))

    def test_guest_failure_propagates_without_retry(self):
        result, report, calls = self.exercise(child_code=7)
        self.assertEqual((result, report['status'], calls), (7, 'fail', 2))

    def test_zero_exit_handshake_error_prevents_suite(self):
        result, report, calls = self.exercise(handshake='', stderr='Connect server failed\n')
        self.assertEqual((result, report['status'], calls), (1, 'fail', 1))

    def test_unowned_lock_prevents_suite(self):
        result, report, calls = self.exercise(owns_lock=False)
        self.assertEqual((result, report['status'], calls), (1, 'fail', 1))
