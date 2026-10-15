"""Execute actual nullable client/service bodies with explicit host doubles."""
import base64
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/connected_vpn_nullable'
SPEC = importlib.util.spec_from_file_location('connected_vpn_nullable_guard', COMPONENT / 'verify_source.py')
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def staged(root):
    fixture = Path(__file__).with_name('fixtures') / 'connected_vpn_nullable_prepared.json.gz.b64'
    files = json.loads(gzip.decompress(base64.b64decode(fixture.read_text())))
    for name, encoded in files.items():
        path = root / GUARD.PROJECT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(encoded))


def body(text, signature):
    start = text.index(signature)
    cursor = text.index('{', start)
    depth = 1
    while depth:
        cursor += 1
        depth += (text[cursor] == '{') - (text[cursor] == '}')
    return text[start:cursor + 1]


class ConnectedVpnNullableTests(unittest.TestCase):
    def apply(self, root):
        subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                       check=True, capture_output=True)

    def test_exact_stack_idempotence_and_unknown_partial_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged(root)
            self.assertFalse(GUARD.validate(root))
            self.apply(root)
            self.assertTrue(GUARD.validate(root, True))
            self.apply(root)
            changed = root / GUARD.PROJECT / GUARD.FILES[0][0]
            changed.write_bytes(changed.read_bytes() + b'// unrelated change\n')
            before = {name: (root / GUARD.PROJECT / name).read_bytes() for name, _, _ in GUARD.FILES}
            result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, {name: (root / GUARD.PROJECT / name).read_bytes()
                                      for name, _, _ in GUARD.FILES})

    def test_actual_client_service_empty_active_malformed_and_permission_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged(root)
            self.apply(root)
            project = root / GUARD.PROJECT
            client = body((project / 'frameworks/native/netvpnclient/src/networkvpn_client.cpp').read_text(),
                          'int32_t NetworkVpnClient::GetConnectedSysVpnConfig(')
            service = body((project / 'services/vpnmanager/src/networkvpn_service.cpp').read_text(),
                           'int32_t NetworkVpnService::GetConnectedSysVpnConfig(')
        declarations = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <shared_mutex>
#include <string>
#include <vector>
template<class T> using sptr=std::shared_ptr<T>;
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
constexpr int NETMANAGER_SUCCESS=0,NETMANAGER_EXT_SUCCESS=0;
constexpr int NETMANAGER_EXT_ERR_INTERNAL=2200003,NETMANAGER_EXT_ERR_GET_PROXY_FAIL=2200002;
namespace Permission {const char *MANAGE_VPN="MANAGE_VPN";}
namespace AppExecFwk {namespace Constants {constexpr int UNSPECIFIED_USERID=-1;}}
namespace ffrt {using shared_mutex=std::shared_mutex;}
struct SysVpnConfig {int value=17;};
int permission=0,account=0,accountChecks=0,backendReads=0,backendError=0;
sptr<SysVpnConfig> active;
struct Backend {
 int user=100;
 int GetUserId(){return user;}
 int GetConnectedSysVpnConfig(sptr<SysVpnConfig>& out){++backendReads;out=active;return backendError;}
};
struct NetworkVpnService {
 std::shared_ptr<Backend> vpnObj_;
 ffrt::shared_mutex netVpnMutex_;
 int CheckIpcPermission(const std::string &p){assert(p==Permission::MANAGE_VPN);return permission;}
 int CheckCurrentAccountType(int32_t& user,std::vector<int32_t>&){++accountChecks;user=100;return account;}
 int32_t GetConnectedSysVpnConfig(std::vector<sptr<SysVpnConfig>>&);
};
struct INetworkVpnService {
 std::vector<sptr<SysVpnConfig>> output;
 int error=0;
 int GetConnectedSysVpnConfig(std::vector<sptr<SysVpnConfig>>& out){out=output;return error;}
};
struct NetworkVpnClient {
 sptr<INetworkVpnService> proxy;
 sptr<INetworkVpnService> GetProxy(){return proxy;}
 int32_t GetConnectedSysVpnConfig(sptr<SysVpnConfig>&);
};
'''
        cases = r'''
int main(){
 NetworkVpnService service;std::vector<sptr<SysVpnConfig>> output;
 active=std::make_shared<SysVpnConfig>();service.vpnObj_=std::make_shared<Backend>();
 for(int denial:{201,202}){
  permission=denial;output={active};accountChecks=backendReads=0;
  assert(service.GetConnectedSysVpnConfig(output)==denial && output.empty());
  assert(accountChecks==0 && backendReads==0);
 }
 permission=0;account=2203001;output={active};backendReads=0;
 assert(service.GetConnectedSysVpnConfig(output)==account && output.empty() && backendReads==0);
 account=0;service.vpnObj_.reset();output={active};
 assert(service.GetConnectedSysVpnConfig(output)==0 && output.empty());
 service.vpnObj_=std::make_shared<Backend>();
 assert(service.GetConnectedSysVpnConfig(output)==0 && output.size()==1 && output[0]==active);
 service.vpnObj_->user=101;output={active};backendReads=0;
 assert(service.GetConnectedSysVpnConfig(output)==0 && output.empty() && backendReads==0);
 service.vpnObj_->user=100;
 backendError=2200003;output={active};
 assert(service.GetConnectedSysVpnConfig(output)==2200003 && output.empty());
 backendError=0;active.reset();output={std::make_shared<SysVpnConfig>()};
 assert(service.GetConnectedSysVpnConfig(output)==0 && output.empty());
 NetworkVpnClient client;sptr<SysVpnConfig> result;
 assert(client.GetConnectedSysVpnConfig(result)==NETMANAGER_EXT_ERR_GET_PROXY_FAIL);
 client.proxy=std::make_shared<INetworkVpnService>();result=std::make_shared<SysVpnConfig>();
 assert(client.GetConnectedSysVpnConfig(result)==0 && !result);
 active=std::make_shared<SysVpnConfig>();client.proxy->output={active};
 assert(client.GetConnectedSysVpnConfig(result)==0 && result==active && result->value==17);
 for(const auto &malformed:std::vector<std::vector<sptr<SysVpnConfig>>>{{nullptr},{active,active}}){
  client.proxy->output=malformed;result=active;
  assert(client.GetConnectedSysVpnConfig(result)==NETMANAGER_EXT_ERR_INTERNAL && !result);
 }
 client.proxy->error=201;client.proxy->output={active};
 assert(client.GetConnectedSysVpnConfig(result)==201 && !result);
}
'''
        compile_run(declarations + client + service + cases, language='c++')

    def test_actual_connected_owners_filter_accounts_state_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged(root)
            self.apply(root)
            source = (root / GUARD.PROJECT / 'services/vpnmanager/src/networkvpn_service.cpp').read_text()
            function = body(source, 'int32_t NetworkVpnService::GetConnectedVpnAppInfo(')
        declarations = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <shared_mutex>
#include <string>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
constexpr int NETMANAGER_SUCCESS=0,NETMANAGER_EXT_SUCCESS=0;
namespace Permission {const char *MANAGE_VPN="MANAGE_VPN";}
namespace AppExecFwk {namespace Constants {constexpr int UNSPECIFIED_USERID=-1;}}
namespace ffrt {using shared_mutex=std::shared_mutex;}
struct MultiInfo {int userId=100;std::string bundleName="org.example.multi";};
struct Backend {
 int user=100;bool connected=true;std::string owner="org.example.single";
 std::shared_ptr<MultiInfo> multiVpnInfo_=std::make_shared<MultiInfo>();
 int GetUserId(){return user;} bool IsVpnConnecting(){return connected;}
 std::string GetVpnPkg(){return owner;}
};
using NetVpnImpl=Backend;
int permission=0,account=0,accountChecks=0;
struct NetworkVpnService {
 std::shared_ptr<Backend> vpnObj_;
 std::map<int,std::shared_ptr<Backend>> vpnObjMap_;
 ffrt::shared_mutex netVpnMutex_;
 int CheckIpcPermission(const std::string& p){assert(p==Permission::MANAGE_VPN);return permission;}
 int CheckCurrentAccountType(int32_t& user,std::vector<int32_t>&){++accountChecks;user=100;return account;}
 int32_t GetConnectedVpnAppInfo(std::vector<std::string>&);
};
'''
        cases = r'''
int main(){
 NetworkVpnService service;std::vector<std::string> names={"stale"};
 for(int denial:{201,202}){
  permission=denial;names={"stale"};
  assert(service.GetConnectedVpnAppInfo(names)==denial && names.empty() && accountChecks==0);
 }
 permission=0;account=2203001;names={"stale"};
 assert(service.GetConnectedVpnAppInfo(names)==account && names.empty());account=0;
 assert(service.GetConnectedVpnAppInfo(names)==0 && names.empty());
 service.vpnObj_=std::make_shared<Backend>();
 assert(service.GetConnectedVpnAppInfo(names)==0 && names==std::vector<std::string>{"org.example.single"});
 service.vpnObj_->user=101;assert(service.GetConnectedVpnAppInfo(names)==0 && names.empty());
 service.vpnObj_->user=100;service.vpnObj_->connected=false;
 assert(service.GetConnectedVpnAppInfo(names)==0 && names.empty());
 service.vpnObj_->connected=true;service.vpnObj_->owner="";
 assert(service.GetConnectedVpnAppInfo(names)==0 && names.empty());
 service.vpnObj_->owner="org.example.single";
 auto other=std::make_shared<Backend>();service.vpnObjMap_[0]=other;
 service.vpnObjMap_[1]=other;service.vpnObjMap_[2]=nullptr;
 auto invalid=std::make_shared<Backend>();invalid->multiVpnInfo_.reset();service.vpnObjMap_[3]=invalid;
 auto foreign=std::make_shared<Backend>();foreign->multiVpnInfo_->userId=101;service.vpnObjMap_[4]=foreign;
 auto stopped=std::make_shared<Backend>();stopped->connected=false;service.vpnObjMap_[5]=stopped;
 auto same=std::make_shared<Backend>();same->multiVpnInfo_->bundleName="org.example.single";service.vpnObjMap_[6]=same;
 auto empty=std::make_shared<Backend>();empty->multiVpnInfo_->bundleName="";service.vpnObjMap_[7]=empty;
 assert(service.GetConnectedVpnAppInfo(names)==0 &&
        names==std::vector<std::string>({"org.example.single","org.example.multi"}));
 service.vpnObj_.reset();service.vpnObjMap_.clear();
 assert(service.GetConnectedVpnAppInfo(names)==0 && names.empty());
}
'''
        compile_run(declarations + function + cases, language='c++')


if __name__ == '__main__':
    unittest.main()
