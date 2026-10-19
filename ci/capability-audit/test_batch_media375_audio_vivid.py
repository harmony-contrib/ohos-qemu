"""Hermetic source install checks; root explicitly opts into native compilation."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT/'patches/common/foundation/multimedia/av_codec/audio_vivid_integrity'
FIXTURE = Path(__file__).parent/'fixtures/batch_media375_audio_vivid'
BASE = json.loads((FIXTURE/'baseline.json').read_text())
BEFORE = gzip.decompress(base64.b64decode(BASE['gzip_base64']))
AFTER = (COMP/'files/audio_sink.cpp').read_bytes()
SIGNATURE = 'bool AudioSink::CopyAudioVividBufferData('
spec = importlib.util.spec_from_file_location('audio_vivid375_install', COMP/'apply.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def function(source):
    begin = source.index(SIGNATURE)
    return source[begin:source.index('\n}', begin)+2]


class AudioVivid375Tests(unittest.TestCase):
    def test_complete_preimage_payload_and_function_only_change(self):
        entry = installer.MANIFEST['files'][BASE['name']]
        self.assertEqual(hashlib.sha256(BEFORE).hexdigest(), BASE['sha256'])
        self.assertEqual(BASE['sha256'], entry['before'])
        self.assertEqual(hashlib.sha256(AFTER).hexdigest(), entry['after'])
        old, new = BEFORE.decode(), AFTER.decode()
        self.assertEqual(new.replace(function(new), function(old)), old)

    def test_exact_install_replay_and_unknown_source_preserved(self):
        with tempfile.TemporaryDirectory(prefix='media375-vivid-') as temp:
            root = Path(temp); target = root/BASE['name']; target.parent.mkdir(parents=True)
            target.write_bytes(BEFORE); target.chmod(0o640)
            installer.run(root); installer.run(root)
            self.assertTrue(installer.validate(root, True))
            self.assertEqual(target.read_bytes(), AFTER)
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            changed = AFTER+b'// unrelated user source\n'; target.write_bytes(changed)
            with self.assertRaises(ValueError): installer.run(root)
            self.assertEqual(target.read_bytes(), changed)

    def test_linked_target_cannot_overwrite_external_file(self):
        with tempfile.TemporaryDirectory(prefix='media375-vivid-') as temp:
            root = Path(temp); target = root/BASE['name']; target.parent.mkdir(parents=True)
            external = root/'external'; external.write_bytes(BEFORE); target.symlink_to(external)
            with self.assertRaises(ValueError): installer.run(root)
            self.assertEqual(external.read_bytes(), BEFORE)

    @unittest.skipUnless(os.environ.get('OHOS_MEDIA375_NATIVE') == '1', 'native compiler belongs to root resource owner')
    def test_actual_function_native_sanitizers(self):
        harness = (FIXTURE/'native_harness.cpp').read_text().replace('// ACTUAL_FUNCTION', function(AFTER.decode()))
        with tempfile.TemporaryDirectory(prefix='media375-vivid-native-') as temp:
            source = Path(temp)/'test.cpp'; binary = Path(temp)/'test'; source.write_text(harness)
            subprocess.run([os.environ.get('OHOS_QA_CXX', '/usr/bin/clang++'), '-std=c++17', '-Wall', '-Wextra',
                '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=20,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname == 'Linux' else 'detect_leaks=0'))


if __name__ == '__main__':
    unittest.main()
