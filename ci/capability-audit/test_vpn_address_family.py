"""Exact native family methods with modeled NAPI under ASan/UBSan; not guest proof."""
from pathlib import Path
import re
import unittest
from test_access_token_kernel import compile_run, patch_sections
from test_vpn_config_prefix import MOCK as PREFIX_MOCK

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays'
PATCH = COMPONENT / '0005-validate-requested-address-family-before-narrowing.patch'
PREFIX = 'foundation/communication/netmanager_ext/frameworks/js/napi/'
FILES = ('vpn/src/context/setup_context.cpp', 'vpn/src/vpn_config_utils.cpp',
         'vpnext/src/context/setup_context_ext.cpp', 'vpnext/src/vpn_config_utils_ext.cpp')


def method(file, name, patched=True):
    source = '\n'.join('\n'.join(hunk[2 if patched else 1]) for hunk in patch_sections(PATCH)[PREFIX + file])
    matches = list(re.finditer(r'^(?:static )?bool ' + re.escape(name) + r'\(', source, re.M))
    if len(matches) != 1:
        raise AssertionError('one complete actual native method required: ' + file + ':' + name)
    begin = matches[0].start(); brace = source.index('{', begin); end = brace + 1; depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}'); end += 1
    return source[begin:end] + '\n'


MOCK = PREFIX_MOCK.replace('struct Env { bool failNumber = false; };',
    'struct Env { bool failNumber=false, failHas=false, failGet=false, failType=false; };')
MOCK = MOCK.replace('napi_undefined, napi_object, napi_string, napi_number',
    'napi_undefined, napi_object, napi_string, napi_number, napi_null, napi_boolean, napi_function, napi_symbol, napi_bigint')
MOCK = MOCK.replace('static_cast<uint8_t>(value->number)',
    'static_cast<uint8_t>(NapiUtils::GetUint32Property(env, object, key))')
MOCK = MOCK.replace('static napi_valuetype GetValueType(', '''static bool HasNamedProperty(Env*, Value* object, const char* key) {
        return object && object->properties.count(key);
    }
    static std::string GetStringPropertyUtf8(Env* env, Value* object, const char* key) {
        auto value=GetNamedProperty(env, object, key); return value ? value->text : "";
    }
    static napi_valuetype GetValueType(''')
MOCK += r'''
constexpr uint8_t NET_FAMILY_IPV4=1, NET_FAMILY_IPV6=2;
#define NET_DESTINATION "destination"
#define NET_GATEWAY "gateway"
napi_status napi_has_named_property(Env* env, Value* object, const char* key, bool* result) {
    if (env->failHas || !object || object->kind!=napi_object) return napi_generic_failure;
    *result=object->properties.count(key); return napi_ok;
}
napi_status napi_get_named_property(Env* env, Value* object, const char* key, Value** result) {
    if (env->failGet || !object || object->kind!=napi_object) return napi_generic_failure;
    *result=NapiUtils::GetNamedProperty(env,object,key); return napi_ok;
}
napi_status napi_typeof(Env* env, Value* value, napi_valuetype* result) {
    if (env->failType) return napi_generic_failure;
    *result=value ? value->kind : napi_undefined; return napi_ok;
}
void CheckConstants() {
    assert(NET_FAMILY_IPV4==1 && NET_FAMILY_IPV6==2);
    assert(IPV6_NET_PREFIX_MAX_LENGTH==128 && NET_MASK_MAX_LENGTH==32);
}
'''


class VpnAddressFamilyTests(unittest.TestCase):
    def test_exact_four_helpers_valid_families_absent_and_explicit_undefined_default(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(MOCK + method(file, 'ParseAddressFamily') + r'''
int main() {
    CheckConstants(); Env env; Value network, value; network.properties["family"]=&value;
    for (double family:{1.,2.}) {
        value.kind=napi_number; value.number=family; uint8_t result=17;
        assert(ParseAddressFamily(&env,&network,result) && result==family);
    }
    uint8_t result=17; value.kind=napi_undefined;
    assert(ParseAddressFamily(&env,&network,result) && result==1);
    result=17; network.properties.erase("family");
    assert(ParseAddressFamily(&env,&network,result) && result==1);
}
''', language='c++')

    def test_exact_four_helpers_invalid_original_numbers_and_types_do_not_narrow_or_write(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(MOCK + method(file, 'ParseAddressFamily') + r'''
int main() {
    CheckConstants(); Env env; Value network, value; network.properties["family"]=&value;
    value.kind=napi_number;
    for(double family:{-1.,0.,3.,257.,258.,4294967297.,1.5,2.5,1e20,
        std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),
        -std::numeric_limits<double>::infinity()}) {
        value.number=family; uint8_t result=17;
        assert(!ParseAddressFamily(&env,&network,result) && result==17);
    }
    for(auto type:{napi_string,napi_object,napi_null,napi_boolean,napi_function,napi_symbol,napi_bigint}) {
        value.kind=type; value.number=1; uint8_t result=17;
        assert(!ParseAddressFamily(&env,&network,result) && result==17);
    }
}
''', language='c++')

    def test_presence_get_type_and_number_failures_are_not_optional_default_success(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(MOCK + method(file, 'ParseAddressFamily') + r'''
int main() {
    CheckConstants(); Value network, value; network.properties["family"]=&value;
    value.kind=napi_number; value.number=1;
    for(int failure=0;failure<4;++failure) {
        Env env; env.failHas=failure==0; env.failGet=failure==1;
        env.failType=failure==2; env.failNumber=failure==3; uint8_t result=17;
        assert(!ParseAddressFamily(&env,&network,result) && result==17);
    }
}
''', language='c++')

    def test_both_real_system_config_address_and_hostname_paths_use_validated_default(self):
        for file in (FILES[1], FILES[3]):
            with self.subTest(file=file):
                compile_run(MOCK + method(file, 'ParseAddressFamily') + method(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.2","audit.example"}) {
        Input input(ip,24); INetAddr result; input.network.properties.erase("family");
        assert(ParseAddress(&env,&input.link,result) && result.family_==1);
        input.network.properties["family"]=&input.family;
        input.family.number=257; result.family_=17;
        assert(!ParseAddress(&env,&input.link,result) && result.family_==17);
    }
}
''', language='c++')

    def test_both_real_destination_and_gateway_paths_reject_wrapping_and_use_defaults(self):
        for file in (FILES[1], FILES[3]):
            with self.subTest(file=file):
                compile_run(MOCK + method(file, 'ParseAddressFamily') +
                    method(file, 'ParseDestination') + method(file, 'ParseGateway') + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24); Value route;
    route.properties["destination"]=&input.link; route.properties["gateway"]=&input.network;
    INetAddr dest, gateway; input.network.properties.erase("family");
    assert(ParseDestination(&env,&route,dest) && dest.family_==1);
    assert(ParseGateway(&env,&route,gateway) && gateway.family_==1);
    input.network.properties["family"]=&input.family;
    for(double family:{257.,258.,1.5}) {
        input.family.number=family; dest.family_=gateway.family_=17;
        assert(!ParseDestination(&env,&route,dest) && dest.family_==17);
        assert(!ParseGateway(&env,&route,gateway) && gateway.family_==17);
    }
}
''', language='c++')

    def test_original_standard_and_extension_helpers_accept_wrapped_family(self):
        for file in (FILES[0], FILES[2]):
            with self.subTest(file=file):
                result = compile_run(MOCK + method(file, 'ParseAddressFamily', False) + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24); input.family.number=257;
    uint8_t result=17; assert(!ParseAddressFamily(&env,&input.network,result));
}
''', language='c++', expect_success=False)
                self.assertNotEqual(result.returncode, 0)

    def test_exact_component_keeps_four_real_paths_and_no_abi_permission_edits(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {PREFIX + file for file in FILES})
        self.assertNotIn('.h b/', PATCH.read_text())
        self.assertNotIn('CheckPermission', PATCH.read_text())
        for file in FILES:
            source = method(file, 'ParseAddressFamily')
            self.assertLess(source.index('std::isfinite'), source.index('static_cast<uint8_t>'))


if __name__ == '__main__':
    unittest.main()
