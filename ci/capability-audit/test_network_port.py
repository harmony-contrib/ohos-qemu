"""Actual patched network port methods with modeled NAPI/Parcel; not guest proof."""
from pathlib import Path
import re
import unittest
from test_access_token_kernel import compile_run, patch_sections
from test_vpn_address_family import MOCK as FAMILY_MOCK, FILES, method as family_method

ROOT = Path(__file__).resolve().parents[2]
BASE = 'foundation/communication/netmanager_base/'
EXT = 'foundation/communication/netmanager_ext/frameworks/js/napi/'
COMPONENT = ROOT / ('patches/common/' + BASE + 'inet_addr_port')
PATCH = COMPONENT / '0001-preserve-full-sdk-port-and-validate-before-narrowing.patch'
VPN_PATCH = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays/0006-preserve-and-validate-full-sdk-port-at-every-vpn-input.patch'


def source(patch, file, patched=True):
    return '\n'.join('\n'.join(hunk[2 if patched else 1]) for hunk in patch_sections(patch)[file])


def extract(text, pattern):
    matches = list(re.finditer(pattern, text, re.M))
    if len(matches) != 1:
        raise AssertionError('one complete actual method/declaration required: ' + pattern)
    begin = matches[0].start(); brace = text.index('{', begin); end = brace + 1; depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return text[begin:end] + '\n'


def vpn_method(file, name):
    return extract(source(VPN_PATCH, EXT + file), r'^(?:static )?bool ' + name + r'\(')


PORT_HELPER = extract(source(PATCH, BASE + 'utils/napi_utils/src/napi_utils.cpp'),
                      r'^bool GetOptionalUint16Property\(')
MOCK = FAMILY_MOCK.replace('uint8_t prefixlen_ = 7, family_ = 0, port_ = 0;',
    'uint8_t prefixlen_ = 7, family_ = 0; uint16_t port_ = 0;')
MOCK = MOCK.replace('struct NapiUtils {', '''
napi_status napi_has_named_property(Env*, Value*, const char*, bool*);
napi_status napi_get_named_property(Env*, Value*, const char*, Value**);
napi_status napi_typeof(Env*, Value*, napi_valuetype*);
struct NapiUtils {
static ''' + PORT_HELPER)
MOCK += '\n#define NETMGR_EXT_LOG_I(...) ((void)0)\n'

CODEC_MOCK = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <new>
#include <string>
#include <vector>
#define NETMGR_LOG_E(...) ((void)0)
template<class T> struct sptr : std::shared_ptr<T> {
    sptr(T* value=nullptr):std::shared_ptr<T>(value) {}
};
struct Parcel {
    std::vector<uint32_t> words;
    std::vector<std::string> strings;
    size_t word=0, text=0, failWrite=SIZE_MAX, writes=0;
    bool WriteUint32(uint32_t value) {
        if (writes++==failWrite) return false;
        words.push_back(value); return true;
    }
    // The pinned c_utils codec pads uint8/uint16 as uint32, not one/two bytes.
    bool WriteUint8(uint8_t value) { return WriteUint32(value); }
    bool WriteUint16(uint16_t value) { return WriteUint32(value); }
    bool ReadUint32(uint32_t& value) {
        if (word==words.size()) return false;
        value=words[word++]; return true;
    }
    bool ReadUint8(uint8_t& value) {
        uint32_t full; if(!ReadUint32(full)) return false;
        value=static_cast<uint8_t>(full); return true;
    }
    bool WriteString(const std::string& value) {
        if (writes++==failWrite) return false;
        strings.push_back(value); return true;
    }
    bool ReadString(std::string& value) {
        if (text==strings.size()) return false;
        value=strings[text++]; return true;
    }
};
struct Parcelable { virtual ~Parcelable()=default; virtual bool Marshalling(Parcel&) const=0; };
'''


def codec(patched=True):
    header = extract(source(PATCH, BASE + 'interfaces/innerkits/include/inet_addr.h', patched),
                     r'^struct INetAddr final') + ';\n'
    text = source(PATCH, BASE + 'frameworks/native/netconnclient/src/inet_addr.cpp', patched)
    return CODEC_MOCK + header + '\n'.join(extract(text, pattern) for pattern in (
        r'^bool INetAddr::Marshalling\(Parcel &parcel\) const',
        r'^sptr<INetAddr> INetAddr::Unmarshalling\(',
        r'^bool INetAddr::Marshalling\(Parcel &parcel, const sptr<INetAddr> &object\)'))


class NetworkPortTests(unittest.TestCase):
    def test_exact_helper_preserves_full_range_and_optional_defaults(self):
        compile_run(MOCK + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24);
    for(double value:{0.,1.,255.,256.,8080.,65535.}) {
        uint16_t result=17; input.port.number=value;
        assert(NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result));
        assert(result==value);
    }
    uint16_t result=17; input.port.kind=napi_undefined;
    assert(NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result) && result==0);
    result=17; input.network.properties.erase("port");
    assert(NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result) && result==0);
}
''', language='c++')

    def test_exact_helper_rejects_original_invalid_numbers_types_without_writing(self):
        compile_run(MOCK + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24);
    for(double value:{-1.,65536.,65537.,8080.5,4294967297.,1e20,
        std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),
        -std::numeric_limits<double>::infinity()}) {
        input.port.number=value; uint16_t result=17;
        assert(!NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result) && result==17);
    }
    for(auto type:{napi_string,napi_object,napi_null,napi_boolean,napi_function,napi_symbol,napi_bigint}) {
        input.port.kind=type; uint16_t result=17;
        assert(!NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result) && result==17);
    }
}
''', language='c++')

    def test_presence_get_type_number_failures_are_not_default_zero_success(self):
        compile_run(MOCK + r'''
int main() {
    CheckConstants(); Input input("198.18.0.2",24);
    for(int failure=0;failure<4;++failure) {
        Env env; env.failHas=failure==0; env.failGet=failure==1;
        env.failType=failure==2; env.failNumber=failure==3; uint16_t result=17;
        assert(!NapiUtils::GetOptionalUint16Property(&env,&input.network,"port",result) && result==17);
    }
}
''', language='c++')

    def test_all_four_actual_vpn_address_paths_preserve_wide_ports_and_reject_wrapping(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(MOCK + family_method(file, 'ParseAddressFamily') + vpn_method(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env;
    for(auto ip:{"198.18.0.2","ffff:ffff:ffff:ffff::2"}) {
        Input input(ip,24); INetAddr result;
        for(double port:{0.,255.,256.,8080.,65535.}) {
            input.port.number=port;
            assert(ParseAddress(&env,&input.link,result) && result.port_==port);
        }
        for(double port:{-1.,65536.,65537.,1.5,std::numeric_limits<double>::quiet_NaN()}) {
            input.port.number=port; result.port_=17;
            assert(!ParseAddress(&env,&input.link,result) && result.port_==17);
        }
    }
}
''', language='c++')

    def test_all_four_actual_destination_gateway_defaults_and_port_failures(self):
        for file in FILES:
            with self.subTest(file=file):
                compile_run(MOCK + family_method(file, 'ParseAddressFamily') +
                    vpn_method(file, 'ParseDestination') + vpn_method(file, 'ParseGateway') + r'''
int main() {
    CheckConstants(); Env env; Input input("198.18.0.2",24); Value route;
    route.properties["destination"]=&input.link; route.properties["gateway"]=&input.network;
    INetAddr destination, gateway;
    for(double port:{0.,255.,256.,8080.,65535.}) {
        input.port.number=port;
        assert(ParseDestination(&env,&route,destination) && destination.port_==port);
        assert(ParseGateway(&env,&route,gateway) && gateway.port_==port);
    }
    input.network.properties.erase("port"); destination.port_=gateway.port_=17;
    assert(ParseDestination(&env,&route,destination) && destination.port_==0);
    assert(ParseGateway(&env,&route,gateway) && gateway.port_==0);
    input.network.properties["port"]=&input.port;
    for(double port:{-1.,65536.,1.5}) {
        input.port.number=port; destination.port_=gateway.port_=17;
        assert(!ParseDestination(&env,&route,destination) && destination.port_==17);
        assert(!ParseGateway(&env,&route,gateway) && gateway.port_==17);
    }
}
''', language='c++')

    def test_actual_system_hostname_paths_cannot_bypass_port_validation(self):
        for file in (FILES[1], FILES[3]):
            with self.subTest(file=file):
                compile_run(MOCK + family_method(file, 'ParseAddressFamily') + vpn_method(file, 'ParseAddress') + r'''
int main() {
    CheckConstants(); Env env; Input input("audit.example",24); INetAddr result;
    input.port.number=65535; assert(ParseAddress(&env,&input.link,result) && result.port_==65535);
    input.port.number=65536; result.port_=17;
    assert(!ParseAddress(&env,&input.link,result) && result.port_==17);
}
''', language='c++')

    def test_both_actual_native_writers_and_reader_preserve_ports_and_following_slot(self):
        compile_run(codec() + r'''
int main() {
    for(uint16_t port:{0,1,255,256,8080,65535}) {
        INetAddr value; value.type_=2; value.family_=2; value.prefixlen_=64;
        value.address_="2001:db8::2"; value.netMask_="mask"; value.hostName_="host"; value.port_=port;
        for(bool shared:{false,true}) {
            Parcel parcel; sptr<INetAddr> object=new INetAddr(value);
            assert(shared ? INetAddr::Marshalling(parcel,object) : value.Marshalling(parcel));
            assert(parcel.words.size()==4 && parcel.words.back()==port);
            assert(parcel.WriteUint32(0x12345678));
            auto read=INetAddr::Unmarshalling(parcel); uint32_t tail;
            assert(read && read->port_==port && read->address_==value.address_ && read->family_==2);
            assert(parcel.ReadUint32(tail) && tail==0x12345678 && parcel.word==parcel.words.size());
        }
    }
    Parcel empty; assert(!INetAddr::Marshalling(empty,sptr<INetAddr>()));
}
''', language='c++')

    def test_actual_codec_fails_closed_for_truncation_invalid_port_and_each_writer_error(self):
        compile_run(codec() + r'''
int main() {
    INetAddr value; value.address_="198.18.0.2"; value.port_=8080;
    Parcel good; assert(value.Marshalling(good));
    for(size_t length=0;length<good.words.size();++length) {
        Parcel bad=good; bad.words.resize(length); assert(!INetAddr::Unmarshalling(bad));
    }
    for(size_t length=0;length<good.strings.size();++length) {
        Parcel bad=good; bad.strings.resize(length); assert(!INetAddr::Unmarshalling(bad));
    }
    for(uint32_t port:{65536u,UINT32_MAX}) {
        Parcel bad=good; bad.words.back()=port; assert(!INetAddr::Unmarshalling(bad));
    }
    for(size_t failure=0;failure<7;++failure) {
        Parcel bad; bad.failWrite=failure; assert(!value.Marshalling(bad));
        Parcel other; other.failWrite=failure; sptr<INetAddr> object=new INetAddr(value);
        assert(!INetAddr::Marshalling(other,object));
    }
}
''', language='c++')

    def test_all_three_actual_connection_contexts_validate_ports_before_callback_or_parse_success(self):
        getters = r'''
    static int32_t GetInt32FromValue(Env*, Value* value) { return value->number; }
    static uint32_t GetUint32FromValue(Env*, Value* value) { return value->number; }
    static int32_t GetInt32Property(Env* env, Value* object, const char* key) {
        return GetUint32Property(env, object, key);
    }
    static std::string GetStringFromValueUtf8(Env*, Value* value) { return value->text; }
    static bool GetBooleanProperty(Env*, Value*, const char*) { return false; }
'''
        mocks = MOCK.replace('struct NapiUtils {', 'struct NapiUtils {' + getters) + r'''
#define NETMANAGER_BASE_LOGE(...) ((void)0)
#define NETMANAGER_ERR_PARAMETER_ERROR 401
#define PARAM_DOUBLE_OPTIONS 2
#define PARAM_DOUBLE_OPTIONS_AND_CALLBACK 3
#define PARAM_TRIPLE_OPTIONS 3
#define ARG_INDEX_0 0
#define ARG_INDEX_1 1
#define ARG_INDEX_2 2
struct Route { std::string iface_; INetAddr destination_,gateway_; bool hasGateway_=false,isDefaultRoute_=false; };
struct ContextFixture {
    Env env;
    bool parseOK=false, needThrow=false;
    int32_t error=0, callbacks=0, netId_=0;
    uint32_t vlanId_=0;
    std::string ifName_;
    INetAddr address_;
    Route route_;
    napi_env GetEnv() { return &env; }
    void SetNeedThrowException(bool value) { needThrow=value; }
    void SetErrorCode(int32_t value) { error=value; }
    void SetParseOK(bool value) { parseOK=value; }
    napi_status SetCallback(napi_value) { ++callbacks; return napi_ok; }
};
'''
        for stem, name in (('addnetworkroute', 'AddNetworkRouteContext'),
                           ('addvlanip', 'AddVlanIpContext'), ('deletevlanip', 'DeleteVlanIpContext')):
            text = source(PATCH, BASE + 'frameworks/js/napi/connection/async_context/src/' + stem + '_context.cpp')
            method = extract(text, r'^void ' + name + r'::ParseParams\(')
            declaration = '\nstruct ' + name + ': ContextFixture { void ParseParams(napi_value*, size_t); };\n'
            preflight = r'''
bool CheckParamsType(napi_env, napi_value* params, size_t count) {
    return params && (count==PARAM_DOUBLE_OPTIONS || count==PARAM_DOUBLE_OPTIONS_AND_CALLBACK);
}
''' if stem == 'addnetworkroute' else ''
            if stem == 'addnetworkroute':
                caller = r'''
    Value id, route, callback; id.kind=napi_number; id.number=100; callback.kind=napi_function;
    route.properties={{"destination",&input.link},{"gateway",&input.network}};
    napi_value params[]={&id,&route,&callback};
    for(size_t count:{2,3}) {
        for(double port:{0.,255.,256.,8080.,65535.}) {
            input.port.number=port; CONTEXT context; context.ParseParams(params,count);
            assert(context.parseOK && !context.needThrow && !context.error && context.callbacks==(count==3));
            assert(context.route_.destination_.port_==port && context.route_.gateway_.port_==port);
        }
        for(double port:{-1.,65536.,65537.,1.5}) {
            input.port.number=port; CONTEXT context; context.ParseParams(params,count);
            assert(!context.parseOK && context.needThrow && context.error==401 && !context.callbacks);
        }
    }
'''
            else:
                caller = r'''
    Value name, id; name.kind=napi_string; name.text="eth0"; id.kind=napi_number; id.number=1;
    napi_value params[]={&name,&id,&input.link};
    for(double port:{0.,255.,256.,8080.,65535.}) {
        input.port.number=port; CONTEXT context; context.ParseParams(params,3);
        assert(context.parseOK && !context.needThrow && !context.error && context.address_.port_==port);
    }
    for(double port:{-1.,65536.,65537.,1.5}) {
        input.port.number=port; CONTEXT context; context.ParseParams(params,3);
        assert(!context.parseOK && context.needThrow && context.error==401);
    }
'''
            with self.subTest(stem=stem):
                compile_run(mocks + declaration + preflight + method +
                    '\nint main() { CheckConstants(); Input input("198.18.0.2",24);\n' +
                    caller.replace('CONTEXT', name) + '\n}\n', language='c++')

    def test_original_actual_innerkit_codec_truncates_wide_ports(self):
        result = compile_run(codec(False) + r'''
int main() {
    INetAddr value; value.port_=static_cast<decltype(value.port_)>(8080);
    Parcel parcel; assert(value.Marshalling(parcel));
    auto read=INetAddr::Unmarshalling(parcel); volatile int wanted=8080;
    assert(read && read->port_==wanted);
}
''', language='c++', expect_success=False)
        self.assertNotEqual(result.returncode, 0)

    def test_complete_components_and_build_order_without_permission_or_sdk_edits(self):
        base = patch_sections(PATCH); ext = patch_sections(VPN_PATCH)
        self.assertEqual(len(base), 7)
        self.assertEqual(set(ext), {EXT + file for file in FILES})
        self.assertIn('uint16_t port_ = 0;', source(PATCH, BASE + 'interfaces/innerkits/include/inet_addr.h'))
        self.assertNotIn('CheckPermission', VPN_PATCH.read_text())
        for file in FILES:
            after = source(VPN_PATCH, EXT + file)
            self.assertNotIn('GetUint8FromJsOptionItem(env, netAddress, NET_PORT', after)
            self.assertNotIn('GetUint8FromJsOptionItem(env, gateway, NET_PORT', after)
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(build.count('bash "${INET_ADDR_PORT_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertLess(build.index('bash "${INET_ADDR_PORT_COMPONENT_SCRIPT}" --source-root'),
                        build.index('bash "${VPN_CONFIG_ARRAYS_COMPONENT_SCRIPT}" --source-root'))


if __name__ == '__main__':
    unittest.main()
