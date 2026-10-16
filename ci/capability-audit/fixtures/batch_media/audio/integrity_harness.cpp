#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <deque>
#include <future>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
using namespace std::chrono_literals;
enum class Status { OK, ERROR_INVALID_PARAMETER, ERROR_AUD_INIT_FAILED, ERROR_INVALID_OPERATION,
 ERROR_AUD_START_FAILED, ERROR_AUD_STOP_FAILED, ERROR_AGAIN, ERROR_NOT_ENOUGH_DATA };
#define MEDIA_LOG_I(...)
#define MEDIA_LOG_E(...)
#define MEDIA_LOG_D(...)
#define MEDIA_LOG_W(...)
#define FALSE_RETURN_V_MSG_E(c,r,...) do {if (!(c)) return r;}while(0)
#define FALSE_RETURN_MSG(c,...) do {if (!(c)) return;}while(0)
using AutoLock = std::lock_guard<std::mutex>;
constexpr size_t MAX_CAPTURE_BUFFER_SIZE=100000;
constexpr int64_t AUDIO_CAPTURE_READ_FRAME_TIME=20000000;
constexpr int64_t AUDIO_CAPTURE_READ_FRAME_TIME_HALF=10000000;
constexpr int64_t AUDIO_CAPTURE_READ_FAILED_WAIT_TIME=20000000;
constexpr int32_t AUDIO_CAPTURE_MAX_CACHED_FRAMES=256;
constexpr int32_t TIME_OUT_MS=0;
namespace MediaAVCodec {struct AVCodecTrace {explicit AVCodecTrace(const char*){}};}
enum MemoryFlag { MEMORY_READ_ONLY=1,MEMORY_WRITE_ONLY=2,MEMORY_READ_WRITE=3 };
struct AVMemory {
 std::vector<uint8_t> bytes=std::vector<uint8_t>(24,0xa5);int32_t capacity=24,offset=3,size=7;
 int flags=MEMORY_READ_WRITE;int setCalls=0,failSetCall=0;bool nullAddr=false;
 int32_t GetCapacity(){return capacity;}int32_t GetOffset(){return offset;}int32_t GetSize(){return size;}
 int GetMemoryFlag(){return flags;}uint8_t* GetAddr(){return nullAddr?nullptr:bytes.data();}
 Status SetSize(int32_t n){++setCalls;if(setCalls==failSetCall||n<0||offset<0||offset>capacity||n>capacity-offset)return Status::ERROR_INVALID_PARAMETER;size=n;return Status::OK;}
 int32_t Write(const uint8_t* p,int32_t n,int32_t pos){if(!(flags&MEMORY_WRITE_ONLY)||nullAddr||!p||n<=0||pos<0||pos>capacity)return 0;int32_t count=std::min(n,capacity-pos);std::memcpy(bytes.data()+pos,p,count);size=std::max(size,pos+count);return count;}
};
struct AVBuffer {std::shared_ptr<int> meta_=std::make_shared<int>(1);std::shared_ptr<AVMemory> memory_=std::make_shared<AVMemory>();};
struct AVBufferConfig {int32_t size;MemoryFlag memoryFlag;};
namespace AudioStandard {
enum CapturerState {CAPTURER_STOPPED,CAPTURER_RUNNING};
class AudioCapturer {public:
 std::atomic<CapturerState> state{CAPTURER_RUNNING}; std::deque<int> chunks;
 std::atomic<int> starts{0},stops{0},releases{0},reads{0}; bool startOK=true,stopOK=true,releaseOK=true;
 std::mutex gate;std::condition_variable cv; bool hold=false,entered=false,allow=false,stopWakes=false;std::atomic<bool> inRead{false};uint8_t next=1;
 CapturerState GetStatus(){return state.load();}
 bool Start(){++starts;if(startOK)state=CAPTURER_RUNNING;return startOK;}
 bool Stop(){++stops;if(stopOK)state=CAPTURER_STOPPED;cv.notify_all();return stopOK;}
 bool Release(){assert(!inRead);++releases;return releaseOK;}
 void RemoveAudioCapturerInfoChangeCallback(const std::shared_ptr<int>&){}
 int32_t Read(uint8_t &buffer,size_t count,bool blocking){assert(blocking);++reads;inRead=true;
  {std::unique_lock<std::mutex> l(gate);entered=true;cv.notify_all();if(hold)cv.wait(l,[&]{return allow||(stopWakes&&state==CAPTURER_STOPPED);});}
  int n=chunks.empty()?static_cast<int>(count):chunks.front();if(!chunks.empty())chunks.pop_front();
  for(int i=0;i<std::max(0,std::min(n,static_cast<int>(count)));++i)(&buffer)[i]=next++;
  inRead=false;return n;
 }
 void WaitRead(){std::unique_lock<std::mutex> l(gate);assert(cv.wait_for(l,1s,[&]{return entered;}));}
 void Allow(){std::lock_guard<std::mutex> l(gate);allow=true;cv.notify_all();}
};}
class AudioCaptureModule {public:
 std::mutex controlMutex_,readMutex_,captureMutex_;uint64_t readGeneration_=0;
 std::shared_ptr<AudioStandard::AudioCapturer> audioCapturer_=std::make_shared<AudioStandard::AudioCapturer>();
 std::shared_ptr<int> audioCapturerInfoChangeCallback_;bool isTrackMaxAmplitude=false;int32_t maxAmplitude_=0;
 void SetFaultEvent(const char*){}
 Status Start();Status Stop();Status Deinit(){return DoDeinit();}Status DoDeinit();
 Status Read(uint8_t*,size_t);Status Read(std::shared_ptr<AVBuffer>&,size_t);
 void TrackMaxAmplitude(const uint8_t*,int32_t);int32_t GetMaxAmplitude();
 Status GetSize(uint64_t &n){n=8;return Status::OK;}
};
struct Task {std::function<void()> waitJob;bool running=false,canRun=true;int starts=0,pauses=0,stops=0;std::shared_ptr<AudioCaptureModule> module;
 void Start(){assert(module->audioCapturer_->GetStatus()==AudioStandard::CAPTURER_RUNNING);++starts;running=canRun;}
 bool IsTaskRunning(){return running;} void Pause(){assert(module->audioCapturer_->GetStatus()!=AudioStandard::CAPTURER_RUNNING);++pauses;running=false;if(waitJob)waitJob();}
 void StopAsync(){running=false;}void Stop(){assert(!module||!module->audioCapturer_||module->audioCapturer_->GetStatus()!=AudioStandard::CAPTURER_RUNNING);++stops;running=false;if(waitJob)waitJob();}
};
struct Queue {std::shared_ptr<AVBuffer> buffer=std::make_shared<AVBuffer>();Status request=Status::OK;int requests=0;std::vector<bool> pushes;
 Status RequestBuffer(std::shared_ptr<AVBuffer>& b,const AVBufferConfig &c,int){assert(c.size>0&&c.size<100000);++requests;b=buffer;return request;}
 Status PushBuffer(const std::shared_ptr<AVBuffer>& b,bool filled){assert(b);pushes.push_back(filled);return Status::OK;}
};
class AudioCaptureFilter {public:
 std::mutex lifecycleMutex_,cachedAudioDataMutex_;std::shared_ptr<AudioCaptureModule> audioCaptureModule_=std::make_shared<AudioCaptureModule>();
 std::shared_ptr<Task> taskPtr_=std::make_shared<Task>();std::shared_ptr<Queue> outputBufferQueue_=std::make_shared<Queue>();
 bool eos_=false,hasCalculateAVTime_=false,withVideo_=false;int64_t currentTime_=0,recordAudioFrameCount_=0,startTime_=0,pauseTime_=0;
 std::atomic<int64_t> firstAudioFramePts_{-1},firstVideoFramePts_{-1};std::deque<std::shared_ptr<uint8_t>> cachedAudioDataDeque_;
 AudioCaptureFilter(){taskPtr_->module=audioCaptureModule_;}
 Status DoStart();Status DoPause();Status DoResume();Status DoStop();Status DoRelease();
 void RecordOneAudioFrame(uint64_t);void RecordCachedData(int32_t);
 void GetCurrentTime(int64_t &t){t=20000000;}void FillLostFrame(int32_t){}int32_t FillLostFrameNum(){return 0;}void RelativeSleep(int64_t){}
};
// ACTUAL_FUNCTIONS
int main(){
 int cases=0;
 {AudioCaptureModule m;uint8_t b[8]{};assert(m.Read(b,8)==Status::OK);assert(b[0]==1&&b[7]==8);++cases;}
 {AudioCaptureModule m;m.audioCapturer_->chunks={1,2,1,4};uint8_t b[8]{};assert(m.Read(b,8)==Status::OK);assert(b[0]==1&&b[7]==8);assert(m.audioCapturer_->reads==4);++cases;}
 for(auto chunks:std::vector<std::deque<int>>{{0},{-1},{9},{2,0},{2,-1},{2,7}}){AudioCaptureFilter f;f.audioCaptureModule_->audioCapturer_->chunks=chunks;f.RecordOneAudioFrame(8);assert(f.outputBufferQueue_->pushes==std::vector<bool>{false});assert(f.outputBufferQueue_->buffer->memory_->GetSize()==0);assert(f.recordAudioFrameCount_==0);++cases;}
 for(uint64_t n:{uint64_t(0),uint64_t(100000),uint64_t(INT32_MAX)+1,UINT64_MAX}){AudioCaptureFilter f;f.RecordOneAudioFrame(n);assert(f.outputBufferQueue_->requests==0);++cases;}
 for(int offset:{-1,17,24,25}){AudioCaptureFilter f;f.outputBufferQueue_->buffer->memory_->offset=offset;f.RecordOneAudioFrame(8);assert(f.outputBufferQueue_->pushes==std::vector<bool>{false});assert(f.audioCaptureModule_->audioCapturer_->reads==0);++cases;}
 {AudioCaptureFilter f;auto mem=f.outputBufferQueue_->buffer->memory_;mem->offset=16;f.RecordOneAudioFrame(8);assert(f.outputBufferQueue_->pushes==std::vector<bool>{true});assert(mem->size==8);for(int i=0;i<16;++i)assert(mem->bytes[i]==0xa5);for(int i=16;i<24;++i)assert(mem->bytes[i]==i-15);++cases;}
 {AudioCaptureFilter f;auto mem=f.outputBufferQueue_->buffer->memory_;f.RecordOneAudioFrame(8);assert(mem->bytes[0]==0xa5&&mem->bytes[2]==0xa5&&mem->bytes[3]==1&&mem->bytes[10]==8&&mem->bytes[11]==0xa5);++cases;}
 for(int failed:{1,2}){AudioCaptureFilter f;f.outputBufferQueue_->buffer->memory_->failSetCall=failed;f.RecordOneAudioFrame(8);assert(f.outputBufferQueue_->pushes==std::vector<bool>{false});assert(f.recordAudioFrameCount_==0);++cases;}
 for(int kind=0;kind<4;++kind){AudioCaptureFilter f;auto mem=f.outputBufferQueue_->buffer->memory_;if(kind==0)mem->flags=MEMORY_READ_ONLY;if(kind==1)mem->nullAddr=true;if(kind==2)f.outputBufferQueue_->buffer->memory_=nullptr;if(kind==3)f.outputBufferQueue_->request=Status::ERROR_INVALID_OPERATION;f.RecordOneAudioFrame(8);assert(f.outputBufferQueue_->pushes==std::vector<bool>{false});++cases;}
 {AudioCaptureModule m;auto c=m.audioCapturer_;c->hold=true;uint8_t b[8]{};auto reader=std::async(std::launch::async,[&]{return m.Read(b,8);});c->WaitRead();assert(m.Stop()==Status::OK);assert(m.Start()==Status::OK);c->Allow();assert(reader.get()==Status::ERROR_AGAIN);assert(m.Read(b,8)==Status::OK);++cases;}
 {AudioCaptureModule m;auto c=m.audioCapturer_;c->hold=true;uint8_t b[8]{};auto reader=std::async(std::launch::async,[&]{return m.Read(b,8);});c->WaitRead();auto release=std::async(std::launch::async,[&]{return m.Deinit();});for(int i=0;i<100&&c->stops==0;++i)std::this_thread::sleep_for(1ms);assert(c->stops==1);assert(release.wait_for(10ms)==std::future_status::timeout);assert(c->releases==0);c->Allow();assert(reader.get()==Status::ERROR_AGAIN);assert(release.get()==Status::OK);assert(c->releases==1);++cases;}
 {AudioCaptureModule m;auto c=m.audioCapturer_;c->stopOK=false;assert(m.Deinit()==Status::ERROR_AUD_STOP_FAILED);assert(c->releases==0&&m.audioCapturer_==c);++cases;}
 {AudioCaptureModule m;auto c=m.audioCapturer_;c->releaseOK=false;assert(m.Deinit()==Status::ERROR_INVALID_OPERATION);assert(m.audioCapturer_==c);++cases;}
 {AudioCaptureFilter f;auto c=f.audioCaptureModule_->audioCapturer_;c->state=AudioStandard::CAPTURER_STOPPED;c->startOK=false;assert(f.DoResume()==Status::ERROR_AUD_START_FAILED);assert(f.taskPtr_->starts==0);++cases;}
 {AudioCaptureFilter f;auto c=f.audioCaptureModule_->audioCapturer_;f.taskPtr_=nullptr;assert(f.DoResume()==Status::ERROR_INVALID_OPERATION);assert(c->starts==0);assert(f.DoStart()==Status::ERROR_INVALID_OPERATION);++cases;}
 {AudioCaptureFilter f;f.taskPtr_->canRun=false;assert(f.DoResume()==Status::ERROR_AUD_START_FAILED);assert(f.audioCaptureModule_->audioCapturer_->stops==1);++cases;}
 {AudioCaptureFilter f;assert(f.DoPause()==Status::OK);assert(f.taskPtr_->pauses==1);assert(f.DoResume()==Status::OK);f.RecordOneAudioFrame(8);assert(f.recordAudioFrameCount_==1);assert(f.DoStop()==Status::OK);assert(f.taskPtr_->stops==1);assert(f.DoRelease()==Status::OK);++cases;}
 {AudioCaptureFilter f;auto c=f.audioCaptureModule_->audioCapturer_;c->stopOK=false;assert(f.DoPause()==Status::ERROR_AUD_STOP_FAILED);assert(f.taskPtr_->pauses==0);assert(f.DoStop()==Status::ERROR_AUD_STOP_FAILED);assert(f.taskPtr_->stops==0);assert(f.DoRelease()==Status::ERROR_AUD_STOP_FAILED);assert(c->releases==0);++cases;}
 for(int offset:{3,16,17,-1}){AudioCaptureFilter f;auto mem=f.outputBufferQueue_->buffer->memory_;mem->offset=offset;auto data=std::shared_ptr<uint8_t>(new uint8_t[8],std::default_delete<uint8_t[]>());std::fill(data.get(),data.get()+8,42);f.cachedAudioDataDeque_.push_back(data);f.RecordCachedData(1);bool good=offset==3||offset==16;assert(f.outputBufferQueue_->pushes==std::vector<bool>{good});if(good){assert(mem->bytes[offset]==42&&mem->size==8);}++cases;}
 {AudioCaptureModule m;assert(m.GetMaxAmplitude()==0);uint8_t b[4]{};assert(m.Read(b,4)==Status::OK);uint8_t loud[]={0,128};m.TrackMaxAmplitude(loud,1);assert(m.GetMaxAmplitude()==32768);++cases;}
 {AudioCaptureFilter f;auto c=f.audioCaptureModule_->audioCapturer_;c->hold=true;c->stopWakes=true;
 auto reader=std::async(std::launch::async,[&]{f.RecordOneAudioFrame(8);});c->WaitRead();f.taskPtr_->waitJob=[&]{reader.get();};
 assert(f.DoStop()==Status::OK);assert(f.outputBufferQueue_->pushes==std::vector<bool>{false});assert(f.recordAudioFrameCount_==0);++cases;}
 {AudioCaptureFilter f;auto c=f.audioCaptureModule_->audioCapturer_;c->state=AudioStandard::CAPTURER_STOPPED;
 auto a=std::async(std::launch::async,[&]{for(int i=0;i<100;++i)assert(f.DoResume()==Status::OK);});
 auto b=std::async(std::launch::async,[&]{for(int i=0;i<100;++i)assert(f.DoPause()==Status::OK);});a.get();b.get();++cases;}
 std::cout<<"actual capture functions: "<<cases<<" cases passed\n";
}
