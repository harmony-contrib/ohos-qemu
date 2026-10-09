"""Exact pinned source fixtures; none of these tests claims guest repair."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/window/window_manager/screen_modes'
spec = importlib.util.spec_from_file_location('screen_modes_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class ScreenModesPatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='screen-modes-component-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.originals = {}
        for index, (relative, original, _) in enumerate(baseline.FILES):
            fixture = Path(__file__).parent / 'fixtures/screen_modes' / (
                str(index).zfill(2) + '-' + Path(relative).name + '.gz.b64')
            data = gzip.decompress(base64.b64decode(fixture.read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), original)
            path = self.root / baseline.PROJECT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.originals[path] = data

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_exact_idempotent_and_original_line_endings(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))
        for path, old in self.originals.items():
            if b'\r\n' in old:
                self.assertNotIn(b'\n', path.read_bytes().replace(b'\r\n', b''))

    def test_unknown_edit_does_not_modify_any_input(self):
        path = next(iter(self.originals))
        path.write_bytes(self.originals[path] + b'\n// unrelated edit\n')
        before = {item: item.read_bytes() for item in self.originals}
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, {item: item.read_bytes() for item in self.originals})

    def test_partial_component_rejected_without_reverting_user_changes(self):
        self.assertEqual(self.apply().returncode, 0)
        path = next(iter(self.originals))
        path.write_bytes(self.originals[path])
        before = {item: item.read_bytes() for item in self.originals}
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, {item: item.read_bytes() for item in self.originals})

    def test_actual_serializer_counts_truncation_and_failed_writes(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('requires host C++ compiler')
        self.assertEqual(self.apply().returncode, 0)
        fixture = Path(__file__).parent / 'fixtures/screen_modes'
        headers = self.root / 'test-headers'
        headers.mkdir()
        for name in ('parcel.h', 'class_var_definition.h', 'dm_common.h', 'noncopyable.h'):
            (headers / name).write_text('#include "parcel_test_support.h"\n')
        project = self.root / baseline.PROJECT
        binary = self.root / 'screen-info-boundary'
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(headers),
            '-I', str(fixture), '-I', str(project / 'utils/include'),
            str(project / 'utils/src/screen_info.cpp'), str(fixture / 'screen_info_boundary.cpp'),
            '-o', str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_proxy_rejects_partial_reply_without_publishing_partial_objects(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('requires host C++ compiler')
        self.assertEqual(self.apply().returncode, 0)
        relative = 'window_scene/screen_session_manager/src/zidl/screen_session_manager_proxy.cpp'
        source = (self.root / baseline.PROJECT / relative).read_text()
        start = source.index('DMError ScreenSessionManagerProxy::GetAllScreenInfos(')
        end = source.index('\nDMError ScreenSessionManagerProxy::GetScreenSupportedColorGamuts(', start)
        (self.root / 'screen_proxy_method.inc').write_text(source[start:end])
        fixture = Path(__file__).parent / 'fixtures/screen_modes/screen_proxy_boundary.cpp'
        binary = self.root / 'screen-proxy-boundary'
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(self.root),
            str(fixture), '-o', str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
