"""Exact-source patch boundaries and actual camera driver host regressions."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/drivers/peripheral/camera/capture_end'
FIXTURE = Path(__file__).parent / 'fixtures/camera_capture_end'
spec = importlib.util.spec_from_file_location('camera_capture_end_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
NAMES = ('capture_message.before.cpp', 'capture_request.before.cpp',
         'capture_request.before.h', 'stream_base.before.cpp')


class CameraCaptureEnd(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='actual-camera-capture-end-')
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'source'
        self.source.mkdir()
        for name, (relative, original, _) in zip(NAMES, baseline.FILES):
            fixture = FIXTURE / name
            self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), original)
            target = self.source / baseline.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture, target)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.source)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {name: (self.source / baseline.PROJECT / name).read_bytes()
                for name, _, _ in baseline.FILES}

    def test_full_stack_idempotent(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.source, require_patched=True))
        before = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_unknown_siblings_preserved(self):
        original = self.snapshot()
        for name, _, _ in baseline.FILES:
            with self.subTest(name=name):
                target = self.source / baseline.PROJECT / name
                target.write_bytes(original[name] + b'\n// unrelated edit\n')
                before = self.snapshot()
                self.assertNotEqual(self.apply().returncode, 0)
                self.assertEqual(before, self.snapshot())
                target.write_bytes(original[name])

    def test_partial_stack_preserved(self):
        original = self.snapshot()
        self.assertEqual(self.apply().returncode, 0)
        name = baseline.FILES[2][0]
        (self.source / baseline.PROJECT / name).write_bytes(original[name])
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_symlink_rejected(self):
        target = self.source / baseline.PROJECT / baseline.FILES[0][0]
        saved = target.with_suffix('.saved')
        target.rename(saved)
        target.symlink_to(saved)
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_actual_host_failures_and_regressions(self):
        self.assertEqual(self.apply().returncode, 0)
        work = Path(self.temporary.name) / 'host'
        shutil.copytree(FIXTURE, work)
        real = work / 'real'
        real.mkdir()
        for (relative, _, _), name in zip(baseline.FILES,
                ('capture_message.cpp', 'real/capture_request.cpp', 'real/capture_request.h', 'real/stream_base.cpp')):
            shutil.copy2(self.source / baseline.PROJECT / relative, work / name)
        def methods(source, include_stop):
            pairs = [('RetCode StreamBase::CancelRequest(', 'void StreamBase::HandleRequest()'),
                     ('RetCode StreamBase::OnFrame(', 'RetCode StreamBase::ReceiveBuffer(')]
            if include_stop:
                pairs.insert(0, ('RetCode StreamBase::StopStream()', 'RetCode StreamBase::AddRequest('))
            return '\n\n'.join(source[source.index(begin):source.index(end)].strip()
                               for begin, end in pairs) + '\n'
        (work / 'actual_stream_methods.inc').write_text(methods((work / 'stream_base.before.cpp').read_text(), False))
        (work / 'candidate_stream_methods.inc').write_text(methods((real / 'stream_base.cpp').read_text(), True))
        compiler = shutil.which('clang++') or shutil.which('c++')
        self.assertIsNotNone(compiler, 'actual host C++ compiler required')
        environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                           UBSAN_OPTIONS='halt_on_error=1')
        cases = (
            ('original-message', ('capture_message.before.cpp', 'test_capture_message.cpp'), ()),
            ('original-cancel-drop', ('capture_message.before.cpp', 'test_stream_cancel.cpp'), ()),
            ('repaired-message', ('capture_message.cpp', 'test_capture_message.cpp'), ('--repaired',)),
            ('repaired-request-stream', ('capture_message.cpp', 'real/capture_request.cpp',
                                         'test_request_end_guard.cpp'), ()),
        )
        for label, names, args in cases:
            with self.subTest(case=label):
                executable = work / label
                command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                           '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(work),
                           *(str(work / name) for name in names), '-o', str(executable)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([str(executable), *args], capture_output=True, text=True,
                                        timeout=120, env=environment)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_recipe_applies_once_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        call = 'bash "${QEMU_CAMERA_CAPTURE_END_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(call), 1)
        self.assertLess(recipe.index(call), recipe.index('  write_source_preparation_metadata\n}'))

    def test_original_capture_publication_race_is_reproduced(self):
        self.assertEqual(self.apply().returncode, 0)
        self.run_publication_case((FIXTURE / 'stream_base.before.cpp').read_text(), repaired=False)

    def run_publication_case(self, source, repaired):
        work = Path(self.temporary.name) / ('publication-repaired' if repaired else 'publication-original')
        shutil.copytree(FIXTURE, work)
        (work / 'real').mkdir()
        for (relative, _, _), name in zip(baseline.FILES,
                ('capture_message.cpp', 'real/capture_request.cpp', 'real/capture_request.h', 'real/stream_base.cpp')):
            shutil.copy2(self.source / baseline.PROJECT / relative, work / name)
        pairs = [('RetCode StreamBase::Capture(', 'RetCode StreamBase::OnFrame('),
                 ('RetCode StreamBase::CancelRequest(', 'void StreamBase::HandleRequest()'),
                 ('RetCode StreamBase::OnFrame(', 'RetCode StreamBase::ReceiveBuffer(')]
        methods = '\n\n'.join(source[source.index(begin):source.index(end)].strip()
                              for begin, end in pairs)
        (work / 'publication_stream_methods.inc').write_text(methods + '\n')
        compiler = shutil.which('clang++') or shutil.which('c++')
        self.assertIsNotNone(compiler)
        executable = work / 'publication'
        environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                           UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                                 '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(work),
                                 str(work / 'capture_message.cpp'), str(work / 'real/capture_request.cpp'),
                                 str(work / 'test_capture_publication.cpp'), '-o', str(executable)],
                                capture_output=True, text=True, timeout=120, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(executable), *(['--repaired'] if repaired else [])],
                                capture_output=True, text=True, timeout=30, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
