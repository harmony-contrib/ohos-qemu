#include "location_vendor_interface.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
namespace V=OHOS::HDI::Location;
using Bridge=V::LocationVendorInterface;
using namespace std::chrono_literals;
#define CHECK(x) do {if(!(x))throw std::runtime_error(#x);}while(0)
std::string scenario;
std::mutex mutex;
std::condition_variable cv;
bool entered=false,released=false;
std::atomic<bool> callbackDone{false};
std::atomic<int> count{0};
std::atomic<int> generation{1};
std::atomic<uint64_t> latestBoot{0};
bool reloadRequested=false;
int Unloads(){std::ifstream file(std::getenv("GNSS_TEST_UNLOADED"));std::string line;int total=0;while(std::getline(file,line))++total;return total;}
void Location(V::GnssLocation* value){
    CHECK(value&&value->timeSinceBoot>0&&value->timeForFix>0);
    int phase=generation.load();
    CHECK(value->latitude==20.125+(phase-1)&&value->longitude==-70.375-(phase-1));
    latestBoot=value->timeSinceBoot;
    ++count;
    if(scenario=="callback_cleanup"&&phase==1){
        Bridge::DestroyInstance();
        if(reloadRequested)CHECK(!Bridge::GetInstance()->GetGnssVendorInterface());
        // If cleanup unmaps the provider before this callback returns, its destructor marker appears too early.
        std::this_thread::sleep_for(80ms);CHECK(!std::ifstream(std::getenv("GNSS_TEST_UNLOADED")).good());
    }else if(scenario=="external_cleanup"){
        std::unique_lock<std::mutex> lock(mutex);entered=true;cv.notify_all();cv.wait(lock,[]{return released;});
    }
    callbackDone=true;cv.notify_all();
}
const V::GnssVendorInterface* Enable(){
    auto* table=Bridge::GetInstance()->GetGnssVendorInterface();CHECK(table);
    V::GnssCallbackStruct cb{};cb.size=sizeof(cb);cb.gnssCallback.size=sizeof(cb.gnssCallback);cb.gnssCallback.locationUpdate=Location;
    CHECK(table->enableGnss(&cb)==0);CHECK(!table->getCachedLocationsSize&&!table->flushCachedGnssLocations);
    CHECK(table->startGnss(1)==0);return table;
}
int main(int argc,char**argv){
 try{
    CHECK(argc==2||(argc==3&&std::string(argv[2])=="reload"));
    scenario=argv[1];reloadRequested=argc==3;
    if(scenario=="missing_symbol"||scenario=="bad_device"||scenario=="bad_table"){
        auto* table=Bridge::GetInstance()->GetGnssVendorInterface();CHECK(!table);
        CHECK(std::ifstream(std::getenv("GNSS_TEST_UNLOADED")).good());Bridge::DestroyInstance();return 0;
    }
    auto* table=Enable();
    if(scenario=="repeated_cleanup"){
        std::thread a(Bridge::DestroyInstance),b(Bridge::DestroyInstance),c(Bridge::DestroyInstance);
        a.join();b.join();c.join();Bridge::DestroyInstance();
        CHECK(Unloads()==1);return 0;
    }
    std::cout<<"READY\n"<<std::flush;
    if(scenario=="external_cleanup"){
        {std::unique_lock<std::mutex> lock(mutex);CHECK(cv.wait_for(lock,2s,[]{return entered;}));}
        std::atomic<bool> cleaned{false};std::thread cleanup([&]{Bridge::DestroyInstance();cleaned=true;});
        std::this_thread::sleep_for(40ms);CHECK(!cleaned&&!std::ifstream(std::getenv("GNSS_TEST_UNLOADED")).good());
        {std::lock_guard<std::mutex> lock(mutex);released=true;cv.notify_all();}
        cleanup.join();
    }else{
        for(int i=0;i<500&&!callbackDone;++i)std::this_thread::sleep_for(5ms);
        CHECK(callbackDone);Bridge::DestroyInstance();
    }
    CHECK(callbackDone&&count==1&&std::ifstream(std::getenv("GNSS_TEST_UNLOADED")).good());
    CHECK(table->startGnss(1)!=0);Bridge::DestroyInstance();
    if(scenario=="callback_cleanup"&&reloadRequested){
        uint64_t previousBoot=latestBoot;
        CHECK(Unloads()==1);
        callbackDone=false;generation=2;
        Enable();
        std::this_thread::sleep_for(30ms);CHECK(count==1); // No old callback or source-generated fix in the new generation.
        std::cout<<"READY2\n"<<std::flush;
        for(int i=0;i<500&&!callbackDone;++i)std::this_thread::sleep_for(5ms);
        CHECK(callbackDone&&count==2&&latestBoot>previousBoot);
        Bridge::DestroyInstance();Bridge::DestroyInstance();
        CHECK(Unloads()==2);
        std::cout<<"same-process reload: two actual unloads and isolated callback generations pass\n";
    }
    std::cout<<scenario<<": pass\n";return 0;
 }catch(const std::exception& e){std::cerr<<scenario<<": "<<e.what()<<'\n';return 1;}
}
