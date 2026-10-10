#!/usr/bin/env python3
"""Execute exact patched callback methods with owned host lifecycle fixtures.

This checks serialization and macro selection, not HDI IPC or a guest radio.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/wpa_scan'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        if source[cursor] == '{':
            depth += 1
        elif source[cursor] == '}':
            depth -= 1
        cursor += 1
    return source[start:cursor]


def run(source_root, output):
    if output.exists():
        raise ValueError('fresh callback evidence output required')
    spec = importlib.util.spec_from_file_location('wifi_scan_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.validate(source_root, require_patched=True)
    files = {name: source_root / baseline.PROJECT / name for name, _, _ in baseline.FILES}
    original = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    source = files[baseline.PREFIX + 'wifi_hal_interface/wifi_supplicant_hal_interface.cpp'].read_text()
    callback_source = files[baseline.PREFIX + 'client/hdi_client/wifi_hdi_wpa_callback.cpp'].read_text()
    methods = '\n'.join(function(source, signature) for signature in (
        'WifiErrorNo WifiSupplicantHalInterface::RegisterSupplicantEventCallback(',
        'WifiErrorNo WifiSupplicantHalInterface::UnRegisterSupplicantEventCallback(',
        'void WifiSupplicantHalInterface::NotifyScanResultEvent('))
    callback = function(callback_source, 'int32_t OnEventScanResult(')
    fixture = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <functional>
#include <future>
#include <mutex>
#include <thread>
#define LOGI(...)
#define LOGE(...)
[[maybe_unused]] constexpr int WIFI_HAL_OPT_OK = 0, WIFI_HAL_OPT_FAILED = 1;
constexpr int HAL_CMD_NEW_SCAN_RESULTS = 34, HAL_CMD_SCAN_ABORTED = 35;
constexpr int HAL_SINGLE_SCAN_FAILED = 1, HAL_SINGLE_SCAN_OVER_OK = 2;
struct IWpaCallback {};
struct HdiWpaRecvScanResultParam { unsigned int scanId; };
namespace OHOS { namespace Wifi {
using WifiErrorNo = int;
struct SupplicantEventCallback { std::function<void(int)> onScanNotify; };
class WifiSupplicantHalInterface {
public:
    static WifiSupplicantHalInterface &GetInstance() {
        static WifiSupplicantHalInterface instance;
        return instance;
    }
    WifiErrorNo RegisterSupplicantEventCallback(SupplicantEventCallback &callback);
    WifiErrorNo UnRegisterSupplicantEventCallback();
    void NotifyScanResultEvent(uint32_t event);
private:
    static std::mutex mSupplicantHalMutex;
    SupplicantEventCallback mCallback;
};
std::mutex WifiSupplicantHalInterface::mSupplicantHalMutex;
'''
    main = r'''
int main()
{
    using namespace OHOS::Wifi;
    auto &service = WifiSupplicantHalInterface::GetInstance();
    SupplicantEventCallback cb;
    int hits = 0, last = -1;
    cb.onScanNotify = [&](int event) { ++hits; last = event; };
#if defined(HDI_CHIP_INTERFACE_SUPPORT) || defined(HDI_WPA_INTERFACE_SUPPORT)
    assert(service.RegisterSupplicantEventCallback(cb) == WIFI_HAL_OPT_OK);
    HdiWpaRecvScanResultParam event {1};
    assert(OnEventScanResult(nullptr, nullptr, "wlan0") == 1 && hits == 0);
    assert(OnEventScanResult(nullptr, &event, "wlan0") == 0 && hits == 1);
    assert(last == HAL_SINGLE_SCAN_OVER_OK);
    service.NotifyScanResultEvent(HAL_CMD_SCAN_ABORTED);
    assert(hits == 2 && last == HAL_SINGLE_SCAN_FAILED);
    assert(service.UnRegisterSupplicantEventCallback() == WIFI_HAL_OPT_OK);
    assert(OnEventScanResult(nullptr, &event, "wlan0") == 0 && hits == 2);
    // Verify that unregister cannot return while an owner's callback is running.
    for (int iteration = 0; iteration < 25; ++iteration) {
        std::promise<void> entered, release, attempting;
        auto releaseFuture = release.get_future().share();
        std::atomic<bool> finished {false};
        cb.onScanNotify = [&](int value) {
            assert(value == HAL_SINGLE_SCAN_OVER_OK);
            entered.set_value();
            releaseFuture.wait();
            finished = true;
        };
        assert(service.RegisterSupplicantEventCallback(cb) == WIFI_HAL_OPT_OK);
        auto delivery = std::async(std::launch::async, [&] {
            return OnEventScanResult(nullptr, &event, "wlan0");
        });
        entered.get_future().wait();
        auto unregister = std::async(std::launch::async, [&] {
            attempting.set_value();
            const int result = service.UnRegisterSupplicantEventCallback();
            assert(finished.load());
            return result;
        });
        attempting.get_future().wait();
        assert(unregister.wait_for(std::chrono::milliseconds(5)) == std::future_status::timeout);
        release.set_value();
        assert(delivery.get() == 0 && unregister.get() == WIFI_HAL_OPT_OK);
        assert(OnEventScanResult(nullptr, &event, "wlan0") == 0);
    }
#else
    assert(service.RegisterSupplicantEventCallback(cb) == WIFI_HAL_OPT_FAILED);
    service.NotifyScanResultEvent(HAL_CMD_NEW_SCAN_RESULTS);
    assert(hits == 0);
    assert(service.UnRegisterSupplicantEventCallback() == WIFI_HAL_OPT_FAILED);
#endif
}
'''
    compiler = shutil.which('clang++')
    if compiler is None:
        raise ValueError('actual host C++ compiler required')
    rows = []
    with tempfile.TemporaryDirectory(prefix='wpa-callback-lifetime-') as directory:
        path = Path(directory)
        unit = path / 'callback.cpp'
        unit.write_text(fixture + methods + '\n}}\n' + callback + main)
        for name, defines in (('wpa', ['HDI_WPA_INTERFACE_SUPPORT']),
                              ('chip', ['HDI_CHIP_INTERFACE_SUPPORT']),
                              ('both', ['HDI_WPA_INTERFACE_SUPPORT', 'HDI_CHIP_INTERFACE_SUPPORT']),
                              ('neither', [])):
            binary = path / name
            argv = [compiler, '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined',
                    *['-D' + define for define in defines], str(unit), '-o', str(binary)]
            built = subprocess.run(argv, text=True, capture_output=True)
            if built.returncode:
                raise ValueError('callback compile failed: ' + built.stdout + built.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise ValueError('callback boundary failed: ' + result.stdout + result.stderr)
            rows.append(dict(configuration=name, argv=argv, exit_code=result.returncode,
                             fixture_sha256=hashlib.sha256(unit.read_bytes()).hexdigest()))
    if any(hashlib.sha256(files[name].read_bytes()).hexdigest() != value for name, value in original.items()):
        raise ValueError('exact callback source changed during validation')
    report = dict(status='pass', scope='exact_callback_host_fixture_NOT_IPC_or_guest',
                  component_revision=baseline.REVISION, source_sha256=original, results=rows,
                  first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_root.resolve(), args.output.resolve())
    print(json.dumps(dict(status=report['status'], configurations=len(report['results']))))
