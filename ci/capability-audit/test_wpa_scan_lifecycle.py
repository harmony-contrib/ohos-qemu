"""Recipe checks; full actual-method ASan fixtures run separately on pinned inputs."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/wpa_scan_lifecycle'


class WpaScanLifecycleTests(unittest.TestCase):
    def test_owner_is_initialized_before_publication_and_not_cleared_before_retirement(self):
        patch = (COMPONENT / '0001-retire-scan-monitor-on-every-destruction-path.patch').read_text()
        self.assertIn('+    pScanMonitor->SetScanStateMachine(pScanStateMachine);\n'
                      '     if (!pScanMonitor->InitScanMonitor()) {', patch)
        self.assertIn('-        pScanMonitor->SetScanStateMachine(nullptr);', patch)
        self.assertIn(' ScanMonitor::~ScanMonitor()\n-{}\n+{\n+    UnInitScanMonitor();\n+}', patch)

    def test_registration_state_guards_unregistered_and_repeated_retirement(self):
        patch = (COMPONENT / '0001-retire-scan-monitor-on-every-destruction-path.patch').read_text()
        self.assertIn('+    bool mRegistered {false};', patch)
        self.assertIn('+    if (mRegistered) {\n+        return true;\n+    }', patch)
        self.assertIn('+    if (!mRegistered) {\n+        return;\n+    }', patch)
        self.assertIn('+    mRegistered = true;', patch)
        self.assertIn('+    mRegistered = false;', patch)

    def test_common_builder_and_header_dependency_check_remain_strict(self):
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(build.count('bash "${QEMU_WPA_SCAN_LIFECYCLE_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertLess(build.index('bash "${QEMU_WPA_SCAN_COMPONENT_SCRIPT}"'),
                        build.index('bash "${QEMU_WPA_SCAN_LIFECYCLE_COMPONENT_SCRIPT}"'))
        helper = (ROOT / 'ci/capability-audit/compile_contact_sync_mode.py').read_text()
        self.assertIn("'-ivfsoverlay'", helper)
        self.assertIn("raise ValueError('actual compiler did not consume candidate header: ' + relative)", helper)


if __name__ == '__main__':
    unittest.main()
