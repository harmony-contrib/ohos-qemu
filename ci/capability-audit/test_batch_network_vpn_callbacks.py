"""Actual callback dispatch functions with bounded explicit FFRT/account/IPC doubles."""
from pathlib import Path
import base64
import json
import os
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT,body,compile_run

PROJECT='foundation/communication/netmanager_ext'
COMPONENT=ROOT/'patches/common'/PROJECT/'vpn_callback_dispatch'
FIXTURE=Path(__file__).with_name('fixtures')/'batch_network/vpn-callback-prepared.json'


def prepared(root):
    for name,encoded in json.loads(FIXTURE.read_text()).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
    return root/PROJECT/'services/vpnmanager'


class VpnCallbackTests(unittest.TestCase):
    def test_exact_dispatch_state_and_unknown_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root)
            subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            p=source/'include/networkvpn_service.h';fixed=p.read_bytes()
            self.assertEqual(fixed.count(b'virtual ~VpnConnStateCb();'),1)
            p.write_bytes(fixed.replace(b'virtual ~VpnConnStateCb();',b'~VpnConnStateCb() override;'))
            before=p.read_bytes()
            denied=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0);self.assertEqual(p.read_bytes(),before)
            p.write_bytes(fixed+b'// unknown\n');before=p.read_bytes()
            denied=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0);self.assertEqual(p.read_bytes(),before)

    def test_complete_predecessor_stack_accepts_only_complete_callback_followup(self):
        from test_connected_vpn_nullable import staged as connected_staged
        from test_batch_network_openvpn_session import prepared as session_prepared
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);connected_staged(root)
            base=ROOT/'patches/common'/PROJECT
            subprocess.run(['bash',str(base/'connected_vpn_nullable/apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            session_prepared(root);prepared(root)
            for name,encoded in json.loads(FIXTURE.with_name('vpn-callback-ancestor-files.json').read_text()).items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(encoded))
            for name in ['always_on_vpn','connected_vpn_nullable','openvpn_lifecycle','openvpn_session','vpn_callback_dispatch']:
                subprocess.run(['bash',str(base/name/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            target=root/PROJECT/'services/vpnmanager/src/net_vpn_impl.cpp'
            target.write_bytes(target.read_bytes()+b'// altered unaffected parent file\n')
            denied=subprocess.run(['bash',str(base/'openvpn_session/apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0)

    def test_actual_functions_reentry_epoch_owner_order_teardown_and_delivery_failures(self):
        declarations=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>
#define SUPPORT_SYSVPN 1
#define NETMGR_EXT_LOG_E(...) do{}while(0)
#define NETMGR_EXT_LOG_I(...) do{}while(0)
constexpr int NETMANAGER_EXT_SUCCESS=0,NETMANAGER_SUCCESS=0,ERR_OK=0;
constexpr int NETMANAGER_EXT_ERR_INTERNAL=2200003,NETMANAGER_EXT_ERR_OPERATION_FAILED=2203002,NETMANAGER_EXT_ERR_PARAMETER_ERROR=2200001,NETMANAGER_ERR_PARAMETER_INVALID=2200001,NETMANAGER_ERR_SYSTEM_INTERNAL=2200003;
constexpr size_t MAX_CALLBACK_COUNT=200;
constexpr int OPERATOR_REMOTE_DIE_DESTORY_VPN_START=5,OPERATOR_DESTORY_VPN_SUCCESS=7,OPERATOR_DESTORY_VPN_ABNORMAL=8,VPN_CONNECT_CODE_SUCCESS=0;
template<class T> struct sptr:std::shared_ptr<T>{using std::shared_ptr<T>::shared_ptr;sptr()=default;template<class U>sptr(const std::shared_ptr<U>& p):std::shared_ptr<T>(p){}T* GetRefPtr()const{return this->get();}template<class...A>static sptr<T> MakeSptr(A&&...a){return sptr<T>(new T(std::forward<A>(a)...));}};
template<class T>struct wptr:std::weak_ptr<T>{wptr(const sptr<T>& p):std::weak_ptr<T>(p){}sptr<T> promote()const{return this->lock();}};
struct IVpnEventCallback;
struct IRemoteObject {std::weak_ptr<IVpnEventCallback> callback;bool dead=false;bool IsObjectDead()const{return dead;}int adds=0,removes=0;bool RemoveDeathRecipient(const std::shared_ptr<int>&){++removes;return true;}};
template<class T>sptr<T> iface_cast(const sptr<IRemoteObject>& p){return std::dynamic_pointer_cast<T>(p->callback.lock());}
struct VpnState {std::string vpnIfName_,vpnIfAddr_,vpnId_,vpnPacketName_;bool isGlobalVpn_=true;std::vector<int> routes_;std::vector<std::string> dnsServers_;VpnState(std::string i,std::string a,std::string v,bool g,std::vector<int> r,std::vector<std::string> d):vpnIfName_(i),vpnIfAddr_(a),vpnId_(v),isGlobalVpn_(g),routes_(r),dnsServers_(d){}};
enum class VpnConnectState {VPN_DISCONNECTED,VPN_CONNECTED};
// The fixed product interface has an implicit, non-virtual destructor.
struct IVpnConnStateCb {virtual void OnVpnConnStateChanged(const VpnConnectState&,const sptr<VpnState>&)=0;virtual void SendConnStateChanged(const VpnConnectState&,int32_t,const std::string&)=0;virtual void OnMultiVpnConnStateChanged(const VpnConnectState&,const std::string&)=0;};
struct IVpnEventCallback {virtual~IVpnEventCallback()=default;sptr<IRemoteObject> remote=sptr<IRemoteObject>::MakeSptr();sptr<IRemoteObject> AsObject()const{return remote;}virtual int OnVpnStateChanged(bool,const sptr<VpnState>&)=0;virtual int OnMultiVpnStateChanged(bool,const std::string&,const std::string&)=0;virtual int OnVpnMultiUserSetUp()=0;};
thread_local int callingUid=20000001,callingPid=123;thread_local std::string callingOwner="owner.one";
struct IPCSkeleton {static int GetCallingUid(){return callingUid;}static int GetCallingPid(){return callingPid;}};
namespace AppExecFwk {namespace Constants {constexpr int UNSPECIFIED_USERID=-1;}}
std::atomic<int> foreground{100};bool accountFail=false,permissionAllowed=true;
namespace AccountSA {struct OsAccountManager {static int GetForegroundOsAccountLocalId(int& out){out=foreground.load();return accountFail?9:0;}static int GetOsAccountLocalIdFromUid(int uid,int& out){out=uid/200000;return accountFail?9:0;}};}
namespace Permission {const char*MANAGE_VPN="MANAGE_VPN";}
struct NetManagerPermission {static bool IsSystemCaller(){return true;}};
namespace ffrt {using shared_mutex=std::shared_mutex;bool reject=false;std::mutex tasksMutex;std::deque<std::function<void()>> tasks;struct queue {explicit queue(const char*){}void* submit_h(std::function<void()> task){std::lock_guard<std::mutex> lock(tasksMutex);if(reject)return nullptr;tasks.push_back(std::move(task));return reinterpret_cast<void*>(1);}};}
bool DrainOne(){std::function<void()> task;{std::lock_guard<std::mutex> lock(ffrt::tasksMutex);if(ffrt::tasks.empty())return false;task=std::move(ffrt::tasks.front());ffrt::tasks.pop_front();}task();return true;}
void Drain(){for(int i=0;i<1000 && DrainOne();++i){}}
struct SysVpnConfig {int value=17;};
struct MultiInfo {int userId=100;std::string ifName="vpn-tun";VpnConnectState vpnConnectState=VpnConnectState::VPN_DISCONNECTED;};
struct NetVpnImpl {int userId=100,destroys=0,destroyError=0;bool system=false;sptr<MultiInfo> multiVpnInfo_;int GetUserId(){return userId;}bool IsSystemVpn(){return system;}int GetConnectedSysVpnConfig(sptr<SysVpnConfig>& c){c=sptr<SysVpnConfig>::MakeSptr();return 0;}int Destroy(){++destroys;return destroyError;}};
struct VpnTrace {int result;};
struct NetworkVpnService:std::enable_shared_from_this<NetworkVpnService>{
 struct CallbackOrigin;struct CallbackDispatchState;
 CALLBACK_CLASS
 struct MultiVpnEventCallback {std::string bundleName;int userId;sptr<IVpnEventCallback> callback;};
 std::shared_ptr<CallbackDispatchState> callbackDispatch_;ffrt::shared_mutex netVpnMutex_,vpnEventCallbacksMutex_,multiVpnEventCallbacksMutex_;
 std::shared_ptr<NetVpnImpl> vpnObj_;std::map<std::string,std::shared_ptr<NetVpnImpl>> vpnObjMap_;
 std::vector<sptr<IVpnEventCallback>> vpnEventCallbacks_;std::vector<sptr<MultiVpnEventCallback>> multiVpnEventCallbacks_;
 std::shared_ptr<int> deathRecipient_=std::make_shared<int>(1);int publishes=0,traces=0;
 NetworkVpnService();~NetworkVpnService();
 std::shared_ptr<VpnConnStateCb> CreateConnectionCallback(const std::shared_ptr<NetVpnImpl>&,const std::string&,int32_t,const std::string&);
 bool RegisterCallbackEpoch(const sptr<IVpnEventCallback>&,bool,const std::string&);
 void QueueConnectionEvent(const std::shared_ptr<CallbackOrigin>&,const VpnConnectState&,const sptr<VpnState>&,int,int32_t=0);
 bool IsNeedNotify(const VpnConnectState&,const std::string&,int32_t);
 void PublishVpnConnectionStateEvent(const VpnConnectState&,int){++publishes;}
 void OnVpnMultiUserSetUp();void OnRemoteDied(const wptr<IRemoteObject>&);void RemoveALLClientDeathRecipient();
 int32_t SyncRegisterVpnEvent(const sptr<IVpnEventCallback>);int32_t SyncUnregisterVpnEvent(const sptr<IVpnEventCallback>);
 int32_t SyncRegisterMultiVpnEvent(const sptr<IVpnEventCallback>,const std::string&);int32_t SyncUnregisterMultiVpnEvent(const sptr<IVpnEventCallback>);
 bool IsSelfCall(){return false;}bool AddClientDeathRecipient(const sptr<IVpnEventCallback>& c){++c->remote->adds;return true;}void RemoveClientDeathRecipient(const sptr<IVpnEventCallback>& c){++c->remote->removes;}
 std::string GetBundleName(){return callingOwner;}
 int CheckIpcPermission(const std::string&){return permissionAllowed?0:201;}
 int CheckCurrentAccountType(int& user,std::vector<int>&){return AccountSA::OsAccountManager::GetOsAccountLocalIdFromUid(callingUid,user);}
 int GetConnectedSysVpnConfig(std::vector<sptr<SysVpnConfig>>&);
 int DestroyMultiVpn(const std::shared_ptr<NetVpnImpl>& object){int r=object->Destroy();if(!r){for(auto it=vpnObjMap_.begin();it!=vpnObjMap_.end();)if(it->second==object)it=vpnObjMap_.erase(it);else ++it;}return r;}
 VpnTrace CreateVpnTrace(std::string&,int,int r){return {r};}void ReportVpnTrace(const std::vector<VpnTrace>& v){traces+=static_cast<int>(v.size());}
};
'''
        cases=r'''
NetworkVpnService::NetworkVpnService():callbackDispatch_(std::make_shared<CallbackDispatchState>()){}
struct Client:IVpnEventCallback {std::vector<std::string> owners;std::vector<bool> states;std::vector<int> routes;std::function<void()> action;int result=0,multi=0,accounts=0;
 int OnVpnStateChanged(bool connected,const sptr<VpnState>& value)override{owners.push_back(value->vpnPacketName_);states.push_back(connected);routes=value->routes_;value->vpnPacketName_="tampered";value->routes_.clear();if(action)action();return result;}
 int OnMultiVpnStateChanged(bool,const std::string& owner,const std::string&)override{++multi;owners.push_back(owner);if(action)action();return result;}
 int OnVpnMultiUserSetUp()override{++accounts;if(action)action();return result;}
};
sptr<Client> NewClient(){auto c=sptr<Client>::MakeSptr();c->remote->callback=c;return c;}
sptr<VpnState> State(std::string id=""){return sptr<VpnState>::MakeSptr("tun0","10.0.0.2",id,true,std::vector<int>{1,2},std::vector<std::string>{"2001:db8::53"});}
void CheckInterfaceCallbackLifetime(const std::shared_ptr<NetworkVpnService>& service){
 static_assert(!std::has_virtual_destructor_v<IVpnConnStateCb>);
 static_assert(std::has_virtual_destructor_v<NetworkVpnService::VpnConnStateCb>);
 auto object=std::make_shared<NetVpnImpl>();
 auto concrete=service->CreateConnectionCallback(object,"pending.interface",100,"interface");assert(concrete);
 auto origin=service->callbackDispatch_->origins.back().lock();assert(origin);
 // A controller keeps the concrete make_shared control block when upcasting.
 std::shared_ptr<IVpnConnStateCb> controller=concrete;concrete.reset();
 std::promise<void> entered;auto started=entered.get_future();
 auto waiter=std::async(std::launch::async,[origin,&entered]{entered.set_value();return origin->WaitReady();});
 assert(started.wait_for(std::chrono::seconds(1))==std::future_status::ready);
 assert(waiter.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout);
 controller.reset();
 assert(waiter.wait_for(std::chrono::seconds(1))==std::future_status::ready && !waiter.get());
 assert(origin->phase.load()==NetworkVpnService::CallbackOrigin::CANCELLED);
}
int main(){
 auto service=std::make_shared<NetworkVpnService>();auto client=NewClient(),other=NewClient();auto object=std::make_shared<NetVpnImpl>();
 CheckInterfaceCallbackLifetime(service);
 assert(service->SyncRegisterVpnEvent(client)==0 && service->SyncRegisterVpnEvent(other)==0);assert(client->remote->adds==1 && other->remote->adds==1);Drain();
 auto callback=service->CreateConnectionCallback(object,"owner.one",100,"");assert(callback);Drain();
 // A pending setup decision cannot deliver a CONNECTED event before publication.
 auto input=State();callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,input);input->routes_.clear();
 auto worker=std::async(std::launch::async,[]{return DrainOne();});
 assert(worker.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout && client->states.empty());
 client->action=[&]{std::vector<sptr<SysVpnConfig>> output;assert(service->GetConnectedSysVpnConfig(output)==0 && output.size()==1);assert(service->SyncUnregisterVpnEvent(client)==0);assert(service->SyncRegisterVpnEvent(client)==0);};
 {std::unique_lock<ffrt::shared_mutex> lock(service->netVpnMutex_);service->vpnObj_=object;callback->Commit();}
 assert(worker.wait_for(std::chrono::seconds(1))==std::future_status::ready);worker.get();Drain();client->action={};
 assert(client->owners==std::vector<std::string>{"owner.one"} && other->owners==client->owners && other->routes==std::vector<int>({1,2}));
 // Old queued registration and a later new registration must not share epochs.
 callback->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,State());assert(service->SyncUnregisterVpnEvent(client)==0);assert(service->SyncRegisterVpnEvent(client)==0);Drain();
 assert(client->states.size()==1 && other->states.size()==2);
 callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());callback->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,State());Drain();
 assert(client->states.size()==3 && client->states[1] && !client->states[2]);
 // A worker's unrelated IPC identity cannot relabel origin data.
 callingUid=8888;callingPid=888;callingOwner="worker.wrong";callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());Drain();assert(client->owners.back()=="owner.one");
 callingUid=20000001;callingPid=123;callingOwner="owner.one";
 auto oldCount=client->states.size();callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());++service->callbackDispatch_->accountEpoch;foreground=101;foreground=100;Drain();assert(client->states.size()==oldCount);
 callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());auto nextObject=std::make_shared<NetVpnImpl>();auto next=service->CreateConnectionCallback(nextObject,"owner.two",100,"");service->vpnObj_=nextObject;next->Commit();Drain();assert(client->states.size()==oldCount);
 callback->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,State());next->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());Drain();assert(client->owners.back()=="owner.two" && client->states.size()==oldCount+1);
 // A different account registration cannot observe foreground owner payloads.
 callingUid=20200001;auto foreign=NewClient();assert(service->SyncRegisterVpnEvent(foreign)==0);callingUid=20000001;Drain();next->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());Drain();assert(foreign->states.empty());
 // Remote death is bound to registration UID/PID/owner, not worker identity or
 // a newer connection owned by a different process.
 callingUid=999;callingPid=999;service->OnRemoteDied(wptr<IRemoteObject>(client->remote));Drain();assert(nextObject->destroys==0 && !service->callbackDispatch_->Find(client,false));
 callingUid=20000001;callingPid=123;callingOwner="owner.two";auto ownerClient=NewClient();assert(service->SyncRegisterVpnEvent(ownerClient)==0);Drain();
 callingUid=999;callingPid=999;service->OnRemoteDied(wptr<IRemoteObject>(ownerClient->remote));assert(nextObject->destroys==1 && !service->vpnObj_ && service->traces==2);
 callingUid=20000001;callingPid=123;callingOwner="owner.one";
 auto multi=NewClient();assert(service->SyncRegisterMultiVpnEvent(multi,"listener.owner")==0);auto multiObject=std::make_shared<NetVpnImpl>();auto mc=service->CreateConnectionCallback(multiObject,"actual.vpn.owner",100,"vpn-id");mc->Commit();Drain();
 mc->OnMultiVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,"vpn-id");Drain();assert(multi->multi==1 && multi->owners.back()=="actual.vpn.owner");
 mc->OnMultiVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,"vpn-id");assert(service->SyncUnregisterMultiVpnEvent(multi)==0);Drain();assert(multi->multi==1);
 // Return-code failures remain explicit; delivery does not modify real state.
 auto dead=NewClient();dead->remote->dead=true;assert(service->SyncRegisterVpnEvent(dead)!=0 && dead->remote->removes==1);
 const auto failures=service->callbackDispatch_->failures.load();ffrt::reject=true;auto rejected=NewClient();assert(service->SyncRegisterVpnEvent(rejected)!=0 && rejected->remote->removes==1);assert(!service->CreateConnectionCallback(object,"x",100,"x"));
 mc->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("vpn-id"));assert(service->callbackDispatch_->failures.load()==failures+3);ffrt::reject=false;
 other->result=17;mc->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("vpn-id"));Drain();assert(service->callbackDispatch_->failures.load()==failures+4);other->result=0;
 service->OnVpnMultiUserSetUp();assert(service->SyncUnregisterVpnEvent(other)==0);Drain();assert(other->accounts==0);
 // The same native service can stop/restart live controllers without reviving
 // an old queue epoch, old listener or retired connection generation.
 const int beforeRestart=service->publishes;mc->SendConnStateChanged(VpnConnectState::VPN_CONNECTED,2,"vpn-id");
 service->callbackDispatch_->Stop();service->RemoveALLClientDeathRecipient();service->callbackDispatch_->Restart();
 auto restarted=NewClient();assert(service->SyncRegisterVpnEvent(restarted)==0);Drain();assert(service->publishes==beforeRestart && restarted->states.empty());
 mc->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("vpn-id"));Drain();assert(restarted->owners==std::vector<std::string>{"actual.vpn.owner"});
 callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State());Drain();assert(restarted->states.size()==1);
 // Pending worker and late callback both survive service destruction safely.
 auto pendingObject=std::make_shared<NetVpnImpl>();auto pending=service->CreateConnectionCallback(pendingObject,"pending",100,"pending");Drain();pending->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("pending"));
 auto waiting=std::async(std::launch::async,[]{return DrainOne();});assert(waiting.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout);
 service.reset();assert(waiting.wait_for(std::chrono::seconds(1))==std::future_status::ready);waiting.get();pending->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("pending"));Drain();
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root);text=(source/'src/networkvpn_service.cpp').read_text();header=(source/'include/networkvpn_service.h').read_text()
            a=header.index('    class VpnConnStateCb :');b=header.index('\n    class ReceiveMessage',a);declarations=declarations.replace(' CALLBACK_CLASS',header[a:b])
            a=text.index('namespace {\nffrt::queue &VpnExternalCallbackQueue()');b=text.index('NetworkVpnService::NetworkVpnService()',a);actual=text[a:b]
            for signature in ['NetworkVpnService::~NetworkVpnService()', 'bool NetworkVpnService::IsNeedNotify(', 'void NetworkVpnService::VpnConnStateCb::OnVpnConnStateChanged(', 'void NetworkVpnService::VpnConnStateCb::SendConnStateChanged(', 'void NetworkVpnService::VpnConnStateCb::OnMultiVpnConnStateChanged(', 'void NetworkVpnService::OnVpnMultiUserSetUp()', 'int32_t NetworkVpnService::SyncRegisterVpnEvent(', 'int32_t NetworkVpnService::SyncUnregisterVpnEvent(', 'int32_t NetworkVpnService::SyncRegisterMultiVpnEvent(', 'int32_t NetworkVpnService::SyncUnregisterMultiVpnEvent(', 'void NetworkVpnService::OnRemoteDied(', 'void NetworkVpnService::RemoveALLClientDeathRecipient()', 'int32_t NetworkVpnService::GetConnectedSysVpnConfig(']:actual+='\n'+body(text,signature)
            # Fixed IsNeedNotify uses the real inner-channel prefix guard.
            declarations+='#include <cstring>\nconstexpr const char *INNER_CHL_NAME="inner-chl";\n'
            native_output=os.environ.get('BATCH_NETWORK_CALLBACK_NATIVE_OUTPUT')
            if native_output:
                begin=declarations.index('namespace ffrt {using shared_mutex=')
                end=declarations.index('struct SysVpnConfig',begin)
                native_declarations=declarations[:begin]+'#include "ffrt.h"\n'+declarations[end:]
                native_cases=cases[:cases.index('int main(){')]+NATIVE_MAIN
                Path(native_output).write_text('// Actual prepared dispatch functions; real FFRT only.\n'
                    '// Account/IPC/backend objects remain explicit doubles; no guest VPN acceptance claim.\n'
                    +native_declarations+actual+native_cases)
            compile_run(declarations+actual+cases,root,extra=('-pthread',))


NATIVE_MAIN = r'''
void NativeFlush()
{
    auto done = std::make_shared<std::promise<void>>();
    auto future = done->get_future();
    auto handle = VpnExternalCallbackQueue().submit_h([done]() { done->set_value(); });
    assert(handle != nullptr);
    assert(future.wait_for(std::chrono::seconds(3)) == std::future_status::ready);
}
struct NativePause {
    std::shared_ptr<std::promise<void>> release = std::make_shared<std::promise<void>>();
    NativePause()
    {
        auto entered = std::make_shared<std::promise<void>>();
        auto ready = entered->get_future();
        auto gate = release->get_future().share();
        auto handle = VpnExternalCallbackQueue().submit_h([entered, gate]() { entered->set_value(); gate.wait(); });
        assert(handle != nullptr && ready.wait_for(std::chrono::seconds(3)) == std::future_status::ready);
    }
    void Resume() { release->set_value(); }
};
int main()
{
    auto service = std::make_shared<NetworkVpnService>();
    CheckInterfaceCallbackLifetime(service);
    auto client = NewClient();
    auto object = std::make_shared<NetVpnImpl>();
    assert(service->SyncRegisterVpnEvent(client) == 0);
    auto callback = service->CreateConnectionCallback(object, "real.ffrt.owner", 100, "");
    assert(callback);
    NativeFlush();
    callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State());
    // Real FFRT worker waits on the pending origin; setup never waits on it.
    client->action = [&]() {
        std::vector<sptr<SysVpnConfig>> output;
        assert(service->GetConnectedSysVpnConfig(output) == 0 && output.size() == 1);
        assert(service->SyncUnregisterVpnEvent(client) == 0);
        assert(service->SyncRegisterVpnEvent(client) == 0);
    };
    {
        std::unique_lock<ffrt::shared_mutex> lock(service->netVpnMutex_);
        service->vpnObj_ = object;
        callback->Commit();
    }
    NativeFlush();
    client->action = {};
    assert(client->owners == std::vector<std::string>{"real.ffrt.owner"});
    {
        NativePause pause;
        callback->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED, State());
        assert(service->SyncUnregisterVpnEvent(client) == 0);
        assert(service->SyncRegisterVpnEvent(client) == 0);
        pause.Resume();
    }
    NativeFlush();
    assert(client->states.size() == 1);
    auto nextObject = std::make_shared<NetVpnImpl>();
    std::shared_ptr<NetworkVpnService::VpnConnStateCb> next;
    {
        NativePause pause;
        callback->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State());
        next = service->CreateConnectionCallback(nextObject, "new.owner", 100, "");
        service->vpnObj_ = nextObject;
        next->Commit();
        pause.Resume();
    }
    NativeFlush();
    assert(client->states.size() == 1);
    next->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State());
    next->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED, State());
    NativeFlush();
    assert(client->states.size() == 3 && client->states[1] && !client->states[2] && client->owners.back() == "new.owner");
    {
        NativePause pause;
        next->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State());
        ++service->callbackDispatch_->accountEpoch;
        pause.Resume();
    }
    NativeFlush();
    assert(client->states.size() == 3);
    const int publications = service->publishes;
    auto restarted = NewClient();
    {
        NativePause pause;
        next->SendConnStateChanged(VpnConnectState::VPN_CONNECTED, 2, "");
        service->callbackDispatch_->Stop();
        service->RemoveALLClientDeathRecipient();
        service->callbackDispatch_->Restart();
        assert(service->SyncRegisterVpnEvent(restarted) == 0);
        pause.Resume();
    }
    NativeFlush();
    assert(service->publishes == publications && restarted->states.empty());
    next->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State());
    NativeFlush();
    assert(restarted->owners == std::vector<std::string>{"new.owner"});
    auto pendingObject = std::make_shared<NetVpnImpl>();
    auto pending = service->CreateConnectionCallback(pendingObject, "pending", 100, "pending");
    NativeFlush();
    pending->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State("pending"));
    service.reset();
    NativeFlush();
    pending->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED, State("pending"));
    NativeFlush();
    return 0;
}
'''

if __name__=='__main__':unittest.main()
