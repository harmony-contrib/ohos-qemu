"""Verification runner fail-closed tests; mocked signer is not crypto evidence."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from sign_web_probe import verify_signed_hap

SUCCESS = 'verify codesign success\nDigest verify result: true\nverify permission sign success\nverify-app success\n'


class HapVerificationTests(unittest.TestCase):
    def run_fixture(self, root, log=SUCCESS, returncode=0, files=True):
        def run(command, **kwargs):
            self.assertTrue(kwargs['capture_output'])
            self.assertTrue(kwargs['text'])
            chain = Path(command[command.index('-outCertChain') + 1])
            profile = Path(command[command.index('-outProfile') + 1])
            self.assertEqual(chain.suffix, '.cer')
            self.assertEqual(profile.suffix, '.p7b')
            if files:
                chain.write_bytes(b'fixture cert not real trust proof')
                profile.write_bytes(b'fixture profile not real trust proof')
            return subprocess.CompletedProcess(command, returncode, log, '')
        with patch('sign_web_probe.subprocess.run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            verify_signed_hap('/pinned/sign-tool.jar', root / 'signed.hap', root)

    def test_exact_outputs_and_all_four_verification_markers_required(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_fixture(Path(directory))
        for marker in SUCCESS.splitlines():
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory, self.assertRaises(RuntimeError):
                self.run_fixture(Path(directory), log=SUCCESS.replace(marker, ''))

    def test_zero_status_without_actual_verification_is_not_success(self):
        for log, code, files in (('ERROR: Not support file output.pem', 0, False),
                                 (SUCCESS, 1, True), (SUCCESS, 0, False)):
            with self.subTest(log=log, code=code, files=files), tempfile.TemporaryDirectory() as directory, self.assertRaises(RuntimeError):
                self.run_fixture(Path(directory), log, code, files)


if __name__ == '__main__': unittest.main()
