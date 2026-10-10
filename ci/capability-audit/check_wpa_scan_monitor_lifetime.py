#!/usr/bin/env python3
"""Run exact repaired ScanMonitor methods against explicit host HAL fixtures."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_wpa_scan_callback_lifetime import function

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/wpa_scan_lifecycle'


def run(source_root, output):
    if output.exists():
        raise ValueError('fresh monitor lifecycle evidence path required')
    spec = importlib.util.spec_from_file_location('wifi_monitor_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.validate(source_root, require_patched=True)
    files = {name: source_root / baseline.PROJECT / name for name, _, _ in baseline.FILES}
    original = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    source = files[baseline.PREFIX + 'scan_monitor.cpp'].read_text()
    header = files[baseline.PREFIX + 'scan_monitor.h'].read_text()
    service = files[baseline.PREFIX + 'scan_service.cpp'].read_text()
    init = function(service, 'bool ScanService::InitScanService(')
    destructor = function(service, 'ScanService::~ScanService()')
    if (init.index('pScanMonitor->SetScanStateMachine(pScanStateMachine)') >=
            init.index('pScanMonitor->InitScanMonitor()') or
            'SetScanStateMachine(nullptr)' in destructor or
            destructor.index('delete pScanMonitor;') >= destructor.index('delete pScanStateMachine;')):
        raise ValueError('actual ScanService publication/destruction order is unsafe')
    declarations = header[header.index('namespace OHOS {'):header.rindex('#endif')]
    methods = source[source.index('namespace OHOS {'):]
    fixture = r'''
#include <cassert>
#include <functional>
#include <vector>
#define FRIEND_GTEST(...)
#define WIFI_LOGI(...)
#define WIFI_LOGE(...)
constexpr int WIFI_HAL_OPT_OK = 0, WIFI_HAL_OPT_FAILED = 1;
constexpr int HAL_SINGLE_SCAN_OVER_OK = 1, HAL_SINGLE_SCAN_FAILED = 2, HAL_PNO_SCAN_OVER_OK = 3;
constexpr int SCAN_RESULT_EVENT = 10, SCAN_FAILED_EVENT = 20, PNO_SCAN_RESULT_EVENT = 30;
namespace OHOS { namespace Wifi {
class ScanStateMachine {
public:
    std::vector<int> messages;
    void SendMessage(int value) { messages.push_back(value); }
};
struct SupplicantEventCallback { std::function<void(int)> onScanNotify; };
class WifiSupplicantHalInterface {
public:
    bool failRegistration = false, emitDuringRegistration = false;
    int registrations = 0, unregistrations = 0;
    SupplicantEventCallback callback;
    static WifiSupplicantHalInterface &GetInstance() {
        static WifiSupplicantHalInterface instance;
        return instance;
    }
    int RegisterSupplicantEventCallback(SupplicantEventCallback &value) {
        ++registrations;
        if (failRegistration) { return WIFI_HAL_OPT_FAILED; }
        callback = value;
        if (emitDuringRegistration) { emit(HAL_SINGLE_SCAN_OVER_OK); }
        return WIFI_HAL_OPT_OK;
    }
    int UnRegisterSupplicantEventCallback() {
        ++unregistrations;
        callback.onScanNotify = nullptr;
        return WIFI_HAL_OPT_OK;
    }
    void emit(int value) { if (callback.onScanNotify) { callback.onScanNotify(value); } }
};
}}
'''
    main = r'''
int main()
{
    using namespace OHOS::Wifi;
    auto &hal = WifiSupplicantHalInterface::GetInstance();
    ScanStateMachine machine;
    // A failed or never attempted registration must not unregister another owner.
    { ScanMonitor monitor; }
    assert(hal.registrations == 0 && hal.unregistrations == 0);
    hal.failRegistration = true;
    { ScanMonitor monitor; assert(!monitor.InitScanMonitor()); }
    assert(hal.registrations == 1 && hal.unregistrations == 0);
    hal.failRegistration = false;
    hal.emitDuringRegistration = true;
    {
        ScanMonitor monitor;
        monitor.SetScanStateMachine(&machine);
        assert(monitor.InitScanMonitor());
        assert(machine.messages == std::vector<int>{SCAN_RESULT_EVENT});
        const int registered = hal.registrations;
        assert(monitor.InitScanMonitor() && hal.registrations == registered);
        hal.emit(HAL_SINGLE_SCAN_FAILED);
        hal.emit(HAL_PNO_SCAN_OVER_OK);
        hal.emit(-1);
        assert((machine.messages == std::vector<int>{SCAN_RESULT_EVENT, SCAN_FAILED_EVENT,
                                                    PNO_SCAN_RESULT_EVENT}));
        // No explicit UnInit: models a later ScanService initialization failure.
    }
    assert(hal.unregistrations == 1 && !hal.callback.onScanNotify);
    hal.emit(HAL_SINGLE_SCAN_OVER_OK); // ASan must not observe a retired capture.
    assert(machine.messages.size() == 3);
    hal.emitDuringRegistration = false;
    auto *retired = new ScanMonitor();
    retired->SetScanStateMachine(&machine);
    assert(retired->InitScanMonitor());
    retired->UnInitScanMonitor();
    retired->UnInitScanMonitor();
    const int removed = hal.unregistrations;
    {
        ScanMonitor replacement;
        replacement.SetScanStateMachine(&machine);
        assert(replacement.InitScanMonitor());
        hal.failRegistration = true;
        { ScanMonitor failed; assert(!failed.InitScanMonitor()); }
        hal.failRegistration = false;
        assert(hal.unregistrations == removed && hal.callback.onScanNotify);
        delete retired; // Already-unregistered destructor cannot clear replacement.
        assert(hal.unregistrations == removed && hal.callback.onScanNotify);
        hal.emit(HAL_SINGLE_SCAN_OVER_OK);
        assert(machine.messages.size() == 4);
    }
    assert(hal.unregistrations == removed + 1 && !hal.callback.onScanNotify);
    for (int i = 0; i < 100; ++i) {
        auto *monitor = new ScanMonitor();
        monitor->SetScanStateMachine(&machine);
        assert(monitor->InitScanMonitor());
        hal.emit(HAL_SINGLE_SCAN_OVER_OK);
        delete monitor;
        hal.emit(HAL_SINGLE_SCAN_OVER_OK);
        assert(!hal.callback.onScanNotify);
    }
    assert(machine.messages.size() == 104);
}
'''
    compiler = shutil.which('clang++')
    if compiler is None:
        raise ValueError('host C++ compiler required')
    with tempfile.TemporaryDirectory(prefix='scan-monitor-lifetime-') as directory:
        path = Path(directory)
        unit, executable = path / 'monitor.cpp', path / 'monitor'
        unit.write_text(fixture + declarations + methods + main)
        argv = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-private-field',
                '-fsanitize=address,undefined', str(unit), '-o', str(executable)]
        built = subprocess.run(argv, text=True, capture_output=True)
        if built.returncode:
            raise ValueError('actual monitor fixture compile failed: ' + built.stdout + built.stderr)
        result = subprocess.run([str(executable)], text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError('actual monitor boundary failed: ' + result.stdout + result.stderr)
        fixture_hash = hashlib.sha256(unit.read_bytes()).hexdigest()
    if any(hashlib.sha256(files[name].read_bytes()).hexdigest() != value for name, value in original.items()):
        raise ValueError('actual scan monitor input changed')
    report = dict(status='pass', scope='exact_monitor_host_HAL_fixture_NOT_IPC_or_guest',
                  source_sha256=original, fixture_sha256=fixture_hash, argv=argv,
                  exit_code=result.returncode, repeated_lifetimes=100,
                  failed_registration_preserves_existing_owner=True,
                  retired_destructor_preserves_replacement=True,
                  first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_root.resolve(), args.output.resolve())
    print(json.dumps(dict(status=report['status'], repeated_lifetimes=report['repeated_lifetimes'])))
