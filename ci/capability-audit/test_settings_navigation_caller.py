"""Settings caller construction guards, explicitly not provider UI acceptance."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class SettingsNavigationCaller(unittest.TestCase):
    def test_public_calls_require_separate_render_proof(self):
        source = (HERE / 'settings_navigation_probe.ets').read_text()
        for call in ('openInputMethodSettings', 'openInputMethodDetail', 'openNetworkManagerSettings',
                     'openDisplaySettingsPage', 'getAllInputMethodsSync'):
            self.assertIn(call + '(', source)
        self.assertIn('void-return-only-not-render-proof', source)
        self.assertIn('16900010', source)
        self.assertIn('ime.name, ime.id', source)
        self.assertNotIn('grantUserGrantedPermission', source)
        self.assertNotIn('startServiceExtensionAbility', source)
        self.assertNotIn('first_artifact_behavior_gate_passed', source)

    def test_every_other_mode_is_mutually_exclusive_before_any_output(self):
        builder = HERE / 'build_hap_probe.py'
        flags = re.findall(r'parser.add_argument\(\s*["\'](--[a-z-]+-only)["\']', builder.read_text())
        self.assertIn('--settings-navigation-only', flags)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'must-not-exist'
            for flag in flags:
                if flag == '--settings-navigation-only': continue
                with self.subTest(flag=flag):
                    result = subprocess.run([sys.executable, str(builder), '--settings-navigation-only', flag,
                        '--udid', 'host-fixture', '--output', str(output)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('mutually exclusive', result.stderr)
                    self.assertFalse(output.exists())

    def test_caller_mode_binds_sources_SDK_and_no_extra_permissions(self):
        source = (HERE / 'build_hap_probe.py').read_text()
        block = source[source.index('if args.settings_navigation_only:'):source.index('if args.arkts_exports_only:')]
        for phrase in ('ordinary_Settings_public_calls_NOT_UI_acceptance', "'request_permissions': []",
                       "digest(api_dir / '@ohos.settings.d.ts')", "digest(api_dir / '@ohos.inputMethod.d.ts')",
                       'digest(template)', 'digest(page)'):
            self.assertIn(phrase, block)


if __name__ == '__main__':
    unittest.main()
