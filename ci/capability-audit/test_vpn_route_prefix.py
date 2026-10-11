"""Exact route parsing under ASan/UBSan; not VPN IPC/store/guest evidence."""
from pathlib import Path
import unittest

from test_access_token_kernel import compile_run, patch_sections
from test_vpn_config_prefix import MOCK

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays/0004-validate-route-prefix-before-narrowing.patch'
CPP = 'foundation/communication/netmanager_ext/frameworks/js/napi/vpn/src/vpn_config_utils.cpp'


def source(patched=True):
    # Model the real existing optional uint8 conversion (uint32 then uint8),
    # not an undefined host floating-point-to-uint8 cast.
    mock = MOCK.replace('static_cast<uint8_t>(value->number)',
                        'static_cast<uint8_t>(NapiUtils::GetUint32Property(env, object, key))')
    return mock + '\n#define NET_DESTINATION "destination"\n' + '\n'.join(
        '\n'.join(hunk[2 if patched else 1]) for hunk in patch_sections(PATCH)[CPP])


class VpnRoutePrefixTests(unittest.TestCase):
    def test_actual_route_families_default_and_host_prefixes(self):
        compile_run(source() + r'''
int main() {
    Env env;
    for (auto ip : {"198.18.1.0", "2001:db8:2::"}) {
        for (int prefix = 0; prefix <= (CommonUtils::IsValidIPV6(ip) ? 128 : 32); ++prefix) {
            Input input(ip, prefix); Value route; route.properties["destination"] = &input.link;
            INetAddr result; assert(ParseDestination(&env, &route, result));
            assert(result.address_ == ip && result.prefixlen_ == prefix);
            assert(result.family_ == input.family.number && result.port_ == 0);
        }
    }
}
''', language='c++')

    def test_invalid_original_numbers_types_and_napi_failures(self):
        compile_run(source() + r'''
int main() {
    Env env;
    for (auto ip : {"198.18.1.0", "2001:db8:2::"}) {
        double width = CommonUtils::IsValidIPV6(ip) ? 128 : 32;
        for (double prefix : {-1., -255., width+1, 257., 4294967297., 2.5, 1e20,
                std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(),
                -std::numeric_limits<double>::infinity()}) {
            Input input(ip, prefix); Value route; route.properties["destination"] = &input.link;
            INetAddr result; assert(!ParseDestination(&env, &route, result));
            assert(result.prefixlen_ == 7);
        }
    }
    Input input("198.18.1.0", 24); Value route; route.properties["destination"] = &input.link;
    INetAddr result; env.failNumber = true; assert(!ParseDestination(&env, &route, result));
    env.failNumber = false; input.prefix.kind = napi_string;
    assert(!ParseDestination(&env, &route, result));
    input.link.properties.erase("prefixLength"); assert(!ParseDestination(&env, &route, result));
}
''', language='c++')

    def test_malformed_destination_and_non_ip_are_still_rejected(self):
        compile_run(source() + r'''
int main() {
    Env env; INetAddr result; Value route;
    assert(!ParseDestination(&env, &route, result));
    Input input("audit.example", 24); route.properties["destination"] = &input.link;
    assert(!ParseDestination(&env, &route, result));
    input.address.text = "198.18.1.0"; input.network.kind = napi_string;
    assert(!ParseDestination(&env, &route, result));
    input.network.kind = napi_object; input.link.kind = napi_string;
    assert(!ParseDestination(&env, &route, result));
}
''', language='c++')

    def test_original_parser_accepts_wrapped_prefix_instead_of_failing(self):
        result = compile_run(source(False) + r'''
int main() {
    assert(IPV6_NET_PREFIX_MAX_LENGTH == 128 && NET_MASK_MAX_LENGTH == 32);
    Env env; INetAddr result; Input input("198.18.1.0", 257);
    Value route; route.properties["destination"] = &input.link;
    assert(!ParseDestination(&env, &route, result));
}
''', language='c++', expect_success=False)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
