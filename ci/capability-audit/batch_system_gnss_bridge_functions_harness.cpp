// Actual extracted fixed bridge functions. Only remote/IDL scaffolding is a declared host shim.
#include "location_vendor_lib.h"
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <iostream>
using namespace OHOS::HDI::Location;
[[maybe_unused]] constexpr int HDF_ERR_INVALID_PARAM=-3,GNSS_WORKING_MODE_STANDALONE=1,GNSS_WORKING_MODE_MS_ASSISTED=3;
template<class... T> void Log(T...){}
#define HDF_LOGI(...) Log(__VA_ARGS__)
#define HDF_LOGE(...) Log(__VA_ARGS__)
struct GnssConfigPara {struct {uint32_t minInterval=0;int gnssMode=0;}gnssBasic;struct{uint32_t interval=0;bool fifoFullNotify=false;}gnssCaching;};
using LocationInfo=GnssLocation;
std::mutex g_mutex;
struct Observer {std::function<void()> run;void ReportLocation(const LocationInfo&){run();}};
using LocationCallBackMap=std::map<int,std::shared_ptr<Observer>>;
LocationCallBackMap g_locationCallBackMap;
[[maybe_unused]] GnssConfigParameter g_configPara;
GnssConfigParameter captured{};
int Capture(GnssConfigParameter* config){captured=*config;return 37;}
struct LocationVendorInterface{
 static LocationVendorInterface* GetInstance(){static LocationVendorInterface value;return &value;}
 const GnssVendorInterface* GetGnssVendorInterface(){static GnssVendorInterface table{};table.setGnssConfigPara=Capture;return &table;}
};
class GnssInterfaceImpl {public:int32_t SetGnssConfigPara(const GnssConfigPara&);bool IsGnssBasicConfigValid(int);};
void GnssWorkingStatusUpdate(uint16_t*){}
void SvStatusCallback(GnssSatelliteStatus*){}
void NmeaCallback(int64_t,const char*,int){}
#include "actual_bridge_functions.inc"
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
int main(int argc,char**argv){try{
 CHECK(argc==2);std::string mode=argv[1];
 if(mode=="callback_size"){GnssBasicCallbackIfaces cb{};GetGnssBasicCallbackMethods(&cb);CHECK(cb.size==sizeof(cb));}
 else if(mode=="callback_reentry"){
  auto observer=std::make_shared<Observer>();bool called=false;
  observer->run=[&]{std::lock_guard<std::mutex> lock(g_mutex);g_locationCallBackMap.clear();called=true;};
  g_locationCallBackMap[1]=observer;GnssLocation value{};LocationUpdate(&value);CHECK(called&&g_locationCallBackMap.empty());
 }else{
  GnssInterfaceImpl impl;GnssConfigPara config{};config.gnssBasic.gnssMode=1;config.gnssBasic.minInterval=1327;
  if(mode=="cache"){config.gnssBasic.gnssMode=0;config.gnssCaching.interval=217;config.gnssCaching.fifoFullNotify=true;}
  if(mode=="invalid_mode"){config.gnssBasic.gnssMode=4;CHECK(impl.SetGnssConfigPara(config)==HDF_ERR_INVALID_PARAM);return 0;}
  CHECK(impl.SetGnssConfigPara(config)==37);
  if(mode=="config_size")CHECK(captured.size==sizeof(captured));
  else if(mode=="interval")CHECK(captured.u.gnssBasicConfig.minInterval==1327);
  else if(mode=="cache")CHECK(captured.size==sizeof(captured)&&captured.startCategory==2&&captured.u.gnssCacheConfig.size==sizeof(GnssCachingConfig)&&captured.u.gnssCacheConfig.interval==217&&captured.u.gnssCacheConfig.fifoFullNotify);
  else throw std::runtime_error("unknown case");
 }
 std::cout<<mode<<": pass\n";return 0;
}catch(const std::exception&e){std::cerr<<argv[1]<<": "<<e.what()<<'\n';return 1;}}
