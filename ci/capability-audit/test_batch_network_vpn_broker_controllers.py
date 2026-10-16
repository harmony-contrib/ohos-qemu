"""Actual updated service/controller bodies, explicit host platform doubles."""
from pathlib import Path
import ast
import os
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT,EXT,BASE,body,compile_run
from test_batch_network_vpn_broker import prepared


def literals(module,method):
    parsed=ast.parse(Path(module.__file__).read_text())
    target=next(n for n in ast.walk(parsed) if isinstance(n,ast.FunctionDef) and n.name==method)
    return {n.targets[0].id:ast.literal_eval(n.value) for n in target.body
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Constant)}


class BrokerControllerTests(unittest.TestCase):
    def test_actual_negotiated_snapshot_claim_reconnect_and_cleanup_errors(self):
        import test_batch_network_openvpn_session as previous
        values=literals(previous,'test_real_json_controller_atomic_dual_stack_and_session_lifecycle')
        declarations=values['declarations'].replace('#include <cmath>', '#include <cmath>\n#include <chrono>').replace('SessionRole TestCallerRole(pid_t,pid_t){return role;}',
            'std::string currentStart="111";bool worker=false;std::string TestProcessStart(pid_t){return currentStart;}bool TestWorkerProcess(pid_t){return worker;}SessionRole TestCallerRole(pid_t,pid_t,const std::string &expected={}){return expected.empty() || expected==currentStart?role:SessionRole::Invalid;}')
        declarations=declarations.replace('#define Executable TestExecutable','#define Executable TestExecutable\n#define ProcessStart TestProcessStart\n#define WorkerProcess TestWorkerProcess')
        declarations=declarations.replace('bool qemuConfigured_=false,qemuTunReady_=false;',
            'std::chrono::steady_clock::time_point qemuClaimDeadline_=std::chrono::steady_clock::now()+std::chrono::seconds(10);int qemuBroker_=-1;std::string qemuBrokerStart_;bool qemuStoppingRequested_=false;std::string qemuWorkerStart_;bool qemuNeedsCleanup_=false,qemuWorkerStopped_=false;bool qemuConfigured_=false,qemuTunReady_=false;')
        cases=values['cases'].replace('&& !ctl.HasQemuSession() && ctl.qemuSupervisor_==-1 && ctl.state==5',
            '&& ctl.HasQemuSession() && !ctl.qemuNeedsCleanup_ && ctl.state==5')
        cases=cases.replace('ctl.HasQemuSession());\n ctl.destroyResult=0;',
            'ctl.HasQemuSession() && ctl.state==5 && ctl.qemuNeedsCleanup_);\n ctl.destroyResult=0;')
        at=cases.rindex('\n}')
        cases=cases[:at]+r'''
 OpenvpnCtl fresh;OhosOpenvpn::worker=false;OhosOpenvpn::currentStart="new-worker";
 assert(fresh.HandleQemuStage("{\"claim\":{}}",0,700)==202 && fresh.qemuSupervisor_==-1);
 OhosOpenvpn::worker=true;assert(fresh.HandleQemuStage("{\"claim\":{\"unexpected\":1}}",0,700)==202);
 assert(fresh.HandleQemuStage("{\"claim\":{}}",0,700)==0 && fresh.qemuSupervisor_==700 && fresh.qemuWorkerStart_=="new-worker");
 role=SessionRole::Bridge;assert(fresh.HandleQemuStage(NetworkJson(config),0,701)==0);
 OhosOpenvpn::currentStart="recycled-pid";assert(fresh.HandleQemuStage("{\"setupVpnTun\":{}}",0,701)==202);
 OhosOpenvpn::currentStart="new-worker";fresh.setupResult=2200998;
 assert(fresh.HandleQemuStage("{\"setupVpnTun\":{}}",0,701)==2200998 && !fresh.qemuTunReady_);
 fresh.qemuWorkerStopped_=true;assert(fresh.HandleQemuStage("{\"claim\":{}}",0,700)==202);
'''+cases[at:]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ('bool QemuInteger(', 'bool QemuString(', 'bool QemuAddress(',
                'int32_t OpenvpnCtl::GetQemuSession(', 'int32_t OpenvpnCtl::UpdateQemuConfig(', 'int32_t OpenvpnCtl::HandleQemuStage('))
            obj=root/'cJSON.o';subprocess.run([os.environ.get('CC','clang'),'-std=c11','-fsanitize=address,undefined','-c',str(previous.CJSON/'cJSON.c'),'-o',str(obj)],check=True,capture_output=True)
            compile_run(declarations+actual+cases,root,extra=['-I',str(previous.CJSON),str(obj)])

    def test_actual_owner_envelope_keeps_all_fields_together(self):
        declarations=r'''
#include "broker_protocol.h"
#include <cassert>
#include <memory>
namespace Base64 {std::string Decode(const std::string &value){return value;}}
struct MultiInfo{int callingUid=23,userId=100;std::string bundleName="owner.one",vpnId="one",ifName="multitun-vpn1";};
struct Config{std::string ovpnConfig_="client\nfirst-real-config\n",askpass_="first-password";};
struct OpenvpnCtl{std::shared_ptr<MultiInfo>multiVpnInfo_=std::make_shared<MultiInfo>();std::shared_ptr<Config>openvpnConfig_=std::make_shared<Config>();std::string qemuGeneration_=std::string(32,'a');std::string QemuBrokerMessage(bool)const;};
'''
        cases=r'''
int main(){OpenvpnCtl first,second;second.multiVpnInfo_->callingUid=45;second.multiVpnInfo_->bundleName="owner.two";
 second.multiVpnInfo_->vpnId="two";second.multiVpnInfo_->ifName="multitun-vpn2";second.qemuGeneration_=std::string(32,'b');
 second.openvpnConfig_->ovpnConfig_="client\nsecond-real-config\n";second.openvpnConfig_->askpass_="second-password";
 OhosOpenvpn::BrokerCommand one,two;assert(OhosOpenvpn::DecodeBroker(first.QemuBrokerMessage(true),one));assert(OhosOpenvpn::DecodeBroker(second.QemuBrokerMessage(true),two));
 assert(one.owner.uid==23 && two.owner.uid==45 && one.owner.bundle=="owner.one" && two.owner.bundle=="owner.two");
 assert(one.session.profile.find("first-real-config")!=std::string::npos && two.session.password=="second-password");
 assert(one.session.token!=two.session.token && one.interfaceName!=two.interfaceName);
 assert(OhosOpenvpn::DecodeBroker(first.QemuBrokerMessage(false),one) && !one.start && one.session.password.empty() && one.owner.vpnId=="one");
 first.multiVpnInfo_->ifName="../tun";assert(first.QemuBrokerMessage(true).empty());first.multiVpnInfo_.reset();assert(first.QemuBrokerMessage(true).empty());}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            compile_run(declarations+body(text,'std::string OpenvpnCtl::QemuBrokerMessage(')+cases,root)

    def test_actual_setup_every_failure_and_destroy_best_effort_retry(self):
        declarations=r'''
#include "broker_protocol.h"
#include <cassert>
#include <cstring>
#include <memory>
#include <string>
#include <vector>
#define SUPPORT_SYSVPN 1
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_W(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
constexpr int NETMANAGER_EXT_SUCCESS=0,NETMANAGER_SUCCESS=0,NETMANAGER_EXT_ERR_INTERNAL=2200003;
enum class VpnType{OPENVPN,IPSEC};
enum class VpnConnectState{VPN_DISCONNECTED,VPN_CONNECTED};
enum class VpnEventType{TYPE_LEGACY,TYPE_EXTENDED};
enum class VpnEventErrorType{ERROR_INTERNAL_ERROR,ERROR_REG_NET_SUPPLIER_ERROR,ERROR_UPDATE_SUPPLIER_INFO_ERROR,ERROR_UPDATE_NETLINK_INFO_ERROR,ERROR_SET_APP_UID_RULE_ERROR};
struct VpnHisysEvent{static void SendFaultEventConnSetting(VpnEventType,VpnEventErrorType,const char*){}static void SendFaultEventConnDestroy(VpnEventType,VpnEventErrorType,const char*){}};
struct INetAddr{std::string address_;};
struct Route{struct Addr{std::string address_;int prefixlen_=24;}destination_,gateway_;std::string iface_;bool isExcludedRoute_=false;};
struct VpnConfig{std::vector<INetAddr>addresses_{{"10.8.0.2"}};std::vector<Route>routes_{Route{},Route{}};};
struct SysConfig{VpnType vpnType_=VpnType::OPENVPN;};
struct Supplier{bool isAvailable_=false;};
int stage=0,failAt=0;bool installed=true;bool Step(){++stage;return stage!=failAt;}
int TestAccess(const char*,int){return installed?0:-1;}
#define access TestAccess
struct NetConnClient{int updateResult=0,unregisterResult=0,updates=0,unregisters=0;static NetConnClient& GetInstance(){static NetConnClient v;return v;}int UpdateNetSupplierInfo(int,const std::shared_ptr<Supplier>&){++updates;return updateResult;}int UnregisterNetSupplier(int){++unregisters;return unregisterResult;}};
struct NetsysController{int addResult=0,delResult=0,routeResult=0,upResult=0;int adds=0,dels=0,routes=0,ups=0;std::vector<int>netIds;static NetsysController&GetInstance(){static NetsysController v;return v;}int NetworkAddUids(int id,const std::vector<int>&,const std::vector<int>&,int){++adds;netIds.push_back(id);return addResult;}int NetworkDelUids(int id,const std::vector<int>&,const std::vector<int>&,int){++dels;netIds.push_back(id);return delResult;}int NetworkRemoveRoute(int id,const std::string&,const std::string&,const std::string&,bool){++routes;netIds.push_back(id);return routeResult;}int UpdateVpnRules(int,const std::vector<std::string>&,bool){++ups;return upResult;}};
struct NetVpnImpl{
 std::shared_ptr<VpnConfig>vpnConfig_=std::make_shared<VpnConfig>();std::shared_ptr<SysConfig>config=std::make_shared<SysConfig>();std::shared_ptr<Supplier>netSupplierInfo_=std::make_shared<Supplier>();
 int netSupplierId_=0,netId_=0,priorityId_=0;bool isInternalChannel_=false,isVpnConnecting_=false;std::vector<int>beginUids_,endUids_;std::string interfaceName="multitun-vpn1";int notifications=0;
 bool IsInternalVpn(){return false;}bool IsSystemVpn(){return true;}std::shared_ptr<SysConfig>GetSysVpnConfig(){return config;}std::string GetInterfaceName(){return interfaceName;}
 bool RegisterNetSupplier(NetConnClient&,bool){if(!Step())return false;netSupplierId_=42;return true;}
 bool UpdateNetSupplierInfo(NetConnClient&,bool);bool UpdateNetLinkInfo(){return Step();}
 int SetNetId(const std::string&,VpnEventType,NetConnClient&){if(!Step())return 2200998;netId_=101;return 0;}
 int GetVpnInterffaceToId(const std::string&){return 1;}void SetAllUidRanges(){beginUids_={23};endUids_={23};}
 void NotifyConnectState(VpnConnectState){++notifications;}void AdjustRouteInfo(Route& route){route.iface_=interfaceName;}
 bool UnregisterNetSupplier(NetConnClient&);bool DelNetLinkInfo(NetConnClient&);int ProcessUpRules(bool);int SetUp(bool=false);int Destroy();
};
'''
        cases=r'''
int main(){auto &native=NetsysController::GetInstance();auto &client=NetConnClient::GetInstance();
 // The supplier-info stage uses its actual return value; link/id methods are
 // explicit platform doubles, with the real SetUp control flow under test.
 for(int failure:{1,2,3}){stage=0;failAt=failure;NetVpnImpl value;assert(value.SetUp()==2200003 && !value.isVpnConnecting_);}
 failAt=0;stage=0;client.updateResult=2200997;{NetVpnImpl value;assert(value.SetUp()==2200003);}client.updateResult=0;
 native.addResult=2200996;{NetVpnImpl value;assert(value.SetUp()==2200003 && !value.isVpnConnecting_);}native.addResult=0;
 for(auto address:{"10.8.0.2","2001:db8::2"}){NetVpnImpl value;value.vpnConfig_->addresses_[0].address_=address;native.upResult=2200995;const int ups=native.ups;assert(value.SetUp()==0 && value.isVpnConnecting_ && native.ups==ups && value.notifications==0);}
 native.upResult=2200995;{NetVpnImpl value;value.config->vpnType_=VpnType::IPSEC;assert(value.SetUp()==2200995 && !value.isVpnConnecting_);}native.upResult=0;
 // Failure must propagate while all later cleanup stages still run. No retry
 // may delete a different owner's netId or publish a CONNECTED transition.
 for(int failure:{0,1,2,3,4}){
  native.delResult=failure==1?9:0;native.routeResult=failure==2?8:0;client.updateResult=failure==3?7:0;client.unregisterResult=failure==4?6:0;
  NetVpnImpl first,second;first.netId_=101;first.netSupplierId_=42;first.isVpnConnecting_=true;second.netId_=202;second.netSupplierId_=84;
  native.netIds.clear();const int unregisters=client.unregisters;const int routes=native.routes;
  assert(first.Destroy()==(failure?2200003:0));assert(!first.isVpnConnecting_ && second.netId_==202 && second.netSupplierId_==84);
  assert(client.unregisters==unregisters+1 && native.routes==routes+2);
  for(int id:native.netIds)assert(id==101);
  native.delResult=native.routeResult=client.updateResult=client.unregisterResult=0;
  assert(first.Destroy()==0 && first.netId_==0 && first.netSupplierId_==0);
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/net_vpn_impl.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ['int32_t NetVpnImpl::SetUp(', 'int32_t NetVpnImpl::Destroy(', 'int32_t NetVpnImpl::ProcessUpRules(', 'bool NetVpnImpl::UpdateNetSupplierInfo(', 'bool NetVpnImpl::UnregisterNetSupplier(', 'bool NetVpnImpl::DelNetLinkInfo('])
            compile_run(declarations+actual+cases,root)

    def test_actual_native_update_per_owner_stop_error_and_ambiguous_start_rollback(self):
        declarations=r'''
#include "broker_protocol.h"
#include <cassert>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#define OHOS_QEMU_OPENVPN 1
#define UNITTEST_FORBID_FFRT 1
#define NETNATIVE_LOGE(...) ((void)0)
constexpr int NETMANAGER_ERROR=-1,START=0;
namespace NetManagerStandard {constexpr int NETMANAGER_SUCCESS=0;}
constexpr int NETMANAGER_SUCCESS=0;
enum class SysVpnStageCode{VPN_STAGE_OPENVPN_RESTART,VPN_STAGE_OPENVPN_STOP,OTHER};
namespace NetsysNative{using SysVpnStageCode=::SysVpnStageCode;}
std::deque<std::string>replies;std::vector<std::thread>servers;std::mutex logMutex;std::vector<OhosOpenvpn::BrokerCommand>requests;
int serviceCalls=0,serviceResult=0,connections=0;bool installed=true;
int TestAccess(const char *path,int){assert(std::string(path)=="/system/bin/qemu_openvpn_service");return installed?0:-1;}
#define access TestAccess
int ServiceControl(const char *name,int action){assert(std::string(name)=="qemu_openvpn" && action==START);++serviceCalls;return serviceResult;}
namespace OhosOpenvpn{
std::string TestProcessStart(pid_t pid){return pid==123?"1000":"";}
int TestConnectBroker(pid_t &pid){++connections;assert(!replies.empty());auto reply=replies.front();replies.pop_front();if(reply=="__CONNECT_FAIL__")return -1;int sockets[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0);pid=123;
 servers.emplace_back([fd=sockets[1],reply]{std::string wire;assert(ReadFrame(fd,wire));BrokerCommand command;assert(DecodeBroker(wire,command));{std::lock_guard<std::mutex>lock(logMutex);requests.push_back(command);}if(reply!="__CLOSE__")assert(SendFrame(fd,reply=="0" && command.start?StartReply(234,"2000"):reply));close(fd);});return sockets[0];}
}
#define ConnectBroker TestConnectBroker
#define ProcessStart TestProcessStart
struct MultiVpnManager{
 std::map<std::string,std::string>bindings;int bindResult=0,binds=0,unbinds=0;
 static MultiVpnManager &GetInstance(){static MultiVpnManager value;return value;}
 bool HasQemuSession(const std::string &token){return bindings.count(token);}
 bool recovery=false,canStart=true;bool QemuRecoveryReady(const OhosOpenvpn::BrokerCommand&){return recovery;}bool QemuCanStartBroker(){return canStart;}
 int BindQemuSession(const OhosOpenvpn::BrokerCommand &command,int broker,const std::string &start,int worker,const std::string &workerStart){assert(broker==123 && start=="1000" && worker==234 && workerStart=="2000");++binds;if(!bindResult)bindings.emplace(command.session.token,command.interfaceName);return bindResult;}
 void UnbindQemuSession(const std::string &token){++unbinds;bindings.erase(token);}
};
struct SystemVpnWrapper{bool vpnFfrtQueue_=true,isIpSecAccess_=true;bool PrepareUpdate(SysVpnStageCode,const std::string&){return false;}void ExecuteUpdate(SysVpnStageCode,const std::string&){}int32_t Update(NetsysNative::SysVpnStageCode,const std::string&);};
void Joined(){for(auto &server:servers)server.join();servers.clear();assert(replies.empty());}
'''
        cases=r'''
int main(){using namespace OhosOpenvpn;SystemVpnWrapper native;auto &manager=MultiVpnManager::GetInstance();BrokerCommand one;one.start=true;one.owner={23,100,"first.owner","one"};one.interfaceName="multitun-vpn1";one.session={std::string(32,'a'),"client\nactual-profile\n","first-secret"};
 auto two=one;two.owner={45,100,"second.owner","two"};two.interfaceName="multitun-vpn2";two.session.token=std::string(32,'b');
 replies={"0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(one))==0);Joined();
 replies={"0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(two))==0);Joined();assert(manager.bindings.size()==2 && serviceCalls==0);
 const int before=connections;assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(one))==-1 && connections==before);assert(manager.bindings.size()==2);
 auto fresh=one;fresh.session.token=std::string(32,'c');fresh.owner.vpnId="fresh";fresh.interfaceName="multitun-vpn3";
 replies={"114"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==-1);Joined();assert(requests.back().start && manager.bindings.size()==2);
 replies={"__CLOSE__","0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==-1);Joined();assert(!requests.back().start && requests.back().session.token==fresh.session.token && requests.back().owner==fresh.owner && manager.bindings.size()==2);
 manager.bindResult=-1;replies={"0","0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==-1);Joined();manager.bindResult=0;
 auto stop=one;stop.start=false;stop.session.profile.clear();stop.session.password.clear();
 replies={"5"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP,EncodeBroker(stop))==-1);Joined();assert(manager.bindings.size()==2 && manager.unbinds==0);
 replies={"0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP,EncodeBroker(stop))==0);Joined();assert(manager.bindings.size()==1 && manager.bindings.count(two.session.token));
 assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP,EncodeBroker(two))==-1);
 replies={"__CONNECT_FAIL__","0"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==0);Joined();assert(serviceCalls==1 && manager.bindings.size()==2);
 fresh.session.token=std::string(32,'d');fresh.interfaceName="multitun-vpn4";installed=false;replies={"__CONNECT_FAIL__"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==-1);Joined();assert(serviceCalls==1);
 // Broker-death recovery starts a cleanup broker only after the native
 // binding's owner/starttime/group checks succeed (tested separately).
 installed=true;manager.recovery=true;manager.canStart=false;replies={"__CONNECT_FAIL__"};auto stopTwo=two;stopTwo.start=false;stopTwo.session.profile.clear();stopTwo.session.password.clear();assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP,EncodeBroker(stopTwo))==-1);Joined();
 manager.canStart=true;replies={"__CONNECT_FAIL__","2"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP,EncodeBroker(stopTwo))==0);Joined();assert(!manager.bindings.count(two.session.token));manager.recovery=false;
 installed=true;serviceResult=1;replies={"__CONNECT_FAIL__"};assert(native.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART,EncodeBroker(fresh))==-1);Joined();assert(serviceCalls==3);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/BASE/'services/netmanagernative/src/netsys/system_vpn_wrapper.cpp').read_text()
            compile_run(declarations+body(text,'int32_t SystemVpnWrapper::Update(')+cases,root,extra=['-pthread'])

    def test_actual_native_binding_owner_and_dead_group_recovery_barrier(self):
        declarations=r'''
#include "broker_protocol.h"
#include <cassert>
#include <map>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <sys/wait.h>
namespace OhosOpenvpn{
std::map<pid_t,std::string>processes;std::map<pid_t,pid_t>parents;
std::string TestProcessStart(pid_t pid){return processes[pid];}pid_t TestParent(pid_t pid){return parents[pid];}bool TestExecutable(pid_t,const char*){return true;}
}
#define ProcessStart TestProcessStart
#define Parent TestParent
#define Executable TestExecutable
constexpr int NETMANAGER_ERROR=-1,NETMANAGER_SUCCESS=0,MAX_UNIX_SOCKET_CLIENT=5;
int GetControlSocket(const char*){return -1;}
struct MultiVpnManager:std::enable_shared_from_this<MultiVpnManager>{
 BINDING_TYPE
 std::mutex mutex_;std::unordered_map<std::string,QemuBinding>qemuBindings_;bool qemuListening_=true;
 void StartQemuSocketListen(int){}
 int BindQemuSession(const OhosOpenvpn::BrokerCommand&,int,const std::string&,int,const std::string&);
 bool HasQemuSession(const std::string&);void UnbindQemuSession(const std::string&);bool QemuRecoveryReady(const OhosOpenvpn::BrokerCommand&);bool QemuCanStartBroker();
};
pid_t Worker(){const pid_t child=fork();assert(child>=0);if(child==0){alarm(10);assert(setpgid(0,0)==0);for(;;)pause();}assert(setpgid(child,child)==0);return child;}
void Finish(pid_t child){assert(kill(-child,SIGKILL)==0);int status=0;while(waitpid(child,&status,0)<0)assert(errno==EINTR);}
'''
        cases=r'''
int main(){using namespace OhosOpenvpn;auto native=std::make_shared<MultiVpnManager>();const pid_t first=Worker(),second=Worker();
 processes[1234]="broker-old";processes[first]="worker-first";processes[second]="worker-second";parents[first]=parents[second]=1234;
 BrokerCommand one;one.start=true;one.owner={23,100,"first.owner","one"};one.interfaceName="multitun-vpn1";one.session={std::string(32,'a'),"client\nactual\n","first-secret"};
 auto two=one;two.owner={45,100,"second.owner","two"};two.interfaceName="multitun-vpn2";two.session.token=std::string(32,'b');
 assert(native->BindQemuSession(one,1234,"broker-old",first,"worker-first")==0);assert(native->BindQemuSession(two,1234,"broker-old",second,"worker-second")==0);
 assert(native->BindQemuSession(one,1234,"broker-old",first,"worker-first")==-1);
 auto stop=one;stop.start=false;stop.session.profile.clear();stop.session.password.clear();assert(!native->QemuRecoveryReady(stop));
 processes[1234].clear();processes[first].clear();assert(!native->QemuRecoveryReady(stop)); // PID read alone cannot prove group exit
 Finish(first);assert(native->QemuRecoveryReady(stop) && !native->QemuCanStartBroker());
 auto foreign=stop;foreign.owner=two.owner;assert(!native->QemuRecoveryReady(foreign));foreign=stop;foreign.interfaceName=two.interfaceName;assert(!native->QemuRecoveryReady(foreign));
 Finish(second);processes[second].clear();assert(native->QemuCanStartBroker());
 native->UnbindQemuSession(one.session.token);assert(!native->HasQemuSession(one.session.token) && native->HasQemuSession(two.session.token));
 // A recycled worker PID never authenticates against the stored starttime.
 processes[first]="recycled";parents[first]=1234;assert(native->BindQemuSession(one,1234,"broker-old",first,"worker-first")==-1);
 processes[1234]="broker-new";processes[first]="worker-new";parents[first]=1234;native->qemuListening_=false;
 assert(native->BindQemuSession(one,1234,"broker-new",first,"worker-new")==-1); // missing init FD is a real error
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);directory=root/BASE/'services/netmanagernative'
            text=(directory/'src/manager/multi_vpn_manager.cpp').read_text();header=(directory/'include/manager/multi_vpn_manager.h').read_text()
            a=header.index('    struct QemuBinding {');b=header.index('\n    };',a)+7;declarations=declarations.replace(' BINDING_TYPE',header[a:b])
            actual='\n'.join(body(text,sig) for sig in ['int32_t MultiVpnManager::BindQemuSession(', 'bool MultiVpnManager::HasQemuSession(', 'void MultiVpnManager::UnbindQemuSession(', 'bool MultiVpnManager::QemuRecoveryReady(', 'bool MultiVpnManager::QemuCanStartBroker('])
            compile_run(declarations+actual+cases,root,extra=['-pthread'])

    def test_actual_getter_and_health_require_live_broker_and_worker_generations(self):
        declarations=r'''
#include "session_contract.h"
#include <cassert>
#include <chrono>
#include <map>
namespace OhosOpenvpn{std::map<pid_t,std::string>starts;std::string TestProcessStart(pid_t pid){return starts[pid];}}
#define ProcessStart TestProcessStart
constexpr int OPENVPN_STATE_CONNECTED=4;
struct OpenvpnCtl{int openvpnState_=4,qemuSupervisor_=23,qemuBroker_=24;std::string qemuGeneration_=std::string(32,'a'),qemuWorkerStart_="worker",qemuBrokerStart_="broker";bool qemuWorkerStopped_=false,qemuStoppingRequested_=false;std::chrono::steady_clock::time_point qemuClaimDeadline_=std::chrono::steady_clock::now()+std::chrono::seconds(10);bool HasQemuSession()const{return !qemuGeneration_.empty();}bool IsOpenvpnConnected()const;bool QemuNeedsRecovery()const;};
'''
        cases=r'''
int main(){using namespace OhosOpenvpn;starts[23]="worker";starts[24]="broker";OpenvpnCtl value;assert(value.IsOpenvpnConnected() && !value.QemuNeedsRecovery());
 starts[23]="recycled-pid";assert(!value.IsOpenvpnConnected() && value.QemuNeedsRecovery());starts[23]="worker";
 starts[24].clear();assert(!value.IsOpenvpnConnected() && value.QemuNeedsRecovery());starts[24]="broker";
 value.qemuStoppingRequested_=true;assert(value.QemuNeedsRecovery());value.qemuStoppingRequested_=false;
 value.qemuWorkerStopped_=true;assert(!value.IsOpenvpnConnected() && value.QemuNeedsRecovery());value.qemuWorkerStopped_=false;
 value.qemuSupervisor_=-1;assert(!value.IsOpenvpnConnected() && !value.QemuNeedsRecovery());value.qemuClaimDeadline_=std::chrono::steady_clock::now()-std::chrono::seconds(1);assert(value.QemuNeedsRecovery());
 value.qemuGeneration_.clear();assert(value.IsOpenvpnConnected() && !value.QemuNeedsRecovery());}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            compile_run(declarations+body(text,'bool OpenvpnCtl::IsOpenvpnConnected() const')+body(text,'bool OpenvpnCtl::QemuNeedsRecovery() const')+cases,root)

    def test_actual_link_update_return_and_controller_cleanup_retry(self):
        import test_batch_network_openvpn_session as previous
        values=literals(previous,'test_real_base_dns_families_and_route_prefix_boundaries')
        declarations=values['declarations'].replace('int calls=0;', 'int calls=0,result=0;').replace('void UpdateNetLinkInfo(int,sptr<NetLinkInfo> value){last=value;++calls;}', 'int UpdateNetLinkInfo(int,sptr<NetLinkInfo> value){last=value;++calls;return result;}')
        declarations+='\nconstexpr int NETMANAGER_SUCCESS=0;\n'
        cases=values['cases'];a=cases.rindex('\n}');cases=cases[:a]+'\n ctl.vpnConfig_->dnsAddresses_={"192.0.2.53"};center.result=2200999;assert(!ctl.UpdateNetLinkInfo());\n'+cases[a:]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/net_vpn_impl.cpp').read_text()
            compile_run(declarations+body(text,'bool NetVpnImpl::UpdateNetLinkInfo(')+body(text,'void NetVpnImpl::AdjustRouteInfo(')+cases,root)
        declarations=r'''
#include "broker_protocol.h"
#include <cassert>
#include <cstdint>
#include <memory>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
constexpr int NETMANAGER_EXT_SUCCESS=0,NETMANAGER_EXT_ERR_INTERNAL=2200003,NETMANAGER_EXT_ERR_PARAMETER_ERROR=2200001,OPENVPN_STATE_DISCONNECTED=5;
namespace Base64{std::string Decode(const std::string&value){return value;}}
struct MultiInfo{int callingUid=23,userId=100;std::string bundleName="first.owner",vpnId="one",ifName="multitun-vpn1";bool isVpnExtCall=true;};
struct Config{std::string ovpnConfig_="client\nactual-profile\n",askpass_="secret";};
enum class SysVpnStageCode{VPN_STAGE_OPENVPN_STOP,VPN_STAGE_SET_VPN_CALL_MODE};
struct NetsysController{int stopResult=0,modeResult=0,stops=0;std::vector<std::string>tokens;static NetsysController&GetInstance(){static NetsysController v;return v;}int ProcessVpnStage(SysVpnStageCode stage,const std::string&message){if(stage==SysVpnStageCode::VPN_STAGE_SET_VPN_CALL_MODE){assert(message=="0");return modeResult;}OhosOpenvpn::BrokerCommand command;assert(OhosOpenvpn::DecodeBroker(message,command) && !command.start);tokens.push_back(command.session.token);++stops;return stopResult;}};
struct MultiVpnHelper{int deletes=0;static MultiVpnHelper&GetInstance(){static MultiVpnHelper v;return v;}int DelMultiVpnInfo(const std::shared_ptr<MultiInfo>&){++deletes;return 0;}};
struct NetVpnImpl{int result=0,destroys=0;int Destroy(){++destroys;return result;}};
struct OpenvpnCtl:NetVpnImpl{std::shared_ptr<MultiInfo>multiVpnInfo_=std::make_shared<MultiInfo>();std::shared_ptr<Config>openvpnConfig_=std::make_shared<Config>();std::string qemuGeneration_=std::string(32,'a'),qemuWorkerStart_="worker",qemuBrokerStart_="broker";int qemuSupervisor_=23,qemuBroker_=24,state=4;bool qemuNeedsCleanup_=true,qemuWorkerStopped_=false,qemuStoppingRequested_=false,qemuConfigured_=true,qemuTunReady_=true;bool HasQemuSession()const{return !qemuGeneration_.empty();}void UpdateOpenvpnState(int value){state=value;}std::string QemuBrokerMessage(bool)const;int StopOpenvpn();int Destroy();};
'''
        cases=r'''
int main(){auto &native=NetsysController::GetInstance();OpenvpnCtl first,second;second.qemuGeneration_=std::string(32,'b');
 native.stopResult=9;assert(first.Destroy()==2200003 && first.state==5 && first.HasQemuSession() && first.qemuStoppingRequested_ && !first.qemuNeedsCleanup_);
 assert(second.state==4 && second.HasQemuSession() && second.destroys==0);
 native.stopResult=0;native.modeResult=8;assert(first.Destroy()==8 && first.HasQemuSession() && first.qemuWorkerStopped_);
 const int stops=native.stops;native.modeResult=0;assert(first.Destroy()==0 && !first.HasQemuSession() && native.stops==stops);
 second.result=2200998;assert(second.Destroy()==2200998 && second.HasQemuSession() && second.qemuNeedsCleanup_ && second.qemuWorkerStopped_);
 const int secondStops=native.stops;second.result=0;assert(second.Destroy()==0 && !second.HasQemuSession() && native.stops==secondStops);
 assert(native.tokens==std::vector<std::string>({std::string(32,'a'),std::string(32,'a'),std::string(32,'b')}));
 OpenvpnCtl pending;pending.qemuNeedsCleanup_=false;assert(pending.Destroy()==0 && pending.destroys==0 && !pending.HasQemuSession());}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/EXT/'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ['std::string OpenvpnCtl::QemuBrokerMessage(', 'int32_t OpenvpnCtl::StopOpenvpn()', 'int32_t OpenvpnCtl::Destroy()'])
            compile_run(declarations+actual+cases,root)

    def test_actual_proc_parent_parser_accepts_real_init_and_rejects_invalid_pid(self):
        from test_batch_network_openvpn_lifecycle import HEADERS
        text=(HEADERS/'session_contract.h').read_text();actual=body(text,'inline pid_t Parent(')
        actual=actual.replace('inline pid_t Parent(', 'pid_t ParseActualParent(').replace('std::ifstream input("/proc/" + std::to_string(pid) + "/status");', '(void)pid;std::istringstream input(statusText);')
        declarations=r'''
#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <sstream>
#include <string>
#include <sys/types.h>
std::string statusText;
'''
        cases=r'''
int main(){for(auto pid:{1,2,2147483647}){statusText="Name:\tqemu_openvpn\nPPid:\t"+std::to_string(pid)+"\n";assert(ParseActualParent(23)==pid);}for(auto value:{"0","-1","2147483648","bad","1x",""}){statusText=std::string("PPid:\t")+value+"\n";assert(ParseActualParent(23)==-1);}}
'''
        with tempfile.TemporaryDirectory() as temporary:compile_run(declarations+actual+cases,Path(temporary))

    def test_actual_native_ipv4_interface_masks_zero_and_edges(self):
        declarations=r'''
#include <arpa/inet.h>
#include <atomic>
#include <cassert>
#include <cstring>
#include <string>
#include <unistd.h>
#define NETNATIVE_LOGE(...) ((void)0)
#define NETNATIVE_LOGI(...) ((void)0)
constexpr int NETMANAGER_SUCCESS=0,NETMANAGER_ERROR=-1,NET_MASK_MAX_LENGTH=32;
constexpr unsigned SIOCSIFADDR=1,SIOCSIFNETMASK=2;
struct ifreq{char ifr_name[16];sockaddr ifr_addr,ifr_netmask;};
int calls=0;in_addr_t lastMask=0;
int TestIoctl(int,unsigned command,ifreq *request){++calls;if(command==SIOCSIFNETMASK)lastMask=reinterpret_cast<sockaddr_in*>(&request->ifr_netmask)->sin_addr.s_addr;return 0;}
#define ioctl TestIoctl
struct MultiVpnManager{int ups=0;int InitIfreq(ifreq &request,const std::string&){memset(&request,0,sizeof(request));return 0;}int AddVpnRemoteAddress(const std::string&,std::atomic_int&,ifreq&){return 0;}int SetVpnUp(const std::string&,bool){++ups;return 0;}int SetVpnAddressIPv4(const std::string&,const std::string&,int);};
'''
        cases=r'''
int main(){MultiVpnManager manager;for(unsigned prefix:{0u,1u,31u,32u}){assert(manager.SetVpnAddressIPv4("multitun-vpn1","203.0.113.255",prefix)==0);assert(ntohl(lastMask)==(prefix?0xffffffffu<<(32-prefix):0));}
 const int previous=calls;assert(manager.SetVpnAddressIPv4("multitun-vpn1","203.0.113.1",-1)==-1);assert(manager.SetVpnAddressIPv4("multitun-vpn1","203.0.113.1",33)==-1);assert(calls==previous);}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);text=(root/BASE/'services/netmanagernative/src/manager/multi_vpn_manager.cpp').read_text()
            compile_run(declarations+body(text,'int32_t MultiVpnManager::SetVpnAddressIPv4(')+cases,root)

if __name__=='__main__':unittest.main()
