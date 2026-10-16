// Uses the exact complete fixed vendor ABI header and shipped provider/transport.
// Explicit host-only Provider config authorizes the host UID; exported product ABI pins UID0.
#include "qemu_gnss_vendor.cpp"
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <random>
#include <stdexcept>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
using namespace OHOS::QemuGnss;
namespace V = OHOS::HDI::Location;
using namespace std::chrono_literals;
#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (0)
struct Sink {
    std::mutex mutex;
    std::condition_variable ready;
    std::vector<V::GnssLocation> values;
    std::function<void()> call;
    void Add(V::GnssLocation* location) {
        { std::lock_guard<std::mutex> lock(mutex); values.push_back(*location); }
        if (call) call();
        ready.notify_all();
    }
    size_t Size() { std::lock_guard<std::mutex> lock(mutex); return values.size(); }
    void Await(size_t size) { std::unique_lock<std::mutex> lock(mutex); CHECK(ready.wait_for(lock,2s,[&]{return values.size()>=size;})); }
};
Sink* current;
void Receive(V::GnssLocation* value) { current->Add(value); }
void Unexpected(V::GnssLocation*) { throw std::runtime_error("callback caller storage was retained"); }
V::GnssCallbackStruct Callbacks()
{
    V::GnssCallbackStruct callbacks{};
    callbacks.size=sizeof(callbacks); callbacks.gnssCallback.size=sizeof(callbacks.gnssCallback);
    callbacks.gnssCallback.locationUpdate=Receive; return callbacks;
}
int Connect(const std::string& path, Nonce& nonce, bool authorized=true)
{
    int fd=socket(AF_UNIX,SOCK_STREAM,0);CHECK(fd>=0);
    timeval timeout{2,0};CHECK(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))==0);
#ifdef SO_NOSIGPIPE
    int flag=1;CHECK(setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&flag,sizeof(flag))==0);
#endif
    sockaddr_un address{};address.sun_family=AF_UNIX;CHECK(path.size()<sizeof(address.sun_path));
    std::memcpy(address.sun_path,path.c_str(),path.size()+1);
    CHECK(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0);
    std::array<uint8_t,HELLO_SIZE> hello{};size_t done=0;
    while(done<hello.size()) {
        auto n=recv(fd,hello.data()+done,hello.size()-done,0);
        if(!authorized){CHECK(n==0||(n<0&&errno==ECONNRESET));return fd;}
        CHECK(n>0);done+=static_cast<size_t>(n);
    }
    CHECK(std::memcmp(hello.data(),"QGN1",4)==0&&ReadLe(hello.data()+4,4)==1);
    CHECK(ReadLe(hello.data()+24,4)==FRAME_SIZE&&ReadLe(hello.data()+28,4)==0);
    std::memcpy(nonce.data(),hello.data()+8,nonce.size());return fd;
}
template<class T> void Number(uint8_t* bytes,T value)
{
    uint64_t bits=0;std::memcpy(&bits,&value,sizeof(value));WriteLe(bytes,bits,sizeof(value));
}
Frame Encode(const Nonce& nonce,uint64_t sequence=1)
{
    Frame frame{};std::memcpy(frame.data(),"QGF1",4);WriteLe(frame.data()+4,1,4);
    std::memcpy(frame.data()+8,nonce.data(),nonce.size());WriteLe(frame.data()+24,sequence,8);
    WriteLe(frame.data()+32,static_cast<uint64_t>(UtcMs())+sequence,8);
    Number(frame.data()+40,38.125);Number(frame.data()+48,-111.25);Number(frame.data()+56,123.75);
    Number(frame.data()+64,2.5F);Number(frame.data()+68,3.5F);Number(frame.data()+72,4.5F);Number(frame.data()+76,70.0F);
    return frame;
}
bool Write(int fd,const uint8_t* data,size_t size)
{
    while(size) {
#ifdef MSG_NOSIGNAL
        auto n=send(fd,data,size,MSG_NOSIGNAL);
#else
        auto n=send(fd,data,size,0);
#endif
        if(n<=0)return false;data+=n;size-=static_cast<size_t>(n);
    }return true;
}
void Closed(int fd){uint8_t byte;auto n=recv(fd,&byte,1,0);CHECK(n==0||(n<0&&errno==ECONNRESET));}
int main(int argc,char** argv)
{
    try {
        CHECK(argc==3);std::string scenario=argv[1],path=argv[2];Sink sink;current=&sink;
        if(scenario=="unauthorized") {
            GnssInput input({path,static_cast<uid_t>(geteuid()+1)});CHECK(input.Start());Nonce nonce;
            int fd=Connect(path,nonce,false);close(fd);input.Stop();return 0;
        }
        if(scenario=="file_protection"||scenario=="symlink_protection") {
            std::ofstream(path+".external")<<"keep";
            if(scenario=="file_protection")std::ofstream(path)<<"keep";
            else CHECK(symlink((path+".external").c_str(),path.c_str())==0);
            GnssInput protectedInput({path,geteuid()});CHECK(!protectedInput.Start());
            std::string text;std::ifstream stream(path);stream>>text;CHECK(text=="keep");
            unlink(path.c_str());unlink((path+".external").c_str());return 0;
        }
        auto provider=std::make_unique<Provider>(InputConfig{path,geteuid()});auto callbacks=Callbacks();
        if(scenario=="abi_boundaries") {
            auto* table=GnssVendorInterface.getGnssInterface();CHECK(GnssVendorInterface.size==sizeof(V::GnssVendorDevice));
            CHECK(table&&table->size==sizeof(*table));CHECK(table->getGnssModuleIface(1)==nullptr);
            CHECK(!table->getCachedLocationsSize&&!table->flushCachedGnssLocations);
            CHECK(table->injectsGnssReferenceInfo(1,nullptr)==-ENOTSUP&&table->injectExtendedEphemeris(nullptr,0)==-ENOTSUP);
            CHECK(table->enableGnss(nullptr)==-EINVAL);CHECK(provider->Enable(nullptr)==-EINVAL);
            callbacks.gnssCallback.size=sizeof(callbacks);CHECK(provider->Enable(&callbacks)==-EINVAL);
            callbacks=Callbacks();callbacks.size=0;CHECK(provider->Enable(&callbacks)==-EINVAL);return 0;
        }
        CHECK(provider->Start(1)!=0);CHECK(provider->Enable(&callbacks)==0);
        CHECK(provider->Enable(&callbacks)==-EBUSY);callbacks.gnssCallback.locationUpdate=Unexpected;
        CHECK(provider->Start(2)==-ENOTSUP&&provider->Stop(2)==-ENOTSUP);
        if(scenario=="config") {
            V::GnssConfigParameter config{};CHECK(provider->Configure(&config)==-EINVAL);
            config.size=sizeof(config);config.startCategory=2;CHECK(provider->Configure(&config)==-ENOTSUP);
            config.startCategory=1;config.u.gnssBasicConfig.size=sizeof(config.u.gnssBasicConfig);
            config.u.gnssBasicConfig.gnssMode=2;CHECK(provider->Configure(&config)==-ENOTSUP);
            config.u.gnssBasicConfig.gnssMode=1;config.u.gnssBasicConfig.minInterval=1000;
            CHECK(provider->Configure(&config)==0);provider->Disable();return 0;
        }
        CHECK(provider->Start(1)==0);std::this_thread::sleep_for(10ms);CHECK(sink.Size()==0);
        if(scenario=="no_source") {provider->Disable();return 0;}
        if(scenario=="callback_stop")sink.call=[&]{CHECK(provider->Stop(1)==0);};
        if(scenario=="callback_cleanup")sink.call=[&]{provider.reset();};
        Nonce nonce;int fd=Connect(path,nonce);auto frame=Encode(nonce);
        if(scenario=="stop_replay"||scenario=="reconnect_replay") {
            auto old=nonce;
            if(scenario=="stop_replay"){CHECK(provider->Stop(1)==0);CHECK(provider->Start(1)==0);}
            close(fd);fd=Connect(path,nonce);CHECK(nonce!=old);frame=Encode(old);CHECK(Write(fd,frame.data(),frame.size()));
            Closed(fd);close(fd);CHECK(sink.Size()==0);fd=Connect(path,nonce);frame=Encode(nonce);
        }
        if(scenario=="backpressure_stop") {
            std::mutex blocked;std::condition_variable unblock;bool entered=false,release=false;
            sink.call=[&]{std::unique_lock<std::mutex> lock(blocked);entered=true;unblock.notify_all();unblock.wait(lock,[&]{return release;});};
            CHECK(Write(fd,frame.data(),frame.size()));
            {std::unique_lock<std::mutex> lock(blocked);CHECK(unblock.wait_for(lock,2s,[&]{return entered;}));}
            int flags=fcntl(fd,F_GETFL);CHECK(flags>=0&&fcntl(fd,F_SETFL,flags|O_NONBLOCK)==0);
            frame=Encode(nonce,2);size_t queued=0;bool full=false;
            while(queued<1024*1024){
#ifdef MSG_NOSIGNAL
                auto n=send(fd,frame.data(),frame.size(),MSG_NOSIGNAL);
#else
                auto n=send(fd,frame.data(),frame.size(),0);
#endif
                if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){full=true;break;}
                CHECK(n>0);queued+=static_cast<size_t>(n);
            }
            CHECK(full);std::atomic<bool> stopped{false};
            std::thread stop([&]{CHECK(provider->Stop(1)==0);stopped=true;});
            std::this_thread::sleep_for(30ms);CHECK(!stopped);
            {std::lock_guard<std::mutex> lock(blocked);release=true;unblock.notify_all();}
            stop.join();CHECK(stopped&&sink.Size()==1);sink.call={};close(fd);
            CHECK(provider->Start(1)==0);fd=Connect(path,nonce);frame=Encode(nonce);
            CHECK(Write(fd,frame.data(),frame.size()));sink.Await(2);provider->Disable();CHECK(sink.Size()==2);close(fd);return 0;
        }
        bool success=scenario=="valid"||scenario=="optional"||scenario=="fragmented"||scenario=="callback_stop"||
            scenario=="callback_cleanup"||scenario=="stop_replay"||scenario=="reconnect_replay";
        if(success) {
            std::mt19937 random(std::random_device{}());std::uniform_real_distribution<double> latitude(-89,89),longitude(-179,179);
            double lat=latitude(random),lon=longitude(random);Number(frame.data()+40,lat);Number(frame.data()+48,lon);
            if(scenario=="optional")WriteLe(frame.data()+80,4|8|16|64,4);
            if(scenario=="fragmented"){for(auto byte:frame)CHECK(Write(fd,&byte,1));}
            else CHECK(Write(fd,frame.data(),frame.size()));sink.Await(1);
            {std::lock_guard<std::mutex> lock(sink.mutex);auto value=sink.values[0];CHECK(value.latitude==lat&&value.longitude==lon);
             CHECK(value.timeForFix==static_cast<int64_t>(ReadLe(frame.data()+32,8))&&value.timeSinceBoot>0);
             CHECK(value.size==sizeof(value)&&value.fieldValidity==(1|2|32|512|1024|(scenario=="optional"?(4|8|16|64):0)));}
            if(scenario=="callback_stop"||scenario=="callback_cleanup")Closed(fd);
            if(scenario=="callback_cleanup"){
                for(int i=0;i<400&&access(path.c_str(),F_OK)==0;++i)std::this_thread::sleep_for(5ms);
                CHECK(access(path.c_str(),F_OK)!=0);
            }
        } else {
            if(scenario=="wrong_magic")frame[0]^=1;
            else if(scenario=="reserved")WriteLe(frame.data()+84,1,4);
            else if(scenario=="altitude")Number(frame.data()+56,100001.0);
            else if(scenario=="infinity")Number(frame.data()+64,std::numeric_limits<float>::infinity());
            else if(scenario=="vertical_accuracy"){WriteLe(frame.data()+80,64,4);Number(frame.data()+68,0.0F);}
            else if(scenario=="wrong_nonce")frame[8]^=1;
            else if(scenario=="wrong_version")frame[4]=2;
            else if(scenario=="zero_sequence")WriteLe(frame.data()+24,0,8);
            else if(scenario=="stale_utc")WriteLe(frame.data()+32,static_cast<uint64_t>(UtcMs()-11000),8);
            else if(scenario=="future_utc")WriteLe(frame.data()+32,static_cast<uint64_t>(UtcMs()+2000),8);
            else if(scenario=="latitude")Number(frame.data()+40,90.01);
            else if(scenario=="longitude")Number(frame.data()+48,-180.01);
            else if(scenario=="nan")Number(frame.data()+40,std::numeric_limits<double>::quiet_NaN());
            else if(scenario=="zero_accuracy")Number(frame.data()+64,0.0F);
            else if(scenario=="speed")Number(frame.data()+72,-1.0F);
            else if(scenario=="bearing")Number(frame.data()+76,360.0F);
            else if(scenario=="unknown_fields")WriteLe(frame.data()+80,0xffffffff,4);
            else if(scenario=="repeated_sequence"||scenario=="repeated_utc") {
                CHECK(Write(fd,frame.data(),frame.size()));sink.Await(1);
                if(scenario=="repeated_utc")WriteLe(frame.data()+24,2,8);
            } else if(scenario!="partial")throw std::runtime_error("unknown case");
            if(scenario=="partial"){CHECK(Write(fd,frame.data(),20));shutdown(fd,SHUT_WR);}
            else CHECK(Write(fd,frame.data(),frame.size()));Closed(fd);
            CHECK(sink.Size()==((scenario=="repeated_sequence"||scenario=="repeated_utc")?1U:0U));
        }
        close(fd);if(provider){CHECK(provider->Disable()==0);callbacks=Callbacks();CHECK(provider->Enable(&callbacks)==0);CHECK(provider->Start(1)==0);provider->Disable();}
        std::cout<<scenario<<": pass\n";return 0;
    }catch(const std::exception& error){std::cerr<<argv[1]<<": "<<error.what()<<'\n';return 1;}
}
