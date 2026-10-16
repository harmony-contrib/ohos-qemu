"""Synthetic mutation checks for caller binding; these are not microphone samples."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import audio_capture_contract as M
from test_avc_media_gate import elf


class CaptureContractTests(unittest.TestCase):
    def test_source_nonce_permission_expectation_and_public_target(self):
        run = 'c' * 32
        for denied in (False, True):
            text = M.source(run, denied)
            self.assertIn(run, text)
            self.assertNotIn('__BATCH_MEDIA_', text)
            self.assertIn('requestPermissionsFromUser', text)
        for invalid in ('', 'a' * 31, 'G' * 32):
            with self.assertRaises(ValueError):
                M.source(invalid)
        for arch in M.ABIS:
            command = M.compile_command(Path('/project'), Path('/sdk'), arch)
            self.assertIn('-lohaudio', command)
            self.assertIn('-Wall', command)
            self.assertIn('-Werror', command)
            self.assertNotIn('-lasound', command)

    def test_actual_hap_loaded_bytes_and_only_mic_permission_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.hap'
            original = elf()
            value = {'native_runtime_sha256': M.runtime_identity(original, 'arm64')}

            def hap(data, permissions):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('libs/arm64-v8a/libbatchmediacapture.so', data)
                    archive.writestr('module.json', json.dumps({'module': {'requestPermissions': permissions}}))

            hap(original, M.PERMISSIONS)
            M.verify_hap(path, value, 'arm64')
            hap(original, [{**M.PERMISSIONS[0], 'reasonId': 16777230}])
            M.verify_hap(path, value, 'arm64')
            for data, permissions in ((original[:-1] + b'X', M.PERMISSIONS), (original, []),
                (original, M.PERMISSIONS * 2), (original, [*M.PERMISSIONS, {'name': 'ohos.permission.MANAGE_AUDIO_CONFIG'}])):
                hap(data, permissions)
                with self.subTest(permissions=permissions), self.assertRaises(ValueError):
                    M.verify_hap(path, value, 'arm64')


if __name__ == '__main__':
    unittest.main()
