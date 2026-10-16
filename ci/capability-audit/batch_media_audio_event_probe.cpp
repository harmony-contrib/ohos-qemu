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
std::atomic<bool> cancelled{false};
struct Chunk {size_t offset;int length;int phase;int64_t time;};
struct Event {int kind;int code;int hint;int64_t time;};
struct Context {std::mutex mutex;std::vector<uint8_t> bytes=std::vector<uint8_t>(CAPACITY);std::vector<Chunk> chunks;std::vector<Event> events;size_t size=0;int phase=1;int invalid=0;Context(){chunks.reserve(MAX_CHUNKS);events.reserve(MAX_EVENTS);}};
struct FreshQueries {
 int stateResult=-1,framesResult=-1,timestampResult=-1,sourceResult=-1,rateResult=-1,channelsResult=-1,formatResult=-1;
 OH_AudioStream_State state=AUDIOSTREAM_STATE_INVALID;
 OH_AudioStream_SourceType source=AUDIOSTREAM_SOURCE_TYPE_INVALID;
 OH_AudioStream_SampleFormat format=AUDIOSTREAM_SAMPLE_U8;
 int32_t rate=-1,channels=-1;int64_t frames=-1,position=-1,timestamp=-1,before=-1,after=-1;
};
struct FreshSnapshot {bool requested=false,replied=false;size_t offset=0,chunks=0;int phase=-1;int64_t seen=-1;FreshQueries base;};
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
bool Step(FILE *out,const char *run,const char *name,int actual,bool primer=false)
{
 fprintf(out,"{\"type\":\"%s\",\"run_id\":\"%s\",\"name\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",primer?"event_primer_step":"event_step",run,name,actual,static_cast<long long>(Now()));fflush(out);return actual==AUDIOSTREAM_SUCCESS;
}
void Phase(Context &c,int phase){std::lock_guard<std::mutex> lock(c.mutex);c.phase=phase;}
bool Snapshot(FILE *out,const char *run,OH_AudioCapturer *capturer,Context &c,const char *point)
{
 OH_AudioStream_State state=AUDIOSTREAM_STATE_INVALID;int64_t frames=-1,position=-1,time=-1;const int64_t before=Now();
 const auto status=OH_AudioCapturer_GetCurrentState(capturer,&state);const auto read=OH_AudioCapturer_GetFramesRead(capturer,&frames);
 const auto stamp=OH_AudioCapturer_GetTimestamp(capturer,CLOCK_MONOTONIC,&position,&time);
 int phase=0,invalid=0;size_t copied=0,events=0;Event latest{};bool hasEvent=false;
 {std::lock_guard<std::mutex> lock(c.mutex);phase=c.phase;invalid=c.invalid;copied=c.size;events=c.events.size();
  hasEvent=!c.events.empty();if(hasEvent)latest=c.events.back();}
 char last[192]="null";
 if(hasEvent){const int size=snprintf(last,sizeof(last),"{\"kind\":%d,\"code\":%d,\"hint\":%d,\"monotonic_ns\":%lld}",latest.kind,latest.code,latest.hint,static_cast<long long>(latest.time));
  if(size<=0||static_cast<size_t>(size)>=sizeof(last))return false;}
 fprintf(out,"{\"type\":\"event_snapshot\",\"run_id\":\"%s\",\"point\":\"%s\",\"phase\":%d,\"state_result\":%d,\"state\":%d,\"frames_result\":%d,\"frames\":%lld,\"timestamp_result\":%d,\"position\":%lld,\"timestamp_ns\":%lld,\"before_ns\":%lld,\"after_ns\":%lld,\"copied_bytes\":%zu,\"events\":%zu,\"invalid\":%d,\"last_callback\":%s}\n",run,point,phase,status,state,read,static_cast<long long>(frames),stamp,static_cast<long long>(position),static_cast<long long>(time),static_cast<long long>(before),static_cast<long long>(Now()),copied,events,invalid,last);fflush(out);
 return invalid==0&&((strcmp(point,"baseline")!=0&&strcmp(point,"primer_baseline")!=0)||(status==AUDIOSTREAM_SUCCESS&&read==AUDIOSTREAM_SUCCESS&&frames>=0));
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
bool SnapshotRequest(const std::string &path,const std::string &nonce,bool &pending)
{
 pending=false;int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
 if(fd<0){pending=errno==ENOENT;return false;}
 struct stat before{},after{};char bytes[34]{};size_t offset=0;
 bool valid=nonce.size()==32&&fstat(fd,&before)==0&&S_ISREG(before.st_mode)&&
  before.st_uid==getuid()&&(before.st_mode&07777)==0600&&before.st_size==33;
 while(valid&&offset<sizeof(bytes)){
  const ssize_t count=read(fd,bytes+offset,sizeof(bytes)-offset);
  if(count<0&&errno==EINTR)continue;if(count<0){valid=false;break;}if(count==0)break;
  offset+=static_cast<size_t>(count);
 }
 valid=valid&&offset==33&&fstat(fd,&after)==0&&before.st_dev==after.st_dev&&before.st_ino==after.st_ino&&
  before.st_uid==after.st_uid&&before.st_mode==after.st_mode&&before.st_size==after.st_size&&
  before.st_mtime==after.st_mtime&&before.st_ctime==after.st_ctime
#if defined(__APPLE__)
  &&before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec&&before.st_ctimespec.tv_nsec==after.st_ctimespec.tv_nsec
#else
  &&before.st_mtim.tv_nsec==after.st_mtim.tv_nsec&&before.st_ctim.tv_nsec==after.st_ctim.tv_nsec
#endif
  ;
 if(close(fd)!=0)valid=false;return valid&&std::string(bytes,33)==nonce+"\n";
}
bool WriteSnapshotPrivate(const std::string &path,const void *bytes,size_t size)
{
 if(size==0||size>CAPACITY)return false;
 int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return false;
 struct stat info{};size_t offset=0;
 bool valid=fstat(fd,&info)==0&&S_ISREG(info.st_mode)&&info.st_uid==getuid()&&
  (info.st_mode&07777)==0600&&info.st_size==0;
 while(valid&&offset<size){const ssize_t count=write(fd,static_cast<const uint8_t*>(bytes)+offset,size-offset);
  if(count<0&&errno==EINTR)continue;if(count<=0){valid=false;break;}offset+=static_cast<size_t>(count);}
 if(valid)valid=fstat(fd,&info)==0&&S_ISREG(info.st_mode)&&info.st_uid==getuid()&&
  (info.st_mode&07777)==0600&&info.st_size>=0&&static_cast<uint64_t>(info.st_size)==size;
 if(fsync(fd)!=0)valid=false;if(close(fd)!=0)valid=false;return valid;
}
bool ReadFreshQueries(OH_AudioCapturer *capturer,FreshQueries &q)
{
 q.before=Now();q.stateResult=OH_AudioCapturer_GetCurrentState(capturer,&q.state);
 q.framesResult=OH_AudioCapturer_GetFramesRead(capturer,&q.frames);
 q.timestampResult=OH_AudioCapturer_GetTimestamp(capturer,CLOCK_MONOTONIC,&q.position,&q.timestamp);
 q.sourceResult=OH_AudioCapturer_GetCapturerInfo(capturer,&q.source);
 q.rateResult=OH_AudioCapturer_GetSamplingRate(capturer,&q.rate);
 q.channelsResult=OH_AudioCapturer_GetChannelCount(capturer,&q.channels);
 q.formatResult=OH_AudioCapturer_GetSampleFormat(capturer,&q.format);q.after=Now();
 return q.before>0&&q.after>=q.before&&q.stateResult==AUDIOSTREAM_SUCCESS&&q.state==AUDIOSTREAM_STATE_RUNNING&&
  q.framesResult==AUDIOSTREAM_SUCCESS&&q.frames>0&&q.timestampResult==AUDIOSTREAM_SUCCESS&&q.position>=0&&q.timestamp>=0&&
  q.sourceResult==AUDIOSTREAM_SUCCESS&&q.source==AUDIOSTREAM_SOURCE_TYPE_MIC&&q.rateResult==AUDIOSTREAM_SUCCESS&&q.rate==48000&&
  q.channelsResult==AUDIOSTREAM_SUCCESS&&q.channels==2&&q.formatResult==AUDIOSTREAM_SUCCESS&&q.format==AUDIOSTREAM_SAMPLE_S16LE;
}
int FreshError(FILE *out,const char *run,const char *action,const char *stage)
{
 fprintf(out,"{\"type\":\"event_fresh_error\",\"run_id\":\"%s\",\"action\":\"%s\",\"stage\":\"%s\",\"monotonic_ns\":%lld}\n",run,action,stage,static_cast<long long>(Now()));fflush(out);return -1;
}
int FreshQueryError(FILE *out,const char *run,const char *action,const char *stage,const FreshQueries &q)
{
 fprintf(out,"{\"type\":\"event_fresh_error\",\"run_id\":\"%s\",\"action\":\"%s\",\"stage\":\"%s\",\"state_result\":%d,\"state\":%d,\"frames_result\":%d,\"frames\":%lld,\"timestamp_result\":%d,\"position\":%lld,\"timestamp_ns\":%lld,\"source_result\":%d,\"source_type\":%d,\"rate_result\":%d,\"rate\":%d,\"channels_result\":%d,\"channels\":%d,\"format_result\":%d,\"format\":%d,\"query_before_ns\":%lld,\"query_after_ns\":%lld}\n",
  run,action,stage,q.stateResult,q.state,q.framesResult,static_cast<long long>(q.frames),q.timestampResult,static_cast<long long>(q.position),static_cast<long long>(q.timestamp),q.sourceResult,q.source,q.rateResult,q.rate,q.channelsResult,q.channels,q.formatResult,q.format,static_cast<long long>(q.before),static_cast<long long>(q.after));fflush(out);return -1;
}
// Control-thread observation only. A request does not mutate stream state, grant
// permissions or inject samples. New callback bytes, not elapsed time, unlock it.
int FreshSnapshotReply(FILE *out,const char *run,const char *action,const std::string &prefix,
 const std::string &nonce,int64_t created,OH_AudioCapturer *capturer,Context &c,FreshSnapshot &fresh)
{
 constexpr size_t BYTES=48000*2*2/2; // exactly 0.5s of actual 48k stereo S16LE
 if(fresh.replied)return 1;
 const auto tick=Now();if(cancelled.load()||tick<created||tick-created>=15000000000LL)return FreshError(out,run,action,"deadline_or_cancel");
 if(!fresh.requested){
  bool pending=false;if(!SnapshotRequest(prefix+"-snapshot-request",nonce,pending))return pending?0:FreshError(out,run,action,"request");
  fresh.seen=Now();fresh.phase=strcmp(action,"focus_begin")==0?1:0;
  {std::lock_guard<std::mutex> lock(c.mutex);
   if(c.invalid!=0||c.size>c.bytes.size()||c.size%4||c.phase!=fresh.phase)return FreshError(out,run,action,"request_context");
   fresh.offset=c.size;fresh.chunks=c.chunks.size();}
  if(!ReadFreshQueries(capturer,fresh.base))return FreshQueryError(out,run,action,"request_queries",fresh.base);
  fresh.requested=true;
  fprintf(out,"{\"type\":\"event_fresh_request\",\"run_id\":\"%s\",\"action\":\"%s\",\"request_nonce\":\"%s\",\"request_seen_ns\":%lld,\"requested_offset\":%zu,\"phase\":%d}\n",run,action,nonce.c_str(),static_cast<long long>(fresh.seen),fresh.offset,fresh.phase);fflush(out);
  return 0;
 }
 std::vector<uint8_t> bytes;size_t begin=0,end=0,count=0;int64_t first=0,last=0,copyBefore=0,copyAfter=0;
 {std::lock_guard<std::mutex> lock(c.mutex);
  if(c.invalid!=0||c.size>c.bytes.size()||c.size%4||fresh.offset>c.size||c.phase!=fresh.phase)return FreshError(out,run,action,"copy_context");
  if(c.size-fresh.offset<BYTES)return 0;
  if(c.chunks.size()<=fresh.chunks)return FreshError(out,run,action,"missing_new_callbacks");
  copyBefore=Now();end=c.size;begin=end-BYTES;size_t covered=begin;
  for(size_t i=fresh.chunks;i<c.chunks.size();++i){const auto &chunk=c.chunks[i];
   if(chunk.length<=0||chunk.length%4||chunk.offset%4||chunk.offset>c.size||static_cast<size_t>(chunk.length)>c.size-chunk.offset)return FreshError(out,run,action,"callback_bounds");
   const size_t tail=chunk.offset+static_cast<size_t>(chunk.length);
   if(tail<=begin)continue;if(chunk.offset>=end)break;
   const size_t start=chunk.offset>begin?chunk.offset:begin;
   if(start!=covered||chunk.phase!=fresh.phase||chunk.time<=fresh.seen||chunk.time>copyBefore||chunk.time<last)return FreshError(out,run,action,"callback_phase_or_clock");
   if(count++==0)first=chunk.time;last=chunk.time;covered=tail<end?tail:end;
  }
  if(covered!=end||count==0||begin<fresh.offset)return FreshError(out,run,action,"callback_coverage");
  bytes.assign(c.bytes.begin()+begin,c.bytes.begin()+end);copyAfter=Now();
 }
 FreshQueries q;if(!ReadFreshQueries(capturer,q)||q.frames<=fresh.base.frames||q.position<=fresh.base.position||q.timestamp<=fresh.base.timestamp)
  return FreshQueryError(out,run,action,"reply_queries_or_progress",q);
 if(copyBefore<fresh.seen||copyAfter<copyBefore||q.before<copyAfter||q.after<last||q.after-last>250000000LL)
  return FreshError(out,run,action,"stale_callback");
 const auto checked=Now();if(cancelled.load()||checked<created||checked-created>=15000000000LL)return FreshError(out,run,action,"deadline_or_cancel");
 const std::string pcm="audio-event-"+std::string(run)+"-"+action+"-snapshot-"+nonce+".pcm";
 if(!WriteSnapshotPrivate(std::string(PRIVATE)+pcm,bytes.data(),bytes.size()))return FreshError(out,run,action,"write_pcm");
 const auto replyTime=Now();if(cancelled.load()||replyTime<created||replyTime-created>=15000000000LL)return FreshError(out,run,action,"deadline_or_cancel");
 char reply[3072]{};const int size=snprintf(reply,sizeof(reply),
  "{\"type\":\"event_fresh_reply\",\"run_id\":\"%s\",\"action\":\"%s\",\"ready_nonce\":\"%s\",\"request_nonce\":\"%s\",\"uid\":%u,\"euid\":%u,\"phase\":%d,\"request_seen_ns\":%lld,\"requested_offset\":%zu,"
  "\"request_frames\":%lld,\"request_position\":%lld,\"request_timestamp_ns\":%lld,\"request_query_before_ns\":%lld,\"request_query_after_ns\":%lld,"
  "\"state_result\":%d,\"state\":%d,\"frames_result\":%d,\"frames\":%lld,\"timestamp_result\":%d,\"position\":%lld,\"timestamp_ns\":%lld,\"source_result\":%d,\"source_type\":%d,\"rate_result\":%d,\"rate\":%d,\"channels_result\":%d,\"channels\":%d,\"format_result\":%d,\"format\":%d,"
  "\"query_before_ns\":%lld,\"query_after_ns\":%lld,\"copy_before_ns\":%lld,\"copy_after_ns\":%lld,\"first_callback_ns\":%lld,\"last_callback_ns\":%lld,\"callback_count\":%zu,\"offset\":%zu,\"bytes\":%zu,\"end_offset\":%zu,\"pcm_basename\":\"%s\",\"persisted\":true,\"reply_prepared_ns\":%lld}\n",
  run,action,nonce.c_str(),nonce.c_str(),getuid(),geteuid(),fresh.phase,static_cast<long long>(fresh.seen),fresh.offset,
  static_cast<long long>(fresh.base.frames),static_cast<long long>(fresh.base.position),static_cast<long long>(fresh.base.timestamp),static_cast<long long>(fresh.base.before),static_cast<long long>(fresh.base.after),
  q.stateResult,q.state,q.framesResult,static_cast<long long>(q.frames),q.timestampResult,static_cast<long long>(q.position),static_cast<long long>(q.timestamp),q.sourceResult,q.source,q.rateResult,q.rate,q.channelsResult,q.channels,q.formatResult,q.format,
  static_cast<long long>(q.before),static_cast<long long>(q.after),static_cast<long long>(copyBefore),static_cast<long long>(copyAfter),static_cast<long long>(first),static_cast<long long>(last),count,begin,bytes.size(),end,pcm.c_str(),static_cast<long long>(replyTime));
 if(size<=0||static_cast<size_t>(size)>=sizeof(reply)||!WriteSnapshotPrivate(prefix+"-snapshot-reply.json",reply,static_cast<size_t>(size)))return FreshError(out,run,action,"write_reply");
 fresh.replied=true;fputs(reply,out);fflush(out);return 1;
}
bool Checkpoint(FILE *out,const char *run,int mode,Context &c,bool primer=false)
{
 std::vector<uint8_t> bytes;
 {std::lock_guard<std::mutex> lock(c.mutex);bytes.assign(c.bytes.begin(),c.bytes.begin()+c.size);}
 const std::string name="audio-event-"+std::string(run)+"-mode"+std::to_string(mode)+(primer?"-primer.pcm":"-baseline.pcm");
 const bool saved=WritePrivate(std::string(PRIVATE)+name,bytes.data(),bytes.size());
 fprintf(out,"{\"type\":\"%s\",\"run_id\":\"%s\",\"basename\":\"%s\",\"bytes\":%zu,\"persisted\":%s,\"monotonic_ns\":%lld}\n",primer?"event_primer_checkpoint":"event_checkpoint",run,name.c_str(),bytes.size(),saved?"true":"false",static_cast<long long>(Now()));fflush(out);return saved;
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
 FreshSnapshot fresh;const bool allowFresh=strcmp(action,"focus_begin")==0||strcmp(action,"contender_start")==0;
 while(true){if(cancelled.load())return false;const auto tick=Now();if(tick<created||tick-created>=15000000000LL)return false;
  if(allowFresh&&FreshSnapshotReply(out,run,action,prefix,nonce,created,capturer,c,fresh)<0)return false;
  const auto checked=Now();if(cancelled.load()||checked<created||checked-created>=15000000000LL)return false;
  bool pending=false;if(Ack(prefix+"-ack",nonce,pending)){
   if(fresh.requested&&!fresh.replied){FreshError(out,run,action,"ack_before_fresh_reply");return false;}
   fprintf(out,"{\"type\":\"event_ack\",\"run_id\":\"%s\",\"action\":\"%s\",\"nonce\":\"%s\",\"monotonic_ns\":%lld}\n",run,action,nonce.c_str(),static_cast<long long>(Now()));fflush(out);return true;}
  if(!pending)return false;usleep(50000);if(!Snapshot(out,run,capturer,c,"await_action"))return false;
 }
}
bool Observe(FILE *out,const char *run,OH_AudioCapturer *capturer,Context &c,const char *point,int ticks)
{
 bool valid=true;for(int i=0;i<ticks;++i){if(cancelled.load())return false;usleep(20000);valid&=Snapshot(out,run,capturer,c,point);}return valid;
}
bool Persist(FILE *out,const char *run,int mode,Context &c,bool primer=false)
{
 std::lock_guard<std::mutex> lock(c.mutex);const std::string name="audio-event-"+std::string(run)+"-mode"+std::to_string(mode)+(primer?"-primer-full.pcm":".pcm");
 const bool saved=WritePrivate(std::string(PRIVATE)+name,c.bytes.data(),c.size);
 for(const auto &chunk:c.chunks)fprintf(out,"{\"type\":\"%s\",\"run_id\":\"%s\",\"offset\":%zu,\"bytes\":%d,\"phase\":%d,\"monotonic_ns\":%lld}\n",primer?"event_primer_chunk":"event_chunk",run,chunk.offset,chunk.length,chunk.phase,static_cast<long long>(chunk.time));
 for(const auto &event:c.events)fprintf(out,"{\"type\":\"%s\",\"run_id\":\"%s\",\"kind\":%d,\"code\":%d,\"hint\":%d,\"monotonic_ns\":%lld}\n",primer?"event_primer_callback":"event_callback",run,event.kind,event.code,event.hint,static_cast<long long>(event.time));
 fprintf(out,"{\"type\":\"%s\",\"run_id\":\"%s\",\"basename\":\"%s\",\"bytes\":%zu,\"persisted\":%s,\"invalid\":%d}\n",primer?"event_primer_pcm":"event_pcm",run,name.c_str(),c.size,saved?"true":"false",c.invalid);fflush(out);return saved&&c.invalid==0;
}
// A real MIC stream keeps audioRecording truthful while the ordinary contender
// is backgrounded and waiting. MIC->MIC is shared by the fixed focus policy.
// Only after the nonce action do we release it and create VOICE_COMMUNICATION.
bool Primer(FILE *out,const char *run)
{
 auto context=std::make_unique<Context>();context->phase=0;
 OH_AudioStreamBuilder *builder=nullptr;OH_AudioCapturer *capturer=nullptr;
 bool valid=Step(out,run,"create",OH_AudioStreamBuilder_Create(&builder,AUDIOSTREAM_TYPE_CAPTURER),true);
 if(builder==nullptr)return false;
 valid&=Step(out,run,"rate",OH_AudioStreamBuilder_SetSamplingRate(builder,48000),true);
 valid&=Step(out,run,"channels",OH_AudioStreamBuilder_SetChannelCount(builder,2),true);
 valid&=Step(out,run,"format",OH_AudioStreamBuilder_SetSampleFormat(builder,AUDIOSTREAM_SAMPLE_S16LE),true);
 valid&=Step(out,run,"encoding",OH_AudioStreamBuilder_SetEncodingType(builder,AUDIOSTREAM_ENCODING_TYPE_RAW),true);
 valid&=Step(out,run,"source",OH_AudioStreamBuilder_SetCapturerInfo(builder,AUDIOSTREAM_SOURCE_TYPE_MIC),true);
 valid&=Step(out,run,"read_callback",OH_AudioStreamBuilder_SetCapturerReadDataCallback(builder,Read,context.get()),true);
 valid&=Step(out,run,"interrupt_callback",OH_AudioStreamBuilder_SetCapturerInterruptCallback(builder,Interrupt,context.get()),true);
 valid&=Step(out,run,"error_callback",OH_AudioStreamBuilder_SetCapturerErrorCallback(builder,Error,context.get()),true);
 valid&=Step(out,run,"generate",OH_AudioStreamBuilder_GenerateCapturer(builder,&capturer),true);
 if(capturer!=nullptr){
  Context &live=*context.release();
  if(valid&&!cancelled.load())valid=Step(out,run,"start",OH_AudioCapturer_Start(capturer),true);
  else valid=false;
  if(valid){usleep(200000);valid=Observe(out,run,capturer,live,"primer_baseline",50);}
  if(valid)valid=Checkpoint(out,run,2,live,true);
  if(valid)valid=Handshake(out,run,"contender_start",capturer,live);
  valid&=Step(out,run,"stop",OH_AudioCapturer_Stop(capturer),true);
  const auto released=OH_AudioCapturer_Release(capturer);valid&=Step(out,run,"release",released,true);
  if(released==AUDIOSTREAM_SUCCESS){valid&=Persist(out,run,2,live,true);delete &live;}
 }
 valid&=Step(out,run,"destroy",OH_AudioStreamBuilder_Destroy(builder),true);
 return valid&&!cancelled.load();
}

}
extern "C" void PrepareBatchMediaAudioEventProbe() {cancelled.store(false);}
extern "C" void CancelBatchMediaAudioEventProbe() {cancelled.store(true);}
extern "C" int RunBatchMediaAudioEventProbe(FILE *out,const char *run,int mode)
{
 if(out==nullptr||run==nullptr||strlen(run)!=32||mode<0||mode>2)return 2;
 for(size_t i=0;i<32;++i)if(!((run[i]>='0'&&run[i]<='9')||(run[i]>='a'&&run[i]<='f')))return 2;
 fprintf(out,"{\"type\":\"event_identity\",\"run_id\":\"%s\",\"mode\":%d,\"uid\":%u,\"euid\":%u}\n",run,mode,getuid(),geteuid());
 if(mode==2&&!Primer(out,run)){
  fprintf(out,"{\"type\":\"event_summary\",\"run_id\":\"%s\",\"mode\":2,\"candidate_complete\":false,\"token_PCM_and_focus_verification_required\":true}\n",run);fflush(out);return 1;
 }
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
  if(valid&&!cancelled.load()){
   const int64_t before=Now();const int started=OH_AudioCapturer_Start(capturer);const int64_t after=Now();
   fprintf(out,"{\"type\":\"event_start_interval\",\"run_id\":\"%s\",\"actual\":%d,\"before_ns\":%lld,\"after_ns\":%lld}\n",run,started,static_cast<long long>(before),static_cast<long long>(after));
   valid=Step(out,run,"start",started);
  }else valid=false;
  if(valid){
   usleep(200000); // actual stream warmup before timestamp/rate baseline
   valid&=Observe(out,run,capturer,live,"baseline",50);
   valid&=Checkpoint(out,run,mode,live);
   if(valid&&mode==0){
    valid=Handshake(out,run,"revoke",capturer,live);
    if(valid){Phase(live,2);valid=Observe(out,run,capturer,live,"after_revoke",75);}
    if(valid&&!cancelled.load()){
     const auto restarted=OH_AudioCapturer_Start(capturer);fprintf(out,"{\"type\":\"event_restart_after_revoke\",\"run_id\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",run,restarted,static_cast<long long>(Now()));
     valid=Observe(out,run,capturer,live,"after_denied_restart",25);
    }
   } else if(valid&&mode==1){
    valid=Handshake(out,run,"focus_begin",capturer,live);
    if(valid){Phase(live,2);valid=Observe(out,run,capturer,live,"interrupted",25);}
    if(valid)valid=Handshake(out,run,"focus_end",capturer,live);
    if(valid&&!cancelled.load()){Phase(live,3);valid=Step(out,run,"restart_after_focus",OH_AudioCapturer_Start(capturer));}
    if(valid)valid=Observe(out,run,capturer,live,"resumed",50);
   } else if(valid)valid=Handshake(out,run,"contender_stop",capturer,live);
  }
  const auto stopped=OH_AudioCapturer_Stop(capturer);fprintf(out,"{\"type\":\"event_stop\",\"run_id\":\"%s\",\"actual\":%d,\"monotonic_ns\":%lld}\n",run,stopped,static_cast<long long>(Now()));
  const auto released=OH_AudioCapturer_Release(capturer);valid&=Step(out,run,"release",released);
  if(released==AUDIOSTREAM_SUCCESS){valid&=Persist(out,run,mode,live);delete &live;}
 }
 valid&=Step(out,run,"destroy",OH_AudioStreamBuilder_Destroy(builder));
 fprintf(out,"{\"type\":\"event_summary\",\"run_id\":\"%s\",\"mode\":%d,\"candidate_complete\":%s,\"token_PCM_and_focus_verification_required\":true}\n",run,mode,(valid&&!cancelled.load())?"true":"false");fflush(out);return valid&&!cancelled.load()?0:1;
}
