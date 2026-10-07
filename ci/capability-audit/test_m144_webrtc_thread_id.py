from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/web/arkweb/m144_webrtc_thread_id'
PATCH = COMPONENT / '0001-use-real-ohos-kernel-thread-id.patch'


class M144WebRTCThreadIdTests(unittest.TestCase):
    def test_only_ohos_real_id_branch_not_ref_or_public_type(self):
        self.assertEqual(set(patch_sections(PATCH)), {'src/third_party/webrtc/rtc_base/platform_thread_types.cc'})
        added = [line for line in PATCH.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(added, ['+#elif defined(OS_OHOS)', '+  return gettid();'])

    def test_pristine_repeated_apply_and_unknown_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, PATCH)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(source)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            subprocess.run(['git', '-C', str(source), 'apply', '--reverse', str(PATCH)], check=True)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_native_and_frozen_hap_paths_share_patch_and_fixed_revision(self):
        bootstrap = (ROOT / 'patches/common/web/arkweb/m144_window_contract/apply_with_core_build.sh').read_text()
        self.assertIn('m144_webrtc_thread_id/apply.sh', bootstrap)
        self.assertIn('prepare_m144_release_sources.py',
                      (ROOT / 'scripts/build_m144_arkweb_core_in_docker.sh').read_text())
        self.assertIn('m144_webrtc_thread_id', (ROOT / 'scripts/package_m144_arkweb_core_in_docker.sh').read_text())


if __name__ == '__main__':
    unittest.main()
