"""Exact remaining VPN prefix parsers with modeled NAPI; not guest proof."""
import unittest
from test_network_port import ROOT, EXT, MOCK as PORT_MOCK, extract, source
from test_vpn_address_family import method as family_method
from test_access_token_kernel import compile_run, patch_sections

PATCH = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays/0007-validate-remaining-setup-and-extension-prefixes.patch'
FILES = ('vpn/src/context/setup_context.cpp', 'vpnext/src/context/setup_context_ext.cpp',
         'vpnext/src/vpn_config_utils_ext.cpp')
MOCK = PORT_MOCK.replace('failType=false;', 'failType=false; Value* failFor=nullptr;')
MOCK = MOCK.replace('if (env->failNumber || !value', 'if (env->failNumber || value==env->failFor || !value')


def method(file, name, patched=True):
    return extract(source(PATCH, EXT + file, patched), r'^(?:static )?bool ' + name + r'\(')


def complete(file, name, patched=True):
    return MOCK + family_method(file, 'ParseAddressFamily') + method(file, name, patched)


class VpnDuplicatePrefixTests(unittest.TestCase):
    def test_actual_requested_address_prefixes_are_not_ipv6_host_masks(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.2","2001:db8::2","ffff:ffff:ffff:ffff::2"}) {
        bool ipv6=CommonUtils::IsValidIPV6(ip);
        for(int prefix:ipv6 ? std::initializer_list<int>{1,24,64,96,127,128}
                            : std::initializer_list<int>{1,24,28,30}) {
            Input input(ip,prefix); input.port.number=65535; INetAddr result;
            assert(ParseAddress(&env,&input.link,result) && result.prefixlen_==prefix && result.port_==65535);
        }
    }
}
''', language='c++')

    def test_original_invalid_address_numbers_never_wrap_truncate_or_derive_mask(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.2","2001:db8::2","ffff:ffff:ffff:ffff::2"}) {
        int width=CommonUtils::IsValidIPV6(ip) ? 128 : 32;
        for(double prefix:{0.,-1.,257.,double(width+1),1.5,4294967297.,1e20,
            std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity()}) {
            Input input(ip,prefix); INetAddr result;
            assert(!ParseAddress(&env,&input.link,result) && result.prefixlen_==7);
        }
    }
}
''', language='c++')

    def test_each_actual_address_path_rejects_missing_types_and_targeted_napi_read_failure(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24); INetAddr result;
    for(auto type:{napi_undefined,napi_string,napi_object,napi_null,napi_boolean}) {
        input.prefix.kind=type; assert(!ParseAddress(&env,&input.link,result) && result.prefixlen_==7);
    }
    input.link.properties.erase("prefixLength");
    assert(!ParseAddress(&env,&input.link,result) && result.prefixlen_==7);
    input.link.properties["prefixLength"]=&input.prefix; input.prefix.kind=napi_number;
    env.failFor=&input.prefix;
    assert(!ParseAddress(&env,&input.link,result) && result.prefixlen_==7);
}
''', language='c++')

    def test_real_destination_paths_preserve_default_and_full_width_routes(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseDestination') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.0","2001:db8::"}) {
        int width=CommonUtils::IsValidIPV6(ip) ? 128 : 32;
        for(int prefix:{0,1,24,width}) {
            Input input(ip,prefix); Value route; route.properties["destination"]=&input.link;
            input.port.number=8080; INetAddr result;
            assert(ParseDestination(&env,&route,result) && result.prefixlen_==prefix && result.port_==8080);
        }
    }
}
''', language='c++')

    def test_actual_route_paths_reject_invalid_types_ranges_and_read_failures_without_writing(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseDestination') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.0","2001:db8::"}) {
        int width=CommonUtils::IsValidIPV6(ip) ? 128 : 32;
        Input input(ip,24); Value route; route.properties["destination"]=&input.link; INetAddr result;
        for(double prefix:{-1.,257.,double(width+1),1.5,4294967297.,1e20,
            std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
            input.prefix.number=prefix;
            assert(!ParseDestination(&env,&route,result) && result.prefixlen_==7);
        }
        for(auto type:{napi_undefined,napi_string,napi_object,napi_null,napi_boolean}) {
            input.prefix.kind=type;
            assert(!ParseDestination(&env,&route,result) && result.prefixlen_==7);
        }
        input.prefix.kind=napi_number; input.prefix.number=24; env.failFor=&input.prefix;
        assert(!ParseDestination(&env,&route,result) && result.prefixlen_==7); env.failFor=nullptr;
        input.link.properties.erase("prefixLength");
        assert(!ParseDestination(&env,&route,result) && result.prefixlen_==7);
    }
}
''', language='c++')

    def test_existing_ipv4_subnet_broadcast_and_ordinary_host_prefix_policy_is_preserved(self):
        for file in FILES:
            host_exception='true' if '/context/' in file else 'false'
            with self.subTest(file=file):
                compile_run(complete(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.0","198.18.0.255"}) {
        Input input(ip,24); INetAddr result; assert(!ParseAddress(&env,&input.link,result));
    }
    Input host("198.18.0.2",32); INetAddr result;
    assert(ParseAddress(&env,&host.link,result)==HOST_EXCEPTION);
}
'''.replace('HOST_EXCEPTION',host_exception), language='c++')

    def test_original_setup_wraps_address_and_original_all_three_routes_wrap_prefix(self):
        for file in FILES:
            if '/context/' in file:
                old=compile_run(complete(file, 'ParseAddress', False) + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",257); INetAddr result;
    assert(!ParseAddress(&env,&input.link,result));
}
''', language='c++', expect_success=False)
                self.assertNotEqual(old.returncode,0)
            old=compile_run(complete(file, 'ParseDestination', False) + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.0",257); INetAddr result;
    Value route; route.properties["destination"]=&input.link;
    assert(!ParseDestination(&env,&route,result));
}
''', language='c++', expect_success=False)
            self.assertNotEqual(old.returncode,0)

    def test_only_the_three_remaining_real_prefix_paths_change_no_sdk_or_permissions(self):
        self.assertEqual(set(patch_sections(PATCH)), {EXT+file for file in FILES})
        for file in FILES:
            after=source(PATCH,EXT+file)
            self.assertNotIn('Ipv6PrefixLen',after)
            self.assertNotIn('GetUint8FromJsOptionItem(env, destination, NET_PREFIXLENGTH',after)
        self.assertNotIn('CheckPermission',PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
