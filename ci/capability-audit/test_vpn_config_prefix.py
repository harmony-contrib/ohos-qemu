"""Exact native prefix-parser regressions under ASAN/UBSAN, not guest proof."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays'
PATCH = COMPONENT / '0002-parse-the-requested-network-prefix-before-narrowing.patch'
CPP = 'foundation/communication/netmanager_ext/frameworks/js/napi/vpn/src/vpn_config_utils.cpp'

MOCK = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <string>
enum napi_valuetype { napi_undefined, napi_object, napi_string, napi_number };
struct Value {
    napi_valuetype kind = napi_object;
    std::map<std::string, Value*> properties;
    std::string text;
    double number = 0;
};
struct Env { bool failNumber = false; };
using napi_env = Env*;
using napi_value = Value*;
enum napi_status { napi_ok, napi_generic_failure };
napi_status napi_get_value_double(Env* env, Value* value, double* result) {
    if (env->failNumber || !value || value->kind != napi_number) return napi_generic_failure;
    *result = value->number; return napi_ok;
}
struct NapiUtils {
    static Value* GetNamedProperty(Env*, Value* object, const char* key) {
        auto it = object->properties.find(key);
        return it == object->properties.end() ? nullptr : it->second;
    }
    static napi_valuetype GetValueType(Env*, Value* value) {
        return value ? value->kind : napi_undefined;
    }
    static uint32_t GetUint32Property(Env* env, Value* object, const char* key) {
        auto value = GetNamedProperty(env, object, key);
        // Model the NAPI uint32 conversion without C++ undefined float casts.
        double n = std::fmod(std::trunc(value->number), 4294967296.0);
        return std::isfinite(n) ? static_cast<uint32_t>(n < 0 ? n + 4294967296.0 : n) : 0;
    }
};
struct INetAddr { std::string address_; uint8_t prefixlen_ = 7, family_ = 0, port_ = 0; };
struct CommonUtils {
    static bool IsValidIPV6(const std::string& address) {
        in6_addr result{}; return inet_pton(AF_INET6, address.c_str(), &result) == 1;
    }
    static bool IsValidIPV4(const std::string& address) {
        in_addr result{}; return inet_pton(AF_INET, address.c_str(), &result) == 1;
    }
    static uint32_t ConvertIpv4Address(const std::string& address) {
        in_addr result{}; assert(inet_pton(AF_INET, address.c_str(), &result) == 1);
        return ntohl(result.s_addr);
    }
    static int32_t Ipv6PrefixLen(const std::string& address) {
        // The pinned helper counts leading mask bits. 2001:db8::2 starts
        // with 0x20 and therefore returns zero, not its requested /64.
        in6_addr result{}; assert(inet_pton(AF_INET6, address.c_str(), &result) == 1);
        int32_t prefix = 0;
        for (auto byte : result.s6_addr) {
            if (byte == 0xff) { prefix += 8; continue; }
            for (auto pair : {std::pair<int,int>{0xfe,7},{0xfc,6},{0xf8,5},
                              {0xf0,4},{0xe0,3},{0xc0,2},{0x80,1}}) {
                if (byte == pair.first) { prefix += pair.second; break; }
            }
            break;
        }
        return prefix;
    }
};
bool GetStringFromJsMandatoryItem(Env* env, Value* object, const char* key, std::string& result) {
    auto value = NapiUtils::GetNamedProperty(env, object, key);
    if (!value || value->kind != napi_string) return false;
    result = value->text; return true;
}
void GetUint8FromJsOptionItem(Env* env, Value* object, const char* key, uint8_t& result) {
    auto value = NapiUtils::GetNamedProperty(env, object, key);
    if (value && value->kind == napi_number) result = static_cast<uint8_t>(value->number);
}
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_W(...) ((void)0)
#define NET_ADDRESS "address"
#define NET_PREFIXLENGTH "prefixLength"
#define NET_FAMILY "family"
#define NET_PORT "port"
constexpr int IPV6_NET_PREFIX_MAX_LENGTH = 128, NET_MASK_MAX_LENGTH = 32;
struct Input {
    Value address, prefix, family, port, network, link;
    Input(const std::string& ip, double length) {
        address.kind = napi_string; address.text = ip;
        prefix.kind = family.kind = port.kind = napi_number;
        prefix.number = length; family.number = CommonUtils::IsValidIPV6(ip) ? 2 : 1;
        port.number = 0;
        network.properties = {{"address",&address},{"family",&family},{"port",&port}};
        link.properties = {{"address",&network},{"prefixLength",&prefix}};
    }
};
'''


def function(patched=True):
    combined = '\n'.join('\n'.join(hunk[2 if patched else 1]) for hunk in patch_sections(PATCH)[CPP])
    begin = combined.index('bool ParseAddress(')
    brace = combined.index('{', begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (combined[end] == '{') - (combined[end] == '}')
        end += 1
    return combined[begin:end] + '\n'


class VpnConfigPrefixTests(unittest.TestCase):
    def test_requested_ipv4_ipv6_prefixes_and_native_fields(self):
        compile_run(MOCK + function() + r'''
int main() {
    Env env;
    for (auto ip : {"198.18.0.2", "2001:db8::2", "ffff:ffff:ffff:ffff::2"}) {
        for (int length : CommonUtils::IsValidIPV6(ip) ? std::initializer_list<int>{1,64,96,127}
                                                     : std::initializer_list<int>{1,24,30}) {
            Input input(ip,length); INetAddr result;
            assert(ParseAddress(&env,&input.link,result));
            assert(result.address_ == ip && result.prefixlen_ == length);
            assert(result.family_ == input.family.number && result.port_ == 0);
        }
    }
}
''', language='c++')

    def test_invalid_original_numbers_never_wrap_or_truncate(self):
        compile_run(MOCK + function() + r'''
int main() {
    Env env;
    for (auto ip : {"198.18.0.2", "2001:db8::2"}) {
        double width = CommonUtils::IsValidIPV6(ip) ? 128 : 32;
        for (double n : {0.,-1.,-255.,2.5,width,width+1,256.,257.,4294967297.,
                         1e20,std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}) {
            Input input(ip,n); INetAddr result;
            assert(!ParseAddress(&env,&input.link,result));
            assert(result.prefixlen_ == 7);
        }
    }
    Input valid("198.18.0.2",24); INetAddr result;
    env.failNumber = true; assert(!ParseAddress(&env,&valid.link,result));
    env.failNumber = false; valid.prefix.kind = napi_string;
    assert(!ParseAddress(&env,&valid.link,result));
    valid.link.properties.erase("prefixLength"); assert(!ParseAddress(&env,&valid.link,result));
}
''', language='c++')

    def test_existing_network_broadcast_and_domain_behavior_is_preserved(self):
        compile_run(MOCK + function() + r'''
int main() {
    Env env;
    for (auto ip : {"198.18.0.0", "198.18.0.255"}) {
        Input input(ip,24); INetAddr result;
        assert(!ParseAddress(&env,&input.link,result));
    }
    Input domain("audit.example",64); INetAddr result;
    assert(ParseAddress(&env,&domain.link,result));
    assert(result.address_ == "audit.example" && result.prefixlen_ == 7);
    Input bad("198.18.0.2",24); bad.network.kind = napi_string;
    assert(!ParseAddress(&env,&bad.link,result));
}
''', language='c++')

    def test_original_implementation_fails_real_ipv6_prefix_regression(self):
        result = compile_run(MOCK + function(False) + r'''
int main() {
    Env env; Input input("2001:db8::2",64); INetAddr result;
    assert(ParseAddress(&env,&input.link,result) && result.prefixlen_ == 64);
}
''', language='c++', expect_success=False)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
