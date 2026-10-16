#!/usr/bin/env python3
"""Execute actual patched fusion-fence wire, evaluator, service and lifetime boundaries.

Host dependency doubles expose callback/provider boundaries only. This is not a
GNSS/WLAN/modem or product-package runtime pass.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import runtime_sources, function
from test_batch_location_ble_napi import PREAMBLE as NAPI_PREAMBLE

COMMON = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>
struct Parcel;
struct Parcelable {virtual ~Parcelable()=default;virtual bool Marshalling(Parcel&)const=0;};
struct Parcel {
 struct Value{char type;double number;std::string text;};std::vector<Value> values;size_t position=0;
 bool fail=false;
 bool WriteInt32(int32_t v){values.push_back({'i',double(v),{}});return !fail;}
 bool WriteInt64(int64_t v){values.push_back({'l',double(v),{}});return !fail;}
 bool WriteDouble(double v){values.push_back({'d',v,{}});return !fail;}
 bool WriteBool(bool v){values.push_back({'b',double(v),{}});return !fail;}
 bool WriteString(const std::string& v){values.push_back({'s',0,v});return !fail;}
 bool ReadInt32(int32_t& v){if(position>=values.size()||values[position].type!='i')return false;v=values[position++].number;return true;}
 bool ReadInt64(int64_t& v){if(position>=values.size()||values[position].type!='l')return false;v=values[position++].number;return true;}
 bool ReadDouble(double& v){if(position>=values.size()||values[position].type!='d')return false;v=values[position++].number;return true;}
 bool ReadBool(bool& v){if(position>=values.size()||values[position].type!='b')return false;v=values[position++].number;return true;}
 bool ReadString(std::string& v){if(position>=values.size()||values[position].type!='s')return false;v=values[position++].text;return true;}
};
'''
SPTR = NAPI_PREAMBLE[NAPI_PREAMBLE.index('struct RefBase'):NAPI_PREAMBLE.index('struct BluetoothScanResult')]
SPTR = SPTR.replace('T* operator->()const', 'bool operator==(const sptr& other)const{return ptr==other.ptr;}T* operator->()const')
SERVICE = r'''
using ErrCode=int;using LocationErrCode=int;
constexpr int ERRCODE_SUCCESS=0,ERRCODE_INVALID_PARAM=401,ERRCODE_NOT_SUPPORTED=801,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_SWITCH_OFF=3301100;
constexpr int LOCATION_ERRCODE_PERMISSION_DENIED=3300201,LOCATION_ERRCODE_SYSTEM_PERMISSION_DENIED=3300202;
constexpr int GNSS_TYPE=1,RTK_TYPE=4,WGS84=1,ENABLED=1,PRIORITY_ACCURACY=1;
constexpr const char* ACCESS_LOCATION="fine";
int64_t now=100000000000LL;bool fine=true,systemApp=true,currentAccount=true,switchedOn=true,background=false,backgroundGranted=true,frozen=false;
struct CommonUtils{static int64_t GetSinceBootTime(){return now;}template<class T>static bool IsAppBelongCurrentAccount(const T&){return currentAccount;}};
struct AppIdentity{int uid=100001,pid=10;uint32_t token=7,first=0;uint64_t ex=9;std::string bundle="owner";
 int GetUid()const{return uid;}int GetPid()const{return pid;}uint32_t GetTokenId()const{return token;}uint32_t GetFirstTokenId()const{return first;}uint64_t GetTokenIdEx()const{return ex;}std::string GetBundleName()const{return bundle;}};
AppIdentity caller;
struct PermissionManager{static bool CheckLocationPermission(uint32_t,uint32_t){return fine;}static bool CheckSystemPermission(uint32_t,uint64_t){return systemApp;}static bool CheckBackgroundPermission(uint32_t,uint32_t){return backgroundGranted;}};
struct ReportManager{static ReportManager* GetInstance(){static ReportManager v;return &v;}bool IsAppBackground(const std::string&,uint32_t,uint64_t,int,int){return background;}};
struct LocationDataRdbManager{static int QuerySwitchStateWithUid(int){return switchedOn;}};
struct ProxyFreezeManager{static ProxyFreezeManager* GetInstance(){static ProxyFreezeManager v;return &v;}bool IsProxyPid(int){return frozen;}};
namespace Security{namespace AccessToken{struct AccessTokenKit{static int GetPermissionUsedType(uint32_t,const char*){return 1;}};}}
struct MessageOption{enum{TF_ASYNC=1};explicit MessageOption(int){}};
struct MessageParcel:Parcel{std::u16string descriptor;bool WriteInterfaceToken(const std::u16string& d){descriptor=d;return true;}};
template<class T>struct wptr{};
struct IRemoteObject:RefBase{
 struct DeathRecipient:RefBase{virtual void OnRemoteDied(const wptr<IRemoteObject>&)=0;};
 std::vector<int> events;std::vector<std::string> identifiers;bool deathOkay=true;sptr<DeathRecipient> death;
 bool IsProxyObject(){return true;}bool AddDeathRecipient(sptr<DeathRecipient> d){death=d;return deathOkay;}void RemoveDeathRecipient(sptr<DeathRecipient>){death=nullptr;}
 int SendRequest(int code,MessageParcel& p,MessageParcel&,MessageOption&){assert(code==1&&p.descriptor==u"location.IFusionFenceCallback");events.push_back(int(p.values[2].number));identifiers.push_back(p.values[0].text);return 0;}
 sptr<IRemoteObject> AsObject(){return this;}
};
struct Location{double lat=0,lon=0,accuracy=1;bool mock=false;int source=GNSS_TYPE;int64_t stamp=now;
 double GetLatitude()const{return lat;}double GetLongitude()const{return lon;}double GetAccuracy()const{return accuracy;}bool GetIsFromMock()const{return mock;}int GetLocationSourceType()const{return source;}int64_t GetTimeSinceBoot()const{return stamp;}};
struct ILocatorCallback:IRemoteObject{virtual void OnLocationReport(const std::unique_ptr<Location>&)=0;virtual void OnLocatingStatusChange(int)=0;virtual void OnErrorReport(int)=0;};
struct WifiScanInfo{std::string bssid;int rssi=-40;int64_t timestamp=now/1000;std::string GetBssid()const{return bssid;}int GetRssi()const{return rssi;}int64_t GetTimestamp()const{return timestamp;}};
struct CellularInfo{int64_t cellId=1,stamp=now;int mcc=460,mnc=0,rat=5,lac=10,pci=3;int64_t GetCellId(){return cellId;}int GetMcc(){return mcc;}int GetMnc(){return mnc;}int GetRat(){return rat;}int GetLac(){return lac;}int GetPci(){return pci;}int64_t GetTimeSinceBoot(){return stamp;}};
struct LocatingRequiredData{std::shared_ptr<WifiScanInfo> wifi=std::make_shared<WifiScanInfo>();int type=1;int GetType(){return type;}std::shared_ptr<WifiScanInfo> GetWifiScanInfo(){return wifi;}};
struct MatchingWlanInfo{};
struct ILocatingRequiredDataCallback:IRemoteObject{virtual void OnLocatingDataChange(const std::vector<std::shared_ptr<LocatingRequiredData>>&)=0;virtual void OnMatchingWlanInfoChange(const std::vector<MatchingWlanInfo>&)=0;};
template<class T>struct IRemoteStub:T{};
enum LocatingRequiredDataType{WIFI=1};
struct LocatingRequiredDataConfig{void SetType(int){}void SetNeedStartScan(bool){}void SetScanIntervalMs(int){}void SetFixNumber(int){}};
struct RequestConfig{bool precise=false;void SetPriority(int){}void SetLocationSourceType(int){}void SetNeedsFinePermission(bool v){precise=v;}void SetFixNumber(int){}void SetTimeInterval(int){}};
struct Request{bool usingPermission=false;sptr<ILocatorCallback> cb;Request(std::unique_ptr<RequestConfig>& config,sptr<ILocatorCallback> callback,AppIdentity&):cb(callback){assert(config->precise);}void SetPermUsedType(int){}};
struct RequestManager{std::vector<std::shared_ptr<Request>> running;int starts=0,stops=0,permissionStarts=0,permissionStops=0;bool permissionStartFails=false,permissionStopFails=false;
 bool IsFinePermissionInUse(std::shared_ptr<Request> request){return request&&request->usingPermission;}
 bool UpdateUsingPermission(std::shared_ptr<Request> request,bool start){if(!request)return true;if(start){if(permissionStartFails)return false;if(!request->usingPermission){++permissionStarts;request->usingPermission=true;}}else if(request->usingPermission){if(permissionStopFails)return false;++permissionStops;request->usingPermission=false;}return true;}
 void HandleStartLocating(std::shared_ptr<Request> request){++starts;running.push_back(request);}void HandleStopLocating(sptr<ILocatorCallback> cb){++stops;running.erase(std::remove_if(running.begin(),running.end(),[&](auto r){return r->cb.GetRefPtr()==cb.GetRefPtr();}),running.end());}
};
struct LocatorRequiredDataManager{int error=0,cellError=0,scanRequests=0,registrations=0;int64_t scanTime=now;std::vector<sptr<IRemoteObject>> callbacks;std::vector<std::shared_ptr<CellularInfo>> cells;
 static LocatorRequiredDataManager* GetInstance(){static LocatorRequiredDataManager v;return &v;}
 int RegisterCallback(AppIdentity&,std::shared_ptr<LocatingRequiredDataConfig>&,sptr<IRemoteObject> cb){if(error)return error;++registrations;callbacks.push_back(cb);return 0;}
 int UnregisterCallback(sptr<IRemoteObject> cb){--registrations;callbacks.erase(std::remove_if(callbacks.begin(),callbacks.end(),[&](auto c){return c.GetRefPtr()==cb.GetRefPtr();}),callbacks.end());return 0;}
 int QueryFusionCells(std::vector<std::shared_ptr<CellularInfo>>& out){out=cells;return cellError?cellError:out.empty()?ERRCODE_SERVICE_UNAVAILABLE:0;}
 int RequestFusionWifiScan(){++scanRequests;return 0;}
 int64_t GetWifiScanCompleteTimestamp(){return scanTime;}int TriggerWifiScan(){++scanRequests;return 0;}
};
struct Handler{std::map<std::string,std::function<void()>> jobs;bool PostTask(std::function<void()> task,const std::string& name,int){jobs[name]=std::move(task);return true;}void RemoveTask(const std::string& name){jobs.erase(name);}};
enum class LocatorInterfaceCode{ADD_FUSION_FENCE=72};
struct FusionFenceRecord;
struct LocatorAbility{std::mutex fusionFenceMutex_;std::vector<std::shared_ptr<FusionFenceRecord>> fusionFences_,stoppedFusionFences_;uint64_t fusionFenceSequence_=0;int64_t lastFusionWifiScanNs_=0;bool fusionCheckScheduled_=false,fusionStopping_=false;RequestManager manager;RequestManager* requestManager_=&manager;std::shared_ptr<Handler> locatorHandler_=std::make_shared<Handler>();
 static LocatorAbility* GetInstance(){static LocatorAbility v;return &v;}
 void GetAppIdentityInfo(AppIdentity& v){v=caller;}bool CheckRequestAvailable(LocatorInterfaceCode,AppIdentity&){return currentAccount;}
 int IsFusionFenceSupported(bool&);int AddFusionFence(const FusionFenceRequest&,const sptr<IRemoteObject>&);int RemoveFusionFence(const std::string&);int ReleaseFusionFence(const std::string&,const sptr<IRemoteObject>&);
 void RemoveFusionFenceRecord(const std::shared_ptr<FusionFenceRecord>&);void CheckFusionFences();void ScheduleFusionFenceCheck();bool HasFusionFences();bool IsFusionFenceLocatingInCurrentAccount();void ClearFusionFences();
 void OnFusionFenceLocation(const std::shared_ptr<FusionFenceRecord>&,const std::unique_ptr<Location>&);void OnFusionFenceWifi(const std::shared_ptr<FusionFenceRecord>&,const std::vector<std::shared_ptr<LocatingRequiredData>>&);
 void UpdateFusionFenceCells(const std::shared_ptr<FusionFenceRecord>&,const std::vector<std::shared_ptr<CellularInfo>>&);void EvaluateFusionFence(const std::shared_ptr<FusionFenceRecord>&);
};
'''
MAIN = r'''
int main(){
 auto* service=LocatorAbility::GetInstance();auto* data=LocatorRequiredDataManager::GetInstance();
 FusionFenceRequest req;req.identifier="a";req.scene=1;req.fenceType=1;req.events=7;req.loiterMs=1000;req.expirationMs=100000;FusionGnssFence shape;shape.type=2;shape.radius=100;shape.expirationMs=100000;req.gnss={shape};
 assert(req.Valid());Parcel parcel;assert(req.Marshalling(parcel));assert(parcel.WriteInt32(777));std::unique_ptr<FusionFenceRequest> copy(FusionFenceRequest::Unmarshalling(parcel));int32_t tail=0;assert(copy&&copy->Valid()&&parcel.ReadInt32(tail)&&tail==777);
 Parcel truncated=parcel;truncated.position=0;truncated.values.resize(3);assert(!FusionFenceRequest::Unmarshalling(truncated));
 auto invalid=req;invalid.events=64;assert(!invalid.Valid());invalid=req;invalid.expirationMs=std::numeric_limits<double>::infinity();assert(!invalid.Valid());
 sptr<IRemoteObject> callback=new IRemoteObject();bool supported=false;assert(service->IsFusionFenceSupported(supported)==0&&supported);systemApp=false;assert(service->IsFusionFenceSupported(supported)==LOCATION_ERRCODE_SYSTEM_PERMISSION_DENIED&&!supported);systemApp=true;
 fine=false;assert(service->AddFusionFence(req,callback)==LOCATION_ERRCODE_PERMISSION_DENIED);fine=true;
 switchedOn=false;assert(service->AddFusionFence(req,callback)==ERRCODE_SWITCH_OFF);switchedOn=true;
 assert(service->AddFusionFence(req,callback)==0&&service->manager.running.size()==1);auto first=service->fusionFences_.front();assert(service->AddFusionFence(req,callback)==3501603);
 caller.first=3;sptr<IRemoteObject> proxyOwner=new IRemoteObject();assert(service->AddFusionFence(req,proxyOwner)==0);assert(service->RemoveFusionFence("missing")==3301602);caller.first=0;
 auto location=std::make_unique<Location>();location->lon=0.002;first->locationCallback->OnLocationReport(location);assert(callback->events.empty());
 now+=1000000000;location->stamp=now;location->lon=0;first->locationCallback->OnLocationReport(location);assert(callback->events==std::vector<int>{1});
 now+=1000000000;service->CheckFusionFences();assert(callback->events==std::vector<int>({1,4}));
 now+=1000000000;location->stamp=now;location->lon=0.002;first->locationCallback->OnLocationReport(location);assert(callback->events==std::vector<int>({1,4,2}));
 auto count=callback->events.size();location->lon=0;location->mock=true;location->stamp=++now;first->locationCallback->OnLocationReport(location);assert(callback->events.size()==count);location->mock=false;location->source=2;first->locationCallback->OnLocationReport(location);assert(callback->events.size()==count);location->source=GNSS_TYPE;
 auto stale=first->locationCallback;assert(service->RemoveFusionFence("a")==0);sptr<IRemoteObject> newCallback=new IRemoteObject();assert(service->AddFusionFence(req,newCallback)==0);auto fresh=service->fusionFences_.back();assert(service->ReleaseFusionFence("a",callback)==3301602);location->stamp=++now;stale->OnLocationReport(location);assert(newCallback->events.empty());
 location->stamp=++now;fresh->locationCallback->OnLocationReport(location);assert(newCallback->events==std::vector<int>{1});
 fine=false;location->stamp=++now;fresh->locationCallback->OnLocationReport(location);assert(service->RemoveFusionFence("a")==3301602);fine=true;
 // Owner switch, death, expiry and failed stop all retain exact request ownership.
 caller.first=3;assert(service->RemoveFusionFence("a")==0);caller.first=0;service->CheckFusionFences();assert(service->manager.permissionStarts==service->manager.permissionStops);
 req.expirationMs=1;assert(service->AddFusionFence(req,callback)==0);service->manager.permissionStopFails=true;now+=2000000;service->CheckFusionFences();assert(service->fusionFences_.empty()&&!service->stoppedFusionFences_.empty());service->manager.permissionStopFails=false;service->CheckFusionFences();assert(!service->HasFusionFences());
 req.expirationMs=100000;req.fenceType=4;req.gnss.clear();FusionWifiFence wifi;wifi.type=2;wifi.features.push_back({-40,3,{"aa:bb:cc:dd:ee:ff"}});req.wifi={wifi};
 data->error=3301800;assert(service->AddFusionFence(req,callback)==3301000);data->error=0;service->CheckFusionFences();assert(service->AddFusionFence(req,callback)==0);auto radio=service->fusionFences_.back();assert(service->IsFusionFenceLocatingInCurrentAccount());auto scan=std::make_shared<LocatingRequiredData>();scan->wifi->bssid="AA:BB:CC:DD:EE:FF";scan->wifi->timestamp=now/1000;data->scanTime=now;
 callback->events.clear();radio->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>{1});scan->wifi->rssi=-80;radio->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>({1,2}));
 callback->events.clear();scan->wifi->rssi=-40;scan->wifi->timestamp=(now-20LL*1000000000)/1000;radio->wifiCallback->OnLocatingDataChange({scan});assert(callback->events.empty());radio->wifiCallback->OnLocatingDataChange({});assert(callback->events.empty());
 currentAccount=false;service->CheckFusionFences();assert(data->callbacks.empty());currentAccount=true;service->CheckFusionFences();assert(!service->HasFusionFences());
 req.fenceType=2;req.wifi.clear();req.cells={{{1,10,460,0,5,3}}};assert(service->AddFusionFence(req,callback)==3301000);data->cells.push_back(std::make_shared<CellularInfo>());callback->events.clear();assert(service->AddFusionFence(req,callback)==0);service->CheckFusionFences();assert(callback->events==std::vector<int>{1});data->cells[0]->cellId=2;service->CheckFusionFences();assert(callback->events==std::vector<int>({1,2}));service->ClearFusionFences();service->fusionStopping_=false;service->CheckFusionFences();assert(!service->HasFusionFences());assert(service->manager.permissionStarts==service->manager.permissionStops);
 // Spherical polygon, orientation, antimeridian and antipode boundaries.
 FusionGnssFence polygon;polygon.type=1;polygon.polygon={{-1,179},{-1,-179},{1,-179},{1,179}};assert(FusionShapeDistance(polygon,{0,180})<0);assert(FusionShapeDistance(polygon,{0,0})>0);std::reverse(polygon.polygon.begin(),polygon.polygon.end());assert(FusionShapeDistance(polygon,{0,180})<0);assert(FusionShapeDistance(polygon,{0,0})>0);
}
'''


def without_includes(text):
    return '\n'.join(line for line in text.splitlines() if not line.startswith('#include'))


class FusionRuntimeTests(unittest.TestCase):
    def test_public_binding_and_wire_contract(self):
        sources = runtime_sources()
        entry = sources['frameworks/js/napi/source/location_napi_entry.cpp']
        for name, native in [('addFusionFence', 'AddFusionFence'), ('removeFusionFence', 'RemoveFusionFence'),
                             ('isFusionFenceSupported', 'IsFusionFenceSupported')]:
            self.assertIn('DECLARE_WRITABLE_NAPI_FUNCTION("' + name + '", ' + native + ')', entry)
            self.assertIn('napi_value ' + native + '(', sources['frameworks/js/napi/source/location_napi_adapter.cpp'])

    def test_actual_wire_geometry_owner_and_service_lifecycle(self):
        sources = runtime_sources()
        header = without_includes(sources['interfaces/inner_api/include/fusion_fence_request.h'])
        header = header.replace('namespace OHOS {', '').replace('namespace Location {', '').replace('} // namespace Location', '').replace('} // namespace OHOS', '')
        source = sources['services/location_locator/locator/source/locator_ability.cpp']
        start = source.index('namespace {\nconstexpr int64_t FUSION_GNSS_FRESH_NS')
        end = source.index('ErrCode LocatorAbility::StartDistrictLocating(', start)
        program = COMMON + SPTR + header + SERVICE + source[start:end] + MAIN
        with tempfile.TemporaryDirectory(prefix='batch-location-fence-') as directory:
            path = Path(directory)
            (path/'test.cpp').write_text(program)
            compiled = subprocess.run(['clang++','-std=c++17','-DFEATURE_GNSS_SUPPORT','-DWIFI_ENABLE','-DTEL_CORE_SERVICE_ENABLE',
                '-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',str(path/'test.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(0,compiled.returncode,compiled.stdout+compiled.stderr)
            result = subprocess.run([str(path/'test')],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)


NAPI_PREFIX = NAPI_PREAMBLE[:NAPI_PREAMBLE.index('struct RefBase')].replace('napi_number,napi_function','napi_number,napi_function,napi_boolean')
FENCE_NAPI = r'''
constexpr int PARAM1=1;constexpr size_t NAPI_AUTO_LENGTH=size_t(-1);
#define NAPI_CALL_RETURN_VOID(env,expression) do{if((expression)!=napi_ok)return;}while(false)
struct MessageOption{};
struct MessageParcel:Parcel{std::u16string descriptor;std::u16string ReadInterfaceToken(){return descriptor;}};
struct IRemoteObject:RefBase{virtual int OnRemoteRequest(uint32_t,MessageParcel&,MessageParcel&,MessageOption&){return -1;}};
struct IPCObjectStub:IRemoteObject{};
struct Work{void* data;void(*execute)(napi_env,void*);void(*complete)(napi_env,napi_status,void*);napi_env env;};
using napi_deferred=napi_value;using napi_async_work=Work*;
std::vector<Work*> works;bool createWorkFailure=false,queueWorkFailure=false;int liveWork=0;
struct AsyncContext{napi_env env;napi_value resourceName=nullptr,result[2]={nullptr,nullptr};napi_deferred deferred=nullptr;napi_async_work work=nullptr;int errCode=0;bool isAsyncWorkAddToQueue=false;std::function<void(void*)> executeFunc,completeFunc;explicit AsyncContext(napi_env e):env(e){}virtual ~AsyncContext()=default;};
int napi_create_promise(napi_env e,napi_deferred* deferred,napi_value* promise){*promise=make(*e,napi_object);*deferred=*promise;return 0;}
int napi_create_async_work(napi_env e,napi_value,napi_value,void(*execute)(napi_env,void*),void(*complete)(napi_env,napi_status,void*),void* data,napi_async_work* out){if(createWorkFailure)return 1;*out=new Work{data,execute,complete,e};++liveWork;return 0;}
int napi_queue_async_work(napi_env,napi_async_work work){if(queueWorkFailure)return 1;works.push_back(work);return 0;}
int napi_delete_async_work(napi_env,napi_async_work work){delete work;--liveWork;return 0;}
int napi_resolve_deferred(napi_env,napi_deferred p,napi_value result){p->text="resolved";p->number=0;p->properties["value"]=result;return 0;}
int napi_reject_deferred(napi_env,napi_deferred p,napi_value error){p->text="rejected";p->number=error->number;return 0;}
int napi_create_string_utf8(napi_env e,const char* text,size_t,napi_value* out){*out=make(*e,napi_string);(*out)->text=text;return 0;}
int napi_get_boolean(napi_env e,bool value,napi_value* out){*out=make(*e,napi_boolean);(*out)->number=value;return 0;}
void SetValueUtf8String(napi_env e,const char* key,const char* value,napi_value object){auto item=make(*e,napi_string);item->text=value;object->properties[key]=item;}
void SetValueInt32(napi_env e,const char* key,int value,napi_value object){auto item=make(*e,napi_number);item->number=value;object->properties[key]=item;}
napi_value GetErrorObject(napi_env e,int code,const std::string&){auto error=make(*e,napi_object);error->number=code;return error;}
struct CommonUtils{static std::string GetErrorMsgByCode(int){return "error";}};
struct LocatorImpl{int error=0;std::map<std::string,sptr<IRemoteObject>> records;int AddFusionFenceV9(const FusionFenceRequest& req,const sptr<IRemoteObject>& cb){if(error)return error;if(records.count(req.identifier))return 3501603;records[req.identifier]=cb;return 0;}int RemoveFusionFenceV9(const std::string& id){return records.erase(id)?0:3301602;}int ReleaseFusionFenceV9(const std::string& id,const sptr<IRemoteObject>& cb){auto i=records.find(id);if(i==records.end()||i->second.GetRefPtr()!=cb.GetRefPtr())return 3301602;records.erase(i);return 0;}int IsFusionFenceSupportedV9(bool& supported){supported=error==0;return error;}
 void Emit(const std::string& id,int event){auto found=records.find(id);if(found==records.end())return;MessageParcel p,reply;p.descriptor=u"location.IFusionFenceCallback";p.WriteString(id);p.WriteInt32(2);p.WriteInt32(event);MessageOption option;found->second->OnRemoteRequest(1,p,reply,option);}};
struct Locator{static std::shared_ptr<LocatorImpl> instance;static auto GetInstance(){return instance;}};std::shared_ptr<LocatorImpl> Locator::instance=std::make_shared<LocatorImpl>();
void finish(int status=0){auto current=std::move(works);works.clear();for(auto* work:current){if(status==0)work->execute(work->env,work->data);work->complete(work->env,status,work->data);}assert(liveWork==0);}
void drain(Env& e){auto jobs=std::move(e.jobs);e.jobs.clear();for(auto& job:jobs)job();assert(e.scopes==0);}
int liveRefs(Env& e){int count=0;for(auto& ref:e.refs)count+=ref->alive;return count;}
void closeEnv(Env& e){auto hooks=std::move(e.hooks);e.hooks.clear();for(auto hook:hooks)hook.first(hook.second);assert(liveRefs(e)==0);e.alive=false;}
'''
FENCE_NAPI_MAIN = r'''
int main(){Env env;auto client=Locator::instance;auto number=[&](double v){auto n=make(env,napi_number);n->number=v;return n;};auto text=[&](const std::string& v){auto n=make(env,napi_string);n->text=v;return n;};
 auto req=make(env,napi_object);auto point=make(env,napi_object);point->properties={{"latitude",number(10)},{"longitude",number(179.5)}};auto circle=make(env,napi_object);circle->properties=point->properties;circle->properties["radius"]=number(100);circle->properties["expiration"]=number(3000);auto shape=make(env,napi_object);shape->properties={{"gnssFenceType",number(2)},{"circularFence",circle}};auto shapes=make(env,napi_object);shapes->array=true;shapes->elements={shape};
 auto callback=make(env,napi_function);std::vector<int> events;callback->callback=[&](Value* event){assert(event->properties["identifier"]->text=="owner-fence"&&event->properties["scene"]->number==2);events.push_back(event->properties["transitionEvent"]->number);};req->properties={{"identifier",text("owner-fence")},{"scene",number(2)},{"fenceType",number(1)},{"poiLocation",point},{"monitorTransitionEvents",number(7)},{"loiterTimeMs",number(10)},{"expirationMs",number(3000)},{"gnssFences",shapes},{"fenceTransitionCallback",callback}};
 auto add=[&](std::vector<Value*> args){env.error=0;Info info{args};return AddFusionFence(&env,&info);};auto remove=[&]{Info info{{req->properties["identifier"]}};return RemoveFusionFence(&env,&info);};
 auto promise=add({req});assert(promise&&promise->text.empty());finish();assert(promise->text=="resolved"&&liveRefs(env)==1);client->Emit("owner-fence",1);drain(env);assert(events==std::vector<int>{1});
 auto duplicate=add({req});finish();assert(duplicate->number==3501603&&liveRefs(env)==1&&client->records.size()==1);
 client->Emit("owner-fence",2);auto removed=remove();finish();assert(removed->number==0&&liveRefs(env)==0);auto next=add({req});finish();drain(env);assert(events.size()==1&&next->number==0);client->Emit("owner-fence",4);drain(env);assert(events==std::vector<int>({1,4}));
 removed=remove();finish();assert(removed->number==0);createWorkFailure=true;promise=add({req});assert(promise->number==3301000&&liveRefs(env)==0&&env.hooks.empty());createWorkFailure=false;queueWorkFailure=true;promise=add({req});assert(promise->number==3301000&&liveRefs(env)==0&&env.hooks.empty());queueWorkFailure=false;promise=add({req});finish(1);assert(promise->number==3301000&&liveRefs(env)==0);
 promise=add({req});auto* completed=works.front();works.clear();completed->execute(completed->env,completed->data);assert(client->records.size()==1);completed->complete(completed->env,1,completed->data);assert(promise->number==3301000&&client->records.empty()&&liveRefs(env)==0&&liveWork==0);
 for(auto args:std::vector<std::vector<Value*>>{{},{req,req},{&nullValue}}){assert(!add(args)&&env.error==401);}req->properties["scene"]=number(2.5);assert(!add({req})&&env.error==401);req->properties["scene"]=number(2);circle->properties["radius"]=number(std::nan(""));assert(!add({req})&&env.error==401);circle->properties["radius"]=number(100);shapes->elements.resize(65,shape);assert(!add({req})&&env.error==401);shapes->elements.resize(1);promise=add({req});finish();assert(promise->number==0);
 client->Emit("owner-fence",1);closeEnv(env);drain(env);assert(client->records.empty()&&events.size()==2&&g_fusionFenceRegistrations.empty());}
'''


def _test_fusion_napi(self):
    sources=runtime_sources()
    header=without_includes(sources['interfaces/inner_api/include/fusion_fence_request.h']).replace('namespace OHOS {','').replace('namespace Location {','').replace('} // namespace Location','').replace('} // namespace OHOS','')
    source=sources['frameworks/js/napi/source/location_napi_adapter.cpp']
    start=source.index('namespace {\nconst std::u16string FUSION_NAPI_DESCRIPTOR')
    end=source.index('struct DistrictAsyncContext',start)
    program=COMMON+NAPI_PREFIX+SPTR+header+FENCE_NAPI+source[start:end]+FENCE_NAPI_MAIN
    with tempfile.TemporaryDirectory(prefix='batch-location-fence-napi-') as directory:
        root=Path(directory);(root/'test.cpp').write_text(program)
        r=subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
        self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        r=subprocess.run([str(root/'test')],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        self.assertEqual(0,r.returncode,r.stdout+r.stderr)
FusionRuntimeTests.test_actual_napi_parser_promise_callback_queue_and_failures=_test_fusion_napi

CELL = r'''
constexpr int ERRCODE_NOT_SUPPORTED=801,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_SUCCESS=0;using LocationErrCode=int;
int64_t bootTime=100000000000LL;int callingIdentity=91;
struct CommonUtils{static int64_t GetSinceBootTime(){return bootTime;}};
struct IPCSkeleton{static std::string ResetCallingIdentity(){auto saved=std::to_string(callingIdentity);callingIdentity=1;return saved;}static void SetCallingIdentity(const std::string& saved){callingIdentity=std::stoi(saved);}};
namespace Telephony{constexpr int TELEPHONY_SUCCESS=0;
struct CellInformation:RefBase{enum class CellType{CELL_TYPE_NONE=0,CELL_TYPE_GSM=1,CELL_TYPE_CDMA=2,CELL_TYPE_WCDMA=3,CELL_TYPE_TDSCDMA=4,CELL_TYPE_LTE=5,CELL_TYPE_NR=6};virtual ~CellInformation()=default;CellType type=CellType::CELL_TYPE_GSM;uint64_t stamp=bootTime/1000000;int id=19;std::string mcc="460",mnc="01";
 uint64_t GetTimeStamp()const{return stamp;}std::string GetMcc()const{return mcc;}std::string GetMnc()const{return mnc;}int GetCellId()const{return id;}CellType GetNetworkType()const{return type;}int GetSignalIntensity()const{return -93;}};
struct GsmCellInformation:CellInformation{int GetLac(){return 11;}int GetArfcn(){return 66;}};
struct LteCellInformation:CellInformation{int GetTac(){return 12;}int GetPci(){return 99;}int GetArfcn(){return 67;}};
struct NrCellInformation:CellInformation{int64_t GetNci(){return 0x123456789LL;}int GetTac(){return 13;}int GetPci(){return 101;}int GetArfcn(){return 68;}};
struct WcdmaCellInformation:CellInformation{int GetLac(){return 14;}int GetPsc(){return 100;}int GetArfcn(){return 69;}};
struct TdscdmaCellInformation:CellInformation{int GetLac(){return 15;}int GetArfcn(){return 70;}};
struct CoreServiceClient{int slots=2,error=0,queries=0;std::vector<std::vector<sptr<CellInformation>>> data{{},{}};static CoreServiceClient& GetInstance(){static CoreServiceClient v;return v;}int GetMaxSimCount(){assert(callingIdentity==1);return slots;}int GetCellInfoList(int slot,std::vector<sptr<CellInformation>>& out){assert(callingIdentity==1&&slot>=0&&slot<slots);++queries;out=data.at(slot);return error;}};
}
template<class T>struct DelayedRefSingleton{static T& GetInstance(){return T::GetInstance();}};
struct CellularInfo{int64_t stamp=0,id=0;int mcc=0,mnc=0,rat=0,rssi=0,lac=0,pci=0,arfcn=0;
 void SetMcc(int n){mcc=n;}void SetMnc(int n){mnc=n;}void SetCellId(int64_t n){id=n;}void SetRat(int n){rat=n;}void SetSignalIntensity(int n){rssi=n;}void SetTimeSinceBoot(int64_t n){stamp=n;}void SetLac(int n){lac=n;}void SetPci(int n){pci=n;}void SetArfcn(int n){arfcn=n;}int64_t GetCellId(){return id;}};
struct LocatorRequiredDataManager{int QueryFusionCells(std::vector<std::shared_ptr<CellularInfo>>&);};
'''
CELL_MAIN = r'''
int main(){LocatorRequiredDataManager manager;std::vector<std::shared_ptr<CellularInfo>> result;auto& core=Telephony::CoreServiceClient::GetInstance();
 assert(manager.QueryFusionCells(result)==3301000&&result.empty()&&callingIdentity==91);core.slots=0;assert(manager.QueryFusionCells(result)==3301000);core.slots=9;assert(manager.QueryFusionCells(result)==3301000);core.slots=2;
 auto lte=sptr<Telephony::LteCellInformation>(new Telephony::LteCellInformation());lte->type=Telephony::CellInformation::CellType::CELL_TYPE_LTE;core.data[0]={lte};assert(manager.QueryFusionCells(result)==0&&result.size()==1&&result[0]->stamp==100000000000LL&&result[0]->mnc==1&&result[0]->lac==12&&result[0]->pci==99&&callingIdentity==91);
 auto nr=sptr<Telephony::NrCellInformation>(new Telephony::NrCellInformation());nr->type=Telephony::CellInformation::CellType::CELL_TYPE_NR;core.data[1]={nr};assert(manager.QueryFusionCells(result)==0&&result.size()==2&&result[1]->id==0x123456789LL&&result[1]->lac==13);
 core.error=1;assert(manager.QueryFusionCells(result)==3301000&&result.empty()&&callingIdentity==91);core.error=0;lte->stamp=1;nr->stamp=100001;assert(manager.QueryFusionCells(result)==3301000&&result.empty());lte->stamp=100000;nr->stamp=100000;lte->mcc="4x0";nr->mcc="";assert(manager.QueryFusionCells(result)==3301000);lte->mcc="460";nr->mcc="460";bootTime+=30000000001LL;assert(manager.QueryFusionCells(result)==3301000&&result.empty());
}
'''


def _test_cell(self):
    sources=runtime_sources()
    header=without_includes(sources['interfaces/inner_api/include/fusion_fence_request.h']).replace('namespace OHOS {','').replace('namespace Location {','').replace('} // namespace Location','').replace('} // namespace OHOS','')
    actual=function(sources['services/location_locator/locator/source/locator_required_data_manager.cpp'],'LocationErrCode LocatorRequiredDataManager::QueryFusionCells(')
    with tempfile.TemporaryDirectory(prefix='batch-location-cell-query-') as directory:
        root=Path(directory);(root/'test.cpp').write_text(COMMON+SPTR+header+CELL+actual+CELL_MAIN)
        r=subprocess.run(['clang++','-std=c++17','-DTEL_CORE_SERVICE_ENABLE','-fsanitize=address,undefined',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        r=subprocess.run([str(root/'test')],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'});self.assertEqual(0,r.returncode,r.stdout+r.stderr)
FusionRuntimeTests.test_actual_core_cell_query_slots_timestamp_and_identity=_test_cell

if __name__ == "__main__":
    unittest.main()
