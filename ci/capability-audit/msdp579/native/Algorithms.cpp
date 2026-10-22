// Apache-2.0. Real product-ABI inner-client supplement, never a provider.
#include <atomic>
#include <cerrno>
#include <cstring>
#include <sys/socket.h>
#include <sys/un.h>
#include <cmath>
#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <vector>
#include <time.h>
#include <unistd.h>
#include "stationary_manager.h"
#include "devicestatus_callback_stub.h"
#include "napi/native_api.h"
#include "napi/native_node_api.h"
using namespace OHOS;
using namespace OHOS::Msdp::DeviceStatus;
namespace {
struct Row { uint64_t seq; int32_t type; int32_t value; int32_t result; uint64_t mono; uint64_t boot; bool off; const char* kind; };
std::mutex mutex;
std::vector<Row> rows;
bool overflow=false;
uint64_t Clock(clockid_t clock) { timespec t{}; if (clock_gettime(clock,&t)) return 0;
 return static_cast<uint64_t>(t.tv_sec)*1000000000ULL+t.tv_nsec; }
void Add(const char* kind,int32_t type,int32_t value,int32_t result,bool off) {
 if (rows.size()>=4096) { overflow=true; return; }
 rows.push_back({rows.size(),type,value,result,Clock(CLOCK_MONOTONIC),Clock(CLOCK_BOOTTIME),off,kind});
}
class Callback final : public DeviceStatusCallbackStub {
public:
 bool off=false;
 void OnDeviceStatusChanged(const Data& data) override {
  std::lock_guard<std::mutex> lock(mutex);Add("callback",static_cast<int32_t>(data.type),static_cast<int32_t>(data.value),0,off);
 }
};
std::map<int32_t,sptr<Callback>> subscriptions;
napi_value Number(napi_env env,int32_t value) { napi_value out=nullptr;if(napi_create_int32(env,value,&out)!=napi_ok)return nullptr;return out; }
bool Type(napi_env env,napi_callback_info info,int32_t& value) {
 size_t argc=1;napi_value argv[1]{};napi_valuetype type=napi_undefined;double input=0;
 if(napi_get_cb_info(env,info,&argc,argv,nullptr,nullptr)!=napi_ok || argc!=1 ||
  napi_typeof(env,argv[0],&type)!=napi_ok || type!=napi_number || napi_get_value_double(env,argv[0],&input)!=napi_ok ||
  !std::isfinite(input) || input!=std::floor(input) || input<0 || input>2) {
  napi_throw_error(env,"401","exact real algorithm type0..2 required");return false;
 }
 value=static_cast<int32_t>(input);return true;
}
napi_value On(napi_env env,napi_callback_info info) {
 int32_t type=0;if(!Type(env,info,type))return nullptr;
 sptr<Callback> callback=new Callback();
 {std::lock_guard<std::mutex> lock(mutex);if(subscriptions.count(type)) {napi_throw_error(env,"401","duplicate native subscription");return nullptr;}subscriptions[type]=callback;}
 const int32_t result=StationaryManager::GetInstance().SubscribeCallback(static_cast<OHOS::Msdp::DeviceStatus::Type>(type),ENTER_EXIT,SHORT,callback);
 {std::lock_guard<std::mutex> lock(mutex);Add("subscribe",type,-1,result,false);}
 return Number(env,result);
}
int32_t Stop(int32_t type) {
 sptr<Callback> callback;
 {std::lock_guard<std::mutex> lock(mutex);auto p=subscriptions.find(type);if(p==subscriptions.end())return -1;callback=p->second;}
 const int32_t result=StationaryManager::GetInstance().UnsubscribeCallback(static_cast<OHOS::Msdp::DeviceStatus::Type>(type),ENTER_EXIT,callback);
 {std::lock_guard<std::mutex> lock(mutex);callback->off=true;Add("unsubscribe",type,-1,result,true);if(result==0)subscriptions.erase(type);}
 return result;
}
napi_value Off(napi_env env,napi_callback_info info) {int32_t type=0;if(!Type(env,info,type))return nullptr;return Number(env,Stop(type));}
napi_value Drain(napi_env env,napi_callback_info info) {
 (void)info;std::lock_guard<std::mutex> lock(mutex);
 std::string out="{\"pid\":"+std::to_string(getpid())+",\"uid\":"+std::to_string(getuid())+",\"overflow\":"+(overflow?"true":"false")+",\"rows\":[";
 for(size_t i=0;i<rows.size();++i){const auto& r=rows[i];if(i)out+=",";
  out+="{\"seq\":"+std::to_string(r.seq)+",\"kind\":\""+r.kind+"\",\"type\":"+std::to_string(r.type)+",\"value\":"+std::to_string(r.value)+",\"result\":"+std::to_string(r.result)+",\"mono_ns\":\""+std::to_string(r.mono)+"\",\"boot_ns\":\""+std::to_string(r.boot)+"\",\"after_off\":"+(r.off?"true":"false")+"}";
 }
 out+="],\"active\":[";bool first=true;for(const auto& p:subscriptions){if(!first)out+=",";first=false;out+=std::to_string(p.first);}out+="]}";
 napi_value value=nullptr;if(napi_create_string_utf8(env,out.data(),out.size(),&value)!=napi_ok)return nullptr;return value;
}
napi_value WriterDenial(napi_env env,napi_callback_info info) {
 (void)info;sockaddr_un address{};address.sun_family=AF_UNIX;
 const char* path="/dev/unix/socket/qemu_sensor/rotation";
 std::memcpy(address.sun_path,path,std::strlen(path)+1);
 int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);const int createError=errno;
 int result=-2;int error=createError;
 if(fd>=0){result=connect(fd,reinterpret_cast<const sockaddr*>(&address),sizeof(address));error=result<0?errno:0;close(fd);}
 std::string out="{\"uid\":"+std::to_string(getuid())+",\"result\":"+std::to_string(result)+",\"errno\":"+std::to_string(error)+"}";
 napi_value value=nullptr;if(napi_create_string_utf8(env,out.data(),out.size(),&value)!=napi_ok)return nullptr;return value;
}
void Cleanup(void*) { for(int32_t type=0;type<3;++type)Stop(type); }
napi_value Init(napi_env env,napi_value exports) {
 napi_property_descriptor properties[]={
  {"on",nullptr,On,nullptr,nullptr,nullptr,napi_default,nullptr},
  {"off",nullptr,Off,nullptr,nullptr,nullptr,napi_default,nullptr},
  {"drain",nullptr,Drain,nullptr,nullptr,nullptr,napi_default,nullptr},
  {"writerDenial",nullptr,WriterDenial,nullptr,nullptr,nullptr,napi_default,nullptr}};
 if(napi_define_properties(env,exports,4,properties)!=napi_ok || napi_add_env_cleanup_hook(env,Cleanup,nullptr)!=napi_ok)return nullptr;
 return exports;
}
napi_module module={1,0,nullptr,Init,"msdp579",nullptr,{0}};
}
extern "C" __attribute__((constructor)) void RegisterMsdp579() {napi_module_register(&module);}
