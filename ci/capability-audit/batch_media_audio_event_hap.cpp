// SPDX-License-Identifier: Apache-2.0
#include <napi/native_api.h>
#include <atomic>
#include <cstdio>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>
extern "C" int RunBatchMediaAudioEventProbe(FILE *, const char *, int);
extern "C" void PrepareBatchMediaAudioEventProbe();
extern "C" void CancelBatchMediaAudioEventProbe();
static std::atomic<bool> running{false};
static std::atomic<int> actualResult{1};
static std::mutex controlMutex;
static std::string activeRun;
static bool ReadRun(napi_env env,napi_value value,std::string &run)
{
    size_t length=0;char bytes[33]{};
    if(napi_get_value_string_utf8(env,value,nullptr,0,&length)!=napi_ok||length!=32||
        napi_get_value_string_utf8(env,value,bytes,sizeof(bytes),&length)!=napi_ok||length!=32)return false;
    for(size_t i=0;i<length;++i)if(!((bytes[i]>='0'&&bytes[i]<='9')||(bytes[i]>='a'&&bytes[i]<='f')))return false;
    run.assign(bytes,length);return true;
}
static napi_value Run(napi_env env,napi_callback_info info)
{
    napi_value argv[3]{},result=nullptr;size_t argc=3;std::string challenge;int32_t mode=-1;
    bool accepted=napi_get_cb_info(env,info,&argc,argv,nullptr,nullptr)==napi_ok&&argc==2&&
        ReadRun(env,argv[0],challenge)&&napi_get_value_int32(env,argv[1],&mode)==napi_ok&&mode>=0&&mode<=2;
    {
        std::lock_guard<std::mutex> lock(controlMutex);
        accepted=accepted&&!running.load();
        if(accepted){activeRun=challenge;actualResult.store(1);PrepareBatchMediaAudioEventProbe();running.store(true);}
    }
    if(accepted){
        try{
            std::thread([challenge,mode]{
                int outcome=1;
                const std::string path="/data/storage/el2/base/files/audio-event-"+challenge+"-mode"+std::to_string(mode)+"-results.log";
                int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
                FILE *out=fd<0?nullptr:fdopen(fd,"w");if(out==nullptr&&fd>=0)close(fd);
                if(out!=nullptr){
                    try{outcome=RunBatchMediaAudioEventProbe(out,challenge.c_str(),mode);}
                    catch(...){fprintf(out,"{\"type\":\"exception\",\"run_id\":\"%s\"}\n",challenge.c_str());}
                    if(fclose(out)!=0)outcome=1;
                }
                actualResult.store(outcome);running.store(false);
            }).detach();
        }catch(...){actualResult.store(1);running.store(false);accepted=false;}
    }
    napi_get_boolean(env,accepted,&result);return result;
}
static napi_value Status(napi_env env,napi_callback_info info)
{
    napi_value argv[2]{},result=nullptr;size_t argc=2;std::string run;int32_t value=-1;
    if(napi_get_cb_info(env,info,&argc,argv,nullptr,nullptr)==napi_ok&&argc==1&&ReadRun(env,argv[0],run)){
        std::lock_guard<std::mutex> lock(controlMutex);
        if(run==activeRun)value=running.load()?0:(actualResult.load()==0?1:2);
    }
    napi_create_int32(env,value,&result);return result;
}
static napi_value Abort(napi_env env,napi_callback_info info)
{
    napi_value argv[2]{},result=nullptr;size_t argc=2;std::string run;bool accepted=false;
    if(napi_get_cb_info(env,info,&argc,argv,nullptr,nullptr)==napi_ok&&argc==1&&ReadRun(env,argv[0],run)){
        std::lock_guard<std::mutex> lock(controlMutex);
        accepted=run==activeRun&&running.load();if(accepted)CancelBatchMediaAudioEventProbe();
    }
    napi_get_boolean(env,accepted,&result);return result;
}
static napi_value Init(napi_env env,napi_value exports)
{
    napi_property_descriptor methods[]={
        {"run",nullptr,Run,nullptr,nullptr,nullptr,napi_default,nullptr},
        {"status",nullptr,Status,nullptr,nullptr,nullptr,napi_default,nullptr},
        {"abort",nullptr,Abort,nullptr,nullptr,nullptr,napi_default,nullptr}};
    if(napi_define_properties(env,exports,sizeof(methods)/sizeof(methods[0]),methods)!=napi_ok)return nullptr;
    return exports;
}
static napi_module module={1,0,nullptr,Init,"batchmediaaudioevent",nullptr,{0}};
extern "C" __attribute__((constructor)) void RegisterBatchMediaAudioEvent(){napi_module_register(&module);}
