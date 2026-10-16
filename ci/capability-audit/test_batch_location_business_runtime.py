#!/usr/bin/env python3
"""Run actual district/track/config code; device and NAPI boundaries are explicit host doubles."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import function, runtime_sources
from test_batch_location_ble_napi import PREAMBLE as NAPI_PREAMBLE

BASE = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <list>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <tuple>
#include <utility>
#include <vector>
using LocationErrCode=int;using ErrCode=int;
constexpr int ERRCODE_SUCCESS=0,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_REVERSE_GEOCODING_FAIL=3301300,ERRCODE_COUNTRYCODE_FAIL=3301500,ERRCODE_SWITCH_OFF=3301100,ERRCODE_PERMISSION_DENIED=201,ERRCODE_SYSTEM_PERMISSION_DENIED=202,ERRCODE_EDM_POLICY_ABANDON=203,LOCATION_ERRCODE_PERMISSION_DENIED=3300201,ERRCODE_INVALID_PARAM=401,ERRCODE_NOT_SUPPORTED=801,ERRCODE_LOCATING_FAIL=3301200;
constexpr int LOCATION_ERRCODE_MIN=3300000;
constexpr int GNSS_TYPE=1,RTK_TYPE=4,SKIING=4,RUNNING=1,DEFAULT_TIMEOUT_5S=5000;
constexpr int SCENE_UNSET=0,PRIORITY_FAST_FIRST_FIX=1,PRIORITY_UNSET=0,LOCATION_PRIORITY_ACCURACY=10,PRIORITY_ACCURACY=2,SCENE_NAVIGATION=3,SCENE_TRAJECTORY_TRACKING=4,SCENE_CAR_HAILING=5,LOCATION_SCENE_SPORT=0x402;
constexpr int LOCATING_FAILED_LOCATION_SWITCH_OFF=-4,LOCATING_FAILED_LOCATION_PERMISSION_DENIED=-2,LOCATION_LOCATOR_SA_ID=2802;
const char* LOCALE_KEY="persist.global.locale";
int64_t bootNow=1000000000000LL;
struct CommonUtils{static int64_t GetSinceBootTime(){return bootNow;}static std::string GenerateUuid(){return "external-request-id";}static LocationErrCode ErrCodeToLocationErrCode(ErrCode);};
struct Location {
 double lat=30,lon=120,alt=100,accuracy=5,speed=0,direction=0;int64_t timestamp=bootNow;int source=1;bool mock=false;
 double GetLatitude()const{return lat;}double GetLongitude()const{return lon;}double GetAltitude()const{return alt;}double GetAccuracy()const{return accuracy;}double GetSpeed()const{return speed;}double GetDirection()const{return direction;}
 int64_t GetTimeSinceBoot()const{return timestamp;}int GetLocationSourceType()const{return source;}bool GetIsFromMock()const{return mock;}
 void SetLatitude(double v){lat=v;}void SetLongitude(double v){lon=v;}void SetAltitude(double v){alt=v;}void SetAccuracy(double v){accuracy=v;}void SetSpeed(double v){speed=v;}void SetDirection(double v){direction=v;}
};
struct Parcelable{virtual ~Parcelable()=default;virtual bool Marshalling(class Parcel&)const=0;};
struct Parcel{std::vector<std::pair<char,double>> values;size_t cursor=0;bool WriteInt32(int v){values.push_back({'i',double(v)});return true;}bool WriteDouble(double v){values.push_back({'d',v});return true;}bool WriteFloat(float v){values.push_back({'f',v});return true;}bool WriteBool(bool v){values.push_back({'b',double(v)});return true;}int ReadInt32(){assert(values.at(cursor).first=='i');return values[cursor++].second;}double ReadDouble(){assert(values.at(cursor).first=='d');return values[cursor++].second;}float ReadFloat(){assert(values.at(cursor).first=='f');return values[cursor++].second;}bool ReadBool(){assert(values.at(cursor).first=='b');return values[cursor++].second;}};
'''

SPTR = NAPI_PREAMBLE[NAPI_PREAMBLE.index('struct RefBase'):NAPI_PREAMBLE.index('struct BluetoothScanResult')]

NATIVE = r'''
struct GeoAddress{std::string locale_,countryCode_,countryName_,administrativeArea_,subAdministrativeArea_,locality_,subLocality_;};
struct IBluetoothScanResultCallback:RefBase{};
struct ILocatorCallback:RefBase{virtual void OnLocationReport(const std::unique_ptr<Location>&)=0;virtual void OnLocatingStatusChange(int)=0;virtual void OnErrorReport(int)=0;};
struct LocatorCallbackHost:ILocatorCallback{void OnLocationReport(const std::unique_ptr<Location>&)override{}void OnLocatingStatusChange(int)override{}void OnErrorReport(int)override{}};
struct GeoConvertCallbackHost:RefBase{virtual void OnResults(std::list<std::shared_ptr<GeoAddress>>&)=0;virtual void OnErrorReport(int)=0;sptr<GeoConvertCallbackHost> AsObject(){return sptr<GeoConvertCallbackHost>(this);}};
struct GeocodeConvertLocationRequest{std::string locale;double lat=0,lon=0;int max=0;void SetLocale(const std::string& v){locale=v;}void SetLatitude(double v){lat=v;}void SetLongitude(double v){lon=v;}void SetMaxItems(int v){max=v;}void SetTransId(const std::string&) {}};
namespace system {std::string GetParameter(const std::string& key,const std::string&){assert(key=="persist.global.locale");return "fr";}}
struct AppIdentity{int uid=100001,pid=1;uint32_t token=7,first=0;int GetUid()const{return uid;}uint32_t GetTokenId()const{return token;}uint32_t GetFirstTokenId()const{return first;}};
bool fine=true,approximate=true,available=true,enabled=true;AppIdentity caller;
struct PermissionManager{static bool CheckLocationPermission(uint32_t,uint32_t){return fine;}static bool CheckApproximatelyPermission(uint32_t,uint32_t){return approximate;}};
enum class LocatorInterfaceCode{START_DISTRICT_LOCATING=68,GET_POST_PROCESSING_TRACK=70};
class LocatorAbility{public:RequestConfig received;sptr<ILocatorCallback> active;int starts=0,startError=0;bool emit=true;Location sample;
 void GetAppIdentityInfo(AppIdentity& value){value=caller;}bool CheckRequestAvailable(LocatorInterfaceCode,const AppIdentity&){return available;}
 int StartLocating(const RequestConfig& request,const sptr<ILocatorCallback>& callback){++starts;if(startError)return startError;if(!enabled)return ERRCODE_SWITCH_OFF;received.Set(const_cast<RequestConfig&>(request));active=callback;if(emit)callback->OnLocationReport(std::make_unique<Location>(sample));return 0;}
 bool GetLocationSwitchIgnoredFlag(uint32_t){return false;}bool CheckLocationSwitchState(){return enabled;}int CheckDistrictAccess();int StartDistrictLocating(const RequestConfig&,const sptr<ILocatorCallback>&);int StartLocatingWithSportsType(const RequestConfig&,int32_t,const sptr<ILocatorCallback>&);
};
struct FakeProxy{bool revokeOnGeo=false,userChangeOnGeo=false;int bleStart=0,bleStop=0;int StartBluetoothSearch(const std::vector<std::string>&,bool,int,const sptr<IBluetoothScanResultCallback>&){return bleStart;}int StopBluetoothSearch(const sptr<IBluetoothScanResultCallback>&){return bleStop;}LocatorAbility service;int stops=0,stopError=0,geoCalls=0,geoError=0;bool emitGeo=true,emptyGeo=false;GeocodeConvertLocationRequest query;sptr<ILocatorCallback> retired;sptr<GeoConvertCallbackHost> geo;
 int StartDistrictLocating(const RequestConfig& r,const sptr<ILocatorCallback>& cb){return service.StartDistrictLocating(r,cb);}
 int CheckDistrictAccess(){return service.CheckDistrictAccess();}
 int StopLocating(const sptr<ILocatorCallback>& cb){assert(cb.GetRefPtr()==service.active.GetRefPtr());++stops;retired=service.active;service.active=nullptr;return stopError;}
 int GetAddressByCoordinate(const sptr<GeoConvertCallbackHost>& cb,const GeocodeConvertLocationRequest& r){++geoCalls;query=r;geo=cb;if(geoError)return geoError;if(emitGeo){std::list<std::shared_ptr<GeoAddress>> results;if(!emptyGeo){auto address=std::make_shared<GeoAddress>();address->locale_=r.locale;address->countryCode_="EX";address->locality_="challenge-district";results.push_back(address);}cb->OnResults(results);}if(revokeOnGeo){fine=false;approximate=false;}if(userChangeOnGeo){available=false;}return 0;}
};
struct SaLoadWithStatistic{static bool InitLocationSa(int){return true;}};
struct LocatorImpl{FakeProxy proxy;bool cache=true,geoAvailable=true;int geoAvailableError=0;Location cached;
 FakeProxy* GetProxy(){return &proxy;}int GetCachedLocationV9(std::unique_ptr<Location>& out){if(!cache)return 3301400;out=std::make_unique<Location>(cached);return 0;}int IsGeoServiceAvailableV9(bool& out){out=geoAvailable;return geoAvailableError;}
 int StartBluetoothSearch(const std::vector<std::string>&,bool,int,const sptr<IBluetoothScanResultCallback>&);int StopBluetoothSearch(const sptr<IBluetoothScanResultCallback>&);
 int GetCurrentDistrictV9(const std::string&,int32_t,std::shared_ptr<GeoAddress>&);
};
'''

NATIVE_MAIN = r'''
int main(){
 LocatorImpl client;std::shared_ptr<GeoAddress> result;
 sptr<IBluetoothScanResultCallback> ble=new IBluetoothScanResultCallback();
 for(int error:{0,201,202,203,401,801,3300201,3300202,3300401,3300801,3301800}){client.proxy.bleStart=error;client.proxy.bleStop=error;int expected=error>3300000&&error<3301000?error-3300000:error;assert(client.StartBluetoothSearch({},false,0,ble)==expected);assert(client.StopBluetoothSearch(ble)==expected);}

 assert(client.GetCurrentDistrictV9("ja",100,result)==0&&result->locale_=="ja"&&result->locality_=="challenge-district");assert(client.proxy.stops==1&&client.proxy.query.lat==30&&client.proxy.query.lon==120&&client.proxy.query.max==1);
 assert(client.GetCurrentDistrictV9("",100,result)==0&&client.proxy.query.locale=="fr");
 approximate=false;fine=false;auto stops=client.proxy.stops;assert(client.GetCurrentDistrictV9("en",100,result)==201&&!result&&client.proxy.stops==stops);approximate=true;fine=true;
 available=false;assert(client.GetCurrentDistrictV9("en",100,result)==201);available=true;enabled=false;assert(client.GetCurrentDistrictV9("en",100,result)==ERRCODE_SWITCH_OFF);enabled=true;
 client.cache=false;client.proxy.service.sample.lat=31.25;assert(client.GetCurrentDistrictV9("en",100,result)==0&&client.proxy.query.lat==31.25);assert(client.proxy.service.received.GetFixNumber()==1&&client.proxy.service.received.GetSportsType()==0);
 client.proxy.service.emit=false;auto before=std::chrono::steady_clock::now();assert(client.GetCurrentDistrictV9("en",2,result)==ERRCODE_SERVICE_UNAVAILABLE);assert(std::chrono::steady_clock::now()-before<std::chrono::seconds(1));client.proxy.retired->OnLocationReport(std::make_unique<Location>());
 client.cache=true;client.proxy.service.sample.timestamp=bootNow-31LL*1000000000;assert(client.GetCurrentDistrictV9("en",2,result)==ERRCODE_SERVICE_UNAVAILABLE);client.proxy.service.emit=true;client.proxy.service.sample.timestamp=bootNow;assert(client.GetCurrentDistrictV9("en",100,result)==0&&client.proxy.query.lat==31.25);
 client.proxy.service.sample.timestamp=bootNow;client.proxy.stopError=3301000;auto geos=client.proxy.geoCalls;assert(client.GetCurrentDistrictV9("en",100,result)==3301000&&client.proxy.geoCalls==geos);client.proxy.stopError=0;
 client.proxy.emptyGeo=true;assert(client.GetCurrentDistrictV9("en",100,result)==3301500);client.proxy.emptyGeo=false;client.proxy.emitGeo=false;assert(client.GetCurrentDistrictV9("en",2,result)==3301500);client.proxy.emitGeo=true;client.proxy.geoError=3301500;assert(client.GetCurrentDistrictV9("en",100,result)==3301500);client.proxy.geoError=0;
 client.geoAvailable=false;assert(client.GetCurrentDistrictV9("en",100,result)==801);client.geoAvailable=true;client.proxy.service.sample.lat=100;assert(client.GetCurrentDistrictV9("en",100,result)==3301000);client.cached.lat=30;client.proxy.service.sample.lat=31.25;
 assert(client.GetCurrentDistrictV9("en",0,result)==3301500);assert(client.GetCurrentDistrictV9("en",-1,result)==3301500);
 approximate=false;assert(client.GetCurrentDistrictV9("en",100,result)==0);approximate=true;
 client.proxy.revokeOnGeo=true;assert(client.GetCurrentDistrictV9("en",100,result)==201&&!result);client.proxy.revokeOnGeo=false;fine=true;approximate=true;client.proxy.userChangeOnGeo=true;assert(client.GetCurrentDistrictV9("en",100,result)==201&&!result);client.proxy.userChangeOnGeo=false;available=true;
 RequestConfig sports;sports.SetFixNumber(0);sports.SetScenario(LOCATION_SCENE_SPORT);sptr<ILocatorCallback> callback=new LocatorCallbackHost();assert(client.proxy.service.StartLocatingWithSportsType(sports,4,callback)==0);assert(client.proxy.service.received.GetSportsType()==4&&client.proxy.service.received.GetScenario()==LOCATION_SCENE_SPORT&&client.proxy.service.received.GetLocationSourceType()==GNSS_TYPE);fine=false;assert(client.proxy.service.StartLocatingWithSportsType(sports,4,callback)==3300201);fine=true;assert(client.proxy.service.StartLocatingWithSportsType(sports,-1,callback)==401);sports.SetScenario(SCENE_UNSET);assert(client.proxy.service.StartLocatingWithSportsType(sports,4,callback)==0&&client.proxy.service.received.GetSportsType()==0&&client.proxy.service.received.GetScenario()==SCENE_UNSET);
 std::cout<<"Actual district native/service: current-fix/cache/deadline/stop/late callbacks/locale/geocoder errors and sports wire route passed\n";
}
'''

TRACK = r'''
struct AppIdentity{int uid=100001;uint32_t token=7,first=0;int GetUid()const{return uid;}uint32_t GetTokenId()const{return token;}uint32_t GetFirstTokenId()const{return first;}};
struct TestLocationCallback{int calls=0;void OnLocationReport(const std::unique_ptr<Location>&){++calls;}};
struct Request{std::shared_ptr<TestLocationCallback> callback=std::make_shared<TestLocationCallback>();auto GetLocatorCallBack(){return callback;}std::string GetPackageName(){return "test";}int GetPermUsedType(){return 0;}AppIdentity identity;std::shared_ptr<RequestConfig> config=std::make_shared<RequestConfig>();bool requesting=true,fineUse=true;auto GetRequestConfig(){return config;}bool GetIsRequesting(){return requesting;}bool GetLocationPermState(){return fineUse;}int GetUid(){return identity.uid;}uint32_t GetTokenId(){return identity.token;}uint32_t GetFirstTokenId(){return identity.first;}};
bool permitted=true;
struct PermissionManager{static bool CheckLocationPermission(uint32_t,uint32_t){return permitted;}};
const std::string ACCESS_LOCATION="fine",ACCESS_APPROXIMATELY_LOCATION="approx";
#define LBSLOGW(...) ((void)0)
#define LBSLOGE(...) ((void)0)
struct BundleMgrHelper{static bool CheckAppDebug(const std::string&){return true;}};
enum class LocatorInterfaceCode{GET_POST_PROCESSING_TRACK=70};
struct LocatorAbility{AppIdentity caller;bool available=true,switchOn=true;void GetAppIdentityInfo(AppIdentity& out){out=caller;}bool CheckRequestAvailable(LocatorInterfaceCode,const AppIdentity&){return available;}bool GetLocationSwitchIgnoredFlag(uint32_t){return false;}bool CheckLocationSwitchState(){return switchOn;}int GetPostProcessingTrack(int32_t,std::vector<Location>&);std::string record;int recordError=0;static LocatorAbility* GetInstance(){static LocatorAbility v;return &v;}bool GetUSBState(){return true;}bool IsHapCaller(uint32_t){return true;}int UpdatePermissionUsedRecord(uint32_t,const std::string& name,int,int,int){record=name;return recordError;}};
struct RequestManager{bool IsSkiingRequestActive(const std::shared_ptr<Request>& request){return request&&request->config&&request->config->GetSportsType()==4&&request->requesting&&request->fineUse;}static RequestManager* GetInstance(){static RequestManager v;return &v;}void ReportLocationError(int,const std::shared_ptr<Request>&){}void UpdateLocationError(const std::shared_ptr<Request>&){}};
class ReportManager{public:
 static ReportManager* GetInstance(){static ReportManager value;return &value;}
 bool ReportLocationByCallback(std::shared_ptr<Request>&,const std::unique_ptr<Location>&);
 struct SkiingHistory{std::shared_ptr<Location> last;double variance=0;uint64_t sequence=0,cursor=0;std::deque<std::pair<uint64_t,std::shared_ptr<Location>>> unread;};
 std::mutex trackMutex_;std::map<std::tuple<int32_t,uint32_t,uint32_t>,SkiingHistory> skiingTracks_;
 void RecordSkiingTrack(const std::shared_ptr<Request>&,const std::unique_ptr<Location>&);void PruneSkiingTracks(int64_t);int GetPostProcessingTrack(const AppIdentity&,std::vector<Location>&);
};
'''

TRACK_MAIN = r'''
int main(){
 auto& manager=*ReportManager::GetInstance();auto request=std::make_shared<Request>();request->config->SetSportsType(4);std::vector<Location> result;auto point=std::make_unique<Location>();point->timestamp=bootNow;
 assert(manager.GetPostProcessingTrack(request->identity,result)==3301000);assert(manager.ReportLocationByCallback(request,point)&&request->callback->calls==1&&LocatorAbility::GetInstance()->record==ACCESS_LOCATION);manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.size()==1&&result[0].lat==30);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.empty());
 auto first=bootNow;bootNow+=1000000000;point->timestamp=bootNow;point->lat+=0.0001;point->alt=90;manager.RecordSkiingTrack(request,point);manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.size()==1);assert(result[0].lat>30&&result[0].lat<point->lat&&result[0].alt>90&&result[0].alt<100&&result[0].speed>0&&result[0].accuracy>0);
 auto before=manager.skiingTracks_.begin()->second.sequence;point->timestamp=++bootNow;point->lat=80;manager.RecordSkiingTrack(request,point);assert(manager.skiingTracks_.begin()->second.sequence==before);point->lat=30.0002;
 point->mock=true;manager.RecordSkiingTrack(request,point);point->mock=false;point->source=2;manager.RecordSkiingTrack(request,point);point->source=1;request->requesting=false;manager.RecordSkiingTrack(request,point);request->requesting=true;request->fineUse=false;manager.RecordSkiingTrack(request,point);request->fineUse=true;permitted=false;manager.RecordSkiingTrack(request,point);permitted=true;assert(manager.skiingTracks_.begin()->second.sequence==before);
 request->identity.first=8;manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.size()==1);request->identity.first=9;assert(manager.GetPostProcessingTrack(request->identity,result)==3301000);request->identity.first=0;request->identity.uid=101001;assert(manager.GetPostProcessingTrack(request->identity,result)==3301000);request->identity.uid=100001;
 point->lat=30.0002;bootNow+=1000000000;point->timestamp=bootNow;manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.size()==1);
 // Retention uses monotonic GNSS nanoseconds, and a consumed cursor never replays.
 bootNow=first+24LL*60*60*1000000000+3000000000;assert(manager.GetPostProcessingTrack(request->identity,result)==3301000&&manager.skiingTracks_.empty());
 point->lat=0;point->lon=179.99999;point->timestamp=bootNow;manager.RecordSkiingTrack(request,point);bootNow+=1000000000;point->timestamp=bootNow;point->lon=-179.99999;manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.size()==2&&std::fabs(result.back().lon)>179);
 point->timestamp=bootNow+1;manager.RecordSkiingTrack(request,point);assert(manager.GetPostProcessingTrack(request->identity,result)==0&&result.empty());
 auto service=LocatorAbility::GetInstance();point->timestamp=++bootNow;manager.RecordSkiingTrack(request,point);permitted=false;assert(service->GetPostProcessingTrack(4,result)==3300201&&result.empty());permitted=true;service->available=false;assert(service->GetPostProcessingTrack(4,result)==3300201);service->available=true;service->switchOn=false;assert(service->GetPostProcessingTrack(4,result)==3301100);service->switchOn=true;assert(service->GetPostProcessingTrack(1,result)==3301200);service->caller.first=10;assert(service->GetPostProcessingTrack(4,result)==3301000);service->caller.first=0;assert(service->GetPostProcessingTrack(4,result)==0&&result.size()==1);assert(service->GetPostProcessingTrack(4,result)==0&&result.empty());
 std::cout<<"Actual skiing processing: changed geometry/altitude/accuracy/derived speed, dedup, outlier, source/privacy/lifecycle gates, owner/delegation, 24h and cursor/antimeridian passed\n";
}
'''


def compile_run(source):
    with tempfile.TemporaryDirectory(prefix='batch-location-business-') as directory:
        cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
        cpp.write_text(source)
        subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined', str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


def config_code(sources):
    header = sources['interfaces/inner_api/include/request_config.h']
    source = sources['frameworks/base_module/source/request_config.cpp']
    signatures = ['RequestConfig::RequestConfig()', 'RequestConfig::RequestConfig(const int scenario)',
                  'void RequestConfig::Set(', 'bool RequestConfig::IsSame(', 'void RequestConfig::ReadFromParcel(',
                  'bool RequestConfig::Marshalling(', 'std::string RequestConfig::ToString()', 'bool RequestConfig::IsRequestForAccuracy()']
    mapper = json.loads((Path(__file__).parent / 'fixtures/batch_location/icon_source.json').read_text())['common_error_mapping']
    return mapper + function(header, 'class RequestConfig') + ';\n' + ''.join(function(source, signature) for signature in signatures)


class LocationBusinessRuntimeTests(unittest.TestCase):
    def test_legacy_request_wire_and_sports_copy(self):
        sources = runtime_sources()
        main = r'''
int main(){RequestConfig legacy,sports; sports.Set(legacy);sports.SetSportsType(4);Parcel a,b;assert(legacy.Marshalling(a)&&sports.Marshalling(b));assert(a.values==b.values&&a.values.size()==10);a.WriteInt32(777);sports.ReadFromParcel(a);assert(sports.GetSportsType()==0&&a.ReadInt32()==777);sports.SetSportsType(4);RequestConfig copied;copied.Set(sports);assert(copied.GetSportsType()==4&&copied.IsSame(sports)&&!legacy.IsSame(sports));assert(copied.ToString().find("sportsType : 4")!=std::string::npos);std::cout<<"Actual RequestConfig: old ten wire fields and following parcel data preserved, sports default/copy/equality passed\n";}
'''
        compile_run(BASE + config_code(sources) + main)

    def test_district_native_and_service(self):
        sources = runtime_sources()
        native = sources['frameworks/native/locator_sdk/source/locator_impl.cpp']
        block = native[native.index('namespace {\nusing DistrictDeadline'):native.index('LocationErrCode LocatorImpl::GetPostProcessingTrackV9')]
        service = sources['services/location_locator/locator/source/locator_ability.cpp']
        actual = ''.join(function(service, signature) for signature in ['ErrCode LocatorAbility::StartDistrictLocating(', 'ErrCode LocatorAbility::CheckDistrictAccess()', 'ErrCode LocatorAbility::StartLocatingWithSportsType('])
        compile_run(BASE + config_code(sources) + SPTR + '#define FEATURE_GNSS_SUPPORT\nnamespace OHOS {\n' + NATIVE + actual + function(native, 'static LocationErrCode LocationRuntimeErrCode(') + function(native, 'LocationErrCode LocatorImpl::StartBluetoothSearch(') + function(native, 'LocationErrCode LocatorImpl::StopBluetoothSearch(') + block + '}\nusing namespace OHOS;\n' + NATIVE_MAIN)

    def test_skiing_processing_history(self):
        sources = runtime_sources()
        source = sources['services/location_locator/locator/source/report_manager.cpp']
        actual = source[source.index('namespace {\nconstexpr int64_t TRACK_RETENTION_NS'):source.index('void ReportManager::LocationReportDelayTimeCheck(')]
        compile_run(BASE + config_code(sources) + '#define FEATURE_GNSS_SUPPORT\n' + TRACK + function(source, 'bool ReportManager::ReportLocationByCallback(') + actual + function(sources['services/location_locator/locator/source/locator_ability.cpp'], 'ErrCode LocatorAbility::GetPostProcessingTrack(') + TRACK_MAIN)

    def test_cache_permission_release_and_retry(self):
        from test_batch_location_icon_state import PREAMBLE as ICON_PREAMBLE, FIXTURE
        sources = runtime_sources()
        fixture = json.loads(FIXTURE.read_text())
        preamble = ICON_PREAMBLE.replace('struct AccessTokenKit {', 'struct AccessTokenKit {static int GetPermissionUsedType(uint32_t,const std::string&){return 0;}', 1).replace('struct RequestConfig {', '''template<class T>using sptr=std::shared_ptr<T>;
struct ILocatorCallback{int calls=0;virtual void OnLocationReport(const std::unique_ptr<struct Location>&){++calls;}};
struct Location{};
class RequestManager;class LocatorHandler;
struct RequestConfig {''', 1)
        preamble = preamble.replace('class LocatorAbility {\npublic:', '''class LocatorAbility {
public:
    RequestManager* requestManager_=nullptr;std::shared_ptr<LocatorHandler> locatorHandler_;
    bool ReportSingleCacheLocation(const std::shared_ptr<Request>&,const sptr<ILocatorCallback>&,std::unique_ptr<Location>&);
    bool ReportCacheLocation(const std::shared_ptr<Request>&,const sptr<ILocatorCallback>&,std::unique_ptr<Location>&);''', 1)
        preamble = preamble.replace('static std::map<std::pair<int,std::string>,int> starts,stops;', 'static std::map<std::pair<int,std::string>,int> starts,stops;static int stopResult;', 1)
        preamble = preamble.replace('++stops[{pid,permission}];return 0;', '++stops[{pid,permission}];return stopResult;', 1)
        preamble += r'''
int PrivacyKit::stopResult=0;
namespace AppExecFwk{struct InnerEvent{using Pointer=std::shared_ptr<InnerEvent>;std::shared_ptr<Request> request;template<class T>std::shared_ptr<T> GetSharedObject(){return std::static_pointer_cast<T>(request);}};}
constexpr int EVENT_GET_CACHED_LOCATION_SUCCESS=1;
class LocatorHandler{public:std::vector<std::pair<std::shared_ptr<Request>,int>> pending;void SendHighPriorityEvent(int,const std::shared_ptr<Request>& request,int delay){pending.emplace_back(request,delay);}void GetCachedLocationSuccess(const AppExecFwk::InnerEvent::Pointer&);void GetCachedLocationFailed(const AppExecFwk::InnerEvent::Pointer&);};
'''
        source = sources['services/location_locator/locator/source/request_manager.cpp']
        actual = fixture['common_error_mapping'] + fixture['permission_functions'] + ''.join(function(source, signature) for signature in [
            'bool RequestManager::UpdateUsingPermission(', 'bool RequestManager::UpdateUsingFinePermission(',
            'bool RequestManager::UpdateUsingApproximatelyPermission(', 'void RequestManager::IncreaseWorkingPidsCount(',
            'void RequestManager::DecreaseWorkingPidsCount(', 'bool RequestManager::IsNeedStartUsingPermission(',
            'bool RequestManager::IsNeedStopUsingPermission('])
        service = sources['services/location_locator/locator/source/locator_ability.cpp']
        actual += ''.join(function(service, signature) for signature in ['bool LocatorAbility::ReportSingleCacheLocation(',
                            'bool LocatorAbility::ReportCacheLocation(', 'void LocatorHandler::GetCachedLocationSuccess(', 'void LocatorHandler::GetCachedLocationFailed('])
        main = r'''
int main(){auto locator=LocatorAbility::GetInstance();auto manager=RequestManager::GetInstance();locator->requestManager_=manager;locator->locatorHandler_=std::make_shared<LocatorHandler>();auto handler=locator->locatorHandler_;auto request=std::make_shared<Request>();request->usingPermission=false;auto callback=std::make_shared<ILocatorCallback>();auto location=std::make_unique<Location>();finePermissions[1]=true;permissions[1]=false;
assert(locator->ReportSingleCacheLocation(request,callback,location)&&callback->calls==1&&request->usingFine&&!request->usingPermission&&handler->pending.size()==1);auto event=std::make_shared<AppExecFwk::InnerEvent>();event->request=handler->pending.back().first;handler->pending.clear();PrivacyKit::stopResult=-1;handler->GetCachedLocationSuccess(event);assert(request->usingFine&&handler->pending.size()==1&&handler->pending.back().second==1000);PrivacyKit::stopResult=0;handler->pending.clear();handler->GetCachedLocationSuccess(event);assert(!request->usingFine&&manager->fineWorkingPidsCountMap_.empty());handler->GetCachedLocationSuccess(event);assert(manager->fineWorkingPidsCountMap_.empty());
permissions[1]=true;assert(!locator->ReportCacheLocation(request,callback,location)&&callback->calls==2&&request->usingPermission&&handler->pending.empty());assert(manager->workingPidsCountMap_[1]==1);assert(manager->UpdateUsingPermission(request,false)&&manager->workingPidsCountMap_[1]==0);
assert(locator->ReportSingleCacheLocation(request,callback,location));event->request=request;handler->pending.clear();PrivacyKit::stopResult=-1;handler->GetCachedLocationSuccess(event);assert(request->usingPermission&&manager->workingPidsCountMap_[1]==1&&handler->pending.size()==1);PrivacyKit::stopResult=0;handler->pending.clear();handler->GetCachedLocationSuccess(event);assert(!request->usingPermission&&manager->workingPidsCountMap_[1]==0);
assert(manager->UpdateUsingPermission(request,true));auto failed=std::make_shared<Request>();failed->usingPermission=false;failed->usingFine=false;event->request=failed;handler->GetCachedLocationFailed(event);assert(manager->workingPidsCountMap_[1]==1&&request->usingPermission);assert(manager->UpdateUsingPermission(request,false));
std::cout<<"Actual cache fast paths: fine-only/approx accounting, retained Request stop retry, no premature continuous decrement, duplicate release passed\n";}
'''
        compile_run(preamble + actual + main)


    def test_district_track_napi_and_sports_parser(self):
        sources = runtime_sources()
        preamble = NAPI_PREAMBLE[:NAPI_PREAMBLE.index('struct RefBase')]
        preamble += r'''
constexpr int PARAM1=1,DEFAULT_TIMEOUT_5S=5000,RUNNING=1,SKIING=4,SUCCESS=0;
constexpr size_t NAPI_AUTO_LENGTH=size_t(-1);
#define NAPI_CALL_RETURN_VOID(env,expression) do{if((expression)!=napi_ok)return;}while(false)
struct GeoAddress{std::string locale_,countryCode_,countryName_,administrativeArea_,subAdministrativeArea_,locality_,subLocality_;};
struct Location{double marker=0;};
struct AsyncContext{napi_env env;napi_value resourceName=nullptr,result[2]={nullptr,nullptr};int errCode=0;std::function<void(void*)> executeFunc,completeFunc;explicit AsyncContext(napi_env value):env(value){}virtual ~AsyncContext()=default;};
struct LocatorImpl{int error=0,calls=0,sport=0,timeout=0;std::string locale;int GetCurrentDistrictV9(const std::string& language,int32_t ms,std::shared_ptr<GeoAddress>& out){++calls;locale=language;timeout=ms;if(error)return error;out=std::make_shared<GeoAddress>();out->locale_="challenge-locale";out->countryCode_="X1";out->subLocality_="challenge-neighborhood";return 0;}int GetPostProcessingTrackV9(int32_t value,std::vector<Location>& out){++calls;sport=value;if(error)return error;out={{17.25},{18.5}};return 0;}};
struct Locator{static std::shared_ptr<LocatorImpl> instance;static std::shared_ptr<LocatorImpl> GetInstance(){return instance;}};std::shared_ptr<LocatorImpl> Locator::instance=std::make_shared<LocatorImpl>();
int napi_create_string_utf8(napi_env env,const char* text,size_t count,napi_value* out){*out=make(*env,napi_string);(*out)->text=count==NAPI_AUTO_LENGTH?text:std::string(text,count);return 0;}
int napi_create_array_with_length(napi_env env,size_t count,napi_value* out){*out=make(*env,napi_object);(*out)->array=true;(*out)->elements.resize(count);return 0;}
int napi_set_element(napi_env,napi_value array,size_t index,napi_value value){array->elements.at(index)=value;return 0;}
void SetValueUtf8String(napi_env env,const char* key,const char* text,napi_value object){auto value=make(*env,napi_string);value->text=text;object->properties[key]=value;}
void LocationToJs(napi_env,const std::unique_ptr<Location>& location,napi_value object){object->number=location->marker;}
napi_value DoAsyncWork(napi_env env,AsyncContext* raw,size_t argc,napi_value*,size_t objectArgs){assert(argc==0&&objectArgs==0);std::unique_ptr<AsyncContext> context(raw);context->executeFunc(context.get());context->completeFunc(context.get());auto promise=make(*env,napi_object);promise->number=context->errCode;promise->properties["value"]=context->result[1];return promise;}
struct RequestConfig{int sports=0;void SetSportsType(int value){sports=value;}void SetPriority(int){}void SetScenario(int){}void SetTimeInterval(int){}void SetMaxAccuracy(double){}void SetDistanceInterval(double){}void SetIsNeedPoi(bool){}};
int JsObjectToInt(napi_env env,napi_value object,const char* key,int& out){napi_value value=nullptr;if(napi_get_named_property(env,object,key,&value)||value->type!=napi_number)return 1;out=value->number;return 0;}
int JsObjectToDouble(napi_env env,napi_value object,const char* key,double& out){napi_value value=nullptr;if(napi_get_named_property(env,object,key,&value)||value->type!=napi_number)return 1;out=value->number;return 0;}
int JsObjectToBool(napi_env,napi_value,const char*,bool&){return 1;}
'''
        adapter = sources['frameworks/js/napi/source/location_napi_adapter.cpp']
        actual = function(adapter, 'struct DistrictAsyncContext').rstrip() + ';\n'
        actual += function(adapter, 'struct TrackAsyncContext').rstrip() + ';\n'
        for signature in ['static bool ReadOptionalDistrictRequest(', 'napi_value GetCurrentDistrict(', 'napi_value GetPostProcessingTrack(']:
            actual += function(adapter, signature)
        actual += function(sources['frameworks/js/napi/source/napi_util.cpp'], 'void JsObjToLocationRequest(')
        main = r'''
int main(){Env env;auto client=Locator::instance;auto invokeDistrict=[&](std::vector<napi_value> args){Info info{args};env.error=0;return GetCurrentDistrict(&env,&info);};auto promise=invokeDistrict({});assert(promise&&promise->number==0&&client->timeout==5000&&client->locale.empty());auto value=promise->properties["value"];assert(value->properties["countryCode"]->text=="X1"&&value->properties["subLocality"]->text=="challenge-neighborhood"&&!value->properties.count("locality"));assert(invokeDistrict({&undefinedValue})->number==0);assert(!invokeDistrict({&nullValue})&&env.error==401);auto request=make(env,napi_object);auto locale=make(env,napi_string);locale->text="en";auto timeout=make(env,napi_number);timeout->number=17;request->properties={{"locale",locale},{"timeoutMs",timeout}};assert(invokeDistrict({request})->number==0&&client->locale=="en"&&client->timeout==17);locale->text=std::string(100,'x');assert(invokeDistrict({request})->number==0);locale->text+='x';assert(!invokeDistrict({request})&&env.error==401);locale->text="en";for(double bad:{0.25,2147483648.0,std::nan(""),std::numeric_limits<double>::infinity()}){timeout->number=bad;assert(!invokeDistrict({request})&&env.error==401);}timeout->number=-1;assert(invokeDistrict({request})->number==0&&client->timeout==-1);request->properties["timeoutMs"]=&undefinedValue;assert(invokeDistrict({request})->number==0&&client->timeout==5000);assert(!invokeDistrict({request,request})&&env.error==401);client->error=3301500;assert(invokeDistrict({})->number==3301500);client->error=0;
auto sport=make(env,napi_number);sport->number=4;auto invokeTrack=[&](std::vector<napi_value> args){Info info{args};env.error=0;return GetPostProcessingTrack(&env,&info);};promise=invokeTrack({sport});assert(promise->number==0&&client->sport==4&&promise->properties["value"]->elements.size()==2&&promise->properties["value"]->elements[1]->number==18.5);sport->number=4.5;assert(!invokeTrack({sport})&&env.error==401);assert(!invokeTrack({})&&env.error==401);client->error=3301200;sport->number=1;assert(invokeTrack({sport})->number==3301200);client->error=0;
auto config=std::make_unique<RequestConfig>();request->properties.clear();JsObjToLocationRequest(&env,request,config);assert(config->sports==0);request->properties["sportsType"]=sport;for(double good:{1,2,3,4}){sport->number=good;JsObjToLocationRequest(&env,request,config);assert(config->sports==good);}for(double bad:{-1.0,0.0,4.5,5.0,std::nan(""),std::numeric_limits<double>::infinity()}){sport->number=bad;JsObjToLocationRequest(&env,request,config);assert(config->sports==-1);}request->properties["sportsType"]=&undefinedValue;config->sports=0;JsObjToLocationRequest(&env,request,config);assert(config->sports==0);
sport->number=4;Locator::instance.reset();assert(invokeDistrict({})->number==3301000);assert(invokeTrack({sport})->number==3301000);
std::cout<<"Actual business NAPI: Promise-only optional/undefined/strict int32, district optional fields/errors, track payload/errors and continuous sports parser passed\n";}
'''
        compile_run(preamble + actual + main)



if __name__ == '__main__':
    unittest.main()
