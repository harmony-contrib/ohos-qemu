"""Run the actual session controller and routing bodies with fixed real cJSON."""
from pathlib import Path
import base64
import json
import os
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT, EXT, HEADERS, body, compile_run

COMPONENT = ROOT / 'patches/common' / EXT / 'openvpn_session'
FIXTURE = Path(__file__).with_name('fixtures') / 'batch_network/session-prepared.json'
CJSON = FIXTURE.parent / 'cjson'


def prepared(root):
    for name,encoded in json.loads(FIXTURE.read_text()).items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(encoded))
    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)


class OpenvpnSessionTests(unittest.TestCase):
    def test_checked_source_stack_rejects_partial_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root)
            before={name:(root/name).read_bytes() for name in json.loads(FIXTURE.read_text())}
            subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            self.assertEqual(before,{name:(root/name).read_bytes() for name in before})
            name=next(iter(before));(root/name).write_bytes(base64.b64decode(json.loads(FIXTURE.read_text())[name]))
            snapshot={name:(root/name).read_bytes() for name in before}
            result=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(snapshot,{name:(root/name).read_bytes() for name in before})

    def test_preceding_component_checks_accept_only_complete_session_followup(self):
        from test_connected_vpn_nullable import staged as connected_staged
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);connected_staged(root)
            previous=ROOT/'patches/common'/EXT/'connected_vpn_nullable/apply.sh'
            subprocess.run(['bash',str(previous),'--source-root',str(root)],check=True,capture_output=True)
            prepared(root)
            for name in ['connected_vpn_nullable','openvpn_lifecycle']:
                subprocess.run(['bash',str(ROOT/'patches/common'/EXT/name/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            target=root/EXT/'services/vpnmanager/src/net_vpn_impl.cpp'
            target.write_bytes(target.read_bytes()+b'// unreviewed change\n')
            denied=subprocess.run(['bash',str(previous),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0)

    def test_real_json_controller_atomic_dual_stack_and_session_lifecycle(self):
        declarations=r'''
#include "session_contract.h"
#include "negotiated_config.h"
#include "cJSON.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <memory>
#include <vector>
#define NETMANAGER_EXT_SUCCESS 0
#define NETMANAGER_EXT_ERR_PARAMETER_ERROR 2200001
#define NETMANAGER_EXT_ERR_INTERNAL 2200003
#define NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL 202
constexpr int OPENVPN_STATE_STARTED=3,OPENVPN_STATE_CONNECTED=4,OPENVPN_STATE_DISCONNECTED=5;
struct INetAddr {enum{IPV4=1,IPV6=2};std::string address_,netMask_;uint8_t family_=0,type_=0,prefixlen_=0;};
struct Route {INetAddr destination_,gateway_;std::string iface_;bool isExcludedRoute_=false,isDefaultRoute_=false;};
struct VpnConfig {std::vector<INetAddr> addresses_;std::vector<Route> routes_;std::vector<std::string> dnsAddresses_,searchDomains_;int mtu_=0;bool isAcceptIPv4_=false,isAcceptIPv6_=false;};
struct OpenvpnConfig {std::string ovpnConfig_,askpass_;std::vector<INetAddr> localAddresses_;};
namespace Base64 {std::string Decode(const std::string &value){return value;}}
struct NetVpnImpl {int destroyCalls=0,destroyResult=0;int Destroy(){++destroyCalls;return destroyResult;}};
OhosOpenvpn::SessionRole role=OhosOpenvpn::SessionRole::Invalid;bool executable=true;
namespace OhosOpenvpn {
SessionRole TestCallerRole(pid_t,pid_t){return role;}
bool TestExecutable(pid_t,const char*){return executable;}
}
#define CallerRole TestCallerRole
#define Executable TestExecutable
struct OpenvpnCtl:NetVpnImpl {
 std::shared_ptr<VpnConfig> vpnConfig_=std::make_shared<VpnConfig>();
 std::shared_ptr<OpenvpnConfig> openvpnConfig_=std::make_shared<OpenvpnConfig>();
 std::string qemuGeneration_=std::string(32,'a');int32_t qemuSupervisor_=-1;
 bool qemuConfigured_=false,qemuTunReady_=false;int state=3,setupCalls=0,setupResult=0;
 std::string GetInterfaceName(){return "vpn-real-tun";}
 bool HasQemuSession(){return !qemuGeneration_.empty();}
 int SetUpVpnTun(){++setupCalls;return setupResult;}
 void UpdateOpenvpnState(int value){state=value;}
 int32_t GetQemuSession(std::string&,int32_t);
 int32_t UpdateQemuConfig(cJSON*);
 int32_t HandleQemuStage(const std::string&,int32_t,int32_t);
};
'''
        cases=r'''
int main(){
 using namespace OhosOpenvpn;OpenvpnCtl ctl;std::string wire;
 ctl.openvpnConfig_->ovpnConfig_="client\n<key>\nactual-key\n</key>\n";ctl.openvpnConfig_->askpass_="secret";
 executable=false;assert(ctl.GetQemuSession(wire,111)==202 && wire.empty());
 executable=true;assert(ctl.GetQemuSession(wire,111)==0 && ctl.qemuSupervisor_==111);
 SessionConfig decoded;assert(DecodeSession(wire,decoded) && decoded.password=="secret");
 assert(ctl.GetQemuSession(wire,222)==202 && wire.empty());
 Environment env{{"TUNTAP_DEV_TYPE","tun"},{"TUNTAP_MTU","1400"},{"ifconfig_local","10.8.0.2"},{"ifconfig_netmask","255.255.255.0"},
 {"ifconfig_ipv6_local","fd12::2"},{"ifconfig_ipv6_netbits","64"},{"dns_server_1_address_1","10.8.0.53"},
 {"dns_server_1_address_2","fd12::53"},{"route_redirect_gateway_ipv4","1"},{"route_redirect_gateway_ipv6","1"}};
 NegotiatedConfig config;assert(ReadNegotiated(env,config));auto network=NetworkJson(config);
 role=SessionRole::Invalid;assert(ctl.HandleQemuStage(network,0,333)==202);
 role=SessionRole::Supervisor;assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":4}}",0,111)==2200001);
 assert(ctl.HandleQemuStage(network,0,111)==2200001);
 role=SessionRole::Bridge;assert(ctl.HandleQemuStage("{\"setupVpnTun\":{}}",0,333)==2200001 && ctl.setupCalls==0);
 assert(ctl.HandleQemuStage(network,0,333)==0 && ctl.qemuConfigured_);
 assert(ctl.vpnConfig_->addresses_.size()==2 && ctl.vpnConfig_->routes_.size()==4 && ctl.vpnConfig_->dnsAddresses_.size()==2);
 assert(ctl.vpnConfig_->isAcceptIPv4_ && ctl.vpnConfig_->isAcceptIPv6_ && ctl.openvpnConfig_->localAddresses_.size()==2);
 assert(ctl.vpnConfig_->addresses_[0].netMask_=="255.255.255.0");
 const auto count=ctl.vpnConfig_->routes_.size();
 for (auto bad:{std::string("{\"config\":{}}"),network+"x",network.substr(0,network.size()-1)+",\"extra\":{}}"})
  assert(ctl.HandleQemuStage(bad,0,333)==2200001 && ctl.vpnConfig_->routes_.size()==count);
 auto broken=network;auto at=broken.find("fd12::53");broken.replace(at,8,"bad-dns!");
 assert(ctl.HandleQemuStage(broken,0,333)==2200001 && ctl.vpnConfig_->dnsAddresses_[1]=="fd12::53");
 assert(ctl.HandleQemuStage("{\"setupVpnTun\":{}}",0,333)==0 && ctl.qemuTunReady_ && ctl.setupCalls==1);
 assert(ctl.HandleQemuStage(network,0,333)==2200001);
 assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":4}}",0,333)==2200001);
 role=SessionRole::Supervisor;
 assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":4}}",0,111)==0 && ctl.state==4);
 assert(ctl.HandleQemuStage("{\"reconnecting\":{}}",0,111)==0 && ctl.state==3 && ctl.destroyCalls==1 && !ctl.qemuTunReady_ && ctl.HasQemuSession());
 assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":4}}",0,111)==2200001);
 env["dns_server_1_address_1"]="10.9.0.53";env.erase("dns_server_1_address_2");assert(ReadNegotiated(env,config));
 role=SessionRole::Bridge;assert(ctl.HandleQemuStage(NetworkJson(config),0,444)==0);
 assert(ctl.vpnConfig_->routes_.size()==count && ctl.vpnConfig_->dnsAddresses_==std::vector<std::string>{"10.9.0.53"});
 assert(ctl.HandleQemuStage("{\"setupVpnTun\":{}}",0,444)==0 && ctl.setupCalls==2);
 role=SessionRole::Supervisor;ctl.destroyResult=2200010;
 assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":5}}",0,111)==2200010 && ctl.HasQemuSession());
 ctl.destroyResult=0;
 assert(ctl.HandleQemuStage("{\"updateState\":{\"state\":5}}",0,111)==0 && !ctl.HasQemuSession() && ctl.qemuSupervisor_==-1 && ctl.state==5);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root)
            text=(root/EXT/'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ('bool QemuInteger(', 'bool QemuString(', 'bool QemuAddress(',
                'int32_t OpenvpnCtl::GetQemuSession(', 'int32_t OpenvpnCtl::UpdateQemuConfig(', 'int32_t OpenvpnCtl::HandleQemuStage('))
            obj=root/'cJSON.o'
            compiled=subprocess.run([os.environ.get('CC','clang'),'-std=c11','-fsanitize=address,undefined','-fno-omit-frame-pointer','-c',str(CJSON/'cJSON.c'),'-o',str(obj)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            compile_run(declarations+actual+cases,root,extra=['-I',str(CJSON),str(obj)])


    def test_real_base_dns_families_and_route_prefix_boundaries(self):
        declarations=r"""
#include <cassert>
#include <arpa/inet.h>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define IPV4_NET_MASK_MAX_LENGTH 32
struct INetAddr {enum IpType{IPV4=1,IPV6=2};uint8_t family_=0,type_=0,prefixlen_=0;std::string address_;};
struct Route {INetAddr destination_,gateway_;std::string iface_;};
template<class T>struct sptr:std::shared_ptr<T>{using std::shared_ptr<T>::shared_ptr;sptr()=default;sptr(T* value):std::shared_ptr<T>(value){}};
struct VpnConfig {std::vector<INetAddr> addresses_;std::vector<Route> routes_;std::vector<std::string> dnsAddresses_,searchDomains_;bool isAcceptIPv4_=true,isAcceptIPv6_=true;int mtu_=1400;};
struct NetLinkInfo {std::string ifaceName_,domain_;std::vector<INetAddr> dnsList_;std::vector<Route> routeList_;bool isUserDefinedDnsServer_=false;int mtu_=0;};
namespace CommonUtils {
uint32_t ConvertIpv4Address(const std::string &text){in_addr a{};assert(inet_pton(AF_INET,text.c_str(),&a)==1);return ntohl(a.s_addr);}
std::string GetIpv6Prefix(const std::string &text,unsigned prefix){in6_addr a{};assert(inet_pton(AF_INET6,text.c_str(),&a)==1);for(unsigned bit=prefix;bit<128;++bit)a.s6_addr[bit/8]&=~(1u<<(7-bit%8));char out[INET6_ADDRSTRLEN]{};assert(inet_ntop(AF_INET6,&a,out,sizeof(out)));return out;}
}
struct NetManagerCenter {sptr<NetLinkInfo> last;int calls=0;static NetManagerCenter &GetInstance(){static NetManagerCenter v;return v;}void UpdateNetLinkInfo(int,sptr<NetLinkInfo> value){last=value;++calls;}};
struct NetVpnImpl {
 std::shared_ptr<VpnConfig> vpnConfig_=std::make_shared<VpnConfig>();int netSupplierId_=17;
 std::string GetInterfaceName(){return "vpn-actual";}
 void UpdateAddress(sptr<NetLinkInfo>&){}
 void SetIpv4DefaultRoute(Route&){}void SetIpv6DefaultRoute(Route&){}
 std::string ConvertVpnIpv4Address(uint32_t host){in_addr a{};a.s_addr=htonl(host);char text[INET_ADDRSTRLEN]{};assert(inet_ntop(AF_INET,&a,text,sizeof(text)));return text;}
 bool UpdateNetLinkInfo();void AdjustRouteInfo(Route&);
};
"""
        cases=r"""
int main(){
 NetVpnImpl ctl;auto &center=NetManagerCenter::GetInstance();ctl.vpnConfig_->routes_.push_back({});
 ctl.vpnConfig_->routes_[0].destination_.address_="10.8.0.2";ctl.vpnConfig_->routes_[0].destination_.prefixlen_=24;
 ctl.vpnConfig_->dnsAddresses_={"192.0.2.53","2001:db8::53"};
 assert(ctl.UpdateNetLinkInfo() && center.calls==1 && center.last->dnsList_.size()==2);
 assert(center.last->dnsList_[0].family_==INetAddr::IPV4 && center.last->dnsList_[1].family_==INetAddr::IPV6);
 auto previous=center.last;ctl.vpnConfig_->dnsAddresses_.push_back("not-an-ip");
 assert(!ctl.UpdateNetLinkInfo() && center.calls==1 && center.last==previous);
 for(unsigned prefix:{0u,1u,31u,32u}){
  Route r;r.destination_.address_="203.0.113.255";r.destination_.prefixlen_=prefix;r.destination_.family_=INetAddr::IPV4;
  ctl.AdjustRouteInfo(r);const uint32_t expected=CommonUtils::ConvertIpv4Address("203.0.113.255")&(prefix?0xffffffffu<<(32-prefix):0);
  assert(r.destination_.address_==ctl.ConvertVpnIpv4Address(expected) && r.destination_.prefixlen_==prefix);
 }
 for(unsigned prefix:{0u,1u,127u,128u}){
  Route r;r.destination_.address_="2001:db8::ffff";r.destination_.prefixlen_=prefix;r.destination_.family_=INetAddr::IPV6;
  ctl.AdjustRouteInfo(r);assert(r.destination_.address_==CommonUtils::GetIpv6Prefix("2001:db8::ffff",prefix));
 }
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root)
            text=(root/EXT/'services/vpnmanager/src/net_vpn_impl.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ('bool NetVpnImpl::UpdateNetLinkInfo(', 'void NetVpnImpl::AdjustRouteInfo('))
            compile_run(declarations+actual+cases,root)



    def test_real_service_routes_generation_and_propagates_controller_errors(self):
        declarations=r"""
#include "session_contract.h"
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
constexpr int NETMANAGER_EXT_SUCCESS=0,NETMANAGER_EXT_ERR_INTERNAL=2200003,NETMANAGER_EXT_ERR_PARAMETER_ERROR=2200001,NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL=202;
constexpr unsigned UID_NET_SYS_NATIVE=1098;const std::string DISCONNECT_TAG="disconnect";
int callerUid=1098,callerPid=123;
namespace IPCSkeleton{int GetCallingUid(){return callerUid;}int GetCallingPid(){return callerPid;}}
namespace ffrt{using shared_mutex=std::shared_mutex;}
enum class VpnType{OPENVPN,OTHER};struct Config{VpnType vpnType_=VpnType::OPENVPN;};
struct Info{bool isVpnExtCall=true;std::string vpnId="owner-vpn";};
struct NetVpnImpl{
 std::shared_ptr<Info> multiVpnInfo_=std::make_shared<Info>();std::shared_ptr<Config> config=std::make_shared<Config>();
 int legacyCalls=0,legacyResult=0;
 bool IsSystemVpn(){return true;}std::shared_ptr<Config> GetSysVpnConfig(){return config;}
 std::shared_ptr<Config> GetVpnConfig(){return config;}int Destroy(){return 0;}
 int NotifyConnectStage(const std::string&,int){++legacyCalls;return legacyResult;}
 int GetSysVpnCertUri(int,std::string &out){out="legacy";return 0;}
};
struct OpenvpnCtl:NetVpnImpl{
 std::string generation;bool connected=false;int calls=0,response=0,snapshotCalls=0;
 bool IsQemuSession(const std::string &value){return !generation.empty() && value==generation;}
 bool HasQemuSession(){return !generation.empty();}bool IsOpenvpnConnected(){return connected;}
 int HandleQemuStage(const std::string&,int,int pid){assert(pid==callerPid);++calls;return response;}
 int GetQemuSession(std::string &out,int pid){assert(pid==callerPid);++snapshotCalls;out=generation+"-atomic-config-and-password";return response;}
};
struct MultiVpnHelper{int adds=0;static MultiVpnHelper& GetInstance(){static MultiVpnHelper v;return v;}void AddMultiVpnInfo(const std::shared_ptr<Info>&){++adds;}bool IsConnectedStage(const std::string&){return true;}void GetDisconnectAddr(const std::string&,std::string&) {}};
struct NetworkVpnService{
 ffrt::shared_mutex netVpnMutex_;std::shared_ptr<NetVpnImpl> vpnObj_,connectingObj_;std::map<std::string,std::shared_ptr<NetVpnImpl>> vpnObjMap_;
 bool IsSelfCall(){return false;}bool CheckVpnHasLocalAddr(const std::shared_ptr<NetVpnImpl>&){return false;}
 bool CheckMultiVpnAddrMatched(const std::shared_ptr<NetVpnImpl>&,const std::string&){return false;}int DestroyMultiVpn(const std::shared_ptr<NetVpnImpl>&){return 0;}
 int32_t NotifyConnectStage(const std::string&,const int32_t);
 int32_t GetSysVpnCertUri(const int32_t,std::string&);
};
"""
        cases=r"""
int main(){
 NetworkVpnService service;auto old=std::make_shared<OpenvpnCtl>(),next=std::make_shared<OpenvpnCtl>();
 old->generation=std::string(32,'a');next->generation=std::string(32,'b');service.vpnObjMap_["old"]=old;service.connectingObj_=next;
 const auto oldEvent=OhosOpenvpn::Stage(old->generation,"{\"config\":{}}");
 callerUid=20000;assert(service.NotifyConnectStage(oldEvent,0)==202 && old->calls==0 && next->calls==0);
 std::string config="stale";assert(service.GetSysVpnCertUri(OhosOpenvpn::SESSION_REQUEST,config)==202);
 callerUid=1098;old->response=2200099;
 assert(service.NotifyConnectStage(oldEvent,0)==2200099 && old->calls==1 && next->calls==0);
 assert(MultiVpnHelper::GetInstance().adds==0);
 old->generation.clear();assert(service.NotifyConnectStage(oldEvent,0)==2200003 && next->calls==0);
 assert(service.GetSysVpnCertUri(OhosOpenvpn::SESSION_REQUEST,config)==0 && next->snapshotCalls==1 && config.find(std::string(32,'b'))==0);
 assert(service.GetSysVpnCertUri(1,config)==202 && config.empty());
 next->response=2200020;assert(service.NotifyConnectStage(OhosOpenvpn::Stage(next->generation,"{}"),0)==2200020 && next->calls==1);
 next->generation.clear();next->legacyResult=2200042;
 assert(service.NotifyConnectStage("legacy-connected",0)==2200042 && next->legacyCalls==1 && MultiVpnHelper::GetInstance().adds==0);
 next->legacyResult=0;assert(service.NotifyConnectStage("legacy-connected",0)==0 && MultiVpnHelper::GetInstance().adds==1);
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root)
            text=(root/EXT/'services/vpnmanager/src/networkvpn_service.cpp').read_text()
            actual='\n'.join(body(text,sig) for sig in ('std::shared_ptr<OpenvpnCtl> QemuOpenvpn(',
                'int32_t NetworkVpnService::NotifyConnectStage(', 'int32_t NetworkVpnService::GetSysVpnCertUri('))
            compile_run(declarations+actual+cases,root)


if __name__=='__main__':unittest.main()
