"""Actual candidate parser and HAL method; isolated backend, not guest proof."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/wifi/wpa_scan/0002-query-real-wpa-frequency-capabilities.patch'
FIXTURE = Path(__file__).with_name('fixtures') / 'wpa_frequency_capabilities.txt'


class WpaFrequencyTests(unittest.TestCase):
    def test_real_parser_and_backend_boundaries(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         'a7ddc07a3719c7937b31dc1b6cc858872b52dd0b5e07e8445cb5940d72f0da5a')
        patch = '+// WPA omits' + PATCH.read_text().split('+// WPA omits', 1)[1].split('diff --git', 1)[0]
        source = '\n'.join(line[1:] for line in patch.splitlines() if line[:1] in (' ', '+'))
        prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
using WifiErrorNo = int;
constexpr int WIFI_HAL_OPT_OK=0, WIFI_HAL_OPT_FAILED=1, WIFI_HAL_OPT_INVALID_PARAM=2;
constexpr int INSTID_WLAN0=0;
class WifiHdiWpaClient { public: WifiErrorNo GetSupportFrequencies(int, std::vector<int>&); };
static std::string response;
static int backend=0, calls=0;
const char *GetHdiStaIfaceName(int id) { assert(id==0); return "wlan0"; }
int HdiWpaGetMloLinkedInfo(const char *iface, const char *cmd, char *reply, size_t size)
{
    assert(std::string(iface)=="wlan0" && std::string(cmd)=="GET_CAPABILITY freq" && size==2048);
    ++calls;
    assert(response.size()<=size);
    memcpy(reply,response.data(),response.size());
    return backend;
}
'''
        main = r'''
int main(int argc, char **argv)
{
    assert(argc==2);
    std::ifstream file(argv[1]);
    assert(file.good());
    const std::string real((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    WifiHdiWpaClient client;
    std::vector<int> actual;
    response=real;
    for (const auto &test : std::vector<std::pair<int,size_t>>{{1,14},{2,9},{3,23},{4,15},{6,24},{7,38}}) {
        actual={999};
        assert(client.GetSupportFrequencies(test.first,actual)==0 && actual.size()==test.second);
        assert(std::is_sorted(actual.begin(),actual.end()));
        assert(std::adjacent_find(actual.begin(),actual.end())==actual.end());
    }
    assert(client.GetSupportFrequencies(1,actual)==0 && actual.back()==2484);
    assert(client.GetSupportFrequencies(4,actual)==0 && actual.front()==5260 && actual.back()==5700);
    actual={999};
    for (int band : {-1,0,5,8,255}) {
        const int before=calls;
        assert(client.GetSupportFrequencies(band,actual)==WIFI_HAL_OPT_INVALID_PARAM && calls==before);
        assert(actual==std::vector<int>{999});
    }
    backend=-1;
    assert(client.GetSupportFrequencies(7,actual)==WIFI_HAL_OPT_FAILED && actual==std::vector<int>{999});
    backend=0;
    for (const std::string &bad : std::vector<std::string>{"", "FAIL\n", "\n\n", "Mode[A] Channels:\n",
        "Mode[G] Channels:\n 1 = 2412 MHz\n", "Mode[G] Channels:\n 1 = 2412 MHz junk\n\n",
        "Mode[G] Channels:\n 1 = 2412 MHz (DFS)\n\n", "Mode[A] Channels:\n 1 = 2412 MHz\n\n",
        "Mode[A] Channels:\n 36 = -5180 MHz\n\n", "Mode[A] Channels:\n 36 = 21474836480 MHz\n\n",
        "Mode[A] Channels:\n 36 = 5180 MHz (DFS) (NO_IR)\n\n",
        "Mode[A] Channels:\n 36 = 5180 MHz (DFS) (DFS)\n\n",
        "Mode[A] Channels:\nMode[G] Channels:\n\n", "Mode[unknown] Channels:\n\n",
        std::string(2047,'x'), std::string(2048,'x')}) {
        response=bad;
        assert(client.GetSupportFrequencies(7,actual)==WIFI_HAL_OPT_FAILED);
        assert(actual==std::vector<int>{999});
    }
    response="Mode[A] Channels:\n 1 = 5955 MHz (NO_IR)\n\nMode[AD] Channels:\n 1 = 58320 MHz\n\n";
    assert(client.GetSupportFrequencies(7,actual)==0 && actual.empty());
    response="Mode[A] Channels:\n\n";
    assert(client.GetSupportFrequencies(4,actual)==0 && actual.empty());
    response=real;
    assert(client.GetSupportFrequencies(7,actual)==0 && actual.size()==38);
}
'''
        with tempfile.TemporaryDirectory(prefix='wpa-frequency-test-') as directory:
            cpp, binary = Path(directory) / 'test.cpp', Path(directory) / 'test'
            cpp.write_text(prefix + source + main)
            built = subprocess.run([shutil.which('clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary), str(FIXTURE)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_hal_retains_chip_branch_and_requires_actual_sta_interface(self):
        patch = PATCH.read_text()
        self.assertIn('+    return mHdiWpaClient->GetSupportFrequencies(band, frequencies);', patch)
        self.assertIn('+    if (ifaceName != WifiConfigCenter::GetInstance().GetStaIfaceName(INSTID_WLAN0)) {', patch)
        self.assertNotIn('-    if (!HalDeviceManager', patch)


if __name__ == '__main__':
    unittest.main()
