#!/usr/bin/env python3
"""Execute the patched unsolicited producer and registry with dependency doubles.

This does not claim a modem/HDI/product runtime pass; real generated HDI and full
platform TUs are a separate parent-owned gate.
"""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import ROOT, function

COMPONENT = ROOT/'patches/common/base/telephony/state_registry/communication_state'
FIXTURE = Path(__file__).parent/'fixtures/batch_location/communication_runtime_before.json'


def sources(prefix=None):
    files=json.loads(FIXTURE.read_text())['files']
    with tempfile.TemporaryDirectory(prefix='batch-location-communication-src-') as directory:
        root=Path(directory)
        for name,text in files.items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        patches=sorted(COMPONENT.glob('*.patch'))
        for patch in patches if prefix is None else patches[:prefix]:
            subprocess.run(['git','apply',str(patch)],cwd=root,check=True,capture_output=True)
        return {name:(root/name).read_bytes().decode() for name in files}


def compile_run(program):
    with tempfile.TemporaryDirectory(prefix='batch-location-communication-') as directory:
        root=Path(directory);(root/'test.cpp').write_text(program)
        result=subprocess.run(['clang++','-std=c++17','-pthread','-fsanitize=address,undefined',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        result=subprocess.run([str(root/'test')],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        if result.returncode:raise AssertionError(result.stdout+result.stderr)


PRODUCER = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <shared_mutex>
#include <mutex>
#include <string>
#include <vector>
constexpr int HRIL_ERR_SUCCESS=0,HRIL_ERR_INVALID_PARAMETER=2,TELEPHONY_SUCCESS=0,TELEPHONY_ERR_ARGUMENT_INVALID=1,TELEPHONY_STATE_REGISTRY_PERMISSION_DENIED=201,TELEPHONY_STATE_REGISTRY_SLODID_ERROR=3;
constexpr int HNOTI_NETWORK_COMMUNICATION_STATE_UPDATED=1412,HRIL_NOTIFICATION=1;
#define TELEPHONY_LOGE(...) ((void)0)
#define TELEPHONY_LOGI(...) ((void)0)
using HRilErrNumber=int;
namespace HDI{namespace Ril{namespace V1_1{enum RilErrType{NONE=0};enum RilResponseTypes{RIL_RESPONSE_NOTICE=2,RIL_RESPONSE_NOTICE_MUST_ACK=4};struct RilRadioResponseInfo{int slotId=0;RilErrType error=NONE;RilResponseTypes type=RIL_RESPONSE_NOTICE;};}namespace V1_5{struct IRilCallback{virtual ~IRilCallback()=default;virtual int32_t CommunicationStateUpdated(const V1_1::RilRadioResponseInfo&,bool)=0;};}}}
namespace Permission{constexpr const char* SET_TELEPHONY_STATE="set";constexpr const char* GET_NETWORK_INFO="read";}
int callingToken=1;bool publishPermission=true;std::map<int,bool> readPermissions{{11,true},{12,true},{13,true}};
struct IPCSkeleton{static int GetCallingTokenID(){return callingToken;}static std::string ResetCallingIdentity(){auto saved=std::to_string(callingToken);callingToken=1;return saved;}static void SetCallingIdentity(const std::string& v){callingToken=std::stoi(v);}};
namespace Security{namespace AccessToken{constexpr int TOKEN_NATIVE=1,PERMISSION_GRANTED=0;struct NativeTokenInfo{std::string processName;};struct AccessTokenKit{static int GetTokenTypeFlag(int token){return token==1||token==2?TOKEN_NATIVE:0;}static int GetNativeTokenInfo(int token,NativeTokenInfo& out){out.processName=token==1?"telephony":"unrelated";return 0;}static int VerifyAccessToken(int token,const char*){return readPermissions[token]?0:1;}};}}
struct TelephonyPermission{static bool CheckPermission(const char*){return publishPermission;}};
struct TelephonyObserverBroker{static constexpr uint32_t OBSERVER_MASK_COMMUNICATION_STATE=0x2000;std::vector<bool> events;std::vector<int> slots;void OnCommunicationStateUpdated(int slot,bool state){slots.push_back(slot);events.push_back(state);}};
struct TelephonyStateRegistryRecord{int slotId_=0,tokenId_=11;uint32_t mask_=0x2000;std::shared_ptr<TelephonyObserverBroker> telephonyObserver_=std::make_shared<TelephonyObserverBroker>();bool IsExistStateListener(uint32_t mask)const{return telephonyObserver_&&(mask_&mask);}};
struct TelephonyStateRegistryService{std::shared_mutex lock_;std::map<int,bool> communicationStates_;std::vector<TelephonyStateRegistryRecord> stateRecords_;bool VerifySlotId(int slot){return slot>=0&&slot<2;}int UpdateCommunicationState(int,bool);};
TelephonyStateRegistryService service;
struct TelephonyStateRegistryClient{static TelephonyStateRegistryClient& GetInstance(){static TelephonyStateRegistryClient v;return v;}int UpdateCommunicationState(int slot,bool state){return service.UpdateCommunicationState(slot,state);}};
template<class T>struct DelayedRefSingleton{static T& GetInstance(){return T::GetInstance();}};
struct TelRilNetwork{int slotId_=0;int CommunicationStateUpdated(bool);};
struct TelRilManager{std::shared_ptr<TelRilNetwork> network=std::make_shared<TelRilNetwork>();int acks=0;void SendAckAndLock(){++acks;}std::shared_ptr<TelRilNetwork> GetTelRilNetwork(int slot){network->slotId_=slot;return network;}};
struct TelRilCallback:HDI::Ril::V1_5::IRilCallback{std::shared_ptr<TelRilManager> telRilManager_=std::make_shared<TelRilManager>();int CommunicationStateUpdated(const HDI::Ril::V1_1::RilRadioResponseInfo&,bool)override;
 template<class F,class M,class...A>int Notify(HDI::Ril::V1_1::RilRadioResponseInfo info,F f,M m,A&&...a){if(info.slotId<0||info.slotId>=2)return 1;if(info.type==HDI::Ril::V1_1::RIL_RESPONSE_NOTICE_MUST_ACK)telRilManager_->SendAckAndLock();auto module=(telRilManager_.get()->*f)(info.slotId);return (module.get()->*m)(std::forward<A>(a)...);}
};
TelRilCallback callback;
struct HRilNetwork{int slot=0;int CommunicationStateUpdated(int,HRilErrNumber,const void*,size_t);template<class F>int Notify(int type,int,F f,bool state){HDI::Ril::V1_1::RilRadioResponseInfo info;info.slotId=slot;info.type=static_cast<HDI::Ril::V1_1::RilResponseTypes>(type);return (callback.*f)(info,state);}} network;
struct ReportInfo{int notifyId=0,error=0,type=0;};
int GetSlotId(void*){return network.slot;}
int reports=0;
void OnNetworkReport(int slot,ReportInfo report,const uint8_t* response,size_t size){assert(slot==network.slot&&report.notifyId==1412&&report.error==0&&report.type==HRIL_NOTIFICATION&&size==4);++reports;assert(network.CommunicationStateUpdated(2,report.error,response,size)==0);}
'''
PRODUCER_MAIN = r'''
int main(){
 service.stateRecords_.resize(3);service.stateRecords_[1].slotId_=1;service.stateRecords_[1].tokenId_=12;service.stateRecords_[2].tokenId_=13;service.stateRecords_[2].mask_=1;
 assert(service.communicationStates_.empty());auto first=service.stateRecords_[0].telephonyObserver_;auto other=service.stateRecords_[1].telephonyObserver_;
 assert(ReportCommunicationState("+OHOS5A: 1")&&first->events==std::vector<bool>{true}&&other->events.empty());assert(ReportCommunicationState("+OHOS5A:0\r\n")&&first->events==std::vector<bool>({true,false}));
 assert(ReportCommunicationState("+OHOS5A:0")&&first->events.size()==2);assert(!ReportCommunicationState("+CEREG: 1"));
 for(const char* value:{"+OHOS5A:","+OHOS5A:2","+OHOS5A:-1","+OHOS5A:01","+OHOS5A:1,1","+OHOS5A: 1 nope"})assert(ReportCommunicationState(value));assert(reports==3);
 network.slot=1;assert(ReportCommunicationState("+OHOS5A:\t1 ")&&other->events==std::vector<bool>{true});
 int32_t invalid=2;assert(network.CommunicationStateUpdated(2,0,&invalid,4)==2);invalid=0;assert(network.CommunicationStateUpdated(2,1,&invalid,4)==2);assert(network.CommunicationStateUpdated(2,0,&invalid,1)==2);assert(network.CommunicationStateUpdated(2,0,nullptr,4)==2);
 char unaligned[5];int32_t value=0;std::memcpy(unaligned+1,&value,4);assert(network.CommunicationStateUpdated(2,0,unaligned+1,4)==0&&other->events==std::vector<bool>({true,false}));
 callingToken=3;assert(service.UpdateCommunicationState(0,true)==201);callingToken=2;assert(service.UpdateCommunicationState(0,true)==201);callingToken=1;publishPermission=false;assert(service.UpdateCommunicationState(0,true)==201);publishPermission=true;assert(service.UpdateCommunicationState(-1,true)==3);assert(service.UpdateCommunicationState(2,true)==3);
 readPermissions[11]=false;assert(service.UpdateCommunicationState(0,true)==0&&first->events.size()==2);readPermissions[11]=true;assert(service.UpdateCommunicationState(0,false)==0&&first->events==std::vector<bool>({true,false,false}));
 HDI::Ril::V1_1::RilRadioResponseInfo info;info.slotId=2;assert(callback.CommunicationStateUpdated(info,true)==1);info.slotId=0;info.type=HDI::Ril::V1_1::RIL_RESPONSE_NOTICE_MUST_ACK;callingToken=2;assert(callback.CommunicationStateUpdated(info,true)==0&&callingToken==2&&callback.telRilManager_->acks==1&&first->events.back());
}
'''


class CommunicationRuntimeTests(unittest.TestCase):
    def test_actual_vendor_notification_hril_and_registry(self):
        files=sources()
        program=PRODUCER
        for name,signature in [
            ('base/telephony/state_registry/services/src/telephony_state_registry_service.cpp','int32_t TelephonyStateRegistryService::UpdateCommunicationState('),
            ('base/telephony/core_service/services/tel_ril/src/tel_ril_network.cpp','int32_t TelRilNetwork::CommunicationStateUpdated('),
            ('base/telephony/core_service/services/tel_ril/src/tel_ril_callback.cpp','int32_t TelRilCallback::CommunicationStateUpdated('),
            ('base/telephony/ril_adapter/services/hril/src/hril_network.cpp','int32_t HRilNetwork::CommunicationStateUpdated('),
            ('base/telephony/ril_adapter/services/vendor/src/vendor_report.c','static void ReportInfoInit('),
            ('base/telephony/ril_adapter/services/vendor/src/vendor_report.c','static bool ReportCommunicationState('),
        ]:program+=function(files[name],signature)
        compile_run(program+PRODUCER_MAIN)


from test_batch_location_ble_napi import PREAMBLE as CALLBACK_PREAMBLE
NAPI = CALLBACK_PREAMBLE[:CALLBACK_PREAMBLE.index('struct RefBase')]
NAPI = NAPI.replace('napi_number,napi_function','napi_number,napi_function,napi_boolean')
NAPI += r'''
#include <set>
using uv_loop_s=Env;struct uv_work_t{void* data=nullptr;};constexpr int uv_qos_default=0;
int uv_queue_work_with_qos(Env* env,uv_work_t* work,void(*)(uv_work_t*),void(*complete)(uv_work_t*,int),int){env->jobs.push_back([work,complete]{complete(work,0);});return 0;}
namespace AppExecFwk{struct InnerEvent{using Pointer=std::shared_ptr<InnerEvent>;void* object=nullptr;template<class T>std::unique_ptr<T> GetUniqueObject(){auto* value=static_cast<T*>(object);object=nullptr;return std::unique_ptr<T>(value);}};}
constexpr int TELEPHONY_SUCCESS=0,TELEPHONY_ERR_CALLBACK_ALREADY_REGISTERED=1,TELEPHONY_ERR_LOCAL_PTR_NULL=2,TELEPHONY_STATE_REGISTRY_PERMISSION_DENIED=201,TELEPHONY_STATE_UNREGISTRY_DATA_NOT_EXIST=3,ERROR_SLOT_ID_INVALID=8300001;
constexpr int EVENT_LISTENER_DIFF=-1,EVENT_LISTENER_SAME=0,EVENT_LISTENER_SLOTID_AND_EVENTTYPE_SAME=1,DEFAULT_SIM_SLOT_ID=0,SIM_SLOT_COUNT=2,JS_ERROR_TELEPHONY_PERMISSION_DENIED=201;
constexpr const char* OBSERVER_JS_PERMISSION_ERROR_STRING="permission";
#define TELEPHONY_LOGI(...) ((void)0)
#define TELEPHONY_LOGE(...) ((void)0)
#define TELEPHONY_LOGD(...) ((void)0)
enum class TelephonyUpdateEventType{NONE_EVENT_TYPE=0,EVENT_CALL_STATE_UPDATE=1,EVENT_SIM_STATE_UPDATE=2,EVENT_CALL_STATE_EX_UPDATE=3,EVENT_CCALL_STATE_UPDATE=4,EVENT_SIM_ACTIVE_STATE=5,EVENT_SIGNAL_STRENGTHS_UPDATE=6,EVENT_COMMUNICATION_STATE=0x2000};
template<class T>uint32_t ToUint32t(T v){return static_cast<uint32_t>(v);}
struct EventListener{napi_env env=nullptr;TelephonyUpdateEventType eventType=TelephonyUpdateEventType::NONE_EVENT_TYPE;int slotId=0;napi_ref callbackRef=nullptr;std::shared_ptr<bool> isDeleting;};
struct ObserverContext{int slotId=0,errorCode=0;bool resolved=false;napi_ref callbackRef=nullptr;TelephonyUpdateEventType eventType=TelephonyUpdateEventType::NONE_EVENT_TYPE;std::list<EventListener> removeListenerList;};
struct JsError{int errorCode;std::string errorMessage;};
struct NapiUtil{static void ThrowError(Env* e,int code,const std::string&){e->error=code;}static void ThrowParameterError(Env* e){e->error=401;}static Value* CreateUndefined(Env*){return &undefinedValue;}static JsError ConverErrorMessageForJs(int e){return {e,"error"};}static JsError ConverErrorMessageCallStateExForJs(int e){return {e,"error"};}};
namespace Permission{constexpr const char* GET_NETWORK_INFO="network";}
bool allowed=true;
struct IPCSkeleton{static int GetSelfTokenID(){return 7;}};
namespace Security{namespace AccessToken{constexpr int PERMISSION_GRANTED=0;struct AccessTokenKit{static int VerifyAccessToken(int,const char*){return allowed?0:1;}};}}
struct UpdateInfo{int32_t slotId_;explicit UpdateInfo(int32_t slot):slotId_(slot){}};
struct CommunicationStateUpdate:UpdateInfo{bool is5A;CommunicationStateUpdate(int32_t slot,bool state):UpdateInfo(slot),is5A(state){}};
struct CommunicationStateContext:EventListener{bool is5A;CommunicationStateContext& operator=(const CommunicationStateUpdate& value){is5A=value.is5A;return *this;}};
Value* GetNapiValue(Env* e,bool value){auto out=make(*e,napi_boolean);out->number=value;return out;}
bool InitLoop(Env* e,Env** loop){*loop=e;return true;}
struct TelephonyObserverBroker{virtual ~TelephonyObserverBroker()=default;};struct NapiTelephonyObserver:TelephonyObserverBroker{};
template<class T>using sptr=std::shared_ptr<T>;
struct TelephonyStateManager{static int adds,removes;static int AddStateObserver(std::shared_ptr<TelephonyObserverBroker>,int,uint32_t,bool){++adds;return 0;}static int RemoveStateObserver(int,uint32_t){++removes;return 0;}};int TelephonyStateManager::adds=0,TelephonyStateManager::removes=0;
struct EventListenerHandler{static std::mutex operatorMutex_;std::list<EventListener> listenerList_;static std::map<TelephonyUpdateEventType,void(*)(uv_work_t*,std::unique_lock<std::mutex>&)> workFuncMap_;
 bool IsCallBackRegister(napi_env,napi_ref,napi_ref)const;int CheckEventListenerRegister(EventListener&);int RegisterEventListener(EventListener&);static void SetEventListenerDeleting(std::shared_ptr<bool>);bool CheckEventTypeExist(int,TelephonyUpdateEventType);void CheckRemoveStateObserver(TelephonyUpdateEventType,int,int&);int UnregisterCommunicationListener(napi_env,napi_ref,int32_t,std::list<EventListener>&);void UnRegisterAllListener(napi_env);
 bool IsNeedHandleCallbackUpdate(TelephonyUpdateEventType a,TelephonyUpdateEventType b,int s,int t){return a==b&&s==t;}
 template<class T,class D,TelephonyUpdateEventType eventType>void HandleCallbackInfoUpdate(const AppExecFwk::InnerEvent::Pointer&);
 static void WorkUpdated(uv_work_t*,int);static void WorkCommunicationUpdated(uv_work_t*,std::unique_lock<std::mutex>&);
};
std::mutex EventListenerHandler::operatorMutex_;std::map<TelephonyUpdateEventType,void(*)(uv_work_t*,std::unique_lock<std::mutex>&)> EventListenerHandler::workFuncMap_{{TelephonyUpdateEventType::EVENT_COMMUNICATION_STATE,EventListenerHandler::WorkCommunicationUpdated}};
EventListenerHandler handler;
struct EventListenerManager{static int RegisterEventListener(EventListener& v){return handler.RegisterEventListener(v);}static int UnregisterCommunicationListener(napi_env e,napi_ref r,int32_t s,std::list<EventListener>& l){return handler.UnregisterCommunicationListener(e,r,s,l);}static void UnRegisterAllListener(napi_env e){handler.UnRegisterAllListener(e);}};
bool IsValidSlotIdEx(TelephonyUpdateEventType,int slot){return slot>=0&&slot<SIM_SLOT_COUNT;}
void emit(int slot,bool value){auto event=std::make_shared<AppExecFwk::InnerEvent>();event->object=new CommunicationStateUpdate(slot,value);handler.HandleCallbackInfoUpdate<CommunicationStateContext,CommunicationStateUpdate,TelephonyUpdateEventType::EVENT_COMMUNICATION_STATE>(event);}
void drain(Env& env){auto jobs=std::move(env.jobs);env.jobs.clear();for(auto& job:jobs)job();assert(env.scopes==0);}
int liveRefs(Env& env){int count=0;for(const auto& ref:env.refs)count+=ref->alive;return count;}
void closeEnv(Env& env){auto hooks=std::move(env.hooks);env.hooks.clear();for(auto hook:hooks)hook.first(hook.second);assert(liveRefs(env)==0);env.alive=false;}
'''
NAPI = '#include <list>\n'+NAPI
NAPI_MAIN = r'''
int main(){
 Env env,other;auto cb=make(env,napi_function);std::vector<bool> received;cb->callback=[&](Value* value){assert(value->type==napi_boolean);received.push_back(bool(value->number));};auto cb2=make(env,napi_function);cb2->callback=cb->callback;
 auto option=[&](double slot){auto out=make(env,napi_object);auto value=make(env,napi_number);value->number=slot;out->properties["slotId"]=value;return out;};
 auto on=[&](Env& e,std::vector<Value*> args){e.error=0;Info info{args};return OnCommunicationStateChange(&e,&info);};auto off=[&](Env& e,std::vector<Value*> args){e.error=0;Info info{args};return OffCommunicationStateChange(&e,&info);};
 assert(on(env,{cb})&&liveRefs(env)==1);assert(on(env,{cb,&undefinedValue})&&liveRefs(env)==1);assert(on(env,{cb,option(1)})&&liveRefs(env)==2);assert(on(env,{cb2,option(0)})&&liveRefs(env)==3);assert(env.hooks.size()==1);
 emit(0,true);off(env,{cb,option(0)});drain(env);assert(received==std::vector<bool>{true}&&liveRefs(env)==2);emit(1,false);drain(env);assert(received==std::vector<bool>({true,false}));
 emit(0,false);off(env,{cb2});on(env,{cb2});drain(env);assert(received.size()==2);emit(0,true);drain(env);assert(received.size()==3&&received.back());
 allowed=false;assert(!on(env,{cb})&&env.error==201);assert(!off(env,{cb})&&env.error==201);allowed=true;
 for(auto args:std::vector<std::vector<Value*>>{{},{cb,option(-1)},{cb,option(2)},{cb,option(0.5)},{cb,&nullValue},{&undefinedValue}}){assert(!on(env,args)&&env.error==401);}
 auto outsider=make(other,napi_function);outsider->callback=[](Value*){};assert(on(other,{outsider,option(0)}));off(env,{cb2});emit(0,true);drain(other);assert(other.calls==1);drain(env);assert(received.size()==3);
 emit(1,true);allowed=false;drain(env);assert(received.size()==3);allowed=true;closeEnv(env);assert(handler.listenerList_.size()==1);emit(0,false);closeEnv(other);drain(other);assert(handler.listenerList_.empty());assert(g_communicationEnvironments.empty());
}
'''


def communication_napi_program(files):
    path='base/telephony/state_registry/frameworks/js/napi/src/'
    source=files[path+'event_listener_handler.cpp'];api=files[path+'napi_state_registry.cpp']
    program=NAPI
    for signature in ['napi_status NapiReturnToJS(', 'bool EventListenerHandler::IsCallBackRegister(',
        'int32_t EventListenerHandler::CheckEventListenerRegister(', 'int32_t EventListenerHandler::RegisterEventListener(',
        'void EventListenerHandler::SetEventListenerDeleting(', 'bool EventListenerHandler::CheckEventTypeExist(',
        'void EventListenerHandler::CheckRemoveStateObserver(', 'int32_t EventListenerHandler::UnregisterCommunicationListener(',
        'void EventListenerHandler::UnRegisterAllListener(', 'void EventListenerHandler::WorkUpdated(',
        'void EventListenerHandler::WorkCommunicationUpdated(']:program+=function(source,signature)
    program+='template<typename T, typename D, TelephonyUpdateEventType eventType>\n'+function(source,'void EventListenerHandler::HandleCallbackInfoUpdate(')
    for signature in ['static void NativeOn(', 'static void OnCallback(', 'static void OffCallback(']:program+=function(api,signature)
    start=api.index('namespace {\nstd::mutex g_communicationEnvironmentMutex');end=api.index('napi_status InitEnumLockReason',start)
    return program+api[start:end]+NAPI_MAIN


def _test_napi(self):
    compile_run(communication_napi_program(sources()))
CommunicationRuntimeTests.test_actual_napi_slot_callbacks_queue_and_env_cleanup=_test_napi

if __name__ == "__main__":
    unittest.main()
