#include <AbilityKit/native_child_process.h>
#include <napi/native_api.h>
#include <unistd.h>
#include <cstdio>
#include <cstdint>
#include <atomic>
#include <string>
namespace {
std::atomic<int32_t> callbackCount{0};
void Started(int, OHIPCRemoteProxy*) { callbackCount.fetch_add(1); }
napi_value Number(napi_env env,int32_t value){napi_value result=nullptr;napi_create_int32(env,value,&result);return result;}
void Add(napi_env env,napi_value array,uint32_t& index,const char* name,int32_t code,int32_t pid=-1){
 napi_value row=nullptr,text=nullptr;napi_create_object(env,&row);napi_create_string_utf8(env,name,NAPI_AUTO_LENGTH,&text);
 napi_set_named_property(env,row,"name",text);napi_set_named_property(env,row,"code",Number(env,code));napi_set_named_property(env,row,"pid",Number(env,pid));napi_set_element(env,array,index++,row);
}
napi_value Run(napi_env env,napi_callback_info){
 napi_value result=nullptr;napi_create_array(env,&result);uint32_t index=0;
 Add(env,result,index,"parent.args.present",OH_Ability_GetCurrentChildProcessArgs()!=nullptr?1:0);
 Add(env,result,index,"native.supported",OH_Ability_IsNativeChildProcessSupported()?1:0);
 Add(env,result,index,"destroy.null",OH_Ability_DestroyChildProcessConfigs(nullptr));
 auto* configs=OH_Ability_CreateChildProcessConfigs();Add(env,result,index,"config.created",configs!=nullptr?1:0);
 if(configs==nullptr)return result;
 Add(env,result,index,"isolation.mode.null",OH_Ability_ChildProcessConfigs_SetIsolationMode(nullptr,NCP_ISOLATION_MODE_NORMAL));
 Add(env,result,index,"isolation.mode.normal",OH_Ability_ChildProcessConfigs_SetIsolationMode(configs,NCP_ISOLATION_MODE_NORMAL));
 Add(env,result,index,"isolation.mode.isolated",OH_Ability_ChildProcessConfigs_SetIsolationMode(configs,NCP_ISOLATION_MODE_ISOLATED));
 Add(env,result,index,"isolation.mode.invalid",OH_Ability_ChildProcessConfigs_SetIsolationMode(configs,static_cast<NativeChildProcess_IsolationMode>(2)));
 Add(env,result,index,"isolation.mode.restored",OH_Ability_ChildProcessConfigs_SetIsolationMode(configs,NCP_ISOLATION_MODE_NORMAL));
 Add(env,result,index,"isolation.uid.null",OH_Ability_ChildProcessConfigs_SetIsolationUid(nullptr,false));
 Add(env,result,index,"isolation.uid",OH_Ability_ChildProcessConfigs_SetIsolationUid(configs,false));
 Add(env,result,index,"process.name",OH_Ability_ChildProcessConfigs_SetProcessName(configs,"profileBoundary"));
 Add(env,result,index,"process.name.null-config",OH_Ability_ChildProcessConfigs_SetProcessName(nullptr,"profileBoundary"));
 Add(env,result,index,"process.name.null",OH_Ability_ChildProcessConfigs_SetProcessName(configs,nullptr));
 Add(env,result,index,"process.name.empty",OH_Ability_ChildProcessConfigs_SetProcessName(configs,""));
 Add(env,result,index,"process.name.invalid",OH_Ability_ChildProcessConfigs_SetProcessName(configs,"invalid:name"));
 Add(env,result,index,"process.name.64",OH_Ability_ChildProcessConfigs_SetProcessName(configs,std::string(64,'a').c_str()));
 Add(env,result,index,"process.name.65",OH_Ability_ChildProcessConfigs_SetProcessName(configs,std::string(65,'a').c_str()));
 Add(env,result,index,"process.name.restored",OH_Ability_ChildProcessConfigs_SetProcessName(configs,"profileBoundary"));
 Add(env,result,index,"create",OH_Ability_CreateNativeChildProcess("libprofile.so",Started));
 Add(env,result,index,"create.configured",OH_Ability_CreateNativeChildProcessWithConfigs("libprofile.so",configs,Started));
 Add(env,result,index,"create.null-library",OH_Ability_CreateNativeChildProcess(nullptr,Started));
 Add(env,result,index,"create.null-callback",OH_Ability_CreateNativeChildProcess("libprofile.so",nullptr));
 Add(env,result,index,"create.configured.null",OH_Ability_CreateNativeChildProcessWithConfigs("libprofile.so",nullptr,Started));
 NativeChildProcess_Args args{};args.entryParams=const_cast<char*>("__RUN__");NativeChildProcess_Options options{};int32_t pid=-1;
 auto code=OH_Ability_StartNativeChildProcess("libprofile.so:Main",args,options,&pid);Add(env,result,index,"start",code,pid);
 pid=-1;code=OH_Ability_StartNativeChildProcessWithConfigs("libprofile.so:Main",args,configs,&pid);Add(env,result,index,"start.configured",code,pid);
 pid=-1;code=OH_Ability_StartNativeChildProcess(nullptr,args,options,&pid);Add(env,result,index,"start.null",code,pid);
 pid=-1;code=OH_Ability_StartNativeChildProcessWithConfigs("libprofile.so:Main",args,nullptr,&pid);Add(env,result,index,"start.configured.null",code,pid);
 Add(env,result,index,"config.destroy",OH_Ability_DestroyChildProcessConfigs(configs));
 Add(env,result,index,"callback.count",callbackCount.load());return result;
}
napi_value Init(napi_env env,napi_value exports){napi_property_descriptor methods[]={{"run",nullptr,Run,nullptr,nullptr,nullptr,napi_default,nullptr}};napi_define_properties(env,exports,1,methods);return exports;}
napi_module module{1,0,nullptr,Init,"profile",nullptr,{0}};
}
extern "C" __attribute__((visibility("default"))) void Main(NativeChildProcess_Args args){
 FILE* file=fopen("/data/storage/el2/base/files/child-profile-__RUN__-native-peer.log","a");
 if(file){fprintf(file,"uid=%u pid=%d entry=%s\n",getuid(),getpid(),args.entryParams?args.entryParams:"");fclose(file);}
}
extern "C" __attribute__((constructor)) void RegisterProfile(){napi_module_register(&module);}
