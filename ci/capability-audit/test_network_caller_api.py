"""Actual constructor/error template with a token API double; not guest proof."""
from pathlib import Path
import base64
import gzip
import hashlib
import re
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/netmanager_base/caller_api_version/0001-capture-caller-api-version-before-selecting-business-errors.patch'


def constructor(repaired):
    data = gzip.decompress(base64.b64decode((Path(__file__).with_name('fixtures') /
        'network_base_context.cpp.gz.b64').read_bytes()))
    if hashlib.sha256(data).hexdigest() != '2ae13a50856041f4807f9a4d53f1e858ce1364843ba203c3aab4c8c5de01f7b5':
        raise ValueError('complete pinned constructor fixture differs')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / 'foundation/communication/netmanager_base/utils/napi_utils/src/base_context.cpp'
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        if repaired:
            subprocess.run(['git', '-C', str(root), 'apply', str(PATCH)], check=True)
            data = target.read_bytes()
            if hashlib.sha256(data).hexdigest() != '0310af124ad55596e34025876cbdc14ef675b668912d4164af096cc29f16a34a':
                raise ValueError('complete patched constructor differs')
    source = data.decode()
    match = re.search(r'BaseContext::BaseContext\([\s\S]*?^}', source, re.M)
    if not match:
        raise ValueError('complete actual constructor absent')
    return match.group()


DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <limits>
#include <memory>
#include <string>
#include <type_traits>
using napi_env=void*;using napi_value=void*;using napi_callback_info=void*;
using AsyncWorkExecutor=void(*)(napi_env,void*);using AsyncWorkCallback=AsyncWorkExecutor;
constexpr int napi_ok=0,napi_function=7;constexpr size_t MAX_PARAM_NUM=64;
constexpr int API_VERSION_THROW_BUSINESS_EXCEPTION=24;
struct EventManager{};
static int callerApi,deleted,code,businessCalls,legacyCalls;static std::string message;
struct NativeEngine { int32_t GetApiVersion() { return callerApi; } };
static NativeEngine engine;
struct BaseContext{
 std::shared_ptr<EventManager> manager_;napi_env env_;bool parseOK_,requestOK_;int32_t errorCode_;
 napi_value callback_,asyncWork_,deferred_;bool needPromise_,needThrowException_;uint32_t releaseVersion_;
 BaseContext(napi_env,std::shared_ptr<EventManager>&);virtual ~BaseContext(){++deleted;}
 void ParseParams(napi_value*,size_t){needThrowException_=true;errorCode_=401;}
 bool IsNeedThrowException(){return needThrowException_;}
 uint32_t GetReleaseVersion(){return releaseVersion_;}int32_t GetErrorCode(){return errorCode_;}
 std::string GetErrorMessage(){return "actual parameter rejection";}
 void CreateAsyncWork(const std::string&,AsyncWorkExecutor,AsyncWorkCallback){assert(false);}
 napi_value GetCallback(){return callback_;}bool IsNeedPromise(){return needPromise_;}
 napi_value CreatePromise(){assert(false);return nullptr;}
};
struct Context:BaseContext{Context(napi_env e,std::shared_ptr<EventManager>&m):BaseContext(e,m){}};
int napi_unwrap(napi_env,napi_value,void**out){*out=nullptr;return napi_ok;}
static int napi_get_cb_info(napi_env,napi_callback_info,size_t*,napi_value*,napi_value*,void*){return napi_ok;}
static int napi_throw_business_error(napi_env,int32_t c,const char*m){code=c;message=m;++businessCalls;return napi_ok;}
static int napi_throw_error(napi_env,const char*c,const char*m){code=std::stoi(c);message=m;++legacyCalls;return napi_ok;}
struct NapiUtils{static napi_value GetUndefined(napi_env){return nullptr;}static int GetValueType(napi_env,napi_value){return 0;}};
#define NAPI_CALL(env,expr) do{assert((expr)==napi_ok);}while(0)
#define NETMANAGER_BASE_LOGE(...) ((void)0)
'''

def interface():
    path = ROOT / 'ci/capability-audit/fixtures/network_module_interface.cpp'
    if hashlib.sha256(path.read_bytes()).hexdigest() != '0bc69e8049aacc1c78c8d30a4941cf95250ba9aa2830920bc75621447537d1b8':
        raise ValueError('complete pinned error template differs')
    manager = ROOT / 'ci/capability-audit/fixtures/network_module_interface_with_manager.cpp'
    if hashlib.sha256(manager.read_bytes()).hexdigest() != '62397dc0ee632932b942c7779d56d95e04a8aeb8899cbbce6584372aa5074cfd':
        raise ValueError('actual manager template differs')
    return path.read_text() + manager.read_text()


class CallerApiTests(unittest.TestCase):
    def test_original_api26_constructor_selects_legacy_string_error(self):
        source = DOUBLES + constructor(False) + interface() + r'''
int main(){callerApi=26;assert(!InterfaceWithoutManager<Context>(&engine,nullptr,"invalid",nullptr,nullptr,nullptr));
 assert(legacyCalls==1&&!businessCalls&&code==401&&deleted==1);}
'''
        compile_run(source, language='c++')

    def test_repaired_real_template_numeric_boundary_and_old_nonhap_versions(self):
        # Compile the complete fixed Release template body, with no behavioral edits.
        source = DOUBLES + constructor(True) + interface() + r'''
int main(){for(auto item:{std::pair<int,bool>{-1,false},{0,false},{9,false},{23,false},
 {24,true},{26,true},{70000023,false},{70000024,true},{70000026,true},
 {50000023,false},{60000026,true},{70000000,false}}){callerApi=item.first;
 legacyCalls=businessCalls=deleted=0;code=0;message.clear();
 assert(!InterfaceWithoutManager<Context>(&engine,nullptr,"invalid",nullptr,nullptr,nullptr));
 assert(deleted==1&&code==401&&message=="actual parameter rejection");
 assert(businessCalls==item.second&&legacyCalls==!item.second);
 legacyCalls=businessCalls=deleted=0;
 assert(!Interface<Context>(&engine,nullptr,"invalid",nullptr,nullptr,nullptr));
 assert(deleted==1&&code==401&&businessCalls==item.second&&legacyCalls==!item.second);}
 callerApi=70000026;legacyCalls=businessCalls=0;
 assert(!Interface<Context>(nullptr,nullptr,"invalid",nullptr,nullptr,nullptr));
 assert(legacyCalls==1&&businessCalls==0);}

'''
        compile_run(source, language='c++')


if __name__ == '__main__':
    unittest.main()
