#!/usr/bin/env python3
"""Run the actual new BLE NAPI parser, registry and queued callback functions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import function, runtime_sources

PREAMBLE = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>
using LocationErrCode=int;
constexpr int ERRCODE_SUCCESS=0,ERRCODE_SCAN_FAIL=3301800,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_INVALID_PARAM=401;
constexpr int napi_ok=0,napi_eprio_immediate=1;
struct Env;struct Value;struct Ref;
using napi_env=Env*;using napi_value=Value*;using napi_ref=Ref*;using napi_status=int;using napi_handle_scope=void*;
enum napi_valuetype{napi_undefined,napi_null,napi_object,napi_string,napi_number,napi_function};
struct Value{napi_valuetype type=napi_undefined;bool array=false;std::string text;double number=0;std::vector<napi_value> elements;std::map<std::string,napi_value> properties;std::function<void(napi_value)> callback;};
Value undefinedValue,nullValue{napi_null};
struct Ref{napi_env env; napi_value value;bool alive=true;};
struct Env{bool alive=true;int error=0,scopes=0,calls=0;std::vector<std::unique_ptr<Value>> values;std::vector<std::unique_ptr<Ref>> refs;std::vector<std::function<void()>> jobs;std::vector<std::pair<void(*)(void*),void*>> hooks;};
struct Info{std::vector<napi_value> values;};using napi_callback_info=Info*;
bool addHookFailure=false,removeHookFailure=false,eventFailure=false;
napi_value make(Env& env,napi_valuetype type){env.values.push_back(std::make_unique<Value>());env.values.back()->type=type;return env.values.back().get();}
int napi_get_cb_info(napi_env env,napi_callback_info info,size_t* count,napi_value* args,napi_value*,void**){assert(env->alive);size_t actual=info->values.size(),copy=std::min(*count,actual);for(size_t i=0;i<copy;++i)args[i]=info->values[i];*count=actual;return 0;}
int napi_typeof(napi_env env,napi_value value,napi_valuetype* type){assert(env->alive);if(!value)return 1;*type=value->type;return 0;}
int napi_get_named_property(napi_env env,napi_value value,const char* name,napi_value* result){assert(env->alive);if(!value||value->type!=napi_object)return 1;auto p=value->properties.find(name);*result=p==value->properties.end()?&undefinedValue:p->second;return 0;}
int napi_has_named_property(napi_env env,napi_value value,const char* name,bool* result){assert(env->alive);if(!value||value->type!=napi_object)return 1;*result=value->properties.count(name);return 0;}
int napi_is_array(napi_env env,napi_value value,bool* result){assert(env->alive);*result=value&&value->array;return 0;}
int napi_get_array_length(napi_env env,napi_value value,uint32_t* size){assert(env->alive);if(!value||!value->array)return 1;*size=value->elements.size();return 0;}
int napi_get_element(napi_env env,napi_value value,uint32_t index,napi_value* result){assert(env->alive);if(index>=value->elements.size())return 1;*result=value->elements[index];return 0;}
int napi_get_value_string_utf8(napi_env env,napi_value value,char* buffer,size_t size,size_t* result){assert(env->alive);if(value->type!=napi_string)return 1;*result=value->text.size();if(buffer){assert(size>value->text.size());std::copy(value->text.begin(),value->text.end(),buffer);buffer[value->text.size()]='\0';}return 0;}
int napi_get_value_double(napi_env env,napi_value value,double* result){assert(env->alive);if(value->type!=napi_number)return 1;*result=value->number;return 0;}
int napi_create_reference(napi_env env,napi_value value,int,napi_ref* result){assert(env->alive);env->refs.push_back(std::make_unique<Ref>(Ref{env,value}));*result=env->refs.back().get();return 0;}
int napi_get_reference_value(napi_env env,napi_ref ref,napi_value* value){assert(env->alive&&ref&&ref->alive&&ref->env==env);*value=ref->value;return 0;}
int napi_delete_reference(napi_env env,napi_ref ref){assert(env->alive&&ref&&ref->alive&&ref->env==env);ref->alive=false;return 0;}
int napi_strict_equals(napi_env env,napi_value a,napi_value b,bool* same){assert(env->alive);*same=a==b;return 0;}
int napi_add_env_cleanup_hook(napi_env env,void(*hook)(void*),void* data){assert(env->alive);if(addHookFailure)return 1;env->hooks.push_back({hook,data});return 0;}
int napi_remove_env_cleanup_hook(napi_env env,void(*hook)(void*),void* data){assert(env->alive);if(removeHookFailure)return 1;auto it=std::find(env->hooks.begin(),env->hooks.end(),std::make_pair(hook,data));assert(it!=env->hooks.end());env->hooks.erase(it);return 0;}
int napi_send_event(napi_env env,std::function<void()> job,int){assert(env->alive);if(eventFailure)return 1;env->jobs.push_back(std::move(job));return 0;}
int napi_open_handle_scope(napi_env env,napi_handle_scope* scope){assert(env->alive);++env->scopes;*scope=env;return 0;}
int napi_close_handle_scope(napi_env env,napi_handle_scope){assert(env->alive);--env->scopes;return 0;}
int napi_create_object(napi_env env,napi_value* result){assert(env->alive);*result=make(*env,napi_object);return 0;}
int napi_get_undefined(napi_env env,napi_value* result){assert(env->alive);*result=&undefinedValue;return 0;}
int napi_call_function(napi_env env,napi_value,napi_value handler,int count,napi_value* args,napi_value* result){assert(env->alive&&handler->type==napi_function&&count==1);++env->calls;handler->callback(args[0]);*result=&undefinedValue;return 0;}
void HandleSyncErrCode(napi_env env,int error){env->error=error;}
napi_value UndefinedNapiValue(const napi_env& env){assert(env->alive);return &undefinedValue;}
#define NAPI_CALL(env,expression) do{if((expression)!=napi_ok)return nullptr;}while(false)
#define LBSLOGD(...) ((void)0)
struct RefBase{mutable std::atomic<int> refs{0};virtual ~RefBase()=default;void IncStrongRef()const{++refs;}void DecStrongRef()const{if(--refs==0)delete this;}};
template<class T>class sptr{
 template<class U>friend class sptr;T* ptr=nullptr;
 public:sptr()=default;sptr(std::nullptr_t){}sptr(T* value):ptr(value){if(ptr)ptr->IncStrongRef();}sptr(const sptr& value):sptr(value.ptr){}
 template<class U>sptr(const sptr<U>& value):sptr(value.ptr){}
 ~sptr(){if(ptr)ptr->DecStrongRef();}sptr& operator=(const sptr& value){if(value.ptr)value.ptr->IncStrongRef();if(ptr)ptr->DecStrongRef();ptr=value.ptr;return *this;}
 T* operator->()const{return ptr;}bool operator==(std::nullptr_t)const{return !ptr;}bool operator!=(std::nullptr_t)const{return ptr;}T* GetRefPtr()const{return ptr;}
};
struct BluetoothScanResult{std::string id;int64_t rssi=-42;};
struct IBluetoothScanResultCallback:RefBase{virtual void OnBluetoothScanResultChange(const std::unique_ptr<BluetoothScanResult>&)=0;};
std::mutex g_regCallbackMutex;std::vector<napi_ref> g_registerCallbacks;
struct BluetoothScanResultCallbackNapi:IBluetoothScanResultCallback{
 napi_env env_=nullptr;napi_ref handlerCb_=nullptr;std::mutex mutex_;static int live;
 BluetoothScanResultCallbackNapi(){++live;}~BluetoothScanResultCallbackNapi(){--live;}
 napi_env GetEnv();void SetEnv(const napi_env&);napi_ref GetHandleCb();void SetHandleCb(const napi_ref&);
 void OnBluetoothScanResultChange(const std::unique_ptr<BluetoothScanResult>&)override;
 void DispatchScanResult(const std::shared_ptr<BluetoothScanResult>&);void DeleteHandler();
};
int BluetoothScanResultCallbackNapi::live=0;
void BluetoothScanResultToJs(const napi_env& env,const std::unique_ptr<BluetoothScanResult>& source,napi_value result){assert(env->alive);result->text=source->id;result->number=source->rssi;}
struct LocatorImpl{
 struct Request{std::vector<std::string> ids;bool has;int32_t rssi;sptr<IBluetoothScanResultCallback> callback;};
 std::vector<Request> requests;int startResult=0,stopResult=0,starts=0,stops=0;
 int StartBluetoothSearch(const std::vector<std::string>& ids,bool has,int32_t rssi,const sptr<IBluetoothScanResultCallback>& callback){++starts;if(startResult)return startResult;requests.push_back({ids,has,rssi,callback});return 0;}
 int StopBluetoothSearch(const sptr<IBluetoothScanResultCallback>& callback){++stops;if(stopResult)return stopResult;requests.erase(std::remove_if(requests.begin(),requests.end(),[&](const Request& r){return r.callback.GetRefPtr()==callback.GetRefPtr();}),requests.end());return 0;}
 void Emit(const std::string& id,int64_t rssi){auto result=std::make_unique<BluetoothScanResult>();result->id=id;result->rssi=rssi;auto pending=requests;for(const auto& request:pending)request.callback->OnBluetoothScanResultChange(result);}
};
struct Locator{static std::shared_ptr<LocatorImpl> instance;static std::shared_ptr<LocatorImpl> GetInstance(){return instance;}};
std::shared_ptr<LocatorImpl> Locator::instance=std::make_shared<LocatorImpl>();
void drain(Env& env){auto jobs=std::move(env.jobs);env.jobs.clear();for(auto& job:jobs)job();assert(env.scopes==0);}
int liveRefs(Env& env){int count=0;for(const auto& ref:env.refs)count+=ref->alive;return count;}
void closeEnv(Env& env){auto hooks=std::move(env.hooks);env.hooks.clear();for(auto hook:hooks)hook.first(hook.second);assert(liveRefs(env)==0);env.alive=false;}
'''

MAIN = r'''
int main(){
 Env env,other;auto client=Locator::instance;
 auto stringValue=[&](std::string text){auto value=make(env,napi_string);value->text=text;return value;};
 auto request=make(env,napi_object);auto ids=make(env,napi_object);ids->array=true;ids->elements={stringValue("AA"),stringValue("cc")};request->properties["deviceIdArray"]=ids;
 auto threshold=make(env,napi_number);threshold->number=-50;request->properties["rssiThreshold"]=threshold;
 auto callback=make(env,napi_function);std::vector<std::pair<std::string,int64_t>> received;callback->callback=[&](napi_value value){received.emplace_back(value->text,value->number);};
 auto callback2=make(env,napi_function);callback2->callback=[&](napi_value value){received.emplace_back(value->text,value->number);};
 auto invokeStart=[&](Env& owner,napi_value fn){owner.error=0;Info info{{request,fn}};return StartBluetoothSearch(&owner,&info);};
 auto invokeStop=[&](Env& owner,std::vector<napi_value> args){owner.error=0;Info info{args};return StopBluetoothSearch(&owner,&info);};
 assert(invokeStart(env,callback)==&undefinedValue&&liveRefs(env)==1&&env.hooks.size()==1);
 assert(client->requests.back().ids==std::vector<std::string>({"AA","cc"})&&client->requests.back().has&&client->requests.back().rssi==-50);
 assert(!invokeStart(env,callback)&&env.error==401&&liveRefs(env)==1);
 assert(invokeStart(env,callback2)==&undefinedValue&&liveRefs(env)==2);
 client->Emit("AA",-40);invokeStop(env,{callback});drain(env);assert(env.calls==1&&received.back()==std::make_pair(std::string("AA"),int64_t(-40)));
 client->Emit("AA",-41);assert(invokeStop(env,{&undefinedValue})==&undefinedValue);drain(env);assert(env.calls==1&&liveRefs(env)==0);
 assert(invokeStop(env,{})==&undefinedValue);assert(invokeStop(env,{callback})==&undefinedValue);
 // Stale work cannot call a later registration, even for the same JS function.
 invokeStart(env,callback);client->Emit("old",-1);invokeStop(env,{callback});invokeStart(env,callback);drain(env);assert(env.calls==1);
 client->Emit("new",-2);drain(env);assert(env.calls==2&&received.back().first=="new");
 callback->callback=[&](napi_value){assert(invokeStop(env,{callback})==&undefinedValue);};client->Emit("self",-3);drain(env);assert(env.calls==3&&liveRefs(env)==0);
 auto foreign=make(other,napi_function);foreign->callback=[](napi_value){};invokeStart(other,foreign);
 invokeStop(env,{});client->Emit("other",-4);drain(other);assert(other.calls==1&&liveRefs(other)==1);
 client->Emit("queued-exit",-4);closeEnv(other);drain(other);assert(other.calls==1);
 // Cleanup hooks retain client/registration after the registry owner disappears.
 callback->callback=[](napi_value){};invokeStart(env,callback);client->Emit("orphan",-5);g_bluetoothSearches.clear();closeEnv(env);drain(env);
 assert(client->requests.empty()&&BluetoothScanResultCallbackNapi::live==0);
 Env errors;auto empty=make(errors,napi_object);auto emptyArray=make(errors,napi_object);emptyArray->array=true;empty->properties["deviceIdArray"]=emptyArray;
 auto fn=make(errors,napi_function);fn->callback=[](napi_value){};
 auto start=[&](){errors.error=0;Info info{{empty,fn}};return StartBluetoothSearch(&errors,&info);};
 assert(start()==&undefinedValue);assert(!client->requests.back().has&&client->requests.back().ids.empty());invokeStop(errors,{});
 empty->properties["rssiThreshold"]=&undefinedValue;assert(start()==&undefinedValue);invokeStop(errors,{});
 auto numeric=make(errors,napi_number);empty->properties["rssiThreshold"]=numeric;
 for(double invalid:{0.5,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),2147483648.0,-2147483649.0}){numeric->number=invalid;assert(!start()&&errors.error==401&&liveRefs(errors)==0);}
 for(double valid:{-2147483648.0,2147483647.0}){numeric->number=valid;assert(start()==&undefinedValue);assert(client->requests.back().rssi==int32_t(valid));invokeStop(errors,{});}
 empty->properties["rssiThreshold"]=&nullValue;assert(!start()&&errors.error==401);empty->properties.erase("rssiThreshold");
 emptyArray->elements={&undefinedValue};assert(!start()&&errors.error==401);emptyArray->elements.clear();
 Info badNull{{&nullValue,fn}},badCount{{empty,fn,fn}};assert(!StartBluetoothSearch(&errors,&badNull)&&errors.error==401);assert(!StartBluetoothSearch(&errors,&badCount)&&errors.error==401);
 assert(!invokeStop(errors,{&nullValue})&&errors.error==401);assert(!invokeStop(errors,{fn,fn})&&errors.error==401);
 client->startResult=ERRCODE_SCAN_FAIL;assert(!start()&&errors.error==ERRCODE_SCAN_FAIL&&liveRefs(errors)==0);client->startResult=0;
 addHookFailure=true;assert(!start()&&errors.error==ERRCODE_SERVICE_UNAVAILABLE&&liveRefs(errors)==0&&client->requests.empty());addHookFailure=false;
 assert(start()==&undefinedValue);client->stopResult=ERRCODE_SERVICE_UNAVAILABLE;assert(!invokeStop(errors,{})&&errors.error==ERRCODE_SERVICE_UNAVAILABLE&&liveRefs(errors)==1);client->stopResult=0;
 eventFailure=true;client->Emit("dropped",0);eventFailure=false;
 removeHookFailure=true;invokeStop(errors,{});removeHookFailure=false;assert(liveRefs(errors)==0&&!errors.hooks.empty());closeEnv(errors);drain(errors);
 g_bluetoothSearches.clear();assert(client->requests.empty()&&BluetoothScanResultCallbackNapi::live==0);
 std::cout<<"BLE actual NAPI functions: parser/integer/undefined, callback identity, payload, queued cancellation/reentry, environment and error/ref lifetime boundaries passed\n";
}
'''


class BluetoothNapiTests(unittest.TestCase):
    def test_execute_actual_napi_and_callback_functions(self):
        files = runtime_sources()
        adapter = files['frameworks/js/napi/source/location_napi_adapter.cpp']
        callback = files['frameworks/js/napi/source/bluetooth_scan_result_callback_napi.cpp']
        actual = function(adapter, 'struct BluetoothSearchRegistration {').rstrip() + ';\n'
        actual += 'static std::mutex g_bluetoothSearchMutex;\nstatic std::vector<std::shared_ptr<BluetoothSearchRegistration>> g_bluetoothSearches;\n'
        for signature in ['static void CleanupBluetoothSearch(', 'static bool ReadBluetoothSearchRequest(',
                          'static bool IsBluetoothSearchCallback(', 'napi_value StartBluetoothSearch(', 'napi_value StopBluetoothSearch(']:
            actual += function(adapter, signature)
        actual += function(callback, 'void DeleteBlueToothCallback(')
        for signature in ['napi_env BluetoothScanResultCallbackNapi::GetEnv(', 'void BluetoothScanResultCallbackNapi::SetEnv(',
                          'napi_ref BluetoothScanResultCallbackNapi::GetHandleCb(', 'void BluetoothScanResultCallbackNapi::SetHandleCb(',
                          'void BluetoothScanResultCallbackNapi::OnBluetoothScanResultChange(',
                          'void BluetoothScanResultCallbackNapi::DispatchScanResult(', 'void BluetoothScanResultCallbackNapi::DeleteHandler(']:
            actual += function(callback, signature)
        with tempfile.TemporaryDirectory(prefix='batch-location-ble-napi-') as directory:
            cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
            cpp.write_text(PREAMBLE + actual + MAIN)
            subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined', str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
