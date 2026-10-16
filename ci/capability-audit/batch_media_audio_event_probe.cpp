// SPDX-License-Identifier: Apache-2.0
// Public Capturer focus/active-revocation candidate. Signals carry no audio or permission privilege.
#include <ohaudio/native_audiocapturer.h>
#include <ohaudio/native_audiostreambuilder.h>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <vector>
namespace {
constexpr size_t CAPACITY=48000*4*40,MAX_CHUNKS=4096,MAX_EVENTS=128;
constexpr const char *PRIVATE="/data/storage/el2/base/files/";
struct Chunk {size_t offset;int length;int phase;int64_t time;};
struct Event {int kind;int code;int hint;int64_t time;};
struct Context {std::mutex mutex;std::vector<uint8_t> bytes=std::vector<uint8_t>(CAPACITY);std::vector<Chunk> chunks;std::vector<Event> events;size_t size=0;int phase=1;int invalid=0;Context(){chunks.reserve(MAX_CHUNKS);events.reserve(MAX_EVENTS);}};
int64_t Now()
{
 timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t)!=0)return -1;return static_cast<int64_t>(t.tv_sec)*1000000000+t.tv_nsec;
}
void Read(OH_AudioCapturer*,void *user,void *audio,int length)
{
 auto &c=*static_cast<Context*>(user);std::lock_guard<std::mutex> lock(c.mutex);const auto time=Now();
 if(audio==nullptr||length<=0||length%4||time<0||static_cast<size_t>(length)>c.bytes.size()-c.size||c.chunks.size()>=MAX_CHUNKS){++c.invalid;return;}
 memcpy(c.bytes.data()+c.size,audio,static_cast<size_t>(length));c.chunks.push_back({c.size,length,c.phase,time});c.size+=static_cast<size_t>(length);
}
void Interrupt(OH_AudioCapturer*,void *user,OH_AudioInterrupt_ForceType type,OH_AudioInterrupt_Hint hint)
{
 auto &c=*static_cast<Context*>(user);std::lock_guard<std::mutex> lock(c.mutex);if(c.events.size()<MAX_EVENTS)c.events.push_back({1,type,hint,Now()});else ++c.invalid;
}
void Error(OH_AudioCapturer*,void *user,OH_AudioStream_Result code)
{
 auto &c=*static_cast<Context*>(user);std::lock_guard<std::mutex> lock(c.mutex);if(c.events.size()<MAX_EVENTS)c.events.push_back({2,code,0,Now()});else ++c.invalid;
}
bool Step(FILE *out,const char *run,const char *name,int actual)
{
 fprintf(out,"{\"type\":\"event_step\",\"run_id\":\"%s\",\"name\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",run,name,actual,static_cast<long long>(Now()));fflush(out);return actual==AUDIOSTREAM_SUCCESS;
}
void Phase(Context &c,int phase){std::lock_guard<std::mutex> lock(c.mutex);c.phase=phase;}
bool Snapshot(FILE *out,const char *run,OH_AudioCapturer *capturer,Context &c,const char *point)
{
 OH_AudioStream_State state=AUDIOSTREAM_STATE_INVALID;int64_t frames=-1,position=-1,time=-1;const int64_t before=Now();
 const auto status=OH_AudioCapturer_GetCurrentState(capturer,&state);const auto read=OH_AudioCapturer_GetFramesRead(capturer,&frames);
 const auto stamp=OH_AudioCapturer_GetTimestamp(capturer,CLOCK_MONOTONIC,&position,&time);
 std::lock_guard<std::mutex> lock(c.mutex);
 fprintf(out,"{\"type\":\"event_snapshot\",\"run_id\":\"%s\",\"point\":\"%s\",\"phase\":%d,\"state_result\":%d,\"state\":%d,\"frames_result\":%d,\"frames\":%lld,\"timestamp_result\":%d,\"position\":%lld,\"timestamp_ns\":%lld,\"before_ns\":%lld,\"after_ns\":%lld,\"copied_bytes\":%zu,\"events\":%zu,\"invalid\":%d}\n",run,point,c.phase,status,state,read,static_cast<long long>(frames),stamp,static_cast<long long>(position),static_cast<long long>(time),static_cast<long long>(before),static_cast<long long>(Now()),c.size,c.events.size(),c.invalid);fflush(out);
 return c.invalid==0&&(strcmp(point,"baseline")!=0||(status==AUDIOSTREAM_SUCCESS&&read==AUDIOSTREAM_SUCCESS&&frames>=0));
}
bool WritePrivate(const std::string &path,const void *bytes,size_t size)
{
 int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return false;size_t offset=0;bool valid=true;
 while(offset<size){ssize_t n=write(fd,static_cast<const uint8_t*>(bytes)+offset,size-offset);if(n<0&&errno==EINTR)continue;if(n<=0){valid=false;break;}offset+=static_cast<size_t>(n);}
 if(fsync(fd)!=0)valid=false;if(close(fd)!=0)valid=false;return valid;
}
bool Nonce(std::string &text)
{
 uint8_t bytes[16]{};size_t count=0;
 int fd=open("/dev/urandom",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return false;
 while(count<sizeof(bytes)){ssize_t n=read(fd,bytes+count,sizeof(bytes)-count);if(n<0&&errno==EINTR)continue;if(n<=0){close(fd);return false;}count+=static_cast<size_t>(n);}
 if(close(fd)!=0)return false;
 constexpr char HEX[]="0123456789abcdef";text.clear();for(uint8_t byte:bytes){text+=HEX[byte>>4];text+=HEX[byte&15];}return true;
}
bool Ack(const std::string &path,const std::string &nonce,bool &pending)
{
 pending=false;int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0){pending=errno==ENOENT;return false;}
 struct stat info{};char bytes[34]{};bool valid=fstat(fd,&info)==0&&S_ISREG(info.st_mode)&&info.st_uid==getuid()&&(info.st_mode&077)==0&&info.st_size==33;
 size_t offset=0;
 while(valid&&offset<33){ssize_t n=read(fd,bytes+offset,33-offset);if(n<0&&errno==EINTR)continue;if(n<=0){valid=false;break;}offset+=static_cast<size_t>(n);}
 if(close(fd)!=0)valid=false;return valid&&std::string(bytes,33)==nonce+"\n";
}
bool Checkpoint(FILE *out,const char *run,int mode,Context &c)
{
 std::vector<uint8_t> bytes;
 {std::lock_guard<std::mutex> lock(c.mutex);bytes.assign(c.bytes.begin(),c.bytes.begin()+c.size);}
 const std::string name="audio-event-"+std::string(run)+"-mode"+std::to_string(mode)+"-baseline.pcm";
 const bool saved=WritePrivate(std::string(PRIVATE)+name,bytes.data(),bytes.size());
 fprintf(out,"{\"type\":\"event_checkpoint\",\"run_id\":\"%s\",\"basename\":\"%s\",\"bytes\":%zu,\"persisted\":%s,\"monotonic_ns\":%lld}\n",run,name.c_str(),bytes.size(),saved?"true":"false",static_cast<long long>(Now()));fflush(out);return saved;
}
bool Handshake(FILE *out,const char *run,const char *action,OH_AudioCapturer *capturer,Context &c)
{
 std::string nonce;if(!Nonce(nonce))return false;const auto created=Now();if(created<=0)return false;
 const std::string prefix=std::string(PRIVATE)+"audio-event-"+run+"-"+action;
 OH_AudioStream_State state=AUDIOSTREAM_STATE_INVALID;int64_t frames=-1;
 const int stateResult=OH_AudioCapturer_GetCurrentState(capturer,&state);
 const int framesResult=OH_AudioCapturer_GetFramesRead(capturer,&frames);
 if(strcmp(action,"focus_begin")==0&&(stateResult!=AUDIOSTREAM_SUCCESS||state!=AUDIOSTREAM_STATE_RUNNING||framesResult!=AUDIOSTREAM_SUCCESS||frames<=0))return false;
 size_t copied=0;{std::lock_guard<std::mutex> lock(c.mutex);copied=c.size;}
 const std::string ready="{\"run_id\":\""+std::string(run)+"\",\"action\":\""+action+"\",\"nonce\":\""+nonce+"\",\"uid\":"+std::to_string(getuid())+",\"monotonic_ns\":"+std::to_string(created)+",\"state_result\":"+std::to_string(stateResult)+",\"state\":"+std::to_string(state)+",\"frames_result\":"+std::to_string(framesResult)+",\"frames\":"+std::to_string(frames)+",\"copied_bytes\":"+std::to_string(copied)+"}\n";
 if(!Snapshot(out,run,capturer,c,"before_ready")||!WritePrivate(prefix+"-ready.json",ready.data(),ready.size()))return false;
 fprintf(out,"{\"type\":\"event_ready\",\"run_id\":\"%s\",\"action\":\"%s\",\"nonce\":\"%s\",\"monotonic_ns\":%lld}\n",run,action,nonce.c_str(),static_cast<long long>(created));fflush(out);
 while(true){const auto tick=Now();if(tick<created||tick-created>=15000000000LL)return false;bool pending=false;if(Ack(prefix+"-ack",nonce,pending)){
   fprintf(out,"{\"type\":\"event_ack\",\"run_id\":\"%s\",\"action\":\"%s\",\"nonce\":\"%s\",\"monotonic_ns\":%lld}\n",run,action,nonce.c_str(),static_cast<long long>(Now()));fflush(out);return true;}
  if(!pending)return false;usleep(50000);if(!Snapshot(out,run,capturer,c,"await_action"))return false;
 }
}
bool Observe(FILE *out,const char *run,OH_AudioCapturer *capturer,Context &c,const char *point,int ticks)
{
 bool valid=true;for(int i=0;i<ticks;++i){usleep(20000);valid&=Snapshot(out,run,capturer,c,point);}return valid;
}
bool Persist(FILE *out,const char *run,int mode,Context &c)
{
 std::lock_guard<std::mutex> lock(c.mutex);const std::string name="audio-event-"+std::string(run)+"-mode"+std::to_string(mode)+".pcm";
 const bool saved=WritePrivate(std::string(PRIVATE)+name,c.bytes.data(),c.size);
 for(const auto &chunk:c.chunks)fprintf(out,"{\"type\":\"event_chunk\",\"run_id\":\"%s\",\"offset\":%zu,\"bytes\":%d,\"phase\":%d,\"monotonic_ns\":%lld}\n",run,chunk.offset,chunk.length,chunk.phase,static_cast<long long>(chunk.time));
 for(const auto &event:c.events)fprintf(out,"{\"type\":\"event_callback\",\"run_id\":\"%s\",\"kind\":%d,\"code\":%d,\"hint\":%d,\"monotonic_ns\":%lld}\n",run,event.kind,event.code,event.hint,static_cast<long long>(event.time));
 fprintf(out,"{\"type\":\"event_pcm\",\"run_id\":\"%s\",\"basename\":\"%s\",\"bytes\":%zu,\"persisted\":%s,\"invalid\":%d}\n",run,name.c_str(),c.size,saved?"true":"false",c.invalid);fflush(out);return saved&&c.invalid==0;
}
}
extern "C" int RunBatchMediaAudioEventProbe(FILE *out,const char *run,int mode)
{
 if(out==nullptr||run==nullptr||strlen(run)!=32||mode<0||mode>2)return 2;
 for(size_t i=0;i<32;++i)if(!((run[i]>='0'&&run[i]<='9')||(run[i]>='a'&&run[i]<='f')))return 2;
 fprintf(out,"{\"type\":\"event_identity\",\"run_id\":\"%s\",\"mode\":%d,\"uid\":%u,\"euid\":%u}\n",run,mode,getuid(),geteuid());
 auto context=std::make_unique<Context>();OH_AudioStreamBuilder *builder=nullptr;OH_AudioCapturer *capturer=nullptr;
 bool valid=Step(out,run,"create",OH_AudioStreamBuilder_Create(&builder,AUDIOSTREAM_TYPE_CAPTURER));
 if(builder==nullptr)return 1;
 valid&=Step(out,run,"rate",OH_AudioStreamBuilder_SetSamplingRate(builder,48000));valid&=Step(out,run,"channels",OH_AudioStreamBuilder_SetChannelCount(builder,2));
 valid&=Step(out,run,"format",OH_AudioStreamBuilder_SetSampleFormat(builder,AUDIOSTREAM_SAMPLE_S16LE));valid&=Step(out,run,"encoding",OH_AudioStreamBuilder_SetEncodingType(builder,AUDIOSTREAM_ENCODING_TYPE_RAW));
 valid&=Step(out,run,"source",OH_AudioStreamBuilder_SetCapturerInfo(builder,mode==2?AUDIOSTREAM_SOURCE_TYPE_VOICE_COMMUNICATION:AUDIOSTREAM_SOURCE_TYPE_MIC));
 valid&=Step(out,run,"read_callback",OH_AudioStreamBuilder_SetCapturerReadDataCallback(builder,Read,context.get()));valid&=Step(out,run,"interrupt_callback",OH_AudioStreamBuilder_SetCapturerInterruptCallback(builder,Interrupt,context.get()));valid&=Step(out,run,"error_callback",OH_AudioStreamBuilder_SetCapturerErrorCallback(builder,Error,context.get()));
 valid&=Step(out,run,"generate",OH_AudioStreamBuilder_GenerateCapturer(builder,&capturer));
 if(capturer!=nullptr){
  Context &live=*context.release();
  if(valid&&mode==2)valid=Handshake(out,run,"contender_start",capturer,live);
  if(valid){
   const int64_t before=Now();const int started=OH_AudioCapturer_Start(capturer);const int64_t after=Now();
   fprintf(out,"{\"type\":\"event_start_interval\",\"run_id\":\"%s\",\"actual\":%d,\"before_ns\":%lld,\"after_ns\":%lld}\n",run,started,static_cast<long long>(before),static_cast<long long>(after));
   valid=Step(out,run,"start",started);
  }
  if(valid){
   usleep(200000); // actual stream warmup before timestamp/rate baseline
   valid&=Observe(out,run,capturer,live,"baseline",50);
   valid&=Checkpoint(out,run,mode,live);
   if(mode==0){
    valid&=Handshake(out,run,"revoke",capturer,live);Phase(live,2);valid&=Observe(out,run,capturer,live,"after_revoke",75);
    const auto restarted=OH_AudioCapturer_Start(capturer);fprintf(out,"{\"type\":\"event_restart_after_revoke\",\"run_id\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",run,restarted,static_cast<long long>(Now()));
    valid&=Observe(out,run,capturer,live,"after_denied_restart",25);
   } else if(mode==1){
    valid&=Handshake(out,run,"focus_begin",capturer,live);Phase(live,2);valid&=Observe(out,run,capturer,live,"interrupted",25);
    valid&=Handshake(out,run,"focus_end",capturer,live);Phase(live,3);valid&=Step(out,run,"restart_after_focus",OH_AudioCapturer_Start(capturer));valid&=Observe(out,run,capturer,live,"resumed",50);
   } else valid&=Handshake(out,run,"contender_stop",capturer,live);
  }
  const auto stopped=OH_AudioCapturer_Stop(capturer);fprintf(out,"{\"type\":\"event_stop\",\"run_id\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",run,stopped,static_cast<long long>(Now()));
  const auto released=OH_AudioCapturer_Release(capturer);valid&=Step(out,run,"release",released);
  if(released==AUDIOSTREAM_SUCCESS){valid&=Persist(out,run,mode,live);delete &live;}
 }
 valid&=Step(out,run,"destroy",OH_AudioStreamBuilder_Destroy(builder));
 fprintf(out,"{\"type\":\"event_summary\",\"run_id\":\"%s\",\"mode\":%d,\"candidate_complete\":%s,\"token_PCM_and_focus_verification_required\":true}\n",run,mode,valid?"true":"false");fflush(out);return valid?0:1;
}
