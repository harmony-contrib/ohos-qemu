#!/usr/bin/env python3
"""Execute actual GNSS callbacks/configuration using frozen generated POD types.

Only HDI transport, service request dispatch, hooks and IPC identity are host
boundaries. This is not a vendor/HDI/QEMU or packaged-runtime validation.
"""
import hashlib
import json
import os
import resource
from pathlib import Path
import subprocess
import tempfile
import unittest

from batch_location_runtime_fixture import ROOT, FIXTURE, function, runtime_sources

ABI = Path(__file__).parent / 'fixtures/batch_location/gnss_abi_before.json'
CALLBACK = 'services/location_gnss/gnss/source/gnss_event_callback.cpp'
ABILITY = 'services/location_gnss/gnss/source/gnss_ability.cpp'
HEADER = 'services/location_gnss/gnss/include/gnss_event_callback.h'


def declaration(source, signature):
    body = function(source, signature).rstrip()
    return body + source[source.index(body) + len(body):source.index(';', source.index(body) + len(body)) + 1] + '\n'


PREAMBLE = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <initializer_list>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <sys/time.h>
#include <vector>
#define LBSLOGE(...) ((void)0)
#define LBSLOGD(...) ((void)0)
#define LBSLOGI(...) ((void)0)
#define CHK_PARCEL_RETURN_VALUE(value) if (!(value)) return false
using LocationErrCode=int;
constexpr int ERRCODE_SUCCESS=0,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_INVALID_PARAM=401,ERR_OK=0,ERR_INVALID_VALUE=-1;
constexpr int MODE_STANDALONE=1,MODE_MS_BASED=2,MODE_MS_ASSISTED=3;
constexpr int MILLI_PER_SEC=1000,MAXIMUM_INTERATION=1024,GNSS=1,GNSS_ABILITY=2,RECEIVE_GNSS_LOCATION=3,RECEIVE_SATELLITESTATUSINFO=4,HDI_EVENT=5,START_GNSS=6,START_GNSS_CACHE=7,EVENT_INTERVAL_UNITE=1000;
constexpr int GNSS_BATCHING_WORKING_STATUS_ENGINE_ON=3,GNSS_BATCHING_WORKING_STATUS_SESSION_BEGIN=1,GNSS_BATCHING_WORKING_STATUS_ENGINE_OFF=4,GNSS_BATCHING_WORKING_STATUS_NONE=0;
void WriteLocationInnerEvent(int,std::initializer_list<std::string>) {}
void WriteLocationInnerEvent(int,const std::vector<std::string>&,const std::vector<std::string>&) {}
struct Parcel{int64_t ReadInt64(){return 0;}double ReadDouble(){return 0;}bool WriteInt64(int64_t){return true;}bool WriteDouble(double){return true;}};
struct Parcelable{virtual ~Parcelable()=default;virtual bool Marshalling(Parcel&)const=0;};
struct CommonUtils{static int64_t GetCurrentTimeStamp(){return 123456;}};
struct Location {
 double latitude=0,longitude=0,altitude=0,accuracy=0,speed=0,direction=0,altitudeAccuracy=0,speedAccuracy=0,directionAccuracy=0;
 int64_t timeStamp=0,timeSinceBoot=0,uncertainty=0;bool mock=false;int source=0;uint32_t validity=0;
 void SetLatitude(double x){latitude=x;}void SetLongitude(double x){longitude=x;}void SetAltitude(double x){altitude=x;}void SetAccuracy(double x){accuracy=x;}void SetSpeed(double x){speed=x;}void SetDirection(double x){direction=x;}void SetAltitudeAccuracy(double x){altitudeAccuracy=x;}void SetSpeedAccuracy(double x){speedAccuracy=x;}void SetDirectionAccuracy(double x){directionAccuracy=x;}
 void SetTimeStamp(int64_t x){timeStamp=x;}int64_t GetTimeStamp()const{return timeStamp;}void SetTimeSinceBoot(int64_t x){timeSinceBoot=x;}void SetUncertaintyOfTimeSinceBoot(int64_t x){uncertainty=x;}void SetIsFromMock(bool x){mock=x;}void SetLocationSourceType(int x){source=x;}void SetFieldValidity(uint32_t x){validity=x;}
};
struct IPCSkeleton{static std::string ResetCallingIdentity(){return "original";}static void SetCallingIdentity(const std::string& value){assert(value=="original");}};
struct LocationSourceType{static constexpr int GNSS_TYPE=1;};
struct GnssStatusInfo{std::vector<float> cn0;int64_t availableTimeStamp=0;};
enum class LocationProcessStage{GNSS_STATUS_REPORT_PROCESS,START_GNSS_PROCESS};
struct HookUtils{static inline GnssStatusInfo received;static LocationErrCode ExecuteHook(LocationProcessStage stage,void* input,void*){if(stage==LocationProcessStage::GNSS_STATUS_REPORT_PROCESS)received=*static_cast<GnssStatusInfo*>(input);return 0;}};
static void SetGpsTime(int64_t){}
'''

BOUNDARIES = r'''
namespace HDI=OHOS::HDI;
using namespace OHOS::HDI::Location::Gnss::V2_0;
struct WorkRecord{std::vector<int> seconds;int Size(){return seconds.size();}int GetTimeInterval(int i){return seconds.at(i);}};
struct LocationConfigManager{int mode=MODE_STANDALONE;static LocationConfigManager* GetInstance(){static LocationConfigManager value;return &value;}int GetSuplMode(){return mode;}};
template<class T>using sptr=std::shared_ptr<T>;
struct IGnssInterface{
 static inline sptr<IGnssInterface> current;std::vector<GnssConfigPara> configs;std::vector<int> starts;int configError=0,startError=0;
 static sptr<IGnssInterface> Get(){return current;}
 int SetGnssConfigPara(const GnssConfigPara& value){configs.push_back(value);return configError;}
 int StartGnss(GnssStartType value){starts.push_back(value);return startError;}
};
class GnssAbility{public:
 bool mock=false,supported=true;int requests=0,batchRequests=1,dispatches=0;std::vector<int> lastRequest;
 int64_t fixInterval_=1000;std::atomic<int> gnssWorkingStatus_{GNSS_WORKING_STATUS_ENGINE_ON},gnssBatchingWorkingStatus_{GNSS_BATCHING_WORKING_STATUS_ENGINE_ON};
 std::vector<std::unique_ptr<SatelliteStatus>> satellites;std::vector<Location> fixes;
 static GnssAbility* GetInstance(){static GnssAbility value;return &value;}
 bool IsMockEnabled(){return mock;}bool IsSupportGps(){return supported;}
 bool IsGnssEnabled();bool IsGnssBatchingEnabled();
 void ReportSv(const std::unique_ptr<SatelliteStatus>& value){satellites.push_back(std::make_unique<SatelliteStatus>(*value));}
 void ReportLocationInfo(int name,const std::shared_ptr<Location>& value){assert(name==GNSS_ABILITY);fixes.push_back(*value);}
 int GetRequestNum(){return requests;}int GetBatchingRequestNum(){return batchRequests;}
 void LocationRequest(WorkRecord& value){++dispatches;lastRequest=value.seconds;requests=value.Size();if(!requests){gnssWorkingStatus_=GNSS_WORKING_STATUS_SESSION_END;return;}StartGnss();}
 LocationErrCode SendLocationRequest(WorkRecord&);LocationErrCode SetPositionMode();LocationErrCode SetCachePositionMode(int,bool);void StartGnss();void StartGnssBatching(int,bool);
};
namespace AppExecFwk{struct InnerEvent{using Pointer=std::unique_ptr<InnerEvent>;std::unique_ptr<WorkRecord> record;template<class T>std::unique_ptr<T> GetUniqueObject(){return std::move(record);}};}
class GnssHandler{public:void HandleSendLocationRequest(const AppExecFwk::InnerEvent::Pointer&);};
class GnssEventCallback{public:int32_t ReportLocation(const LocationInfo&);int32_t ReportSatelliteStatusInfo(const SatelliteStatusInfo&);
 ORIGINAL_DUMMY_DECLARATIONS
};
'''

MAIN = r'''
SatelliteStatusInfo measurement(unsigned int count){
 SatelliteStatusInfo data{};data.satellitesNumber=count;
 for(unsigned int i=0;i<count;++i){data.satelliteIds.push_back(20+i);data.constellation.push_back(i%2?CONSTELLATION_CATEGORY_GALILEO:CONSTELLATION_CATEGORY_GPS);data.carrierToNoiseDensitys.push_back(15.25+i);data.elevation.push_back(10.5+i);data.azimuths.push_back(40.5+i);data.carrierFrequencies.push_back(1575420000.0f+i*1000);data.additionalInfo.push_back(i%2?0:SATELLITES_ADDITIONAL_INFO_USED_IN_FIX);}
 return data;
}
void checkMeasurement(const SatelliteStatusInfo& input,SatelliteStatus& actual){
 assert(actual.GetSatellitesNumber()==int(input.satellitesNumber));
 for(unsigned int i=0;i<input.satellitesNumber;++i){assert(actual.GetSatelliteIds().at(i)==input.satelliteIds[i]);assert(actual.GetConstellationTypes().at(i)==input.constellation[i]);assert(actual.GetCarrierToNoiseDensitys().at(i)==input.carrierToNoiseDensitys[i]);assert(actual.GetAltitudes().at(i)==input.elevation[i]);assert(actual.GetAzimuths().at(i)==input.azimuths[i]);assert(actual.GetCarrierFrequencies().at(i)==input.carrierFrequencies[i]);assert(uint32_t(actual.GetSatelliteAdditionalInfoList().at(i))==input.additionalInfo[i]);}
}
int main(){
 auto* service=GnssAbility::GetInstance();GnssEventCallback callback;LocationInfo fix{};fix.latitude=23.625;fix.longitude=-71.875;fix.altitude=42;fix.horizontalAccuracy=4.25;fix.speed=7.5;fix.bearing=33;fix.verticalAccuracy=5;fix.speedAccuracy=0.5;fix.bearingAccuracy=1.5;fix.timeForFix=1700000034567LL;fix.timeSinceBoot=9876543210LL;fix.timeUncertainty=19;fix.fieldValidity=GNSS_LOCATION_LAT_VALID|GNSS_LOCATION_LONG_VALID|GNSS_LOCATION_HORIZONTAL_ACCURACY_VALID|GNSS_LOCATION_TIME_VALID|GNSS_LOCATION_TIME_SINCE_BOOT_VALID;
 // No satellite report exists: a location alone must not synthesize one.
 assert(callback.ReportLocation(fix)==0&&service->satellites.empty());
 for(unsigned int count:{0u,1u,3u,4u,64u,128u}){
  auto input=measurement(count);auto before=service->satellites.size();assert(callback.ReportSatelliteStatusInfo(input)==0);assert(service->satellites.size()==before+1);checkMeasurement(input,*service->satellites.back());
  assert(HookUtils::received.cn0==input.carrierToNoiseDensitys);assert(callback.ReportLocation(fix)==0);assert(service->satellites.size()==before+1);checkMeasurement(input,*service->satellites.back());
 }
 const auto& actual=service->fixes.back();assert(actual.latitude==fix.latitude&&actual.longitude==fix.longitude&&actual.altitude==fix.altitude&&actual.accuracy==fix.horizontalAccuracy&&actual.speed==fix.speed&&actual.direction==fix.bearing&&actual.altitudeAccuracy==fix.verticalAccuracy&&actual.speedAccuracy==fix.speedAccuracy&&actual.directionAccuracy==fix.bearingAccuracy&&actual.timeStamp==fix.timeForFix&&actual.timeSinceBoot==fix.timeSinceBoot&&actual.uncertainty==fix.timeUncertainty&&actual.validity==fix.fieldValidity&&!actual.mock&&actual.source==1);
 auto before=service->satellites.size();for(int field=0;field<7;++field){auto bad=measurement(3);switch(field){case 0:bad.satelliteIds.pop_back();break;case 1:bad.constellation.pop_back();break;case 2:bad.carrierToNoiseDensitys.pop_back();break;case 3:bad.elevation.pop_back();break;case 4:bad.azimuths.pop_back();break;case 5:bad.carrierFrequencies.pop_back();break;case 6:bad.additionalInfo.pop_back();break;}assert(callback.ReportSatelliteStatusInfo(bad)==ERR_INVALID_VALUE&&service->satellites.size()==before);}
 auto huge=measurement(0);huge.satellitesNumber=std::numeric_limits<uint32_t>::max();assert(callback.ReportSatelliteStatusInfo(huge)==ERR_INVALID_VALUE&&service->satellites.size()==before);
 auto tail=measurement(3);tail.satellitesNumber=1;assert(callback.ReportSatelliteStatusInfo(tail)==0);checkMeasurement(tail,*service->satellites.back());assert(HookUtils::received.cn0.size()==1);
 service->mock=true;auto fixes=service->fixes.size();assert(callback.ReportLocation(fix)==0&&service->fixes.size()==fixes);service->mock=false;

 auto hdi=std::make_shared<IGnssInterface>();IGnssInterface::current=hdi;
 for(int mode:{MODE_STANDALONE,MODE_MS_BASED,MODE_MS_ASSISTED}){LocationConfigManager::GetInstance()->mode=mode;for(int64_t interval:{0LL,1000LL,90000LL,4294967295LL}){service->fixInterval_=interval;assert(service->SetPositionMode()==0);const auto& config=hdi->configs.back();assert(config.gnssBasic.minInterval==uint32_t(interval)&&int(config.gnssBasic.gnssMode)==mode&&config.gnssCaching.interval==0&&!config.gnssCaching.fifoFullNotify);}}
 LocationConfigManager::GetInstance()->mode=-1;auto configurations=hdi->configs.size();assert(service->SetPositionMode()==3301000&&hdi->configs.size()==configurations);LocationConfigManager::GetInstance()->mode=1;
 for(int64_t interval:{-1LL,4294967296LL}){service->fixInterval_=interval;assert(service->SetPositionMode()==401&&hdi->configs.size()==configurations);}service->fixInterval_=1000;
 for(int error:{-5,-95,7}){hdi->configError=error;assert(service->SetPositionMode()==3301000);assert(service->SetCachePositionMode(5000,true)==3301000);auto starts=hdi->starts.size();service->requests=1;service->gnssWorkingStatus_=GNSS_WORKING_STATUS_ENGINE_ON;service->StartGnss();assert(hdi->starts.size()==starts&&service->gnssWorkingStatus_==GNSS_WORKING_STATUS_ENGINE_ON);service->gnssBatchingWorkingStatus_=GNSS_BATCHING_WORKING_STATUS_ENGINE_ON;service->StartGnssBatching(5000,true);assert(hdi->starts.size()==starts&&service->gnssBatchingWorkingStatus_==GNSS_BATCHING_WORKING_STATUS_ENGINE_ON);}hdi->configError=0;
 assert(service->SetCachePositionMode(5000,true)==0);const auto& cache=hdi->configs.back();assert(cache.gnssCaching.interval==5000&&cache.gnssCaching.fifoFullNotify&&cache.gnssBasic.minInterval==0&&int(cache.gnssBasic.gnssMode)==0);
 service->requests=1;service->gnssWorkingStatus_=GNSS_WORKING_STATUS_ENGINE_ON;service->StartGnss();assert(hdi->starts.back()==GNSS_START_TYPE_NORMAL&&service->gnssWorkingStatus_==GNSS_WORKING_STATUS_SESSION_BEGIN);
 service->gnssBatchingWorkingStatus_=GNSS_BATCHING_WORKING_STATUS_ENGINE_ON;service->StartGnssBatching(5000,false);assert(hdi->starts.back()==GNSS_START_TYPE_GNSS_CACHE&&service->gnssBatchingWorkingStatus_==GNSS_BATCHING_WORKING_STATUS_SESSION_BEGIN);
 auto starts=hdi->starts.size();service->StartGnss();assert(hdi->starts.size()==starts);
 hdi->startError=-5;service->gnssWorkingStatus_=GNSS_WORKING_STATUS_ENGINE_ON;service->StartGnss();assert(service->gnssWorkingStatus_==GNSS_WORKING_STATUS_ENGINE_ON);hdi->startError=0;
 IGnssInterface::current=nullptr;assert(service->SetPositionMode()==3301000&&service->SetCachePositionMode(10,false)==3301000);IGnssInterface::current=hdi;
 WorkRecord requests{{30,2,7}};service->gnssWorkingStatus_=GNSS_WORKING_STATUS_ENGINE_ON;assert(service->SendLocationRequest(requests)==0&&service->fixInterval_==2000&&hdi->configs.back().gnssBasic.minInterval==2000);
 requests.seconds={9,0,5};assert(service->SendLocationRequest(requests)==0&&service->fixInterval_==0&&hdi->configs.back().gnssBasic.minInterval==0);
 auto dispatches=service->dispatches;configurations=hdi->configs.size();requests.seconds={-1};assert(service->SendLocationRequest(requests)==401&&service->dispatches==dispatches&&hdi->configs.size()==configurations);
 hdi->configError=-5;requests.seconds={4};assert(service->SendLocationRequest(requests)==3301000&&service->fixInterval_==0&&service->dispatches==dispatches);hdi->configError=0;
 requests.seconds={std::numeric_limits<int>::max()};assert(service->SendLocationRequest(requests)==0&&service->fixInterval_==4294967295LL&&hdi->configs.back().gnssBasic.minInterval==4294967295U);
 WorkRecord none;assert(service->SendLocationRequest(none)==0&&service->requests==0);
 AppExecFwk::InnerEvent::Pointer event=std::make_unique<AppExecFwk::InnerEvent>();event->record=std::make_unique<WorkRecord>();event->record->seconds={13,3,8};GnssHandler handler;handler.HandleSendLocationRequest(event);assert(service->fixInterval_==3000&&hdi->configs.back().gnssBasic.minInterval==3000);
 hdi->configError=-5;requests.seconds={1};service->gnssWorkingStatus_=GNSS_WORKING_STATUS_ENGINE_ON;starts=hdi->starts.size();assert(service->SendLocationRequest(requests)==3301000&&hdi->starts.size()==starts);hdi->configError=0;
 std::cout<<"Actual GNSS callbacks preserve no/zero/1/3/4/64/128 SV measurements and every field; malformed vectors rejected. Generated POD configuration, intervals, real error gates and start types passed. Host boundaries only.\n";
}
'''


class GnssRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = runtime_sources()
        cls.abi = json.loads(ABI.read_text())

    def harness(self, original=False):
        abi = self.abi
        raw = abi['/ohos/out/arm64_virt/gen/drivers/interface/location/gnss/v2_0/gnss_types.h']['text']
        types = ''.join(declaration(raw, name) for name in [
            'enum GnssLocationValidity', 'enum GnssWorkingMode', 'enum GnssStartType', 'enum GnssWorkingStatus',
            'enum ConstellationCategory', 'enum SatelliteAdditionalInfo', 'struct SatelliteStatusInfo',
            'struct GnssBasicConfig', 'struct GnssCachingConfig', 'struct GnssConfigPara', 'struct LocationInfo'])
        satellite = abi['/ohos/base/location/location/interfaces/inner_api/include/satellite_status.h']['text']
        satellite_class = declaration(satellite, 'class SatelliteStatus :')
        source = abi['/ohos/base/location/location/frameworks/base_module/source/satellite_status.cpp']['text']
        satellite_functions = source[source.index('SatelliteStatus::SatelliteStatus()'):source.index('} // namespace Location')]
        callback = json.loads(FIXTURE.read_text())['files'][CALLBACK] if original else self.sources[CALLBACK]
        body = ''.join(function(callback, signature) for signature in ['int32_t GnssEventCallback::ReportLocation(', 'int32_t GnssEventCallback::ReportSatelliteStatusInfo('])
        dummy = ''
        declarations = ''
        if original:
            dummy = callback[callback.index('const int WEAK_GPS_SIGNAL_SCENARIO_COUNT'):callback.index('static void SetGpsTime')]
            body += callback[callback.index('void GnssEventCallback::SendDummySvInfo()'):callback.index('int32_t GnssEventCallback::RequestGnssReferenceInfo')]
            header = json.loads(FIXTURE.read_text())['files'][HEADER]
            declarations = header[header.index('    void SendDummySvInfo();'):header.index('\n};')]
        ability = self.sources[ABILITY]
        functions = ''.join(function(ability, signature) for signature in ['bool GnssAbility::IsGnssEnabled(', 'bool GnssAbility::IsGnssBatchingEnabled(', 'LocationErrCode GnssAbility::SetPositionMode(', 'LocationErrCode GnssAbility::SetCachePositionMode(', 'void GnssAbility::StartGnss()', 'void GnssAbility::StartGnssBatching(', 'LocationErrCode GnssAbility::SendLocationRequest(', 'void GnssHandler::HandleSendLocationRequest('])
        return PREAMBLE + '\nnamespace OHOS::HDI::Location::Gnss::V2_0 {\n' + types + '\n}\n' + satellite_class + satellite_functions + BOUNDARIES.replace('ORIGINAL_DUMMY_DECLARATIONS', declarations) + dummy + body + functions + MAIN

    def execute(self, source, expect_success=True):
        with tempfile.TemporaryDirectory(prefix='batch-location-gnss-') as directory:
            path = Path(directory)
            (path / 'gnss.cpp').write_text(source)
            build = subprocess.run(['clang++', '-std=c++17', '-O1', '-g', '-fno-omit-frame-pointer', '-fsanitize=address,undefined', str(path / 'gnss.cpp'), '-o', str(path / 'gnss')], capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            result = subprocess.run([str(path / 'gnss')], env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1'}, capture_output=True, text=True, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            if expect_success:
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                print(result.stdout.strip())
            else:
                self.assertNotEqual(0, result.returncode)
                self.assertIn('service->satellites.size()==before+1', result.stderr)
                print('Original fixed callback reproduces synthetic SV assertion failure; patched function passes.')

    def test_actual_callbacks_configuration_and_request_dispatch(self):
        self.execute(self.harness())

    def test_fixed_original_reproduces_synthetic_satellite_regression(self):
        self.execute(self.harness(original=True), expect_success=False)

    def test_abi_frozen_and_production_dummy_removed(self):
        for data in self.abi.values():
            self.assertEqual(data['sha256'], hashlib.sha256(data['text'].encode()).hexdigest())
        for token in ['SendDummySvInfo', 'AddDummySv', 'ReportDummySv', 'IsNeedSvIncrease', 'g_svInfo', 'g_svIncrease', 'g_hasLocation']:
            self.assertNotIn(token, self.sources[CALLBACK] + self.sources[HEADER])
        handler = function(self.sources[ABILITY], 'void GnssHandler::HandleSendLocationRequest(')
        self.assertIn('gnssAbility->SendLocationRequest(*workrecord)', handler)
        self.assertNotIn('gnssAbility->LocationRequest(', handler)


if __name__ == '__main__':
    unittest.main()
