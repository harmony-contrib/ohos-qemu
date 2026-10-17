// Uses complete production CPPs and their actual class headers. Controlled external dependencies only.
// Never evidence of real IPC, audio decoding, PCM output, vibrator HDI, or guest success.
#include "host_prelude.h"
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <sys/stat.h>
#include "audio_haptic_sound.h"
#include "audio_haptic_vibrator.h"
#include "player.h"
#define private public
#include "audio_haptic_player_impl.h"
#include "audio_haptic_sound_normal_impl.h"
#undef private
using namespace OHOS;
using namespace OHOS::Media;

namespace {
struct Plan {
    int registerResult=0,sourceResult=0,parameterResult=0,prepareResult=0,playResult=0;
    bool prepareCallback=true,firstDuringPlay=false,errorDuringPrepare=false;
};
struct Backend final : Player {
    explicit Backend(Plan value):plan(value){}
    ~Backend()override{if(fd>=0)close(fd);}
    Plan plan;
    PlayerStates state=PLAYER_IDLE;
    std::shared_ptr<PlayerCallback> callback;
    int registers=0,resets=0,prepares=0,plays=0,releases=0,fd=-1;
    int64_t offset=0,length=0;
    float volume=1;bool loop=false;
    std::function<void()> beforeGetTime,beforeRelease;
    int SetPlayerCallback(const std::shared_ptr<PlayerCallback>& cb)override {
        ++registers; assert(state==PLAYER_IDLE); callback=cb;return plan.registerResult;
    }
    int Reset()override {
        ++resets;
        // Preserve the actual server's fresh-IDLE Reset rejection, rather than making the double permissive.
        return state==PLAYER_IDLE?MSERR_INVALID_OPERATION:MSERR_OK;
    }
    int SetSource(int value,int64_t start,int64_t size)override {
        if(plan.sourceResult)return plan.sourceResult;
        fd=dup(value);if(fd<0)return MSERR_OPEN_FILE_FAILED;
        offset=start;length=size;state=PLAYER_INITIALIZED;return 0;
    }
    int SetParameter(const Format&)override{return plan.parameterResult;}
    int PrepareAsync()override {
        ++prepares;
        if(plan.errorDuringPrepare){callback->OnError(MSERR_UNSUPPORT_FILE,"controlled unsupported");return plan.prepareResult;}
        if(plan.prepareCallback){state=PLAYER_PREPARED;callback->OnInfo(INFO_TYPE_STATE_CHANGE,PLAYER_PREPARED,Format{});}
        return plan.prepareResult;
    }
    int Play()override {
        ++plays;state=PLAYER_STARTED;
        callback->OnInfo(INFO_TYPE_STATE_CHANGE,PLAYER_STARTED,Format{});
        if(plan.firstDuringPlay)First(0);
        return plan.playResult;
    }
    int Stop()override {state=PLAYER_STOPPED;return 0;}
    int Release()override {if(beforeRelease)beforeRelease();++releases;if(fd>=0){close(fd);fd=-1;}return 0;}
    int SetVolume(float a,float b)override{assert(a==b);volume=a;return 0;}
    int SetLooping(bool value)override{loop=value;return 0;}
    int GetCurrentTime(int &out)override{if(beforeGetTime)beforeGetTime();out=123;return 0;}
    void First(int64_t value){Format body;body.PutLongValue(PlayerKeys::AUDIO_FIRST_FRAME,value);callback->OnInfo(INFO_TYPE_AUDIO_FIRST_FRAME,0,body);}
    void Eos(bool repeat=false){callback->OnInfo(INFO_TYPE_EOS,repeat?1:0,Format{});}
    void Interrupt(){callback->OnInfo(INFO_TYPE_INTERRUPT_EVENT,0,Format{});}
    void AssertPinned()const {
        char bytes[4]={};assert(fd>=0);assert(offset==2&&length==4);
        assert(pread(fd,bytes,4,offset)==4);assert(std::string(bytes,4)=="2345");
    }
};
std::vector<std::shared_ptr<Backend>> backends;
std::vector<Plan> plans;
bool factoryReturnsNull=false;
struct Vibrator final : AudioHapticVibrator {
    std::atomic<int> starts{0};
    int32_t PreLoad(const HapticSource&,const AudioStandard::StreamUsage&)override{return 0;}
    int32_t Release()override{return 0;}
    void ResetStopState()override{}
    int32_t StartVibrate(const AudioLatencyMode&)override{++starts;return 0;}
    int32_t SetHapticIntensity(float)override{return 0;}
    int32_t StopVibrate()override{return 0;}
    int32_t GetDelayTime()override{return 0;}
    void EnableHapticsInSilentMode(bool)override{}
    bool IsHapticsCustomSupported()override{return false;}
    int32_t SetHapticsRamp(int32_t,float,float)override{return 0;}
    int32_t SetHapticsFeature(const HapticsFeature&)override{return 0;}
    void SetAudioHapticSyncId(const int32_t&)override{}
};
struct Observer final : AudioHapticPlayerCallback {
    std::mutex mutex;std::condition_variable cv;int eos=0,interrupts=0,errors=0;
    std::function<void()> onError,onEos;
    void OnInterrupt(const AudioStandard::InterruptEvent&)override{std::lock_guard<std::mutex> l(mutex);++interrupts;cv.notify_all();}
    void OnEndOfStream()override{if(onEos)onEos();std::lock_guard<std::mutex> l(mutex);++eos;cv.notify_all();}
    void OnError(int)override{if(onError)onError();std::lock_guard<std::mutex> l(mutex);++errors;cv.notify_all();}
    bool Wait(int &field,int value){std::unique_lock<std::mutex> l(mutex);return cv.wait_for(l,std::chrono::seconds(3),[&]{return field==value;});}
};
#ifndef AUDIO_HAPTIC_BASELINE
struct QueryGate {
    std::mutex mutex;std::condition_variable cv;bool entered=false,proceed=false;
    void Block(){std::unique_lock<std::mutex> lock(mutex);entered=true;cv.notify_one();cv.wait(lock,[&]{return proceed;});}
    void Await(){std::unique_lock<std::mutex> lock(mutex);assert(cv.wait_for(lock,std::chrono::seconds(3),[&]{return entered;}));}
    void Open(){std::lock_guard<std::mutex> lock(mutex);proceed=true;cv.notify_one();}
};
// A transport-delay relay carries the immutable real Session it received, never an invented/current epoch.
struct Relay final : AudioHapticPlaybackCallback {
    explicit Relay(std::shared_ptr<AudioHapticPlaybackCallback> target):target(std::move(target)){}
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    bool delayFirst=false;
    std::function<void()> delayed;
    void OnPlaybackCreated(const std::shared_ptr<AudioHapticPlaybackSession>& s)override{target->OnPlaybackCreated(s);}
    void OnPlaybackFirstFrame(const std::shared_ptr<AudioHapticPlaybackSession>& s,uint64_t latency)override{
        if(delayFirst){delayed=[target=target,s,latency]{target->OnPlaybackFirstFrame(s,latency);};return;}
        target->OnPlaybackFirstFrame(s,latency);
    }
    void OnPlaybackEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession>& s,bool loop)override{target->OnPlaybackEndOfStream(s,loop);}
    void OnPlaybackInterrupt(const std::shared_ptr<AudioHapticPlaybackSession>& s,const AudioStandard::InterruptEvent&e)override{target->OnPlaybackInterrupt(s,e);}
    void OnPlaybackError(const std::shared_ptr<AudioHapticPlaybackSession>& s,int code)override{target->OnPlaybackError(s,code);}
};
struct OwnedSource {
    std::string path;int fd=-1;
    explicit OwnedSource(const std::string& directory){
        path=directory+"/source-XXXXXX";std::vector<char> value(path.begin(),path.end());value.push_back(0);
        fd=mkstemp(value.data());assert(fd>=0);path=value.data();assert(write(fd,"0123456789",10)==10);
    }
    ~OwnedSource(){if(fd>=0)close(fd);unlink(path.c_str());}
    AudioSource FromFd()const{AudioSource s;s.fd=fd;s.offset=2;s.length=4;return s;}
    AudioSource FromPath()const{AudioSource s;s.audioUri=path;s.offset=2;s.length=4;return s;}
    void DropCaller(){if(fd>=0){close(fd);fd=-1;}assert(unlink(path.c_str())==0);}
};
struct PlayerFixture {
    std::shared_ptr<AudioHapticPlayerImpl> player;
    std::shared_ptr<AudioHapticSoundNormalImpl> normal;
    std::shared_ptr<Observer> observer=std::make_shared<Observer>();
    std::shared_ptr<Relay> relay;
    PlayerFixture(const AudioSource& source,bool muteAudio=false,bool muteHaptic=false){
        player=std::make_shared<AudioHapticPlayerImpl>();
        AudioHapticPlayerParam param;
        param.options={muteAudio,muteHaptic,false};param.audioSource=source;
        param.latencyMode=AUDIO_LATENCY_MODE_NORMAL;param.streamUsage=AudioStandard::STREAM_USAGE_MEDIA;
        player->SetPlayerParam(param);player->LoadPlayer();
        player->SetAudioHapticPlayerCallback(observer);
        normal=std::static_pointer_cast<AudioHapticSoundNormalImpl>(player->audioHapticSound_);
        relay=std::make_shared<Relay>(std::static_pointer_cast<AudioHapticSoundCallbackImpl>(player->soundCallback_));
        assert(normal->SetPlaybackCallback(relay)==0);
    }
    ~PlayerFixture(){assert(player->Release()==0);}
    bool Armed()const{std::lock_guard<std::mutex> l(player->waitStartVibrateMutex_);return player->canStartVibrate_;}
    uint64_t Latency()const{std::lock_guard<std::mutex> l(player->waitStartVibrateMutex_);return player->audioLatency_;}
    std::shared_ptr<AudioHapticPlaybackSession> Session()const{std::lock_guard<std::mutex> l(player->waitStartVibrateMutex_);return player->normalPlaybackSession_;}
};
#endif
}
namespace OHOS { namespace Media {
std::shared_ptr<Player> PlayerFactory::CreatePlayer(){
    if(factoryReturnsNull){factoryReturnsNull=false;return nullptr;}
    Plan plan;if(!plans.empty()){plan=plans.front();plans.erase(plans.begin());}
    auto backend=std::make_shared<Backend>(plan);backends.push_back(backend);return backend;
}
std::shared_ptr<AudioHapticVibrator> AudioHapticVibrator::CreateAudioHapticVibrator(AudioHapticPlayer&){return std::make_shared<Vibrator>();}
} }

#ifndef AUDIO_HAPTIC_BASELINE
int main(int argc,char **argv){
    assert(argc==2);const std::string directory=argv[1];
    // A controlled fresh backend demonstrably rejects Reset(IDLE); production Prepare must avoid calling it.
    {Backend idle(Plan{});assert(idle.Reset()==MSERR_INVALID_OPERATION);}
    for(bool pathSource:{false,true}){
        OwnedSource source(directory);PlayerFixture f(pathSource?source.FromPath():source.FromFd());
        assert(f.player->Prepare()==0);auto first=backends.back();assert(first->resets==0&&first->registers==1);
        source.DropCaller();
        for(int i=0;i<4;++i){
            assert(f.player->Start()==0);auto backend=backends.back();backend->AssertPinned();
            if(i==0)assert(backend==first);else assert(backend!=first);
            auto session=f.Session();assert(session->backend.lock()==backend);
            assert(f.player->Stop()==0);assert(session->end==AudioHapticSessionEnd::STOPPED);
        }
    }
    // GetCurrentTime must not invert worker wait -> normal API against normal API -> Created/wait.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd());assert(f.player->Prepare()==0);
        std::mutex gateMutex;std::condition_variable gate;bool locked=false,done=false;
        std::thread holder([&]{
            std::unique_lock<std::mutex> normalLock(f.normal->audioHapticPlayerLock_);
            std::unique_lock<std::mutex> signal(gateMutex);locked=true;gate.notify_one();gate.wait(signal,[&]{return done;});
        });
        {std::unique_lock<std::mutex> signal(gateMutex);gate.wait(signal,[&]{return locked;});}
        {std::lock_guard<std::mutex> wait(f.player->waitStartVibrateMutex_);assert(f.normal->GetAudioCurrentTime()==123);}
        {std::lock_guard<std::mutex> signal(gateMutex);done=true;gate.notify_one();}holder.join();
    }
    // Same real registered native callback receives concurrent mapped states; no mutable callback-local member.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd());assert(f.player->Prepare()==0);
        auto callback=backends.back()->callback;
        std::thread a([callback]{for(int i=0;i<100;++i)callback->OnInfo(INFO_TYPE_STATE_CHANGE,PLAYER_PREPARED,Format{});});
        std::thread b([callback]{for(int i=0;i<100;++i)callback->OnInfo(INFO_TYPE_STATE_CHANGE,PLAYER_INITIALIZED,Format{});});
        a.join();b.join();callback->OnInfo(INFO_TYPE_STATE_CHANGE,PLAYER_PREPARED,Format{});
        assert(f.normal->playerState_.load()==AudioHapticPlayerState::STATE_PREPARED);assert(f.player->Start()==0);
    }
    // Getter/live first-frame readers race the public mode setter using the actual class methods.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);assert(f.player->Prepare()==0);assert(f.player->Start()==0);
        auto backend=backends.back();
        std::thread setter([p=f.player]{for(int i=0;i<100;++i)p->SetHapticsMode(i%2?HAPTICS_MODE_SYNC:HAPTICS_MODE_NON_SYNC);});
        for(int i=0;i<100;++i){(void)f.player->GetHapticsMode();backend->First(0);}
        setter.join();assert(f.player->Stop()==0);
    }
    // SetVolume's existing pre-lock player-state check races lifecycle state writers; the enum must be atomic.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);assert(f.player->Prepare()==0);
        std::thread lifecycle([p=f.player]{for(int i=0;i<20;++i){assert(p->Start()==0);assert(p->Stop()==0);}});
        for(int i=0;i<100;++i)assert(f.player->SetVolume(0.5f)==0);
        lifecycle.join();
    }
    // The actual core GetTime snapshot owns normal while Release unpublishes and reenters time query.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);assert(f.player->Prepare()==0);
        auto backend=backends.back();QueryGate gate;
        std::weak_ptr<AudioHapticSoundNormalImpl> normal=f.normal;f.normal.reset();
        backend->beforeGetTime=[&]{gate.Block();};
        backend->beforeRelease=[player=std::weak_ptr<AudioHapticPlayerImpl>(f.player)]{
            auto owner=player.lock();assert(owner);
            assert(std::atomic_load(&owner->audioHapticSound_)==nullptr);
            assert(owner->GetAudioCurrentTime()==-1); // Reentry occurs outside the atomic publication operation.
        };
        int result=-999;
        std::thread query([player=f.player,&result]{result=player->GetAudioCurrentTime();});gate.Await();
        assert(f.player->Release()==0);
        assert(!normal.expired()); // Only the real GetTime local sound snapshot still owns this core object.
        assert(f.player->GetAudioCurrentTime()==-1);
        gate.Open();query.join();assert(result==123);assert(normal.expired());
    }
    // A real GetTime backend snapshot can overlap normal Stop/restart replacement; native Release reentry is safe.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);assert(f.player->Prepare()==0);assert(f.player->Start()==0);
        auto a=backends.back();QueryGate gate;std::atomic<bool> reentered{false};
        a->beforeGetTime=[&]{gate.Block();};
        a->beforeRelease=[player=std::weak_ptr<AudioHapticPlayerImpl>(f.player),&reentered]{
            auto owner=player.lock();assert(owner);
            assert(std::atomic_load(&owner->audioHapticSound_)!=nullptr);
            // The old normal backend has been unpublished before native Release, while top-level sound remains.
            assert(owner->GetAudioCurrentTime()==-1);reentered=true;
        };
        int result=-999;std::thread query([player=f.player,&result]{result=player->GetAudioCurrentTime();});gate.Await();
        assert(f.player->Stop()==0);assert(f.player->Start()==0);assert(backends.back()!=a);assert(reentered.load());
        gate.Open();query.join();assert(result==123);assert(f.player->GetAudioCurrentTime()==123);
    }
    // Actual A first-frame passes normal validation, pauses at relay, then reaches player after B rearm.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);
        assert(f.player->Prepare()==0);assert(f.player->Start()==0);auto a=backends.back();
        f.relay->delayFirst=true;a->First(777);assert(bool(f.relay->delayed));
        assert(f.player->Stop()==0);assert(f.player->Start()==0);auto b=backends.back();assert(a!=b);
        auto session=f.Session();assert(session->backend.lock()==b);
        assert(!f.Armed()&&f.Latency()==0);f.relay->delayed();assert(!f.Armed()&&f.Latency()==0);
        a->First(888);assert(!f.Armed()&&f.Latency()==0);
        f.relay->delayFirst=false;b->First(12);assert(f.Armed()&&f.Latency()==12);
        Format missing;b->callback->OnInfo(INFO_TYPE_AUDIO_FIRST_FRAME,0,missing);b->First(-1);assert(f.Latency()==12);
    }
    // First-frame produced synchronously inside a failed Play must never be published; retry gets a fresh backend.
    {
        OwnedSource source(directory);Plan failed;failed.playResult=-77;failed.firstDuringPlay=true;plans.push_back(failed);
        PlayerFixture f(source.FromFd(),false,true);assert(f.player->Prepare()==0);auto a=backends.back();
        assert(f.player->Start()==MSERR_START_FAILED);assert(f.player->vibrateThread_==nullptr);assert(!f.Armed());
        auto old=f.Session();assert(old->end==AudioHapticSessionEnd::START_FAILED);
        assert(f.player->Start()==0);auto b=backends.back();assert(a!=b);a->First(999);assert(f.Latency()==0);
        b->First(3);assert(f.Latency()==3);
    }
    // Nonloop EOS retires, user callback is reentrant, and restart uses a real new backend.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd());assert(f.player->Prepare()==0);assert(f.player->Start()==0);
        auto a=backends.back();auto old=f.Session();
        f.observer->onEos=[p=f.player]{assert(p->Start()==0);};
        a->Eos();assert(f.observer->Wait(f.observer->eos,1));
        auto b=backends.back();assert(a!=b);auto current=f.Session();assert(old->end==AudioHapticSessionEnd::REPLACED);
        // Exercise the real delayed worker body with A's factory-originated identity after B starts.
        f.player->HandlePlaybackEndOfStream(old,false);assert(f.Session()==current);assert(f.player->playerState_==AudioHapticPlayerState::STATE_RUNNING);
    }
    // Loop EOS must retain the live session and retain the backend; old loop worker cannot mutate a restarted B.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),false,true);assert(f.player->SetLoop(true)==0);
        assert(f.player->Prepare()==0);assert(f.player->Start()==0);auto a=backends.back();auto old=f.Session();
        a->Eos(true);assert(f.observer->Wait(f.observer->eos,1));assert(old->end==AudioHapticSessionEnd::LIVE);
        assert(f.player->Start()==0&&backends.back()==a);assert(f.player->Stop()==0);assert(f.player->Start()==0);
        auto current=f.Session();f.player->HandlePlaybackEndOfStream(old,true);assert(f.Session()==current);assert(current->end==AudioHapticSessionEnd::LIVE);
    }
    // Interrupt worker carries A's actual identity and is rejected after explicit retirement/retry/release.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd());assert(f.player->Prepare()==0);assert(f.player->Start()==0);
        auto a=backends.back();auto old=f.Session();a->Interrupt();assert(f.observer->Wait(f.observer->interrupts,1));
        assert(f.player->Start()==0);auto current=f.Session();AudioStandard::InterruptEvent event{};
        f.player->HandlePlaybackInterrupt(old,event);assert(f.Session()==current);assert(f.player->playerState_==AudioHapticPlayerState::STATE_RUNNING);
        assert(f.player->Release()==0);a->First(222);a->Eos();a->Interrupt();a->callback->OnError(MSERR_UNSUPPORT_FILE,"late");
        assert(f.player->Start()==MSERR_INVALID_OPERATION);assert(f.player->Stop()==MSERR_INVALID_OPERATION);
    }
    // Preparation errors are real and retained even while no vibration waiter is armed; reentrant user can retry.
    {
        OwnedSource source(directory);Plan bad;bad.errorDuringPrepare=true;plans.push_back(bad);
        PlayerFixture f(source.FromFd());
        auto badIndex=backends.size();
        f.observer->onError=[p=f.player]{assert(p->Prepare()==0);};
        assert(f.player->Prepare()==MSERR_UNSUPPORT_FILE);assert(f.observer->Wait(f.observer->errors,1));
        auto a=backends.at(badIndex);assert(backends.back()!=a);assert(f.player->Start()==0);
        a->callback->OnError(MSERR_UNSUPPORT_FILE,"late after retry");assert(f.observer->errors==1);
    }
    for(int failure:{0,1,2,3}){
        OwnedSource source(directory);Plan bad;
        if(failure==0)bad.registerResult=-81;
        if(failure==1)bad.sourceResult=-82;
        if(failure==2)bad.parameterResult=-83;
        if(failure==3)bad.prepareResult=-84;
        plans.push_back(bad);PlayerFixture f(source.FromFd());
        const int expected[]={-81,MSERR_OPEN_FILE_FAILED,-83,-84};assert(f.player->Prepare()==expected[failure]);
        assert(f.player->Prepare()==0);assert(f.player->Start()==0);
    }
    // A successful old prepare must not satisfy a later backend whose PrepareAsync never completes.
    {
        OwnedSource source(directory);PlayerFixture f(source.FromFd());assert(f.player->Prepare()==0);
        Plan pending;pending.prepareCallback=false;plans.push_back(pending);
        assert(f.player->Prepare()==MSERR_OPEN_FILE_FAILED);assert(f.player->Prepare()==0);
    }
    // Release/recreate uses another real endpoint; no old callback can arm its waiter.
    {
        OwnedSource source(directory);PlayerFixture first(source.FromFd(),false,true);
        assert(first.player->Prepare()==0);assert(first.player->Start()==0);auto a=backends.back();
        assert(first.player->Release()==0);
        PlayerFixture second(source.FromFd(),false,true);assert(second.player->Prepare()==0);assert(second.player->Start()==0);
        a->First(234);a->Eos();a->Interrupt();assert(second.Latency()==0&&!second.Armed());
    }
    // Failed replacement retains only its pinned FD; destructor must close that FD even with avPlayer_ null.
    {
        OwnedSource source(directory);
        auto normal=std::make_shared<AudioHapticSoundNormalImpl>(source.FromFd(),false,AudioStandard::STREAM_USAGE_MEDIA);
        assert(normal->PrepareSound()==0);int pinned=normal->fileDes_;assert(pinned>=0);
        source.DropCaller();assert(normal->StopSound()==0);factoryReturnsNull=true;
        assert(normal->StartSound()==MSERR_INVALID_VAL);assert(normal->avPlayer_==nullptr);
        assert(fcntl(pinned,F_GETFD)>=0);normal.reset();assert(fcntl(pinned,F_GETFD)==-1);
    }
    for(bool muteAudio:{false,true})for(bool muteHaptic:{false,true}){
        OwnedSource source(directory);PlayerFixture f(source.FromFd(),muteAudio,muteHaptic);
        assert(f.player->Prepare()==0);assert(backends.back()->volume==(muteAudio?0.0f:1.0f));
        assert(f.player->Start()==0);assert(f.player->Stop()==0);assert(f.player->Start()==0);assert(f.player->Stop()==0);
    }
    for(const auto& backend:backends){assert(backend->registers==1);assert(backend->resets==0);}
    std::cout<<"actual full component/header host boundary checks passed; no guest/PCM/HDI claim\n";
}

#else
int main(int argc,char **argv){
    assert(argc==2);
    std::string path=std::string(argv[1])+"/baseline-source-XXXXXX";
    std::vector<char> value(path.begin(),path.end());value.push_back(0);
    int fd=mkstemp(value.data());assert(fd>=0);assert(write(fd,"0123456789",10)==10);
    {
        AudioSource source;source.fd=fd;source.offset=2;source.length=4;
        auto normal=std::make_shared<AudioHapticSoundNormalImpl>(source,false,AudioStandard::STREAM_USAGE_MEDIA);
        assert(normal->PrepareSound()==MSERR_INVALID_OPERATION);
        assert(backends.size()==1&&backends.back()->resets==1&&backends.back()->prepares==0);
    }
    close(fd);unlink(value.data());
    std::cout<<"actual B4 full CPP fresh-IDLE Reset rejection counterexample reproduced\n";
}
#endif
