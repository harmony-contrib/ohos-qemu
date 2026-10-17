#!/usr/bin/env python3
"""Actual pinned lifecycle methods + actual FutexTool/AudioRingCache; controlled dependencies are not guest/audio proof."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / 'patches/common/foundation/multimedia/audio_framework/capturer_read_lifecycle'
FIX = Path(__file__).parent / 'fixtures/batch_media/capturer_read_lifecycle'
CPP = 'foundation/multimedia/audio_framework/services/audio_service/client/src/capturer_in_client.cpp'
HDR = 'foundation/multimedia/audio_framework/services/audio_service/client/include/capturer_in_client_inner.h'
SOURCE = json.loads((FIX / 'source.json').read_text())


def original(name):
    row = SOURCE['files'][name]
    data = gzip.decompress(base64.b64decode(row['gzip_base64']))
    if hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError('pinned source differs: ' + name)
    return data


def method(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def installer():
    spec = importlib.util.spec_from_file_location('capturer_read_lifecycle', COMP / 'apply.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Lifecycle(unittest.TestCase):
    def tree(self, root):
        for name in SOURCE['files']:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original(name))

    def test_complete_exact_install_and_mixed_state_rejection(self):
        install = installer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.tree(root)
            self.assertEqual(install.inspect(root), 'before')
            install.run(root)
            self.assertTrue(install.validate(root, True))
            after = {name: (root / name).read_bytes() for name in SOURCE['files']}
            install.run(root)
            self.assertEqual(after, {name: (root / name).read_bytes() for name in SOURCE['files']})
            (root / HDR).write_bytes(original(HDR))
            snapshot = {name: (root / name).read_bytes() for name in SOURCE['files']}
            with self.assertRaises(ValueError):
                install.run(root)
            self.assertEqual(snapshot, {name: (root / name).read_bytes() for name in SOURCE['files']})
            self.tree(root)
            (root / CPP).write_bytes(original(CPP) + b'\n// foreign edit\n')
            with self.assertRaises(ValueError):
                install.run(root)

    def test_failed_second_publication_restores_complete_preimage(self):
        install = installer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.tree(root)
            before = {name: (root / name).read_bytes() for name in SOURCE['files']}
            writer, calls = install.atomic_write, []
            def fail_second(path, data, mode):
                calls.append(str(path))
                if len(calls) == 2:
                    raise OSError('injected second publication failure')
                return writer(path, data, mode)
            with patch.object(install, 'atomic_write', side_effect=fail_second):
                with self.assertRaises(OSError):
                    install.run(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in SOURCE['files']})
            self.assertEqual(install.inspect(root), 'before')

    def test_atomic_generation_and_no_callback_path_rewrite(self):
        header = (COMP / 'files/capturer_in_client_inner.h').read_text()
        self.assertIn('std::atomic<uint64_t> normalReadGeneration_ {0};', header)
        before = original(CPP).decode()
        after = (COMP / 'files/capturer_in_client.cpp').read_text()
        # This deliberately documents the limited normal-mode scope.
        for signature in ('int32_t CapturerInClientInner::HandleCapturerRead(',
                          'bool CapturerInClientInner::ReadCallbackFunc()',
                          'bool CapturerInClientInner::RestoreAudioStream('):
            self.assertEqual(method(before, signature), method(after, signature))
        for name, row in json.loads((COMP / 'manifest.json').read_text())['files'].items():
            self.assertEqual(hashlib.sha256((COMP / 'files' / row['payload']).read_bytes()).hexdigest(), row['after'])
            self.assertEqual(hashlib.sha256(original(name)).hexdigest(), row['before'])
        for relative, row in SOURCE['upstream'].items():
            self.assertEqual(hashlib.sha256((FIX / relative).read_bytes()).hexdigest(), row['sha256'])

    @unittest.skipUnless(sys.platform.startswith('linux'), 'requires real Linux futex syscall; must run in root native batch')
    def test_actual_methods_against_baseline_and_candidate(self):
        common = [
            'void CapturerInClientInner::UpdateStreamState(',
            'bool CapturerInClientInner::StartAudioStream(',
            'bool CapturerInClientInner::PauseAudioStream(',
            'bool CapturerInClientInner::StopAudioStream(',
            'bool CapturerInClientInner::ReleaseAudioStream(',
            'void CapturerInClientInner::ReleaseCallbackResources(',
            'void CapturerInClientInner::FinalizeRelease(',
            'int32_t CapturerInClientInner::HandleCapturerRead(',
            'int32_t CapturerInClientInner::Read(uint8_t',
            'void CapturerInClientInner::HandleCapturerPositionChanges(',
        ]
        added = [
            'void CapturerInClientInner::RetireNormalReadsLocked(',
            'bool CapturerInClientInner::NormalReadIsCurrent(',
            'int32_t CapturerInClientInner::HandleNormalCapturerRead(',
            'bool CapturerInClientInner::CommitNormalReadPositionChanges(',
        ]
        compiler = os.environ.get('OHOS_QA_CXX', '/usr/bin/clang++')
        for candidate in (False, True):
            with self.subTest(candidate=candidate), tempfile.TemporaryDirectory() as temp:
                source = (COMP / 'files/capturer_in_client.cpp').read_text() if candidate else original(CPP).decode()
                bodies = '\n\n'.join(method(source, signature) for signature in common + (added if candidate else []))
                harness = (FIX / 'native_harness.cpp').read_text().replace('// ACTUAL_METHODS', bodies)
                cpp, exe = Path(temp) / 'test.cpp', Path(temp) / 'test'
                cpp.write_text(harness)
                command = [compiler, '-D_GNU_SOURCE', '-std=c++17', '-fno-rtti', '-pthread', '-Wall', '-Wextra', '-Werror',
                           '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable',
                           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                           '-DCANDIDATE=' + str(int(candidate)), '-I', str(FIX / 'upstream'),
                           '-I', str(FIX / 'stubs'), '-include', 'cstring', '-include', 'climits',
                           str(cpp), str(FIX / 'upstream/futex_tool.cpp'), str(FIX / 'upstream/audio_ring_cache.cpp'), '-o', str(exe)]
                try:
                    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
                except subprocess.TimeoutExpired as error:
                    self.fail('actual compiler timed out: argv=' + repr(command) +
                              '\nstdout=' + repr(error.stdout) + '\nstderr=' + repr(error.stderr))
                except OSError as error:
                    self.fail('actual compiler could not start: argv=' + repr(command) + '\n' + str(error))
                self.assertEqual(compiled.returncode, 0,
                                 'actual compiler failed: argv=' + repr(command) +
                                 '\nreturncode=' + str(compiled.returncode) +
                                 '\nstdout:\n' + compiled.stdout + '\nstderr:\n' + compiled.stderr)
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20,
                                     env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1'))
                self.assertEqual(run.returncode, 0 if candidate else 10, run.stdout + run.stderr)
                self.assertIn('CANDIDATE_METHOD_BOUNDARIES' if candidate else 'BASELINE_COUNTEREXAMPLE', run.stdout)


if __name__ == '__main__':
    unittest.main()
