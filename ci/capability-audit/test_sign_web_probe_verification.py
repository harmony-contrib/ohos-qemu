"""Verification runner fail-closed tests; mocked signer is not crypto evidence."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from sign_web_probe import FA_PROBE_BUNDLE, fa_probe_config, verify_signed_hap

SUCCESS = 'verify codesign success\nDigest verify result: true\nverify permission sign success\nverify-app success\n'


class HapVerificationTests(unittest.TestCase):
    def run_fixture(self, root, log=SUCCESS, returncode=0, files=True, fa=False):
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
            verify_signed_hap('/pinned/sign-tool.jar', root / 'signed.hap', root, fa_no_permissions=fa)

    def fa_hap(self, root, permissions=None, stage=False, bundle=FA_PROBE_BUNDLE):
        path = root / 'signed.hap'
        config = {'app': {'bundleName': bundle}, 'module': {'package': bundle,
                  'reqPermissions': permissions or [], 'distro': {'moduleType': 'entry'},
                  'abilities': [{'name': '.MainAbility', 'type': 'page'},
                                {'name': '.ParticleService', 'type': 'service'}]}}
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('config.json', json.dumps(config))
            if stage:
                archive.writestr('module.json', '{}')
        return path

    def test_explicit_zero_permission_fa_still_requires_codesign_digest_and_certificate(self):
        log = SUCCESS.replace('verify permission sign success\n', '')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fa_hap(root)
            self.run_fixture(root, log=log, fa=True)
            with self.assertRaises(RuntimeError):
                self.run_fixture(root, log=log)
        for marker in log.splitlines():
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fa_hap(root)
                with self.assertRaises(RuntimeError):
                    self.run_fixture(root, log=log.replace(marker, ''), fa=True)

    def test_fa_exception_rejects_stage_extra_permissions_and_other_bundles(self):
        for options in ({'stage': True}, {'permissions': [{'name': 'ohos.permission.MANAGE_VPN'}]},
                        {'bundle': 'com.ohos.settings'}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = self.fa_hap(root, **options)
                with self.assertRaises(ValueError):
                    fa_probe_config(path)

    def test_fa_duplicate_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'signed.hap'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('config.json', '{"module":{},"module":{}}')
            with self.assertRaises(ValueError):
                fa_probe_config(path)

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
