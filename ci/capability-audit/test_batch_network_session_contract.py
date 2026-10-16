"""Exercise the real session codec, negotiated env parser and private cleanup."""
from pathlib import Path
import os
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import compile_run


class SessionContractTests(unittest.TestCase):
    def run_cpp(self, source, *args):
        with tempfile.TemporaryDirectory() as temporary:
            compile_run(source, Path(temporary), args)

    def test_atomic_envelope_and_generation_stage_boundaries(self):
        self.run_cpp(r'''
#include "session_contract.h"
#include "profile_policy.h"
#include <cassert>
#include <vector>
int main(){
 using namespace OhosOpenvpn;
 assert(!ValidateProfile("client\npersist-tun\n"));
 assert(ValidateProfile("client\ndns server 0 address 10.8.0.53\n"));
 SessionConfig original{std::string(32,'a'),"client\n<key>\nprivate\n</key>\n","secret"},result;
 auto wire=EncodeSession(original);assert(!wire.empty() && DecodeSession(wire,result));
 assert(result.token==original.token && result.profile==original.profile && result.password==original.password);
 auto previous=result;
 for(auto bad:std::vector<std::string>{wire+"x",wire.substr(0,wire.size()-1),"b\n1\n0\nx",std::string(32,'a')+"\n-1\n0\nx",std::string(32,'a')+"\n999999999\n0\nx"}){
  assert(!DecodeSession(bad,result));assert(result.profile==previous.profile && result.password==previous.password);
 }
 original.password=std::string("x\0y",3);assert(EncodeSession(original).empty());
 original.password="x\ny";assert(EncodeSession(original).empty());
 std::string token,body;auto stage=Stage(previous.token,"{\"reconnecting\":{}}");
 assert(DecodeStage(stage,token,body) && token==previous.token && body=="{\"reconnecting\":{}}");
 assert(!DecodeStage("openvpn {\"state\":4}",token,body));
 assert(!DecodeStage("qemu-openvpn "+std::string(32,'g')+" {}",token,body));
 assert(!DecodeStage("qemu-openvpn "+std::string(32,'a')+" ",token,body));
 assert(Stage("remote-peer-token","{}").empty());
}
''')

    def test_final_dns_dual_stack_routes_and_rejection_preserve_output(self):
        self.run_cpp(r'''
#include "negotiated_config.h"
#include <cassert>
int main(){
 using namespace OhosOpenvpn;
 Environment base{{"TUNTAP_DEV_TYPE","tun"},{"TUNTAP_MTU","1400"},
 {"ifconfig_local","10.8.0.2"},{"ifconfig_netmask","255.255.255.0"},
 {"ifconfig_ipv6_local","fd12::2"},{"ifconfig_ipv6_netbits","64"},{"ifconfig_ipv6_remote","fd12::1"},
 {"route_network_1","10.50.0.0"},{"route_netmask_1","255.255.0.0"},{"route_gateway_1","10.8.0.1"},
 {"route_network_3","198.51.100.1"},{"route_netmask_3","255.255.255.255"},{"route_gateway_3","10.0.2.2"},
 {"route_net_gateway","10.0.2.2"},{"route_ipv6_network_2","2001:db8:2::/64"},{"route_ipv6_gateway_2","fd12::1"},
 {"route_redirect_gateway_ipv4","1"},{"route_redirect_gateway_ipv6","1"},
 {"dns_server_1_address_1","10.8.0.1"},{"dns_server_1_address_2","fd12::1"},{"dns_search_domain_1","corp.example"},
 {"foreign_option_1","dhcp-option DNS 192.0.2.53"}};
 NegotiatedConfig out;assert(ReadNegotiated(base,out));
 assert(out.addresses.size()==2 && out.addresses[0].prefix==24 && out.addresses[1].prefix==64);
 assert(out.routes.size()==7 && out.routes[3].excluded);
 assert(out.dns==std::vector<std::string>({"10.8.0.1","fd12::1"}));
 assert(out.domains==std::vector<std::string>({"corp.example"}));
 const auto json=NetworkJson(out);assert(json.find("fd12::2")!=std::string::npos && json.find("198.51.100.1")!=std::string::npos);
 const auto previous=NetworkJson(out);
 for(auto bad:std::vector<std::pair<std::string,std::string>>{
  {"TUNTAP_MTU","1279"},{"ifconfig_netmask","255.0.255.0"},{"ifconfig_ipv6_netbits","129"},
  {"dns_server_1_port_1","853"},{"dns_server_1_transport","https"},{"dns_server_1_dnssec","yes"},
  {"dns_server_1_resolve_domain_1","private.example"},{"dns_server_1_address_9","10.8.0.1"},
  {"dns_search_domain_1","bad\"domain"},{"route_network_257","10.9.0.0"},
  {"route_netmask_3","255.255.0.255"},{"route_ipv6_network_2","2001:db8:2::/129"},
  {"route_redirect_gateway_ipv4","2"}}){
  auto env=base;env[bad.first]=bad.second;assert(!ReadNegotiated(env,out));assert(NetworkJson(out)==previous);
 }
 for(unsigned prefix:{0u,1u,31u,32u}){
  unsigned result=99;uint32_t mask=prefix?0xffffffffu<<(32-prefix):0;
  in_addr a{};a.s_addr=htonl(mask);char text[INET_ADDRSTRLEN]{};assert(inet_ntop(AF_INET,&a,text,sizeof(text)));
  assert(MaskPrefix(text,result) && result==prefix);
 }
 for(const char *bits:{"0","1","127","128"}){
  auto env=base;env["ifconfig_ipv6_netbits"]=bits;assert(ReadNegotiated(env,out));
 }
 auto legacy=base;
 for(auto it=legacy.begin();it!=legacy.end();)if(it->first.find("dns_")==0)it=legacy.erase(it);else ++it;
 legacy["foreign_option_3"]="dhcp-option DNS6 fd12::53";
 legacy["foreign_option_5"]="dhcp-option DOMAIN-SEARCH one.example two.example";
 assert(ReadNegotiated(legacy,out) && out.dns==std::vector<std::string>({"192.0.2.53","fd12::53"}) && out.domains.size()==2);
 auto p2p=Environment{{"TUNTAP_DEV_TYPE","tun"},{"TUNTAP_MTU","1400"},{"ifconfig_local","10.8.0.2"},{"ifconfig_remote","10.8.0.1"}};
 assert(ReadNegotiated(p2p,out) && out.addresses[0].prefix==32 && out.routes.size()==2);
 auto only6=Environment{{"TUNTAP_DEV_TYPE","tun"},{"TUNTAP_MTU","1400"},{"ifconfig_ipv6_local","fd12::2"},{"ifconfig_ipv6_netbits","128"}};
 assert(ReadNegotiated(only6,out) && out.addresses.size()==1 && out.addresses[0].family==AF_INET6);
 only6["foreign_option_1"]="dhcp-option DNS 192.0.2.53";assert(!ReadNegotiated(only6,out));
}
''')

    def test_sigkill_stale_secret_cleanup_no_symlink_or_unknown_tree_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source=r'''
#include "session_files.h"
#include <cassert>
#include <filesystem>
#include <fstream>
int main(int argc,char** argv){
 assert(argc==2);namespace fs=std::filesystem;using namespace OhosOpenvpn;
 const fs::path base(argv[1]),outside=base/"outside",storage=base/"sessions";
 fs::create_directory(storage);fs::permissions(storage,fs::perms::owner_all);
 fs::create_directory(outside);std::ofstream(outside/"preserve")<<"unrelated";
 fs::create_directory(storage/"session-abc123");fs::permissions(storage/"session-abc123",fs::perms::owner_all);
 std::ofstream(storage/"session-abc123"/"client.ovpn")<<"private-key";
 fs::create_symlink(outside/"preserve",storage/"session-abc123"/"askpass");
 {SessionStore store;assert(store.Open(storage.c_str(),getuid()));assert(!fs::exists(storage/"session-abc123"));}
 assert(fs::exists(outside/"preserve"));
 fs::create_symlink(outside,storage/"session-xyz789");
 {SessionStore store;assert(!store.Open(storage.c_str(),getuid()));}
 assert(fs::exists(outside/"preserve"));fs::remove(storage/"session-xyz789");
 fs::create_directory(storage/"session-ZYX987");fs::permissions(storage/"session-ZYX987",fs::perms::owner_all);
 std::ofstream(storage/"session-ZYX987"/"unrecognized")<<"do not delete";
 {SessionStore store;assert(!store.Open(storage.c_str(),getuid()));}
 assert(fs::exists(storage/"session-ZYX987"/"unrecognized"));
 fs::remove(storage/"session-ZYX987"/"unrecognized");fs::remove(storage/"session-ZYX987");
 fs::permissions(storage,fs::perms::owner_all|fs::perms::group_read);
 {SessionStore store;assert(!store.Open(storage.c_str(),getuid()));}
 fs::permissions(storage,fs::perms::owner_all);
 fs::create_symlink(storage,base/"alias");
 {SessionStore store;assert(!store.Open((base/"alias").c_str(),getuid()));}
}
'''
            compile_run(source,root,[str(root)])


if __name__=='__main__':unittest.main()
