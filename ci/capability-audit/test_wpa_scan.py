"""Scan command boundaries from the actual patch body; not radio/guest proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


COMPONENT = Path(__file__).resolve().parents[2] / 'patches/common/foundation/communication/wifi/wpa_scan'
PATCH = COMPONENT / '0001-route-non-chip-scans-through-wpa.patch'


def patched_scan():
    block = PATCH.read_text().split(' WifiErrorNo WifiHdiWpaClient::Scan(', 1)[1]
    block = ' WifiErrorNo WifiHdiWpaClient::Scan(' + block
    block = block.split(' WifiErrorNo WifiHdiWpaClient::QueryScanInfos', 1)[0]
    return '\n'.join(line[1:] for line in block.splitlines() if line[:1] in (' ', '+'))


class WpaScanTests(unittest.TestCase):
    def test_real_scan_body_parameter_and_backend_failure_boundaries(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler, 'C++ compiler required for scan boundary validation')
        prefix = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
using WifiErrorNo = int;
constexpr int WIFI_HAL_OPT_OK = 0, WIFI_HAL_OPT_FAILED = 1;
constexpr int WIFI_HAL_OPT_NOT_SUPPORT = 2, WIFI_HAL_OPT_INVALID_PARAM = 3;
constexpr int INSTID_WLAN0 = 0;
struct WifiHalScanParam {
    std::vector<std::string> hiddenNetworkSsid;
    std::vector<int> scanFreqs;
    int scanStyle = 0;
};
class WifiHdiWpaClient { public: WifiErrorNo Scan(const WifiHalScanParam &); };
static std::string seen, response = "OK\n";
static int calls = 0, backend = 0;
const char *GetHdiStaIfaceName(int id) { assert(id == 0); return "wlan0"; }
int HdiWpaGetMloLinkedInfo(const char *iface, const char *command, char *reply, size_t size)
{
    assert(std::string(iface) == "wlan0");
    assert(size == 2048);
    ++calls;
    seen = command;
    if (backend == 0) {
        assert(response.size() < size);
        memcpy(reply, response.c_str(), response.size() + 1);
    }
    return backend;
}
'''
        main = r'''
int main()
{
    WifiHdiWpaClient client;
    WifiHalScanParam p;
    assert(client.Scan(p) == WIFI_HAL_OPT_OK && seen == "SCAN" && calls == 1);
    p.scanFreqs = {2412, 5180};
    p.hiddenNetworkSsid = {"hello world", std::string("A\0\xff", 3)};
    assert(client.Scan(p) == WIFI_HAL_OPT_OK);
    assert(seen == "SCAN freq=2412,5180 ssid 68656c6c6f20776f726c64 ssid 4100ff");
    p.hiddenNetworkSsid = {"\nSCAN; freq=1"};
    assert(client.Scan(p) == WIFI_HAL_OPT_OK);
    assert(seen.find('\n') == std::string::npos && seen.find(';') == std::string::npos);
    p = {};
    p.hiddenNetworkSsid = {std::string(32, 'x')};
    assert(client.Scan(p) == WIFI_HAL_OPT_OK);
    auto reject = [&](const WifiHalScanParam &bad, int expected) {
        const int before = calls;
        assert(client.Scan(bad) == expected);
        assert(calls == before); // Validation must precede any backend action.
    };
    p.hiddenNetworkSsid = {std::string(33, 'x')};
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.hiddenNetworkSsid = {""};
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.hiddenNetworkSsid.assign(17, "a");
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.hiddenNetworkSsid.assign(16, std::string(32, 'a'));
    reject(p, WIFI_HAL_OPT_INVALID_PARAM); // Combined command exceeds bound.
    p = {};
    p.scanFreqs.assign(257, 2412);
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.scanFreqs.assign(256, 2412);
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.scanFreqs = {2412, 0};
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p.scanFreqs = {-1};
    reject(p, WIFI_HAL_OPT_INVALID_PARAM);
    p = {};
    for (int style : {-1, 1, 9, 256, 255}) {
        p.scanStyle = style;
        reject(p, WIFI_HAL_OPT_NOT_SUPPORT);
    }
    p = {};
    backend = -1;
    assert(client.Scan(p) == WIFI_HAL_OPT_FAILED);
    backend = 0;
    for (const char *value : {"FAIL\n", "FAIL-BUSY\n", "", "OK extra", "OK\nextra"}) {
        response = value;
        assert(client.Scan(p) == WIFI_HAL_OPT_FAILED);
    }
    for (const char *value : {"OK", "OK\n"}) {
        response = value;
        assert(client.Scan(p) == WIFI_HAL_OPT_OK);
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='wpa-scan-boundary-') as directory:
            source = Path(directory) / 'test.cpp'
            executable = Path(directory) / 'test'
            source.write_text(prefix + patched_scan() + main)
            built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                    '-fsanitize=address,undefined', str(source), '-o', str(executable)],
                                   text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_chip_route_kept_and_wpa_interface_not_silently_ignored(self):
        patch = PATCH.read_text()
        self.assertEqual(patch.count('+#elif defined(HDI_WPA_INTERFACE_SUPPORT)'), 2)
        self.assertEqual(patch.count('+    if (ifaceName != WifiConfigCenter::GetInstance()'
                                     '.GetStaIfaceName(INSTID_WLAN0)) {'), 2)
        self.assertIn('+    return mHdiWpaClient->Scan(scanParam);', patch)
        self.assertIn('+    return mHdiWpaClient->QueryScanInfos(scanInfos);', patch)
        self.assertNotIn('-    ParseScanInfo(', patch)

    def test_registration_and_delivery_use_existing_synchronized_path(self):
        patch = PATCH.read_text()
        self.assertEqual(patch.count('+#if defined(HDI_CHIP_INTERFACE_SUPPORT) || '
                                     'defined(HDI_WPA_INTERFACE_SUPPORT)'), 2)
        self.assertIn('NotifyScanResultEvent(HAL_CMD_NEW_SCAN_RESULTS);', patch)
        self.assertIn('-        OHOS::Wifi::WifiSupplicantHalInterface::GetInstance().GetCallbackInst();', patch)
        self.assertNotIn('+        cbk.onScanNotify', patch)

    def test_component_is_registered_once_in_common_build(self):
        build = Path(__file__).resolve().parents[2] / 'scripts/build_standard_qemu_in_docker.sh'
        source = build.read_text()
        self.assertEqual(source.count('bash "${QEMU_WPA_SCAN_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertIn('common/foundation/communication/wifi/wpa_scan/apply.sh', source)


if __name__ == '__main__':
    unittest.main()
