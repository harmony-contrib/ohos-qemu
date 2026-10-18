#!/usr/bin/env python3
"""Production assembler + exact installer gates; never proof of guest PCM."""
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
COMP = ROOT / 'patches/common/foundation/multimedia/audio_framework/capturer_frame_assembly'
FIX = Path(__file__).parent / 'fixtures/batch_media/capturer_frame_assembly'
SPEC = importlib.util.spec_from_file_location('frame_assembly_installer', COMP / 'install.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


def original():
    rows = json.loads((FIX / 'source.json').read_text())['files']
    result = {}
    for name, row in rows.items():
        data = gzip.decompress(base64.b64decode(row['gzip_base64'])) if row['gzip_base64'] is not None else None
        if INSTALL.digest(data) != row['sha256']:
            raise ValueError('actual E fixture hash mismatch: ' + name)
        result[name] = data
    return result


def populate(root):
    for name, data in original().items():
        if data is not None:
            path = root / INSTALL.PROJECT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def method(source, signature):
    begin = source.index(signature)
    return source[begin:source.index('\n}', begin) + 2]


class FrameAssembly(unittest.TestCase):
    def test_real_production_class_short_read_and_lifecycle_barriers(self):
        with tempfile.TemporaryDirectory(prefix='hpae-frame-assembly-') as directory:
            binary = Path(directory) / 'frame-assembly'
            argv = [os.environ.get('OHOS_QA_CXX', '/usr/bin/clang++'), '-std=c++17', '-pthread',
                    '-Wall', '-Wextra', '-Werror', '-fno-rtti', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-I' + str(COMP / 'files'), str(FIX / 'harness.cpp'), '-o', str(binary)]
            compiled = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            self.assertEqual(compiled.returncode, 0, 'argv=' + repr(argv) + '\nstdout:\n' + compiled.stdout + '\nstderr:\n' + compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname == 'Linux' else 'detect_leaks=0'))
            self.assertEqual(ran.returncode, 0, 'stdout:\n' + ran.stdout + '\nstderr:\n' + ran.stderr)

    def test_exact_three_member_install_repeat_and_each_rollback(self):
        for count in (None, 1, 2, 3):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); populate(root)
                self.assertEqual(INSTALL.state(root), 'before')
                def fail(name, actual):
                    if actual == count:
                        raise OSError('controlled publication failure')
                if count is not None:
                    with self.assertRaisesRegex(OSError, 'controlled'):
                        INSTALL.install(root, after_write=fail)
                    self.assertEqual(INSTALL.snapshot(root), original())
                    self.assertEqual(INSTALL.state(root), 'before')
                else:
                    self.assertEqual(INSTALL.install(root), 'after')
                    self.assertEqual(INSTALL.install(root), 'after')
                    INSTALL.state(root, True)

    def test_unknown_mixed_and_symlink_rejected_without_source_writes(self):
        for variant in ('mixed', 'foreign', 'header', 'symlink'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); populate(root)
                name = next(name for name, data in original().items() if data is not None)
                path = root / INSTALL.PROJECT / name
                if variant == 'mixed':
                    path.write_bytes((COMP / 'files' / Path(name).name).read_bytes())
                elif variant == 'foreign':
                    path.write_bytes(path.read_bytes() + b'// foreign\n')
                elif variant == 'header':
                    new = next(name for name, data in original().items() if data is None)
                    (root / INSTALL.PROJECT / new).write_bytes(b'// foreign\n')
                else:
                    saved = root / 'saved'; path.rename(saved); path.symlink_to(saved)
                before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):
                    INSTALL.install(root)
                after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(before, after)

    def test_normal_path_and_invalidation_preserve_actual_ec_micref(self):
        old = {Path(name).name: data.decode().replace('\r\n', '\n') for name, data in original().items() if data is not None}
        source = (COMP / 'files/hpae_source_input_node.cpp').read_text()
        for signature in ('void HpaeSourceInputNode::DoProcessInnerMicAndEc(',
                          'void HpaeSourceInputNode::DoProcessInner(',
                          'void HpaeSourceInputNode::DoProcessMicInner('):
            self.assertEqual(method(source, signature), method(old['hpae_source_input_node.cpp'], signature))
        body = method(source, 'void HpaeSourceInputNode::ProcessAssembledMic(')
        self.assertIn('ret == SUCCESS && actualBytes != 0 && actualBytes <= capacity', body)
        self.assertLess(body.index('IsCurrent(lease)'), body.index('CaptureFrame('))
        self.assertIn('actualBytes % sampleFrameBytes == 0', body)
        self.assertNotIn('memset', body)
        for name in ('Reset', 'ResetAll', 'CapturerSourceDeInit', 'CapturerSourceFlush',
                     'CapturerSourceReset', 'CapturerSourceStart', 'CapturerSourceStop'):
            prefix = 'bool' if name in ('Reset', 'ResetAll') else 'int32_t'
            self.assertIn('micFrameAssembler_.Invalidate()', method(source, prefix + ' HpaeSourceInputNode::' + name + '('))
        process = method(source, 'void HpaeSourceInputNode::DoProcess()')
        self.assertEqual(process.count('ProcessAssembledMic(sourceBufferType)'), 1)
        self.assertIn('sourceInputNodeType_ == HPAE_SOURCE_MIC &&', process)


if __name__ == '__main__':
    unittest.main()
