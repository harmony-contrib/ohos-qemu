// SPDX-License-Identifier: Apache-2.0
// Ordinary foreground app; real public MIC and native surface -> real AVRecorder file.
#include <multimedia/player_framework/avrecorder.h>
#include <native_buffer/native_buffer.h>
#include <native_window/external_window.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <poll.h>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>
namespace {
constexpr int WIDTH=64,HEIGHT=64,FPS=30,FRAMES=60,CYCLES=2,TILES=64;
constexpr size_t CHALLENGE_BYTES=FRAMES*CYCLES*TILES;
constexpr const char *PRIVATE="/data/storage/el2/base/files/";
int64_t Now(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t)!=0)return -1;return static_cast<int64_t>(t.tv_sec)*1000000000+t.tv_nsec;}
struct StateEvent{int state;int reason;int64_t time;};
struct ErrorEvent{int code;int64_t time;};
struct Context{
 std::mutex mutex;std::condition_variable ready;std::vector<StateEvent> events;std::vector<ErrorEvent> errorEvents;int errors=0;int last=-1;
 Context(){events.reserve(32);errorEvents.reserve(16);}
};
void State(OH_AVRecorder*,OH_AVRecorder_State state,OH_AVRecorder_StateChangeReason reason,void *user)
{
 auto &c=*static_cast<Context*>(user);std::lock_guard<std::mutex> lock(c.mutex);
 c.last=state;if(c.events.size()<32)c.events.push_back({state,reason,Now()});else ++c.errors;c.ready.notify_all();
}
void Error(OH_AVRecorder*,int32_t code,const char*,void *user){auto &c=*static_cast<Context*>(user);std::lock_guard<std::mutex> lock(c.mutex);++c.errors;if(c.errorEvents.size()<16)c.errorEvents.push_back({code,Now()});c.ready.notify_all();}
bool Step(FILE *out,const char *run,int cycle,const char *name,int actual,int expected=AV_ERR_OK)
{
 fprintf(out,"{\"type\":\"recorder_step\",\"run_id\":\"%s\",\"cycle\":%d,\"name\":\"%s\",\"actual\":%d,\"expected\":%d,\"monotonic_ns\":%lld}\n",run,cycle,name,actual,expected,static_cast<long long>(Now()));fflush(out);return actual==expected;
}
bool Wait(Context &c,int state)
{
 std::unique_lock<std::mutex> lock(c.mutex);
 return c.ready.wait_for(lock,std::chrono::seconds(2),[&]{return c.last==state||c.errors!=0;})&&c.last==state&&c.errors==0;
}
bool ReadChallenge(const char *run,std::vector<uint8_t> &bytes)
{
 const std::string path=std::string(PRIVATE)+"recorder-"+run+"-video.bin";
 int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return false;
 struct stat info{};bool valid=fstat(fd,&info)==0&&S_ISREG(info.st_mode)&&info.st_uid==getuid()&&(info.st_mode&077)==0&&info.st_size==static_cast<off_t>(CHALLENGE_BYTES);
 bytes.resize(CHALLENGE_BYTES);size_t offset=0;
 while(valid&&offset<bytes.size()){ssize_t n=read(fd,bytes.data()+offset,bytes.size()-offset);if(n<0&&errno==EINTR)continue;if(n<=0){valid=false;break;}offset+=static_cast<size_t>(n);}
 if(close(fd)!=0)valid=false;
 return valid&&std::all_of(bytes.begin(),bytes.end(),[](uint8_t value){return value>=48&&value<=204;});
}
bool Surface(OHNativeWindow *window,const uint8_t *tiles,int64_t timestamp)
{
 // Actual recorder SurfaceEncoderAdapter uses monotonic nanoseconds, converting
 // output to microseconds itself. This differs from the direct codec probe.
 if(window==nullptr||timestamp<0||OH_NativeWindow_NativeWindowHandleOpt(window,SET_UI_TIMESTAMP,static_cast<uint64_t>(timestamp))!=0)return false;
 OHNativeWindowBuffer *native=nullptr;int fence=-1;int requested=OH_NativeWindow_NativeWindowRequestBuffer(window,&native,&fence);bool ready=true;
 if(fence>=0){pollfd item{fence,POLLIN,0};ready=poll(&item,1,2000)==1&&(item.revents&POLLIN)!=0&&(item.revents&(POLLERR|POLLNVAL|POLLHUP))==0;close(fence);}
 if(native==nullptr)return false;
 auto abort=[&]{OH_NativeWindow_NativeWindowAbortBuffer(window,native);return false;};
 if(requested!=0||!ready)return abort();
 OH_NativeBuffer *buffer=nullptr;if(OH_NativeBuffer_FromNativeWindowBuffer(native,&buffer)!=0||buffer==nullptr)return abort();
 OH_NativeBuffer_Config config{};OH_NativeBuffer_GetConfig(buffer,&config);BufferHandle *handle=OH_NativeWindow_GetBufferHandleFromNative(native);
 if(handle==nullptr||config.width!=WIDTH||config.height!=HEIGHT||config.format!=NATIVEBUFFER_PIXEL_FMT_RGBA_8888||config.stride<WIDTH*4||config.stride>16384||handle->size<static_cast<int64_t>(config.stride)*HEIGHT)return abort();
 void *address=nullptr;if(OH_NativeBuffer_Map(buffer,&address)!=0)return abort();
 if(address==nullptr){OH_NativeBuffer_Unmap(buffer);return abort();}
 auto *bytes=static_cast<uint8_t*>(address);
 for(int y=0;y<HEIGHT;++y)for(int x=0;x<WIDTH;++x){uint8_t *pixel=bytes+static_cast<size_t>(y)*config.stride+x*4;const uint8_t value=tiles[(y/8)*8+x/8];pixel[0]=value;pixel[1]=value;pixel[2]=value;pixel[3]=255;}
 if(OH_NativeBuffer_Unmap(buffer)!=0)return abort();
 Region::Rect rectangle{0,0,WIDTH,HEIGHT};Region region{&rectangle,1};
 if(OH_NativeWindow_NativeWindowFlushBuffer(window,native,-1,region)!=0)return abort();return true;
}
bool Frames(FILE *out,const char *run,int cycle,int phase,OHNativeWindow *window,const std::vector<uint8_t> &challenge)
{
 bool valid=true;const auto begin=std::chrono::steady_clock::now();
 for(int local=0;local<FRAMES/2;++local){
  std::this_thread::sleep_until(begin+std::chrono::nanoseconds(static_cast<int64_t>(local)*1000000000/FPS));
  const int frame=(phase-1)*(FRAMES/2)+local;const size_t offset=static_cast<size_t>((cycle-1)*FRAMES+frame)*TILES;
  const int64_t timestamp=Now();const bool flushed=Surface(window,challenge.data()+offset,timestamp);
  fprintf(out,"{\"type\":\"recorder_frame\",\"run_id\":\"%s\",\"cycle\":%d,\"phase\":%d,\"frame\":%d,\"input_ns\":%lld,\"after_ns\":%lld,\"flushed\":%s}\n",run,cycle,phase,frame,static_cast<long long>(timestamp),static_cast<long long>(Now()),flushed?"true":"false");fflush(out);
  if(!flushed){valid=false;break;}
 }
 // Keep the final frame's interval before pause/stop; no synthetic extra frame.
 std::this_thread::sleep_until(begin+std::chrono::seconds(1));return valid;
}
bool Cycle(FILE *out,const char *run,int cycle,bool expectedDenied,const std::vector<uint8_t> &challenge)
{
 auto context=std::make_unique<Context>();OH_AVRecorder *recorder=OH_AVRecorder_Create();
 if(!Step(out,run,cycle,"create",recorder!=nullptr?0:-1))return false;
 Context &live=*context.release();bool valid=Step(out,run,cycle,"state_callback",OH_AVRecorder_SetStateCallback(recorder,State,&live));
 valid&=Step(out,run,cycle,"error_callback",OH_AVRecorder_SetErrorCallback(recorder,Error,&live));
 const std::string basename="recorder-"+std::string(run)+"-cycle"+std::to_string(cycle)+".mp4";
 const std::string path=std::string(PRIVATE)+basename;int fd=open(path.c_str(),O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
 valid&=Step(out,run,cycle,"output_open",fd>=0?0:-1);
 std::unique_ptr<OHNativeWindow,void(*)(OHNativeWindow*)> window(nullptr,OH_NativeWindow_DestroyNativeWindow);
 bool prepared=false,started=false,rejected=false;
 if(fd>=0&&valid){
  std::string url="fd://"+std::to_string(fd);OH_AVRecorder_Config config{};config.audioSourceType=AVRECORDER_MIC;config.videoSourceType=AVRECORDER_SURFACE_YUV;
  config.profile.audioBitrate=192000;config.profile.audioChannels=2;config.profile.audioCodec=AVRECORDER_AUDIO_AAC;config.profile.audioSampleRate=48000;
  config.profile.fileFormat=AVRECORDER_CFT_MPEG_4;config.profile.videoCodec=AVRECORDER_VIDEO_AVC;config.profile.videoBitrate=1000000;
  config.profile.videoFrameWidth=WIDTH;config.profile.videoFrameHeight=HEIGHT;config.profile.videoFrameRate=FPS;config.url=url.data();config.fileGenerationMode=AVRECORDER_APP_CREATE;config.maxDuration=15;
  const int result=OH_AVRecorder_Prepare(recorder,&config);prepared=result==AV_ERR_OK;
  if(expectedDenied){fprintf(out,"{\"type\":\"recorder_denial\",\"run_id\":\"%s\",\"cycle\":%d,\"operation\":\"prepare\",\"actual\":%d}\n",run,cycle,result);rejected=result!=AV_ERR_OK;}
  else valid&=Step(out,run,cycle,"prepare",result);
  if(prepared){
   valid&=Wait(live,AVRECORDER_PREPARED);
   OHNativeWindow *surface=nullptr;valid&=Step(out,run,cycle,"input_surface",OH_AVRecorder_GetInputSurface(recorder,&surface));window.reset(surface);
   if(surface==nullptr)valid=false;
   if(surface!=nullptr){
    const uint64_t usage=NATIVEBUFFER_USAGE_CPU_READ|NATIVEBUFFER_USAGE_CPU_WRITE|NATIVEBUFFER_USAGE_MEM_DMA;
    valid&=Step(out,run,cycle,"surface_geometry",OH_NativeWindow_NativeWindowHandleOpt(surface,SET_BUFFER_GEOMETRY,WIDTH,HEIGHT));
    valid&=Step(out,run,cycle,"surface_format",OH_NativeWindow_NativeWindowHandleOpt(surface,SET_FORMAT,NATIVEBUFFER_PIXEL_FMT_RGBA_8888));
    valid&=Step(out,run,cycle,"surface_usage",OH_NativeWindow_NativeWindowHandleOpt(surface,SET_USAGE,usage));
    valid&=Step(out,run,cycle,"surface_timeout",OH_NativeWindow_NativeWindowHandleOpt(surface,SET_TIMEOUT,2000));
   }
   if(valid){
    const int result=OH_AVRecorder_Start(recorder);started=result==AV_ERR_OK;
    if(expectedDenied){fprintf(out,"{\"type\":\"recorder_denial\",\"run_id\":\"%s\",\"cycle\":%d,\"operation\":\"start\",\"actual\":%d}\n",run,cycle,result);rejected=result!=AV_ERR_OK;}
    else valid&=Step(out,run,cycle,"start",result);
    if(started){
     valid&=Wait(live,AVRECORDER_STARTED);valid&=Frames(out,run,cycle,1,surface,challenge);
     valid&=Step(out,run,cycle,"pause",OH_AVRecorder_Pause(recorder));valid&=Wait(live,AVRECORDER_PAUSED);
     const int64_t pause=Now();usleep(300000);fprintf(out,"{\"type\":\"recorder_pause\",\"run_id\":\"%s\",\"cycle\":%d,\"before_ns\":%lld,\"after_ns\":%lld}\n",run,cycle,static_cast<long long>(pause),static_cast<long long>(Now()));
     valid&=Step(out,run,cycle,"resume",OH_AVRecorder_Resume(recorder));valid&=Wait(live,AVRECORDER_STARTED);valid&=Frames(out,run,cycle,2,surface,challenge);
     valid&=Step(out,run,cycle,"stop",OH_AVRecorder_Stop(recorder));valid&=Wait(live,AVRECORDER_STOPPED);
    }
   }
  }
 }
 window.reset();
 if(prepared)valid&=Step(out,run,cycle,"reset",OH_AVRecorder_Reset(recorder));
 const int released=OH_AVRecorder_Release(recorder);valid&=Step(out,run,cycle,"release",released);
 struct stat info{};bool saved=fd>=0&&fsync(fd)==0&&fstat(fd,&info)==0&&S_ISREG(info.st_mode);if(fd>=0&&close(fd)!=0)saved=false;
 fprintf(out,"{\"type\":\"recorder_file\",\"run_id\":\"%s\",\"cycle\":%d,\"basename\":\"%s\",\"bytes\":%lld,\"persisted\":%s}\n",run,cycle,basename.c_str(),static_cast<long long>(info.st_size),saved?"true":"false");
 if(released==AV_ERR_OK){
  std::lock_guard<std::mutex> lock(live.mutex);
  for(const auto &event:live.events)fprintf(out,"{\"type\":\"recorder_state\",\"run_id\":\"%s\",\"cycle\":%d,\"state\":%d,\"reason\":%d,\"monotonic_ns\":%lld}\n",run,cycle,event.state,event.reason,static_cast<long long>(event.time));
  for(const auto &event:live.errorEvents)fprintf(out,"{\"type\":\"recorder_error\",\"run_id\":\"%s\",\"cycle\":%d,\"code\":%d,\"monotonic_ns\":%lld}\n",run,cycle,event.code,static_cast<long long>(event.time));
  if(!expectedDenied)valid&=live.errors==0;
 }
 if(released==AV_ERR_OK)delete &live; // failed Release retains callback memory
 fflush(out);return expectedDenied?valid&&rejected&&saved&&info.st_size==0:valid&&saved&&info.st_size>0&&started;
}
}
extern "C" int RunBatchMediaRecorderProbe(FILE *out,const char *run,bool denied)
{
 if(out==nullptr||run==nullptr||strlen(run)!=32)return 2;
 for(size_t i=0;i<32;++i)if(!((run[i]>='0'&&run[i]<='9')||(run[i]>='a'&&run[i]<='f')))return 2;
 fprintf(out,"{\"type\":\"recorder_identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u,\"expected_denied\":%s}\n",run,getuid(),geteuid(),denied?"true":"false");
 std::vector<uint8_t> challenge;bool valid=ReadChallenge(run,challenge);Step(out,run,0,"video_challenge",valid?0:-1);
 for(int cycle=1;valid&&cycle<=CYCLES;++cycle)valid=Cycle(out,run,cycle,denied,challenge);
 fprintf(out,"{\"type\":\"recorder_summary\",\"run_id\":\"%s\",\"cycles\":%d,\"candidate_ok\":%s,\"independent_decode_required\":true}\n",run,CYCLES,valid?"true":"false");fflush(out);return valid?0:1;
}
