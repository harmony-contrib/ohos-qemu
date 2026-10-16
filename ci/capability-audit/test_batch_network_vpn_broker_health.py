"""Actual bounded health queue and reconciliation; backend/IPC explicit doubles."""
from pathlib import Path
import os
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT,EXT,body,compile_run
from test_batch_network_vpn_broker import prepared

DECLARATIONS=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <deque>
#include <functional>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <vector>
#define SUPPORT_SYSVPN 1
#define NETMGR_EXT_LOG_E(...) ((void)0)
constexpr int NETMANAGER_EXT_SUCCESS=0;
FFRT_DECLARATIONS
struct NetVpnImpl{std::atomic<bool>has{true},lost{false};std::atomic<int>result{0},calls{0};bool HasQemuSession(){return has;}bool QemuNeedsRecovery(){return lost;}};
std::shared_ptr<NetVpnImpl>QemuOpenvpn(const std::shared_ptr<NetVpnImpl>&value){return value;}
struct NetworkVpnService:std::enable_shared_from_this<NetworkVpnService>{
 struct Dispatch{std::mutex mutex;std::atomic<bool>running{true};uint64_t healthEpoch=0;bool healthScheduled=false;std::atomic<int>failures{0};void Stop(){std::lock_guard<std::mutex>lock(mutex);running=false;++healthEpoch;healthScheduled=false;}void Restart(){std::lock_guard<std::mutex>lock(mutex);running=true;}};
 std::shared_ptr<Dispatch>callbackDispatch_=std::make_shared<Dispatch>();ffrt::shared_mutex netVpnMutex_;
 std::shared_ptr<NetVpnImpl>vpnObj_,connectingObj_;std::map<std::string,std::shared_ptr<NetVpnImpl>>vpnObjMap_;
 int DestroyOwnedConnection(const std::shared_ptr<NetVpnImpl>&value){++value->calls;if(value->result==0)value->has=false;return value->result;}
 bool ScheduleQemuHealthCheck();bool ReconcileQemuSessions(bool,uint64_t=0);
 ~NetworkVpnService(){callbackDispatch_->Stop();ReconcileQemuSessions(true);}
};
'''
FAKE_FFRT=r'''
namespace ffrt{
 using shared_mutex=std::shared_mutex;std::deque<std::function<void()>>tasks;bool reject=false;
 struct task_attr{uint64_t value=0;task_attr&delay(uint64_t us){value=us;return *this;}};
 struct queue{explicit queue(const char*){}void*submit_h(std::function<void()>fn,const task_attr&attr){assert(attr.value==500000);if(reject)return nullptr;tasks.push_back(std::move(fn));return reinterpret_cast<void*>(1);}};
}
void Tick(){assert(!ffrt::tasks.empty());auto fn=std::move(ffrt::tasks.front());ffrt::tasks.pop_front();fn();}
'''
HOST_MAIN=r'''
int main(){auto service=std::make_shared<NetworkVpnService>();auto one=std::make_shared<NetVpnImpl>(),two=std::make_shared<NetVpnImpl>();
 service->vpnObj_=one;service->connectingObj_=two;service->vpnObjMap_={{"one",one},{"two",two}};
 assert(service->ScheduleQemuHealthCheck());for(int i=0;i<20;++i)assert(service->ScheduleQemuHealthCheck());assert(ffrt::tasks.size()==1);
 Tick();assert(one->calls==0 && two->calls==0 && ffrt::tasks.size()==1);
 one->lost=true;one->result=2200999;Tick();assert(one->calls==1 && two->calls==0 && service->vpnObjMap_.size()==2 && service->callbackDispatch_->failures==1);
 one->result=0;Tick();assert(one->calls==2 && !one->has && two->calls==0 && service->vpnObjMap_.size()==1 && !service->vpnObj_);
 auto state=service->callbackDispatch_;state->Stop();state->Restart();assert(service->ScheduleQemuHealthCheck() && ffrt::tasks.size()==2);
 Tick();assert(state->healthScheduled && ffrt::tasks.size()==1 && two->calls==0);
 assert(!service->ReconcileQemuSessions(false,0) && two->calls==0);Tick();assert(ffrt::tasks.size()==1);
 service.reset();assert(two->calls==1 && !two->has);Tick();assert(ffrt::tasks.empty());
 auto rejected=std::make_shared<NetworkVpnService>();ffrt::reject=true;assert(!rejected->ScheduleQemuHealthCheck() && rejected->callbackDispatch_->failures==1 && !rejected->callbackDispatch_->healthScheduled);
}
'''
NATIVE_MAIN=r'''
template<class F>void Until(F predicate){const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(4);while(!predicate()){assert(std::chrono::steady_clock::now()<deadline);std::this_thread::sleep_for(std::chrono::milliseconds(10));}}
int main(){auto service=std::make_shared<NetworkVpnService>();auto one=std::make_shared<NetVpnImpl>(),two=std::make_shared<NetVpnImpl>();
 service->vpnObj_=one;service->connectingObj_=two;service->vpnObjMap_={{"one",one},{"two",two}};
 one->lost=true;one->result=2200999;assert(service->ScheduleQemuHealthCheck());for(int i=0;i<20;++i)assert(service->ScheduleQemuHealthCheck());
 Until([&]{return one->calls.load()>=1;});assert(two->calls==0);one->result=0;Until([&]{return !one->has.load();});
 {std::unique_lock<ffrt::shared_mutex>lock(service->netVpnMutex_);assert(service->vpnObjMap_.size()==1 && service->vpnObjMap_.at("two")==two);}
 auto dispatch=service->callbackDispatch_;dispatch->Stop();dispatch->Restart();assert(service->ScheduleQemuHealthCheck());
 assert(!service->ReconcileQemuSessions(false,0) && two->calls==0);
 std::weak_ptr<NetworkVpnService>weak=service;service.reset();Until([&]{return weak.expired() && two->calls.load()==1;});
 auto done=std::make_shared<std::promise<void>>();auto future=done->get_future();auto handle=VpnBackendHealthQueue().submit_h([done]{done->set_value();},ffrt::task_attr().delay(700000));
 assert(handle!=nullptr && future.wait_for(std::chrono::seconds(3))==std::future_status::ready);
}
'''


class BrokerHealthTests(unittest.TestCase):
    def test_actual_schedule_epoch_failure_retry_isolation_and_teardown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/networkvpn_service.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ['ffrt::queue &VpnBackendHealthQueue()', 'bool NetworkVpnService::ScheduleQemuHealthCheck()', 'bool NetworkVpnService::ReconcileQemuSessions('])
            compile_run(DECLARATIONS.replace('FFRT_DECLARATIONS',FAKE_FFRT)+actual+HOST_MAIN,root,extra=['-pthread'])
            output=os.environ.get('BATCH_NETWORK_BROKER_HEALTH_NATIVE_OUTPUT')
            if output:Path(output).write_text('// Actual health functions with real FFRT; backend/IPC are explicit doubles.\n'+DECLARATIONS.replace('FFRT_DECLARATIONS','#include "ffrt.h"\n')+actual+NATIVE_MAIN)

if __name__=='__main__':unittest.main()
