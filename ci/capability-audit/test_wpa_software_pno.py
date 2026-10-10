"""Candidate selection boundaries; not timed scans or a guest radio test."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/wpa_software_pno'
PATCH = COMPONENT / '0001-use-software-pno-without-chip-offload.patch'


class WpaSoftwarePnoTests(unittest.TestCase):
    def test_actual_selection_preserves_chip_configuration_and_avoids_nonexistent_offload(self):
        text = PATCH.read_text().split('+++ b/', 2)[-1]
        selection = '\n'.join(line[1:] for line in text.splitlines() if line[:1] in (' ', '+'))
        selection = selection[selection.index('    /* init supportHwPnoFlag value */'):]
        selection = selection[:selection.index('    if (!InitialStateMachine')]
        prefix = r'''
#include <cassert>
static bool configured = true;
static int reads = 0;
struct WifiSettings {
    static WifiSettings &GetInstance() { static WifiSettings settings; return settings; }
    bool GetSupportHwPnoFlag(int instance) { assert(instance == 3); ++reads; return configured; }
};
bool select() {
    [[maybe_unused]] int m_instId = 3;
    bool supportHwPnoFlag = true;
'''
        main = r'''
    return supportHwPnoFlag;
}
int main() {
    configured = true;
#ifdef WIFI_SOFTWARE_SCAN_BACKEND
    assert(!select() && reads == 0);
    configured = false;
    assert(!select() && reads == 0);
#else
    assert(select() && reads == 1);
    configured = false;
    assert(!select() && reads == 2);
#endif
}
'''
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='wpa-pno-selection-') as directory:
            root = Path(directory)
            source = root / 'selection.cpp'
            source.write_text(prefix + selection + main)
            for name, defines in (('software', ['-DWIFI_SOFTWARE_SCAN_BACKEND']), ('chip', [])):
                binary = root / name
                built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', *defines, str(source), '-o', str(binary)],
                    capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                result = subprocess.run([str(binary)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_only_non_chip_standard_target_selects_software_pno(self):
        patch = PATCH.read_text()
        self.assertIn('+    if (!wifi_feature_with_hdi_chip_supported) {\n'
                      '+      defines += [ "WIFI_SOFTWARE_SCAN_BACKEND" ]\n+    }', patch)
        self.assertEqual(patch.count('+    supportHwPnoFlag = false;'), 1)
        self.assertNotIn('-    supportHwPnoFlag = WifiSettings', patch)

    def test_common_build_registers_exact_component(self):
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(build.count('bash "${QEMU_WPA_SOFTWARE_PNO_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertIn('common/foundation/communication/wifi/wpa_software_pno/apply.sh', build)


if __name__ == '__main__':
    unittest.main()
