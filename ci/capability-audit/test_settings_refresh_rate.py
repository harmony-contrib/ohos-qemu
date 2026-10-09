import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/refresh_rate_page'
spec = importlib.util.spec_from_file_location('settings_refresh_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class SettingsRefreshRateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-refresh-rate-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / baseline.PROJECT
        self.route = self.project / baseline.FILES[0][0]
        self.route.parent.mkdir(parents=True)
        fixture = Path(__file__).parent / 'fixtures/settings_refresh_rate/PageRouteController.ets'
        # Upstream has no EOF newline. Reconstruct exactly and hash before use.
        data = fixture.read_bytes()[:-1]
        self.assertEqual(hashlib.sha256(data).hexdigest(), baseline.FILES[0][1])
        self.route.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_exact_idempotent_and_partial_rejection(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))
        target = self.project / baseline.FILES[-1][0]
        target.unlink()
        before = self.route.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertFalse(target.exists())
        self.assertEqual(self.route.read_bytes(), before)

    def test_unknown_route_preserved(self):
        self.route.write_bytes(self.route.read_bytes() + b'\n// unrelated edit\n')
        before = self.route.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.route.read_bytes(), before)
        self.assertFalse((self.project / baseline.FILES[-1][0]).exists())

    def test_actual_controller_boundaries(self):
        sdk = Path(os.environ.get('QEMU_TEST_SDK_HOME',
            '/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0'))
        typescript = sdk / 'ets/build-tools/ets-loader/node_modules/typescript'
        node = shutil.which('node')
        if not node or not (typescript / 'package.json').is_file():
            self.skipTest('requires Node and the OHOS 26 SDK compiler')
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([node, str(Path(__file__).with_name('settings_refresh_rate_boundary.cjs')),
            str(self.project / baseline.FILES[1][0]), str(typescript)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence['status'], 'pass')
        self.assertGreaterEqual(evidence['cases'], 35)


if __name__ == '__main__':
    unittest.main()
