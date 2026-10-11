"""Exact native control sanitizer fixtures, not real network/IPC/guest proof."""
from pathlib import Path
import re
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/ethernet_control'
PATCH = COMPONENT / '0001-commit-real-interface-and-settings-state-before-success.patch'
CPP = 'foundation/communication/netmanager_ext/services/ethernetmanager/src/ethernet_management.cpp'


def function(name, patched=True):
    source = '\n'.join('\n'.join(hunk[2 if patched else 1]) for hunk in patch_sections(PATCH)[CPP])
    found = list(re.finditer(r'^(?:void|bool|int32_t) EthernetManagement::' + name + r'\(', source, re.M))
    if len(found) != 1:
        raise AssertionError('one complete exact native method required: ' + name)
    begin = found[0].start(); brace = source.index('{', begin); end = brace + 1; depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}'); end += 1
    return source[begin:end] + '\n'


MOCK = r'''
#include <algorithm>
#include <cassert>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>
constexpr int ERR_NONE=0, NETMANAGER_EXT_SUCCESS=0, NETMANAGER_EXT_ERR_INTERNAL=2200003;
constexpr const char* IFACE_LINK_UP="up";
constexpr const char* IFACE_LINK_DOWN="down";
constexpr const char* ETHERNET_ENABLED_URI="fixture-uri";
constexpr const char* KEY_ETHERNET_ENABLED="fixture-key";
constexpr int SLEEP_TIME_S=2;
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
#define NETMGR_EXT_LOG_D(...) ((void)0)
#define NETMGR_EXT_LOG_W(...) ((void)0)
#define NETMANAGER_EXT_ETHERNET_ENABLE_DISABLE
namespace OHOS { namespace nmd {
struct InterfaceConfigurationParcel { std::string ifName; std::vector<std::string> flags; };
}}
std::function<void()> ioCheck;
std::function<void()> sleepHook;
unsigned MockSleep(unsigned seconds) { assert(seconds==SLEEP_TIME_S); assert(sleepHook); sleepHook(); return 0; }
#define sleep MockSleep
struct NetsysController {
    std::mutex mutex;
    std::map<std::string,bool> kernel;
    std::vector<std::pair<std::string,bool>> actions;
    std::set<int> failSets, ignoreSets, failGets;
    int gets=0, malformed=0;
    std::function<void()> setHook;
    static NetsysController& GetInstance() { static NetsysController value; return value; }
    int GetInterfaceConfig(OHOS::nmd::InterfaceConfigurationParcel& config) {
        if(ioCheck) ioCheck(); std::lock_guard<std::mutex> lock(mutex); ++gets;
        if(failGets.count(gets)) return -1;
        auto found=kernel.find(config.ifName);
        if(found==kernel.end() || malformed==1) { config.flags.clear(); return 0; }
        if(malformed==2) { config.flags={"up","down"}; return 0; }
        if(malformed==3) { config.ifName="foreign"; return 0; }
        config.flags={found->second ? "up" : "down"}; return 0;
    }
    int Set(const std::string& name,bool enabled) {
        if(ioCheck) ioCheck(); if(setHook) setHook();
        std::lock_guard<std::mutex> lock(mutex); actions.emplace_back(name,enabled);
        const int count=static_cast<int>(actions.size());
        if(failSets.count(count)) return -1;
        // Model the real Netsys false-success path as well as explicit errors.
        if(kernel.count(name) && !ignoreSets.count(count)) kernel[name]=enabled;
        return 0;
    }
    int SetInterfaceUp(const std::string& name) { return Set(name,true); }
    int SetInterfaceDown(const std::string& name) { return Set(name,false); }
    void Reset() { kernel.clear(); actions.clear(); failSets.clear(); ignoreSets.clear();
        failGets.clear(); gets=malformed=0; setHook={}; }
};
struct NetDataShareHelperUtilsIface {
    inline static std::string value="1";
    inline static int updates=0,queries=0,failUpdate=0,failQuery=0,ignoreUpdate=0;
    static int Update(const char*,const char*,const std::string& next) {
        if(ioCheck) ioCheck(); ++updates;
        if(updates==failUpdate) return -1;
        if(updates!=ignoreUpdate) value=next;
        return 0;
    }
    static int Query(const char*,const char*,std::string& result) {
        if(ioCheck) ioCheck(); ++queries; if(queries==failQuery) return -1; result=value; return 0;
    }
    static void Reset(bool enabled) { value=enabled ? "1" : "0";
        updates=queries=failUpdate=failQuery=ignoreUpdate=0; }
};
struct DevInterfaceState { bool linkUp=true; };
template<class T> using sptr=std::shared_ptr<T>;
struct EthernetManagement {
    std::shared_mutex mutex_;
    std::mutex ethernetControlMutex_;
    bool ethernetEnabled_=true;
    std::map<std::string,sptr<DevInterfaceState>> devs_;
    std::map<std::string,int> netLinkConfigs_,configsV4_,configsV6_;
    int refreshed=0, withdrawn=0;
    int32_t EnableEthernet(); int32_t DisableEthernet(); bool IsEthernetEnabled();
    int32_t SetEthernetEnabled(bool); int32_t SnapshotInterfaceStates(std::map<std::string,bool>&);
    int32_t ReadInterfaceAdminState(const std::string&,bool&); int32_t SetInterfaceAdminState(const std::string&,bool);
    int32_t StoreEthernetEnabled(bool); void RestoreInterfaceStates(const std::map<std::string,bool>&);
    void ConfigureAddedInterface(const std::string&); void DisableAllInterfaces();
    void EnableAllInterfaces(); void ReinitializeNetwork(); void CleanupNetworkState();
    void InitEthernetEnabledState(); void StartSetDevUpThd();
    bool IsIfaceLinkUp(const std::string&) { ++refreshed; return false; }
    void UpdateInterfaceState(const std::string& name,bool up) {
        assert(!up); assert(mutex_.try_lock()); mutex_.unlock();
        if(devs_.count(name)) devs_.at(name)->linkUp=false;
        ++withdrawn;
    }
};
void Setup(EthernetManagement& manager,bool policy,std::map<std::string,bool> states) {
    ioCheck={}; sleepHook={}; auto& controller=NetsysController::GetInstance(); controller.Reset();
    controller.kernel=states; manager.ethernetEnabled_=policy; NetDataShareHelperUtilsIface::Reset(policy);
    for(const auto& [name,up]:states) {
        auto state=std::make_shared<DevInterfaceState>(); state->linkUp=up; manager.devs_[name]=state;
        manager.netLinkConfigs_[name]=manager.configsV4_[name]=manager.configsV6_[name]=1;
    }
    ioCheck=[&manager] { assert(manager.mutex_.try_lock()); manager.mutex_.unlock(); };
}
'''

METHODS = ('EnableEthernet', 'DisableEthernet', 'IsEthernetEnabled', 'SnapshotInterfaceStates',
    'ReadInterfaceAdminState', 'SetInterfaceAdminState', 'StoreEthernetEnabled', 'RestoreInterfaceStates',
    'SetEthernetEnabled', 'ConfigureAddedInterface', 'DisableAllInterfaces', 'ReinitializeNetwork',
    'CleanupNetworkState', 'InitEthernetEnabledState', 'StartSetDevUpThd')


def source():
    return MOCK + ''.join(function(name) for name in METHODS)


class EthernetControlTests(unittest.TestCase):
    def test_real_mixed_admin_states_repeated_toggles_cleanup_and_no_carrier_requirement(self):
        compile_run(source() + r'''
int main() {
    EthernetManagement manager; Setup(manager,true,{{"eth0",true},{"eth1",false}});
    auto& native=NetsysController::GetInstance();
    for(int repeat=0;repeat<64;++repeat) {
        assert(manager.DisableEthernet()==0 && !manager.IsEthernetEnabled());
        assert(!native.kernel.at("eth0") && !native.kernel.at("eth1"));
        assert(NetDataShareHelperUtilsIface::value=="0");
        assert(manager.netLinkConfigs_.empty() && manager.configsV4_.empty() && manager.configsV6_.empty());
        assert(!manager.devs_.at("eth0")->linkUp && !manager.devs_.at("eth1")->linkUp);
        const int updates=NetDataShareHelperUtilsIface::updates;
        assert(manager.DisableEthernet()==0 && NetDataShareHelperUtilsIface::updates==updates);
        assert(manager.EnableEthernet()==0 && manager.IsEthernetEnabled());
        assert(native.kernel.at("eth0") && native.kernel.at("eth1"));
        assert(NetDataShareHelperUtilsIface::value=="1");
    }
    assert(manager.withdrawn==256); assert(manager.refreshed==128);
}
''', language='c++')

    def test_empty_contradictory_foreign_and_failed_get_are_not_down_evidence(self):
        compile_run(source() + r'''
int main() {
    for(int malformed=0;malformed<4;++malformed) {
        EthernetManagement manager; Setup(manager,true,{{"eth0",true}});
        auto& native=NetsysController::GetInstance(); native.malformed=malformed;
        if(malformed==0) native.failGets={1};
        assert(manager.DisableEthernet()==NETMANAGER_EXT_ERR_INTERNAL);
        assert(manager.IsEthernetEnabled() && native.kernel.at("eth0"));
        assert(native.actions.empty() && NetDataShareHelperUtilsIface::updates==0);
    }
    EthernetManagement manager; Setup(manager,true,{{"eth0",true}});
    NetsysController::GetInstance().kernel.erase("eth0");
    assert(manager.DisableEthernet()==NETMANAGER_EXT_ERR_INTERNAL && manager.IsEthernetEnabled());
}
''', language='c++')

    def test_explicit_false_success_and_post_write_read_failures_restore_exact_prior_states(self):
        compile_run(source() + r'''
int main() {
    for(int failure=0;failure<3;++failure) {
        EthernetManagement manager; const std::map<std::string,bool> prior={{"eth0",true},{"eth1",false}};
        Setup(manager,true,prior); auto& native=NetsysController::GetInstance();
        if(failure==0) native.failSets={2};
        else if(failure==1) native.ignoreSets={1};
        else native.failGets={3};
        assert(manager.DisableEthernet()==NETMANAGER_EXT_ERR_INTERNAL && manager.IsEthernetEnabled());
        assert(native.kernel==prior && NetDataShareHelperUtilsIface::value=="1");
        assert(NetDataShareHelperUtilsIface::updates==0);
    }
}
''', language='c++')

    def test_policy_write_and_readback_failures_do_not_commit_optimistic_state(self):
        compile_run(source() + r'''
int main() {
    for(bool prior:{false,true}) for(int failure=0;failure<3;++failure) {
        EthernetManagement manager; const std::map<std::string,bool> states={{"eth0",prior},{"eth1",!prior}};
        Setup(manager,prior,states); auto& native=NetsysController::GetInstance();
        if(failure==0) NetDataShareHelperUtilsIface::failUpdate=1;
        else if(failure==1) NetDataShareHelperUtilsIface::ignoreUpdate=1;
        else NetDataShareHelperUtilsIface::failQuery=1;
        assert(manager.SetEthernetEnabled(!prior)==NETMANAGER_EXT_ERR_INTERNAL);
        assert(manager.IsEthernetEnabled()==prior && native.kernel==states);
        assert(NetDataShareHelperUtilsIface::value==(prior ? "1" : "0"));
    }
}
''', language='c++')

    def test_failed_rollback_stays_an_error_and_attempts_all_saved_interfaces(self):
        compile_run(source() + r'''
int main() {
    EthernetManagement manager; Setup(manager,true,{{"eth0",true},{"eth1",false},{"eth2",true}});
    auto& native=NetsysController::GetInstance(); native.failSets={2,3};
    assert(manager.DisableEthernet()==NETMANAGER_EXT_ERR_INTERNAL);
    assert(manager.IsEthernetEnabled() && native.actions.size()==5);
    assert(native.actions.back()==std::make_pair(std::string("eth2"),true));
    assert(!native.kernel.at("eth0") && !native.kernel.at("eth1") && native.kernel.at("eth2"));
}
''', language='c++')

    def test_startup_retry_stops_after_real_disable_or_removal_and_does_not_hold_control_during_sleep(self):
        compile_run(source() + r'''
int main() {
    for(bool remove:{false,true}) {
        EthernetManagement manager; Setup(manager,true,{{"eth0",false}});
        auto& native=NetsysController::GetInstance(); native.failSets={1}; int sleeps=0;
        sleepHook=[&] { ++sleeps;
            if(remove) { std::unique_lock<std::shared_mutex> lock(manager.mutex_); manager.devs_.erase("eth0"); }
            else assert(manager.DisableEthernet()==0);
        };
        manager.StartSetDevUpThd(); assert(sleeps==1);
        assert(native.actions.size()==(remove ? 1u : 2u));
        assert(!native.kernel.at("eth0"));
    }
}
''', language='c++')

    def test_getter_and_hot_add_wait_for_committed_global_policy(self):
        compile_run(source() + r'''
int main() {
    using namespace std::chrono_literals;
    EthernetManagement manager; Setup(manager,false,{{"eth0",false}});
    auto& native=NetsysController::GetInstance();
    std::promise<void> entered, release; auto resume=release.get_future().share(); std::atomic<bool> first{true};
    native.setHook=[&] { if(first.exchange(false)) { entered.set_value(); resume.wait(); } };
    auto enabling=std::async(std::launch::async,[&] { return manager.EnableEthernet(); });
    entered.get_future().wait();
    std::promise<void> readerEntered, addEntered;
    auto reading=std::async(std::launch::async,[&] { readerEntered.set_value(); return manager.IsEthernetEnabled(); });
    readerEntered.get_future().wait();
    assert(reading.wait_for(20ms)==std::future_status::timeout);
    { std::unique_lock<std::shared_mutex> lock(manager.mutex_);
      manager.devs_["eth1"]=std::make_shared<DevInterfaceState>(); }
    { std::lock_guard<std::mutex> lock(native.mutex); native.kernel["eth1"]=false; }
    auto added=std::async(std::launch::async,[&] { addEntered.set_value(); manager.ConfigureAddedInterface("eth1"); });
    addEntered.get_future().wait();
    assert(added.wait_for(20ms)==std::future_status::timeout);
    release.set_value(); assert(enabling.get()==0); assert(reading.get()); added.get();
    assert(native.kernel.at("eth0") && native.kernel.at("eth1"));
    assert(manager.DisableEthernet()==0 && !manager.IsEthernetEnabled());
    manager.ConfigureAddedInterface("eth1"); assert(!native.kernel.at("eth1"));
}
''', language='c++')

    def test_original_enable_ignores_a_real_settings_and_device_failure(self):
        original = MOCK + function('EnableEthernet', False) + function('EnableAllInterfaces', False)
        original += 'void EthernetManagement::ReinitializeNetwork() {}\n'
        result = compile_run(original + r'''
int main() {
    assert(std::string(IFACE_LINK_UP)=="up" && std::string(IFACE_LINK_DOWN)=="down" && SLEEP_TIME_S==2);
    EthernetManagement manager; Setup(manager,false,{{"eth0",false}});
    NetsysController::GetInstance().failSets={1}; NetDataShareHelperUtilsIface::failUpdate=1;
    assert(manager.EnableEthernet()==NETMANAGER_EXT_ERR_INTERNAL);
}
''', language='c++', expect_success=False)
        self.assertNotEqual(result.returncode, 0)

    def test_common_recipe_native_macro_and_private_boundary(self):
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(build.count('bash "${ETHERNET_CONTROL_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertIn('netmanager_ext/ethernet_control/apply.sh', build)
        hunks = patch_sections(PATCH)
        self.assertEqual(set(hunks), {CPP,
            'foundation/communication/netmanager_ext/services/ethernetmanager/include/ethernet_management.h'})
        self.assertNotIn('CheckPermission', PATCH.read_text())
        compile_check = (ROOT / 'ci/capability-audit/compile_ethernet_control.py').read_text()
        self.assertIn("'-DNETMANAGER_EXT_ETHERNET_ENABLE_DISABLE' in item['executed_argv']", compile_check)
        self.assertIn("report.update(status='fail'", compile_check)
        self.assertNotIn('candidate_defines=', compile_check)


if __name__ == '__main__':
    unittest.main()
