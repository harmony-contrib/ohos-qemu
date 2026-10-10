"""Exercise the actual added software-band selection; no radio acceptance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/wpa_channels'
PATCH = COMPONENT / '0001-use-real-WPA-scan-channel-table.patch'


class WpaChannelTests(unittest.TestCase):
    def test_empty_tables_never_broaden_or_reuse_stale_caller_output(self):
        patch = PATCH.read_text()
        body = patch.split('+#ifdef WIFI_SOFTWARE_SCAN_BACKEND\n', 1)[1].split('+#else', 1)[0]
        body = '\n'.join(line[1:] for line in body.splitlines() if line.startswith('+'))
        source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <vector>
enum class ScanBandType { SCAN_BAND_24_GHZ=1, SCAN_BAND_5_GHZ=2, SCAN_BAND_5_GHZ_DFS_ONLY=4 };
std::map<ScanBandType,std::vector<int>> mValidFreqs;
bool select(ScanBandType band,std::vector<int32_t>& freqs) {
''' + body + r'''
}
int main() {
    std::vector<int32_t> out={999};
    assert(!select(ScanBandType::SCAN_BAND_24_GHZ,out) && out.empty());
    mValidFreqs[ScanBandType::SCAN_BAND_24_GHZ]={2417,2412,2412};
    mValidFreqs[ScanBandType::SCAN_BAND_5_GHZ]={5180};
    mValidFreqs[ScanBandType::SCAN_BAND_5_GHZ_DFS_ONLY]={5260};
    for(int band : {-1,0,5,8,255}) {
        out={999};
        assert(!select(static_cast<ScanBandType>(band),out) && out.empty());
    }
    assert(select(static_cast<ScanBandType>(1),out) && (out==std::vector<int32_t>{2412,2417}));
    assert(select(static_cast<ScanBandType>(2),out) && (out==std::vector<int32_t>{5180}));
    assert(select(static_cast<ScanBandType>(3),out) && (out==std::vector<int32_t>{2412,2417,5180}));
    assert(select(static_cast<ScanBandType>(4),out) && (out==std::vector<int32_t>{5260}));
    assert(select(static_cast<ScanBandType>(6),out) && (out==std::vector<int32_t>{5180,5260}));
    assert(select(static_cast<ScanBandType>(7),out) && (out==std::vector<int32_t>{2412,2417,5180,5260}));
    mValidFreqs[ScanBandType::SCAN_BAND_5_GHZ].clear();
    assert(!select(static_cast<ScanBandType>(2),out) && out.empty());
    mValidFreqs.clear();
    for(int band : {1,2,3,4,6,7}) {
        out={999};
        assert(!select(static_cast<ScanBandType>(band),out) && out.empty());
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='wpa-channels-test-') as directory:
            cpp, binary = Path(directory) / 'test.cpp', Path(directory) / 'test'
            cpp.write_text(source)
            built = subprocess.run([shutil.which('clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_wpa_queries_all_three_real_band_tables(self):
        patch = PATCH.read_text()
        for name in ('freqs2G', 'freqs5G', 'freqsDfs'):
            self.assertIn('GetSupportFrequencies(ifaceName, band, ' + name + ') != WIFI_HAL_OPT_OK', patch)
        self.assertNotIn('-    if (!HalDeviceManager', patch)
        self.assertIn('+      defines += [ "WIFI_SOFTWARE_SCAN_BACKEND" ]', patch)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${QEMU_WPA_CHANNELS_COMPONENT_SCRIPT}" --source-root'), 1)

    def test_live_refresh_precedes_getter_lock(self):
        patch = (COMPONENT / '0002-refresh-software-tables-from-live-supplicant.patch').read_text()
        for name in ('GetValidBands', 'GetValidChannels', 'GetAvailableScanFreqs'):
            body = patch.split('WifiChannelHelper::' + name, 1)[1].split('@@', 1)[0]
            self.assertLess(body.index('+    UpdateValidFreqs();'), body.index('lock(mMutex);'))
            self.assertIn('+#ifdef WIFI_SOFTWARE_SCAN_BACKEND', body)


if __name__ == '__main__':
    unittest.main()
