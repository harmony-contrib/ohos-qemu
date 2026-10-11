"""Execute exact patched serializers under sanitizers; NOT guest/DB proof."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays'
PATCH = COMPONENT / '0001-preserve-vpn-config-array-elements-and-prefixes.patch'
CPP = 'foundation/communication/netmanager_ext/frameworks/js/napi/vpn/src/vpn_config_utils.cpp'

MOCK = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value {
    std::map<std::string,Value*> properties;
    std::vector<Value*> elements;
    std::string text;
    uint32_t number=0;
    bool boolean=false;
};
using napi_env=void*; using napi_value=Value*;
std::vector<std::unique_ptr<Value>> values;
Value undefined;
struct NapiUtils {
    static Value* CreateObject(napi_env) {
        values.push_back(std::make_unique<Value>()); return values.back().get(); }
    static Value* GetUndefined(napi_env) { return &undefined; }
    static Value* CreateArray(napi_env env, size_t count) {
        auto array=CreateObject(env); array->elements.resize(count); return array; }
    static Value* CreateStringUtf8(napi_env env,const std::string& text) {
        auto value=CreateObject(env); value->text=text; return value; }
    static void SetNamedProperty(napi_env,Value* object,const char* name,Value* value) {
        assert(object->properties.emplace(name,value).second); }
    static void SetArrayElement(napi_env,Value* array,size_t index,Value* value) {
        assert(index<array->elements.size()); assert(!array->elements[index]); array->elements[index]=value; }
    static void SetStringPropertyUtf8(napi_env env,Value* object,const char* name,const std::string& text) {
        SetNamedProperty(env,object,name,CreateStringUtf8(env,text)); }
    static void SetUint32Property(napi_env env,Value* object,const char* name,uint32_t number) {
        auto value=CreateObject(env); value->number=number; SetNamedProperty(env,object,name,value); }
    static void SetInt32Property(napi_env env,Value* object,const char* name,int32_t number) {
        SetUint32Property(env,object,name,static_cast<uint32_t>(number)); }
    static void SetBooleanProperty(napi_env env,Value* object,const char* name,bool boolean) {
        auto value=CreateObject(env); value->boolean=boolean; SetNamedProperty(env,object,name,value); }
};
struct INetAddr {
    uint8_t family_=0, prefixlen_=0;
    std::string address_;
    uint8_t port_=0;
};
struct SysVpnConfig {
    std::vector<INetAddr> addresses_, localAddresses_;
    std::vector<std::string> remoteAddresses_, dnsAddresses_, searchDomains_;
    std::string vpnId_="audit-uuid",vpnName_="audit-name",userName_="audit-user",
        password_="synthetic-password",forwardingRoutes_="audit-route";
    int32_t vpnType_=2;
    bool saveLogin_=true;
};
template<typename T> using sptr=std::shared_ptr<T>;
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NET_ADDRESS "address"
#define NET_PREFIXLENGTH "prefixLength"
#define NET_FAMILY "family"
#define NET_PORT "port"
#define CONFIG_ADDRESSES "addresses"
#define CONFIG_LOCAL_ADDRESSES "localAddresses"
#define CONFIG_REMOTE_ADDRS "remoteAddresses"
#define CONFIG_DNSADDRESSES "dnsAddresses"
#define CONFIG_SEARCHDOMAINS "searchDomains"
#define CONFIG_VPN_ID "vpnId"
#define CONFIG_VPN_NAME "vpnName"
#define CONFIG_VPN_TYPE "vpnType"
#define CONFIG_USER_NAME "userName"
#define CONFIG_PASSWORD "password"
#define CONFIG_SAVE_LOGIN "saveLogin"
#define CONFIG_FORWARDED_ROUTES "forwardingRoutes"
void SetLocalAddressesProperty(napi_env, napi_value, const std::vector<INetAddr>&);
'''

CHECKS = r'''
void CheckLinks(Value* object,const char* name,const std::vector<INetAddr>& expected) {
    const auto& actual=object->properties.at(name)->elements;
    assert(actual.size()==expected.size());
    for(size_t i=0;i<actual.size();++i) {
        assert(actual[i]); auto address=actual[i]->properties.at("address");
        assert(address->properties.at("address")->text==expected[i].address_);
        assert(address->properties.at("family")->number==expected[i].family_);
        assert(address->properties.at("port")->number==expected[i].port_);
        assert(actual[i]->properties.at("prefixLength")->number==expected[i].prefixlen_);
    }
}
void CheckStrings(Value* object,const char* name,const std::vector<std::string>& expected) {
    if(expected.empty()) { assert(object->properties.count(name)==0); return; }
    const auto& actual=object->properties.at(name)->elements;
    assert(actual.size()==expected.size());
    for(size_t i=0;i<actual.size();++i) { assert(actual[i]); assert(actual[i]->text==expected[i]); }
}
void Check(const sptr<SysVpnConfig>& input,Value* actual) {
    CheckLinks(actual,"addresses",input->addresses_);
    if(input->localAddresses_.empty()) assert(actual->properties.count("localAddresses")==0);
    else CheckLinks(actual,"localAddresses",input->localAddresses_);
    CheckStrings(actual,"remoteAddresses",input->remoteAddresses_);
    CheckStrings(actual,"dnsAddresses",input->dnsAddresses_);
    CheckStrings(actual,"searchDomains",input->searchDomains_);
    assert(actual->properties.at("vpnId")->text==input->vpnId_);
    assert(actual->properties.at("vpnName")->text==input->vpnName_);
    assert(actual->properties.at("vpnType")->number==static_cast<uint32_t>(input->vpnType_));
    assert(actual->properties.at("userName")->text==input->userName_);
    assert(actual->properties.at("password")->text==input->password_);
    assert(actual->properties.at("saveLogin")->boolean==input->saveLogin_);
    assert(actual->properties.at("forwardingRoutes")->text==input->forwardingRoutes_);
}
'''


def source(patched=True):
    return MOCK + '\n'.join('\n'.join(hunk[2 if patched else 1])
                             for hunk in patch_sections(PATCH)[CPP]) + CHECKS


class VpnConfigArraysTests(unittest.TestCase):
    def test_exact_empty_and_null_native_configs(self):
        compile_run(source() + r'''
int main() {
    sptr<SysVpnConfig> none;
    assert(CreateNapiSysVpnConfig(nullptr,none)==&undefined);
    auto config=std::make_shared<SysVpnConfig>();
    Check(config,CreateNapiSysVpnConfig(nullptr,config));
}
''', language='c++')

    def test_all_native_entries_prefixes_family_port_and_independent_envs(self):
        compile_run(source() + r'''
int main() {
    for(size_t size : {size_t(1),size_t(2),size_t(64),size_t(1024)}) {
        auto config=std::make_shared<SysVpnConfig>();
        for(size_t i=0;i<size;++i) {
            INetAddr address;
            address.address_="address-"+std::to_string(i);
            address.family_=i%2+1; address.port_=i%256;
            address.prefixlen_=i%2 ? 64 : 24;
            config->addresses_.push_back(address);
            address.address_="local-"+std::to_string(i); address.prefixlen_=i%2 ? 96 : 28;
            config->localAddresses_.push_back(address);
            config->remoteAddresses_.push_back("remote-"+std::to_string(i));
            config->dnsAddresses_.push_back("dns-"+std::to_string(i));
            config->searchDomains_.push_back("domain-"+std::to_string(i));
        }
        auto first=CreateNapiSysVpnConfig(reinterpret_cast<void*>(1),config);
        Check(config,first);
        config->addresses_.back().prefixlen_=30;
        config->localAddresses_.back().prefixlen_=31;
        config->searchDomains_.back()="changed.example";
        auto second=CreateNapiSysVpnConfig(reinterpret_cast<void*>(2),config);
        Check(config,second); assert(first!=second);
        assert(first->properties.at("addresses")->elements.back()->properties.at("prefixLength")->number==
            (size%2==0 ? 64u : 24u));
        assert(first->properties.at("searchDomains")->elements.back()->text=="domain-"+std::to_string(size-1));
        values.clear();
    }
}
''', language='c++')

    def test_regression_detects_original_prefix_and_array_truncation(self):
        result = compile_run(source(False) + r'''
int main() {
    auto config=std::make_shared<SysVpnConfig>();
    config->addresses_.push_back({1,24,"198.18.0.2",0});
    config->addresses_.push_back({2,64,"2001:db8::2",255});
    config->searchDomains_={"first.example","second.example"};
    Check(config,CreateNapiSysVpnConfig(nullptr,config));
}
''', language='c++', expect_success=False)
        self.assertNotEqual(result.returncode, 0)

    def test_build_recipe_applies_independent_component(self):
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('netmanager_ext/vpn_config_arrays/apply.sh', build)
        self.assertIn('bash "${VPN_CONFIG_ARRAYS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', build)


if __name__ == '__main__':
    unittest.main()
