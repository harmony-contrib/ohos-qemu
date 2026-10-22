// Apache-2.0. Diagnostic caller of the shipped SDKs; implements no provider.
#include <atomic>
#include <chrono>
#include <cerrno>
#include <condition_variable>
#include <cstdint>
#include <ctime>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <unistd.h>
#include <vector>
#include "device_security_info.h"
#include "dev_slinfo_mgr.h"
#include "device_auth.h"
#include "dump_manager_client.h"
#include "ipc_skeleton.h"
#include "napi/native_api.h"
#include "napi/native_node_api.h"

namespace {
uint64_t Now() { timespec t{}; if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
 return static_cast<uint64_t>(t.tv_sec)*1000000000ULL+t.tv_nsec; }
std::string Hex(const uint8_t *p,size_t n) { static const char h[]="0123456789abcdef";
 std::string s; for(size_t i=0;i<n;++i){s+=h[p[i]>>4];s+=h[p[i]&15];} return s; }
struct Callback { uint64_t ns; int32_t result; int32_t level; std::string identity; std::string kind; };
std::mutex mutex; std::condition_variable condition; std::vector<Callback> callbacks;
// Only ONE request is live in this process. Timed-out callbacks are retained;
// no subsequent query is admitted until this process is actually restarted.
std::atomic<bool> poisoned{false};
void DslCallback(const DeviceIdentify *id, DeviceSecurityInfo *info) {
 int32_t level=-1; int32_t result=GetDeviceSecurityLevelValue(info,&level);
 std::string identity=id && id->length<=DEVICE_ID_MAX_LEN ? Hex(id->identity,id->length) : "invalid";
 { std::lock_guard<std::mutex> l(mutex); callbacks.push_back({Now(),result,level,identity,"dsl"}); }
 FreeDeviceSecurityInfo(info); condition.notify_all();
}
void DtmCallback(DEVSLQueryParams *id,int32_t result,uint32_t level) {
 std::string identity=id && id->udidLen<=MAX_UDID_LENGTH ? Hex(id->udid,id->udidLen) : "invalid";
 { std::lock_guard<std::mutex> l(mutex); callbacks.push_back({Now(),result,static_cast<int32_t>(level),identity,"dtm"}); }
 condition.notify_all();
}
struct Work { napi_env env{}; napi_deferred deferred{}; napi_async_work work{};
 std::string action,arg,output,text; int32_t account=0,rc=-1,value=-1; uint64_t begin=0,end=0;
 uint32_t uid=0,pid=0; uint64_t token=0; bool outputEof=false; int outputError=0; std::vector<Callback> observed; };
std::mutex operation;
void Run(napi_env,void *opaque) {
 auto &w=*static_cast<Work*>(opaque); std::lock_guard<std::mutex> serial(operation);
 w.begin=Now();w.uid=getuid();w.pid=getpid();w.token=OHOS::IPCSkeleton::GetSelfTokenID();
 {std::lock_guard<std::mutex> l(mutex); if(!callbacks.empty()) poisoned=true;}
 if(poisoned){w.rc=-9001;w.text="previous request has unconsumed/late callback; restart required";w.end=Now();return;}
 if(w.action=="dump" || w.action=="dump-invalid") {
  int fd=open(w.output.c_str(),O_CREAT|O_EXCL|O_RDWR|O_CLOEXEC,0600);
  if(fd<0){w.rc=-9002;w.end=Now();return;}
  std::vector<std::u16string> args=w.action=="dump"?std::vector<std::u16string>{u"-ls"}:std::vector<std::u16string>{};
  w.rc=OHOS::HiviewDFX::DumpManagerClient::GetInstance().Request(args,fd);
  // The shipped client issues synchronous IPC. Service RequestMain closes
  // its output FD before Request returns; a complete caller read must still
  // reach an actual EOF, and any bounded-read error is retained separately.
  if(lseek(fd,0,SEEK_SET)<0){w.outputError=errno;}
  else {char b[4096];for(;;){ssize_t n=read(fd,b,sizeof(b));
   if(n==0){w.outputEof=true;break;}
   if(n<0){if(errno==EINTR)continue;w.outputError=errno;break;}
   if(w.text.size()+static_cast<size_t>(n)>1048576){w.outputError=EFBIG;break;}
   w.text.append(b,static_cast<size_t>(n));}}
  close(fd);
 } else if(w.action=="dsl-sync" || w.action=="dsl-async" || w.action=="dsl-invalid") {
  DeviceIdentify id{};id.length=static_cast<uint32_t>(w.arg.size());
  if(id.length<=DEVICE_ID_MAX_LEN) memcpy(id.identity,w.arg.data(),id.length);
  RequestOption option{0,5,0};DeviceSecurityInfo *info=nullptr;
  if(w.action=="dsl-invalid") w.rc=RequestDeviceSecurityInfo(nullptr,&option,&info);
  else if(w.action=="dsl-sync") {w.rc=RequestDeviceSecurityInfo(&id,&option,&info);
   if(info){w.value=-1;int r=GetDeviceSecurityLevelValue(info,&w.value);w.text=std::to_string(r);FreeDeviceSecurityInfo(info);}}
  else { w.rc=RequestDeviceSecurityInfoAsync(&id,&option,DslCallback);
   if(w.rc==0){std::unique_lock<std::mutex> l(mutex); if(!condition.wait_for(l,std::chrono::seconds(55),[]{return !callbacks.empty();})) poisoned=true;
    w.observed=callbacks;callbacks.clear();}}
 } else if(w.action=="dtm-sync" || w.action=="dtm-async" || w.action=="dtm-invalid") {
  DEVSLQueryParams id{};id.udidLen=static_cast<uint32_t>(w.arg.size());
  if(id.udidLen<=MAX_UDID_LENGTH)memcpy(id.udid,w.arg.data(),id.udidLen);
  int init=DATASL_OnStart();w.text=std::to_string(init);
  if(init==0){uint32_t level=UINT32_MAX;
   if(w.action=="dtm-invalid")w.rc=DATASL_GetHighestSecLevel(nullptr,&level);
   else if(w.action=="dtm-sync"){w.rc=DATASL_GetHighestSecLevel(&id,&level);w.value=static_cast<int32_t>(level);}
   else {w.rc=DATASL_GetHighestSecLevelAsync(&id,DtmCallback);
    if(w.rc==0){std::unique_lock<std::mutex> l(mutex);if(!condition.wait_for(l,std::chrono::seconds(55),[]{return !callbacks.empty();}))poisoned=true;
     w.observed=callbacks;callbacks.clear();}}
   // OnStop frees the provider's callback registry. Never race it with a live
   // asynchronous request: timeout poisons this process and forces stop/reap.
   if(!poisoned && w.action!="dtm-async")DATASL_OnStop();
   // Async client registry is reclaimed only by actual caller process death;
   // DATASL supplies no callback-join/cancel API. This avoids destroying its
   // list while its provider callback stack is still unwinding.
  } else w.rc=init;
 } else {
  w.rc=InitDeviceAuthService();
  if(w.rc==0){const CredManager *cm=GetCredMgrInstance();const DeviceGroupManager *gm=GetGmInstance();char *data=nullptr;
   if(w.action=="cred-add" && cm)w.rc=cm->addCredential(w.account,w.arg.c_str(),&data);
   else if(w.action=="cred-query" && cm)w.rc=cm->queryCredInfoByCredId(w.account,w.arg.c_str(),&data);
   else if(w.action=="cred-export" && cm)w.rc=cm->exportCredential(w.account,w.arg.c_str(),&data);
   else if(w.action=="cred-delete" && cm)w.rc=cm->deleteCredential(w.account,w.arg.c_str());
   else if(w.action=="cred-invalid" && cm)w.rc=cm->addCredential(w.account,nullptr,&data);
   else if(w.action=="gm-denied" && gm)w.rc=gm->createGroup(w.account,1,"org.ohos.qemu.services579",w.arg.c_str());
   else w.rc=-9004;
   if(data){w.text=data;if(cm)cm->destroyInfo(&data);}
   DestroyDeviceAuthService();
  }
 }
 w.end=Now();
}
napi_value String(napi_env e,const std::string &s){napi_value v;napi_create_string_utf8(e,s.data(),s.size(),&v);return v;}
void Put(napi_env e,napi_value o,const char *k,napi_value v){napi_set_named_property(e,o,k,v);}
void Num(napi_env e,napi_value o,const char *k,double x){napi_value v;napi_create_double(e,x,&v);Put(e,o,k,v);}
void Finish(napi_env e,napi_status status,void *opaque){auto *w=static_cast<Work*>(opaque);napi_value o;napi_create_object(e,&o);
 Put(e,o,"action",String(e,w->action));Put(e,o,"argument",String(e,w->arg));Put(e,o,"data",String(e,w->text));
 Num(e,o,"rc",w->rc);Num(e,o,"value",w->value);
 napi_value eof;napi_get_boolean(e,w->outputEof,&eof);Put(e,o,"output_eof",eof);Num(e,o,"output_errno",w->outputError);Num(e,o,"uid",w->uid);Num(e,o,"pid",w->pid);Num(e,o,"account",w->account);
 Put(e,o,"begin_ns",String(e,std::to_string(w->begin)));Put(e,o,"end_ns",String(e,std::to_string(w->end)));
 Put(e,o,"token",String(e,std::to_string(w->token)));Num(e,o,"napi_status",status);
 napi_value a;napi_create_array(e,&a);for(size_t i=0;i<w->observed.size();++i){const auto &c=w->observed[i];napi_value b;napi_create_object(e,&b);
 Num(e,b,"rc",c.result);Num(e,b,"level",c.level);Put(e,b,"ns",String(e,std::to_string(c.ns)));Put(e,b,"identity_hex",String(e,c.identity));Put(e,b,"kind",String(e,c.kind));napi_set_element(e,a,i,b);}Put(e,o,"callbacks",a);
 napi_resolve_deferred(e,w->deferred,o);napi_delete_async_work(e,w->work);delete w;}
bool Text(napi_env e,napi_value v,std::string &s,size_t bound){size_t n=0;if(napi_get_value_string_utf8(e,v,nullptr,0,&n)!=napi_ok||n>bound)return false;
 std::vector<char>b(n+1);if(napi_get_value_string_utf8(e,v,b.data(),b.size(),&n)!=napi_ok)return false;s.assign(b.data(),n);return true;}
napi_value Execute(napi_env e,napi_callback_info i){napi_value argv[5];size_t n=5;napi_get_cb_info(e,i,&n,argv,nullptr,nullptr);auto *w=new Work();
 if(n!=4||!Text(e,argv[0],w->action,32)||!Text(e,argv[1],w->arg,65536)||!Text(e,argv[3],w->output,4096)||
 napi_get_value_int32(e,argv[2],&w->account)!=napi_ok){delete w;napi_throw_type_error(e,nullptr,"fixed action/string/account/output required");return nullptr;}
 const std::vector<std::string> actions={"dump","dump-invalid","dsl-sync","dsl-async","dsl-invalid","dtm-sync","dtm-async","dtm-invalid","cred-add","cred-query","cred-export","cred-delete","cred-invalid","gm-denied"};
 bool found=false;for(const auto &a:actions)if(a==w->action)found=true;if(!found){delete w;napi_throw_type_error(e,nullptr,"unlisted native action");return nullptr;}
 napi_value promise;napi_create_promise(e,&w->deferred,&promise);napi_create_async_work(e,nullptr,String(e,"services579"),Run,Finish,w,&w->work);napi_queue_async_work(e,w->work);return promise;}
napi_value Init(napi_env e,napi_value exports){napi_property_descriptor p={"execute",nullptr,Execute,nullptr,nullptr,nullptr,napi_default,nullptr};napi_define_properties(e,exports,1,&p);return exports;}
napi_module module={1,0,nullptr,Init,"owning_services579",nullptr,{0}};
__attribute__((constructor)) void Register(){napi_module_register(&module);}
}
