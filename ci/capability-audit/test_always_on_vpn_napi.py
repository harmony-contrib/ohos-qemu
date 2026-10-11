"""Compile actual NAPI header with explicit async/IPC doubles; not guest proof."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/netmanager_ext/always_on_vpn/0002-bind-public-always-on-promises-to-real-ipc.patch'


class AlwaysOnVpnNapiTests(unittest.TestCase):
    def test_argument_identity_async_results_failure_and_cancellation(self):
        sections = patch_sections(PATCH)
        header = '\n'.join(next(value for name, value in sections.items() if name.endswith('.h'))[0][2])
        header = '\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <vector>
enum napi_status {napi_ok,napi_generic_failure,napi_cancelled};
enum napi_valuetype {napi_undefined,napi_boolean,napi_string,napi_number,napi_object};
struct Value {napi_valuetype type=napi_undefined;std::string text;bool boolean=false;int number=0,settled=0;Value* value=nullptr;};
struct Work;
using napi_env=void*;using napi_value=Value*;using napi_deferred=Value*;using napi_ref=Value*;
using napi_callback_info=void*;using napi_async_work=Work*;
using Exec=void(*)(napi_env,void*);using Done=void(*)(napi_env,napi_status,void*);
struct Work {Exec exec;Done done;void* data;};
constexpr size_t NAPI_AUTO_LENGTH=static_cast<size_t>(-1);
std::vector<std::unique_ptr<Value>> values;std::vector<Value*> arguments;
int calls=0,failure=0,thrown=0,liveWorks=0,liveRefs=0,ipcCalls=0,remoteResult=0;
bool injectPending=false;Value exceptionValue;Value* pendingException=nullptr;
bool remoteValue=false,lastEnabled=false;std::string lastBundle;Work* queued=nullptr;
napi_status Step(){if(++calls==failure){if(injectPending)pendingException=&exceptionValue;
    return napi_generic_failure;}return napi_ok;}
Value* Make(napi_valuetype type=napi_undefined){values.push_back(std::make_unique<Value>());values.back()->type=type;return values.back().get();}
napi_status napi_get_cb_info(napi_env,napi_callback_info,size_t* count,napi_value* args,napi_value*,void**){
    auto s=Step();if(s==napi_ok){*count=std::min(*count,arguments.size());std::copy_n(arguments.begin(),*count,args);}return s;}
napi_status napi_typeof(napi_env,napi_value value,napi_valuetype* type){auto s=Step();if(s==napi_ok)*type=value->type;return s;}
napi_status napi_get_value_bool(napi_env,napi_value value,bool* result){auto s=Step();if(s==napi_ok)*result=value->boolean;return s;}
napi_status napi_get_value_string_utf8(napi_env,napi_value value,char* buffer,size_t length,size_t* copied){
    auto s=Step();if(s==napi_ok){*copied=buffer?std::min(length-1,value->text.size()):value->text.size();
        if(buffer){std::memcpy(buffer,value->text.data(),*copied);buffer[*copied]=0;}}return s;}
napi_status napi_create_string_utf8(napi_env,const char* text,size_t length,napi_value* result){
    auto s=Step();if(s==napi_ok){*result=Make(napi_string);(*result)->text=std::string(text,length==NAPI_AUTO_LENGTH?std::strlen(text):length);}return s;}
napi_status napi_create_error(napi_env,napi_value,napi_value message,napi_value* result){
    auto s=Step();if(s==napi_ok){*result=Make(napi_object);(*result)->text=message->text;}return s;}
napi_status napi_create_int32(napi_env,int code,napi_value* result){auto s=Step();if(s==napi_ok){*result=Make(napi_number);(*result)->number=code;}return s;}
napi_status napi_set_named_property(napi_env,napi_value object,const char* key,napi_value value){
    assert(std::string(key)=="code" && value->type==napi_number);auto s=Step();if(s==napi_ok)object->number=value->number;return s;}
napi_status napi_throw_business_error(napi_env,int code,const char*){thrown=code;return napi_ok;}
napi_status napi_get_undefined(napi_env,napi_value* result){auto s=Step();if(s==napi_ok)*result=Make();return s;}
napi_status napi_get_boolean(napi_env,bool value,napi_value* result){auto s=Step();if(s==napi_ok){*result=Make(napi_boolean);(*result)->boolean=value;}return s;}
napi_status napi_is_exception_pending(napi_env,bool* pending){*pending=pendingException!=nullptr;return napi_ok;}
napi_status napi_get_and_clear_last_exception(napi_env,napi_value* value){assert(pendingException);
    *value=pendingException;pendingException=nullptr;return napi_ok;}
napi_status napi_create_reference(napi_env,napi_value value,uint32_t count,napi_ref* ref){
    assert(count==1);auto s=Step();if(s==napi_ok){*ref=value;++liveRefs;}return s;}
napi_status napi_get_reference_value(napi_env,napi_ref ref,napi_value* value){assert(ref && liveRefs==1);
    *value=ref;return napi_ok;}
napi_status napi_delete_reference(napi_env,napi_ref ref){assert(ref && liveRefs==1);--liveRefs;return napi_ok;}
napi_status napi_create_promise(napi_env,napi_deferred* deferred,napi_value* result){
    auto s=Step();if(s==napi_ok)*deferred=*result=Make(napi_object);return s;}
napi_status napi_resolve_deferred(napi_env,napi_deferred deferred,napi_value value){
    assert(deferred->settled==0);deferred->settled=1;deferred->value=value;return napi_ok;}
napi_status napi_reject_deferred(napi_env,napi_deferred deferred,napi_value value){
    assert(deferred->settled==0);deferred->settled=-1;deferred->value=value;return napi_ok;}
napi_status napi_create_async_work(napi_env,napi_value,napi_value,Exec exec,Done done,void* data,napi_async_work* work){
    auto s=Step();if(s==napi_ok){*work=new Work{exec,done,data};++liveWorks;}return s;}
napi_status napi_queue_async_work(napi_env,napi_async_work work){auto s=Step();if(s==napi_ok)queued=work;return s;}
napi_status napi_delete_async_work(napi_env,napi_async_work work){assert(work);delete work;--liveWorks;return napi_ok;}
namespace OHOS {namespace NetManagerStandard {
constexpr int NETMANAGER_SUCCESS=0,NETMANAGER_ERR_INTERNAL=2200003,NETMANAGER_EXT_ERR_PARAMETER_ERROR=401;
struct NetBaseErrorCodeConvertor {std::string ConvertErrorCode(int&){return "actual error double";}};
struct NetworkVpnClient {
    static NetworkVpnClient& GetInstance(){static NetworkVpnClient client;return client;}
    int SetAlwaysOnVpnEnabled(bool enabled,const std::string& bundle){++ipcCalls;lastBundle=bundle;lastEnabled=enabled;return remoteResult;}
    int IsAlwaysOnVpnEnabled(const std::string& bundle,bool& enabled){++ipcCalls;lastBundle=bundle;enabled=remoteValue;return remoteResult;}
};
}}
'''
        main = r'''
void Reset(bool write){
    assert(liveWorks==0 && liveRefs==0);values.clear();arguments.clear();calls=failure=thrown=ipcCalls=remoteResult=0;queued=nullptr;
    injectPending=false;pendingException=nullptr;exceptionValue.number=2200003;exceptionValue.type=napi_object;
    if(write){auto value=Make(napi_boolean);value->boolean=true;arguments.push_back(value);}
    auto bundle=Make(napi_string);bundle->text="com.example.vpn";arguments.push_back(bundle);
}
Value* Call(bool write){return write?OHOS::NetManagerStandard::SetAlwaysOnVpnEnabled(nullptr,nullptr):
    OHOS::NetManagerStandard::IsAlwaysOnVpnEnabled(nullptr,nullptr);}
void Finish(napi_status status=napi_ok){auto work=queued;queued=nullptr;assert(work);
    if(status==napi_ok)work->exec(nullptr,work->data);work->done(nullptr,status,work->data);assert(liveWorks==0 && liveRefs==0);}
int main(){
    for(bool write:{false,true}) {
        Reset(write);auto promise=Call(write);int creationCalls=calls;assert(promise && queued && !promise->settled);
        remoteValue=true;Finish();assert(promise->settled==1 && ipcCalls==1 && lastBundle=="com.example.vpn");
        assert(promise->value->type==(write?napi_undefined:napi_boolean));if(write)assert(lastEnabled);else assert(promise->value->boolean);
        Reset(write);remoteValue=false;if(write)arguments.front()->boolean=false;
        arguments.back()->text="com.example.\xe6\xb5\x8b\xe8\xaf\x95";promise=Call(write);Finish();
        assert(promise->settled==1 && ipcCalls==1 && lastBundle=="com.example.\xe6\xb5\x8b\xe8\xaf\x95");
        if(write)assert(!lastEnabled);else assert(!promise->value->boolean);
        for(int error:{201,202,401,2200003}){Reset(write);remoteResult=error;promise=Call(write);Finish();
            assert(promise->settled==-1 && promise->value->number==error && ipcCalls==1);}
        Reset(write);promise=Call(write);Finish(napi_cancelled);assert(promise->settled==-1 && ipcCalls==0);
        for(int point=1;point<=creationCalls;++point){Reset(write);failure=point;promise=Call(write);
            assert(!queued && liveWorks==0 && ipcCalls==0);if(promise)assert(promise->settled==-1);}
        Reset(write);promise=Call(write);failure=calls+1;Finish();assert(promise->settled==-1 && ipcCalls==1);
        // Fail each BusinessError construction operation during completion,
        // both when the engine raises an exception and when it only returns a
        // failure status. The published Promise must settle and release work
        // and its strong fallback reference in both paths.
        for(bool pending:{false,true})for(int point=1;point<=4;++point){
            Reset(write);remoteResult=201;promise=Call(write);failure=calls+point;injectPending=pending;
            Finish();assert(promise->settled==-1 && promise->value && promise->value->number==2200003);
            assert(ipcCalls==1 && !pendingException && liveRefs==0);}
        for(int invalid=0;invalid<6;++invalid){Reset(write);
            if(invalid==0)arguments.clear();if(invalid==1)arguments.push_back(Make());
            if(invalid==2)arguments.back()->text.clear();if(invalid==3)arguments.back()->text=std::string("com.x\0hidden",12);
            if(invalid==4)arguments.back()->type=napi_object;
            if(invalid==5)arguments.front()->type=napi_number;
            assert(Call(write)==nullptr && thrown==401 && !queued && ipcCalls==0 && liveWorks==0);}
    }
}
'''
        compile_run(source + header + main, language='c++')


if __name__ == '__main__':
    unittest.main()
