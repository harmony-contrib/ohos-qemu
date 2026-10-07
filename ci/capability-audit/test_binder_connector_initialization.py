"""Actual singleton function under host concurrency; not guest-driver proof."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/communication/ipc/binder_connector_initialization'
SPEC = importlib.util.spec_from_file_location('binder_connector_baseline_test', COMPONENT / 'verify_source.py')
BC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BC)


class BinderConnectorInitializationTests(unittest.TestCase):
    def test_current_thread_token_query_deterministic_success_and_failure_interleaving(self):
        source = r'''#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <thread>
constexpr unsigned ACCESS_TOKENID_GET_TOKENID=1;
std::atomic<unsigned> phase=0;
thread_local unsigned role=0;
bool secondFails=false;
int QueryIoctl(int,unsigned,uint64_t* result) {
    if(role==0) {
        *result=0x1122334455667788ULL;
        phase.store(1);
        while(phase.load()!=2) std::this_thread::yield();
        return 0;
    }
    while(phase.load()!=1) std::this_thread::yield();
    *result=0x8877665544332211ULL;
    phase.store(2);
    return secondFails ? -1 : 0;
}
int CloseFile(FILE*) { return 0; }
#define ioctl QueryIoctl
#define fclose CloseFile
uint64_t QueryToken() {
    int fd=0;
    FILE* fp=nullptr;
''' + BC.NEW_TOKEN_QUERY + r'''}
int main() {
    for(unsigned repeat=0;repeat<256;++repeat) {
        phase.store(0);secondFails=repeat%2!=0;
        uint64_t first=0,second=0;
        std::thread a([&] { role=0;first=QueryToken(); });
        std::thread b([&] { role=1;second=QueryToken(); });
        a.join();b.join();
        assert(first==0x1122334455667788ULL);
        assert(second==(secondFails ? 0 : 0x8877665544332211ULL));
    }
}
'''
        self.assertNotIn('selfTokenID_', BC.NEW_TOKEN_QUERY)
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, binary = root / 'probe.cpp', root / 'probe'
            path.write_text(source)
            subprocess.run([compiler, '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(path), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_all_publication_reads_are_locked_and_manifest_plan_is_pinned(self):
        self.assertLess(BC.NEW.index('lockGuard(skeletonMutex)'), BC.NEW.index('instance_ == nullptr'))
        self.assertEqual(BC.NEW.count('lockGuard('), 1)
        self.assertEqual(BC.NEW.count('instance_ == nullptr'), 1)
        self.assertNotIn('call_once', BC.NEW)
        self.assertIn('delete temp;', BC.NEW)
        projects = json.loads((REPO / 'scripts/openharmony_7_0_release_source_lock.json').read_text())['projects']
        self.assertEqual(next(row['revision'] for row in projects if row['path'] == BC.PROJECT), BC.REVISION)
        plan = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text().split(
            'apply_qemu_capability_patch_plan() {', 1)[1].split('\n}\n', 1)[0]
        self.assertEqual(plan.count('bash "${QEMU_BINDER_CONNECTOR_COMPONENT_SCRIPT}"'), 1)
        self.assertLess(plan.index('QEMU_BINDER_CONNECTOR_COMPONENT_SCRIPT'), plan.index('configure_qemu_device_profile'))

    def test_actual_function_retries_failures_then_publishes_once_for_32_threads(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        source = '''#include <atomic>
#include <cassert>
#include <cstdlib>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <vector>
#define ZLOGE(...) ((void)0)
constexpr const char* DRIVER_NAME="owned-test-context";
static std::atomic<unsigned> opened=0, destroyed=0;
static bool failAllocation=true;
struct BinderConnector {
    static std::mutex skeletonMutex;
    static BinderConnector* instance_;
    unsigned initialized=0;
    explicit BinderConnector(const std::string&) {}
    ~BinderConnector() { ++destroyed; }
    static void* operator new(size_t bytes,const std::nothrow_t&) noexcept {
        return failAllocation?nullptr:std::malloc(bytes);
    }
    static void operator delete(void* pointer) noexcept { std::free(pointer); }
    bool OpenDriver() {
        const unsigned attempt=opened.fetch_add(1);
        if(attempt==0) return false;
        initialized=73; return true;
    }
    static BinderConnector* GetInstance();
};
std::mutex BinderConnector::skeletonMutex;
BinderConnector* BinderConnector::instance_=nullptr;
''' + BC.NEW + '''int main() {
    assert(BinderConnector::GetInstance()==nullptr && opened==0 && destroyed==0);
    failAllocation=false;
    assert(BinderConnector::GetInstance()==nullptr && opened==1 && destroyed==1);
    std::vector<std::thread> threads;
    std::vector<BinderConnector*> observed(32);
    for(unsigned i=0;i<observed.size();++i) threads.emplace_back([&,i] {
        for(unsigned repeat=0;repeat<4096;++repeat) {
            auto* value=BinderConnector::GetInstance();
            assert(value!=nullptr && value->initialized==73);
            if(repeat==0) observed[i]=value;
            assert(observed[i]==value);
        }
    });
    for(auto& thread:threads) thread.join();
    for(auto* value:observed) assert(value==observed[0]);
    assert(opened==2 && destroyed==1);
    delete observed[0]; // Test-owned singleton, after all threads have joined.
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, binary = root / 'probe.cpp', root / 'probe'
            path.write_text(source)
            subprocess.run([compiler, '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(path), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
