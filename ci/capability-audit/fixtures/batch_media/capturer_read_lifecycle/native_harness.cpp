// Actual production method bodies are inserted unchanged at ACTUAL_METHODS.
// Dependencies (IPC, shared buffer and logging) are controlled, not an audio backend.
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
#include <fstream>
#include <sstream>
#include <sys/syscall.h>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>
#include "futex_tool.h"
#include "audio_ring_cache.h"
#include "securec.h"
#include "audio_service_log.h"
#include "audio_utils.h"
#define CHECK_AND_CALL_FUNC_RETURN_RET_LOG(c,r,action,...) do { if (!(c)) { action; return (r); } } while (0)
#define CHECK_AND_CALL_FUNC_RETURN(c,action) do { if (!(c)) { action; return; } } while (0)
#define LOGLITMITTIMES 10
#define OPERATION_TIMEOUT_IN_MS 1000
#define OPERATION_TIMEOUT_FOR_STOP_IN_MS 1000
#define MAX_CLIENT_READ_SIZE 16384
#define SUCCESS 0
#define ERROR -1
#define ERR_ILLEGAL_STATE -2
#define ERR_INVALID_PARAM -3
#define RECORD_START_ILLEGAL_STATE 1
#define RECORD_START_OPERATION_FAILED 2
#define RECORD_PAUSE_ILLEGAL_STATE 3
#define RECORD_PAUSE_OPERATION_FAILED 4
#define RECORD_STOP_ILLEGAL_STATE 5
#define RECORD_STOP_OPERATION_FAILED 6
#define RECORD_RELEASE_ILLEGAL_STATE 7
#define RECORD_SEND_DATA_INVALID_PARAM 8
#define RECORD_SEND_DATA_ILLEGAL_STATE 9
#define RECORD_SEND_DATA_OPERATION_FAILED 10
#define STATE_CHANGE_EVENT 1
#define CMD_FROM_CLIENT 0
#define METHOD_WRITE_OR_READ 1
#define THREAD_PRIORITY_QOS_7 1
namespace OHOS { namespace AudioStandard {
enum State { NEW, PREPARED, RUNNING, PAUSED, STOPPING, STOPPED, RELEASED, INVALID };
enum StreamFocusState { FOCUS_INVALID = INVALID };
enum AudioCaptureMode { CAPTURE_MODE_NORMAL, CAPTURE_MODE_CALLBACK };
enum Operation { MAX_OPERATION_CODE, START_STREAM, PAUSE_STREAM, STOP_STREAM };
using StateChangeCmdType = int;
using AudioStreamDeviceChangeReasonExt = int;
struct Gate {
 std::mutex mutex; std::condition_variable cv; bool enabled=false, entered=false, released=false;
 void Wait() { std::unique_lock<std::mutex> l(mutex); if (!enabled) return; entered=true; cv.notify_all(); cv.wait(l,[&]{return released;}); }
 void Await() { std::unique_lock<std::mutex> l(mutex); assert(cv.wait_for(l,std::chrono::seconds(2),[&]{return entered;})); }
 void Open() { std::lock_guard<std::mutex> l(mutex); released=true; cv.notify_all(); }
};
struct BufferDesc { uint8_t *buffer=nullptr; size_t bufLength=0, dataLength=0; uint64_t position=0; int64_t timeStampInNs=0; };
struct OHAudioBuffer {
 std::atomic<uint32_t> futex {IS_READY}; std::atomic<uint64_t> read {0}, write {0};
 std::atomic<int> waitEntered {0}, waiterTid {0}; Gate beforeWait, afterWait;
 uint8_t data[4] {1,2,3,4};
 uint64_t GetCurWriteFrame() const { return write.load(); } uint64_t GetCurReadFrame() const { return read.load(); }
 void GetTimeStampInfo(uint64_t &p,int64_t &t) { p=read.load();t=42; }
 void GetReadbuffer(uint64_t,BufferDesc &b) { b.buffer=data;b.bufLength=sizeof(data); }
 void SetCurReadFrame(uint64_t p,bool) { read=p; }
 FutexCode WaitFor(int64_t ns,const std::function<bool()> &pred) { beforeWait.Wait(); waiterTid=static_cast<int>(syscall(__NR_gettid)); ++waitEntered; auto r=FutexTool::FutexWait(&futex,ns,pred); afterWait.Wait(); return r; }
 void WakeFutex() { assert(FutexTool::FutexWake(&futex)==FUTEX_SUCCESS); }
};
struct FakeIPC {
 std::function<void(Operation,int)> ack; std::function<void()> release;
 int startResult=0,pauseResult=0,stopResult=0,ackResult=0;
 int Start(bool) { if(!startResult)ack(START_STREAM,ackResult);return startResult; }
 int Pause() { if(!pauseResult)ack(PAUSE_STREAM,ackResult);return pauseResult; }
 int Stop() { if(!stopResult)ack(STOP_STREAM,ackResult);return stopResult; }
 int Release(bool) { if(release)release();return 0; }
 template<class... T> void RegisterThreadPriority(T&&...) {}
};
struct FakeQueue { bool IsEmpty() {return false;} void Push(BufferDesc) {} void PushNoWait(BufferDesc) {} };
struct FakeHandler { void ReleaseEventRunner() {} };
struct FakeStreamCallback { void OnStateChange(State,StateChangeCmdType) {} };
// Host dependency alias for the exact interface name used by unchanged FinalizeRelease.
using AudioStreamCallback = FakeStreamCallback;
struct StreamDfxManager { static StreamDfxManager &GetInstance(){static StreamDfxManager x;return x;} template<class... T>void SendAudioErrorEvent(T&&...) {} };
struct DumpFileUtil { static constexpr int DUMP_CLIENT_PARA=0; template<class... T>static void CloseDumpFile(T&&...) {} template<class... T>static void WriteDumpFile(T&&...) {} };
struct VolumeTools { template<class... T>static void DfxOperation(T&&...) {} };
struct AppBundle { static AppBundle &GetInstance(){static AppBundle x;return x;} static std::string GetSelfBundleName(int) {return "fixture";} };
using AppBundleManager=AppBundle;
struct CapturerInClientInner {
 // Only the class carrier/dependencies are reduced; core method bodies are actual pinned source.
 std::mutex statusMutex_, readMutex_, callServerMutex_, runnerMutex_, streamCbMutex_, markReachMutex_, periodReachMutex_;
 std::condition_variable callServerCV_, cbThreadCv_;
 std::atomic<State> state_ {PREPARED}; std::atomic<StreamFocusState> streamFocusState_ {FOCUS_INVALID};
 std::atomic<uint64_t> normalReadGeneration_ {0};
 AudioCaptureMode capturerMode_ = CAPTURE_MODE_NORMAL;
 std::shared_ptr<OHAudioBuffer> clientBuffer_ = std::make_shared<OHAudioBuffer>();
 std::unique_ptr<AudioRingCache> ringCache_ = AudioRingCache::Create(16);
 std::shared_ptr<FakeIPC> ipcStream_ = std::make_shared<FakeIPC>();
 Operation notifiedOperation_=MAX_OPERATION_CODE; int64_t notifiedResult_=0;
 std::shared_ptr<int> readCb_; FakeQueue cbBufferQueue_;
 std::unique_ptr<uint8_t[]> cbBuffer_; size_t cbBufferSize_=4; bool cbThreadReleased_=false;
 std::thread callbackLoop_; bool paramsIsSet_=true,runnerReleased_=false;
 std::shared_ptr<FakeHandler> callbackHandler_; std::weak_ptr<AudioStreamCallback> streamCallback_;
 FILE *dumpMetaDataFile_=nullptr,*dumpInFd_=nullptr; std::string dumpMetaDataFileName_,logUtilsTag_;
 int sessionId_=1,clientUid_=20010040; bool needSetThreadPriority_=false;
 struct { struct {int appUid=20010040;} appInfo; int streamInfo=0; } clientConfig_;
 std::atomic<int> readLogTimes_ {0}; int volumeDataCount_=0;
 size_t clientSpanSizeInByte_=4,spanSizeInFrame_=1,sizePerFrameInByte_=4;
 uint64_t totalBytesRead_=0; bool capturerMarkReached_=true; int64_t capturerMarkPosition_=0,capturerPeriodRead_=0,capturerPeriodSize_=0;
 std::function<void()> onPositionEvent;
 CapturerInClientInner() { ipcStream_->ack=[this](Operation op,int result){std::lock_guard<std::mutex> l(callServerMutex_);notifiedOperation_=op;notifiedResult_=result;callServerCV_.notify_all();}; }
 template<class... T>void SendAudioErrorEventAndProcessOther(T&&...) {}
 void SafeSendCallbackEvent(int64_t,int64_t) {} void UpdateTracker(const char*) {}
 void StateCmdTypeToParams(int64_t &out,State state,int) {out=state;}
 void SendCapturerMarkReachedEvent(int64_t) {if(onPositionEvent)onPositionEvent();}
 void SendCapturerPeriodReachedEvent(int64_t) {if(onPositionEvent)onPositionEvent();}
 void UpdateStreamState(State);
 bool StartAudioStream(StateChangeCmdType=0,AudioStreamDeviceChangeReasonExt=0);
 bool PauseAudioStream(StateChangeCmdType=0); bool StopAudioStream();
 bool ReleaseAudioStream(bool=true,bool=false); void ReleaseCallbackResources(bool);void FinalizeRelease();
 void RetireNormalReadsLocked(); bool NormalReadIsCurrent(uint64_t) const;
 int32_t HandleCapturerRead(size_t&,size_t&,uint8_t&,bool);
 int32_t HandleNormalCapturerRead(size_t&,size_t,uint8_t&,bool,uint64_t);
 int32_t Read(uint8_t&,size_t,bool);
 bool CommitNormalReadPositionChanges(size_t,uint64_t,int64_t&,int64_t&);void HandleCapturerPositionChanges(size_t);
};
// ACTUAL_METHODS
} }
using namespace OHOS::AudioStandard;
using namespace std::chrono_literals;
static std::future<int> Reader(CapturerInClientInner &c,uint8_t *bytes,std::atomic<int> *tid=nullptr) { return std::async(std::launch::async,[&c,bytes,tid]{if(tid)*tid=static_cast<int>(syscall(__NR_gettid));return c.Read(*bytes,4,true);}); }
// /proc reports the real kernel syscall ABI when an amd64 container is
// translated on an arm64 Docker kernel. Root binds this from Docker Engine's
// observed Architecture; production FutexTool still uses its own __NR_futex.
static long ObservedKernelFutexSyscall() {
 const char *architecture=std::getenv("OHOS_QA_KERNEL_ARCH");
 if(architecture==nullptr)return __NR_futex;
 if(std::string(architecture)=="aarch64"||std::string(architecture)=="arm64")return 98;
 if(std::string(architecture)=="x86_64"||std::string(architecture)=="amd64")return 202;
 assert(false && "unsupported observed Docker kernel architecture");return -1;
}
static void AwaitMutexWait(std::atomic<int> &ownedTid,std::mutex &mutex) {
 auto end=std::chrono::steady_clock::now()+2s;
 for (;;) {
  int tid=ownedTid.load();
  if(tid>0){std::ifstream in("/proc/self/task/"+std::to_string(tid)+"/syscall");long call=-1;uintptr_t address=0;
   if((in>>call>>std::hex>>address)&&call==ObservedKernelFutexSyscall()&&address==reinterpret_cast<uintptr_t>(mutex.native_handle()))return;}
  assert(std::chrono::steady_clock::now()<end);std::this_thread::yield();
 }
}
static void AwaitWait(const std::shared_ptr<OHAudioBuffer> &b) {
 // Observe this owned host thread inside the exact real FutexTool syscall. Merely
 // setting a pre-wait flag races with Stop and could invent a baseline counterexample.
 auto end=std::chrono::steady_clock::now()+2s;
 for (;;) {
  int tid=b->waiterTid.load();
  if(tid>0){std::ifstream in("/proc/self/task/"+std::to_string(tid)+"/syscall");long call=-1;uintptr_t address=0;
   if((in>>call>>std::hex>>address)&&call==ObservedKernelFutexSyscall()&&address==reinterpret_cast<uintptr_t>(&b->futex))return;}
  assert(std::chrono::steady_clock::now()<end);std::this_thread::yield();
 }
}
static void Finish(std::future<int> &f) { assert(f.wait_for(1s)==std::future_status::ready);assert(f.get()==ERROR); }
int main() {
 alarm(15);
#if !CANDIDATE
 CapturerInClientInner old;assert(old.StartAudioStream());uint8_t bytes[4]={};auto f=Reader(old,bytes);AwaitWait(old.clientBuffer_);assert(old.StopAudioStream());
 bool blocked=f.wait_for(200ms)!=std::future_status::ready;
 // Explicit host-only recovery occurs after observing the genuine baseline failure.
 old.clientBuffer_->WakeFutex();Finish(f);assert(blocked);
 puts("BASELINE_COUNTEREXAMPLE: actual normal Stop did not wake actual blocking Read; host recovery after observation");return 10;
#else
 // Retirement before the real FutexWait starts must not be lost.
 for(int op=0;op<3;++op){CapturerInClientInner c;assert(c.StartAudioStream());auto b=c.clientBuffer_;b->beforeWait.enabled=true;uint8_t bytes[4]={};auto f=Reader(c,bytes);b->beforeWait.Await();
  if(op==0)assert(c.StopAudioStream());else if(op==1)assert(c.PauseAudioStream());else assert(c.ReleaseAudioStream());
  b->beforeWait.Open();Finish(f);assert(c.totalBytesRead_==0&&b->read.load()==0);}
 // During a real futex wait: Stop, Pause, Release, and accepted Stop with negative ack.
 for(int op=0;op<4;++op){CapturerInClientInner c;assert(c.StartAudioStream());uint8_t bytes[4]={};auto f=Reader(c,bytes);AwaitWait(c.clientBuffer_);
  if(op==0)assert(c.StopAudioStream());else if(op==1)assert(c.PauseAudioStream());else if(op==2){c.ipcStream_->release=[&]{assert(f.wait_for(1s)==std::future_status::ready);};assert(c.ReleaseAudioStream());}
  else {c.ipcStream_->ackResult=ERROR;assert(!c.StopAudioStream());assert(c.state_==INVALID);}Finish(f);assert(c.totalBytesRead_==0);}
 // Delay A after actual wait returned; rearm B before A resumes. A must not consume B.
 {CapturerInClientInner c;assert(c.StartAudioStream());auto b=c.clientBuffer_;b->afterWait.enabled=true;uint8_t bytes[4]={};auto a=Reader(c,bytes);AwaitWait(b);assert(c.StopAudioStream());b->afterWait.Await();assert(c.StartAudioStream());b->write=1;b->afterWait.Open();Finish(a);assert(b->read==0&&c.totalBytesRead_==0);assert(c.Read(*bytes,4,false)==4);assert(b->read==1&&c.totalBytesRead_==4);}
 // Synchronous control rejection preserves a still-running Read and original error semantics.
 for(int op=0;op<2;++op){CapturerInClientInner c;assert(c.StartAudioStream());uint8_t bytes[4]={};auto f=Reader(c,bytes);AwaitWait(c.clientBuffer_);auto gen=c.normalReadGeneration_.load();
  if(op==0){c.ipcStream_->stopResult=ERROR;assert(!c.StopAudioStream());c.ipcStream_->stopResult=0;}else{c.ipcStream_->pauseResult=ERROR;assert(!c.PauseAudioStream());c.ipcStream_->pauseResult=0;}
  assert(c.state_==RUNNING&&c.normalReadGeneration_==gen);assert(f.wait_for(20ms)!=std::future_status::ready);assert(c.StopAudioStream());Finish(f);}
 // A failed asynchronous Pause keeps RUNNING and leaves the blocked read current.
 {CapturerInClientInner c;assert(c.StartAudioStream());uint8_t bytes[4]={};auto f=Reader(c,bytes);AwaitWait(c.clientBuffer_);auto g=c.normalReadGeneration_.load();c.ipcStream_->ackResult=ERROR;assert(!c.PauseAudioStream());assert(c.state_==RUNNING&&c.normalReadGeneration_==g);assert(f.wait_for(20ms)!=std::future_status::ready);c.ipcStream_->ackResult=0;assert(c.StopAudioStream());Finish(f);}
 // A partially filled old blocking read is cancelled, never returned as a success.
 {CapturerInClientInner c;assert(c.StartAudioStream());auto b=c.clientBuffer_;b->write=1;uint8_t bytes[8]={};auto f=std::async(std::launch::async,[&]{return c.Read(*bytes,8,true);});AwaitWait(b);assert(b->read==1);assert(c.StopAudioStream());Finish(f);assert(c.totalBytesRead_==0);assert(c.StartAudioStream());b->write=2;assert(c.Read(*bytes,4,false)==4&&c.totalBytesRead_==4);assert(c.ReleaseAudioStream());auto g=c.normalReadGeneration_.load();assert(c.Read(*bytes,4,false)==ERR_ILLEGAL_STATE);assert(c.ReleaseAudioStream()&&c.normalReadGeneration_==g);}
 // Multiple real Stop/Start operations on the same object do not make old A reads current again.
 {CapturerInClientInner c;auto b=c.clientBuffer_;uint8_t bytes[4]={};
  for(int round=0;round<8;++round){assert(c.StartAudioStream());{std::lock_guard<std::mutex> l(b->afterWait.mutex);b->afterWait.enabled=true;b->afterWait.entered=false;b->afterWait.released=false;}
   auto f=Reader(c,bytes);AwaitWait(b);assert(c.StopAudioStream());b->afterWait.Await();assert(c.StartAudioStream());b->write=b->read.load()+1;b->afterWait.Open();Finish(f);uint64_t oldCount=c.totalBytesRead_;assert(c.Read(*bytes,4,false)==4&&c.totalBytesRead_==oldCount+4);assert(c.StopAudioStream());}
  assert(c.totalBytesRead_==32);}
 // Failed Start does not create a new generation; retry remains usable.
 {CapturerInClientInner c;c.ipcStream_->startResult=ERROR;auto g=c.normalReadGeneration_.load();assert(!c.StartAudioStream());assert(c.state_==PREPARED&&c.normalReadGeneration_==g);c.ipcStream_->startResult=0;assert(c.StartAudioStream());assert(c.StopAudioStream());}
 // A committed position event may re-enter Stop: dispatch must be outside statusMutex_.
 {CapturerInClientInner c;assert(c.StartAudioStream());c.capturerMarkReached_=false;c.capturerMarkPosition_=1;c.clientBuffer_->write=1;c.onPositionEvent=[&]{assert(c.StopAudioStream());};uint8_t bytes[4]={};assert(c.Read(*bytes,4,false)==4);assert(c.state_==STOPPED&&c.totalBytesRead_==4);}
 // Existing mark callbacks hold markReachMutex_ while re-entering Stop. A Read
 // waiting for that mark lock must not hold statusMutex_ (the old draft's ABBA).
 {CapturerInClientInner c;assert(c.StartAudioStream());c.clientBuffer_->write=1;Gate callback;callback.enabled=true;
  auto cb=std::async(std::launch::async,[&]{std::lock_guard<std::mutex> mark(c.markReachMutex_);callback.Wait();assert(c.StopAudioStream());});
  callback.Await();uint8_t bytes[4]={};auto f=Reader(c,bytes);auto deadline=std::chrono::steady_clock::now()+2s;
  for(;;){{std::lock_guard<std::mutex> lock(c.periodReachMutex_);if(c.totalBytesRead_==4)break;}assert(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}
  callback.Open();assert(cb.wait_for(1s)==std::future_status::ready);cb.get();assert(f.wait_for(1s)==std::future_status::ready&&f.get()==4);}
 // Existing period callback lock order is period->status. Stop can run while
 // a new Read waits for period, without a status->period inversion.
 {CapturerInClientInner c;assert(c.StartAudioStream());c.clientBuffer_->write=1;Gate callback;callback.enabled=true;
  auto cb=std::async(std::launch::async,[&]{std::lock_guard<std::mutex> period(c.periodReachMutex_);callback.Wait();assert(c.StopAudioStream());});
  callback.Await();uint8_t bytes[4]={};std::atomic<int> readTid{0};auto f=Reader(c,bytes,&readTid);AwaitMutexWait(readTid,c.periodReachMutex_);callback.Open();assert(cb.wait_for(1s)==std::future_status::ready);cb.get();Finish(f);assert(c.totalBytesRead_==0);}
 // Callback mode keeps its existing Stop wake behavior and generation untouched.
 {CapturerInClientInner c;c.capturerMode_=CAPTURE_MODE_CALLBACK;assert(c.StartAudioStream());uint8_t bytes[4]={};auto f=Reader(c,bytes);AwaitWait(c.clientBuffer_);assert(c.StopAudioStream());Finish(f);assert(c.normalReadGeneration_==0);}
 puts("CANDIDATE_METHOD_BOUNDARIES: normal retire/wake, Stop-Start generation, errors, Release ordering and lock-free event dispatch");return 0;
#endif
}
