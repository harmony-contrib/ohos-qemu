"""Execute exact network-output helpers; mocked NAPI is not guest proof."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections
from test_vpn_config_arrays import MOCK, CPP, COMPONENT

PATCH = COMPONENT / '0003-return-stored-network-fields-and-preserve-excluded-routes.patch'

BASE = MOCK.replace('struct SysVpnConfig {', r'''
struct Route {
    std::string iface_;
    INetAddr destination_, gateway_;
    bool hasGateway_=false, isDefaultRoute_=false, isExcludedRoute_=false;
};
struct SysVpnConfig {
    std::vector<Route> routes_;
    int32_t mtu_=0, userId_=0;
    bool isAcceptIPv4_=true, isAcceptIPv6_=false, isLegacy_=false, isBlocking_=false;
    std::vector<std::string> acceptedApplications_, refusedApplications_;
''') + r'''
#define CONFIG_MTU "mtu"
#define CONFIG_ISIPV4ACCEPTED "isIPv4Accepted"
#define CONFIG_ISIPV6ACCEPTED "isIPv6Accepted"
#define CONFIG_ISLEGACY "isLegacy"
#define CONFIG_ISBLOCKING "isBlocking"
#define CONFIG_TRUSTEDAPPLICATIONS "trustedApplications"
#define CONFIG_BLOCKEDAPPLICATIONS "blockedApplications"
#define NET_INTERFACE "interface"
#define NET_DESTINATION "destination"
#define NET_GATEWAY "gateway"
#define NET_HAS_GATEWAY "hasGateway"
#define NET_ISDEFAULTROUTE "isDefaultRoute"
#define CONFIG_ROUTES "routes"
'''


def helpers():
    added = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                      if line.startswith('+') and not line.startswith('+++'))
    begin = added.index('namespace {')
    end = added.index('} // namespace', begin) + len('} // namespace')
    return added[begin:end]


class VpnConfigNetworkFieldsTests(unittest.TestCase):
    def test_all_stored_network_flags_routes_and_application_arrays(self):
        compile_run(BASE + helpers() + r'''
int main() {
    for (size_t count : {size_t(0),size_t(1),size_t(2),size_t(256)}) {
        SysVpnConfig input; input.mtu_=1401; input.userId_=100;
        input.isAcceptIPv4_=false; input.isAcceptIPv6_=true;
        input.isLegacy_=true; input.isBlocking_=true;
        for (size_t i=0;i<count;++i) {
            Route r; r.iface_="iface-"+std::to_string(i);
            r.destination_={1,24,"198.18.0."+std::to_string(i),0};
            r.gateway_={2,0,"2001:db8::"+std::to_string(i),255};
            r.hasGateway_=i%2; r.isDefaultRoute_=i%3; r.isExcludedRoute_=i%4;
            input.routes_.push_back(r);
            input.acceptedApplications_.push_back("trusted-"+std::to_string(i));
            input.refusedApplications_.push_back("blocked-"+std::to_string(i));
        }
        auto output=NapiUtils::CreateObject(nullptr);
        SetNetworkConfigFields(nullptr,output,input);
        assert(output->properties.at("mtu")->number==1401);
        assert(output->properties.at("userId")->number==100);
        assert(!output->properties.at("isIPv4Accepted")->boolean);
        assert(output->properties.at("isIPv6Accepted")->boolean);
        assert(output->properties.at("isLegacy")->boolean);
        assert(output->properties.at("isBlocking")->boolean);
        if (!count) {
            assert(!output->properties.count("routes"));
            assert(!output->properties.count("trustedApplications"));
            assert(!output->properties.count("blockedApplications"));
        } else {
            const auto& actual=output->properties.at("routes")->elements;
            assert(actual.size()==count);
            for(size_t i=0;i<count;++i) {
                const auto& expected=input.routes_[i]; auto route=actual[i];
                auto destination=route->properties.at("destination");
                auto address=destination->properties.at("address");
                auto gateway=route->properties.at("gateway");
                assert(destination->properties.at("prefixLength")->number==24);
                assert(address->properties.at("address")->text==expected.destination_.address_);
                assert(address->properties.at("family")->number==1);
                assert(address->properties.at("port")->number==0);
                assert(gateway->properties.at("address")->text==expected.gateway_.address_);
                assert(gateway->properties.at("family")->number==2);
                assert(gateway->properties.at("port")->number==255);
                assert(route->properties.at("interface")->text==expected.iface_);
                assert(route->properties.at("hasGateway")->boolean==expected.hasGateway_);
                assert(route->properties.at("isDefaultRoute")->boolean==expected.isDefaultRoute_);
                assert(route->properties.at("isExcludedRoute")->boolean==expected.isExcludedRoute_);
                assert(output->properties.at("trustedApplications")->elements[i]->text==
                    input.acceptedApplications_[i]);
                assert(output->properties.at("blockedApplications")->elements[i]->text==
                    input.refusedApplications_[i]);
            }
        }
        values.clear();
    }
}
''', language='c++')

    def test_independent_native_changes_are_not_cached(self):
        compile_run(BASE + helpers() + r'''
int main() {
    SysVpnConfig input; input.mtu_=1400; input.userId_=100;
    auto first=NapiUtils::CreateObject(nullptr); SetNetworkConfigFields(nullptr,first,input);
    input.mtu_=1500; input.userId_=101; input.isAcceptIPv4_=false;
    input.isAcceptIPv6_=true; input.isBlocking_=true;
    auto second=NapiUtils::CreateObject(nullptr); SetNetworkConfigFields(nullptr,second,input);
    assert(first->properties.at("mtu")->number==1400);
    assert(first->properties.at("userId")->number==100);
    assert(first->properties.at("isIPv4Accepted")->boolean);
    assert(!first->properties.at("isIPv6Accepted")->boolean);
    assert(!first->properties.at("isBlocking")->boolean);
    assert(second->properties.at("mtu")->number==1500);
    assert(second->properties.at("userId")->number==101);
    assert(!second->properties.at("isIPv4Accepted")->boolean);
    assert(second->properties.at("isIPv6Accepted")->boolean);
    assert(second->properties.at("isBlocking")->boolean);
}
''', language='c++')

    def test_exact_recipe_parses_exclusion_and_wires_all_typed_variants(self):
        hunks = patch_sections(PATCH)
        self.assertEqual(set(hunks), {CPP})
        text = PATCH.read_text()
        self.assertIn('+    GetBoolFromJsOptionItem(env, jsRoute, "isExcludedRoute", route.isExcludedRoute_);', text)
        self.assertEqual(text.count('+    SetNetworkConfigFields(env, config, *sysVpnConfig);'), 1)
        self.assertNotIn('pkcs12', helpers())


if __name__ == '__main__':
    unittest.main()
