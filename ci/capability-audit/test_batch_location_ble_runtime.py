#!/usr/bin/env python3
"""Execute patched BLE service/backend functions with an explicit scanner boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import function, runtime_sources

PREAMBLE = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <utility>
#include <vector>
template<class T>using sptr=std::shared_ptr<T>;
template<class T,class U>sptr<T> iface_cast(sptr<U> object){return std::dynamic_pointer_cast<T>(object);}
using LocationErrCode=int;using ErrCode=int;
constexpr int ERRCODE_SUCCESS=0,ERRCODE_SERVICE_UNAVAILABLE=3301000,ERRCODE_SCAN_FAIL=3301800,ERRCODE_INVALID_PARAM=401,ERRCODE_NOT_SUPPORTED=801,LOCATION_ERRCODE_PERMISSION_DENIED=3300201,MAX_CALLBACKS_MAP_NUM=1000;
const std::string TYPE_BLE="ble";
#define LBSLOGE(...) ((void)0)
#define LBSLOGI(...) ((void)0)
#define LBSLOGD(...) ((void)0)
#define LBSLOGW(...) ((void)0)
struct BluetoothScanResult{std::string id;int64_t rssi=-30;std::string GetDeviceId()const{return id;}int64_t GetRssi()const{return rssi;}};
struct IRemoteObject:std::enable_shared_from_this<IRemoteObject>{
 struct DeathRecipient{virtual ~DeathRecipient()=default;};virtual ~IRemoteObject()=default;
 bool deathAllowed=true;std::vector<sptr<DeathRecipient>> deaths;
 bool AddDeathRecipient(sptr<DeathRecipient> death){if(!deathAllowed)return false;deaths.push_back(death);return true;}
 bool RemoveDeathRecipient(sptr<DeathRecipient> death){auto it=std::find(deaths.begin(),deaths.end(),death);if(it==deaths.end())return false;deaths.erase(it);return true;}
};
struct IBluetoothScanResultCallback:IRemoteObject{
 virtual void OnBluetoothScanResultChange(const std::unique_ptr<BluetoothScanResult>&)=0;
 sptr<IRemoteObject> AsObject(){return shared_from_this();}
};
struct TestCallback:IBluetoothScanResultCallback{
 int received=0;std::vector<BluetoothScanResult> payloads;
 void OnBluetoothScanResultChange(const std::unique_ptr<BluetoothScanResult>& result)override{++received;payloads.push_back(*result);}
};
struct BluetoothScanCallbackDeathRecipient:IRemoteObject::DeathRecipient{};
struct AppIdentity{int uid=100001,pid=1;uint32_t token=1,first=0;int GetUid()const{return uid;}int GetPid()const{return pid;}uint32_t GetTokenId()const{return token;}uint32_t GetFirstTokenId()const{return first;}std::string GetBundleName()const{return "app";}};
int currentUser=100;bool requestAvailable=true,startHook=true,reportHook=true;
std::map<uint32_t,bool> approximate,precise;
struct CommonUtils{static bool IsAppBelongCurrentAccount(AppIdentity& identity){return identity.uid/1000==currentUser;}};
struct PermissionManager{
 static bool allowed(std::map<uint32_t,bool>& grants,uint32_t token,uint32_t first){return grants[token]&&(!first||grants[first]);}
 static bool CheckApproximatelyPermission(uint32_t token,uint32_t first){return allowed(approximate,token,first);}
 static bool CheckLocationPermission(uint32_t token,uint32_t first){return allowed(precise,token,first);}
};
struct HookUtils{static bool ExecuteHookWhenStartScanBluetoothDevice(const std::string&,const std::string&){return startHook;}static bool ExecuteHookWhenReportBluetoothScanResult(const std::string&,const std::string&){return reportHook;}};
struct ProxyFreezeManager{std::set<int> frozen;static ProxyFreezeManager* GetInstance(){static ProxyFreezeManager v;return &v;}bool IsProxyPid(int pid){return frozen.count(pid);}};
namespace Bluetooth{
 enum class SCAN_MODE{SCAN_MODE_LOW_POWER};struct BleScanSettings{void SetScanMode(SCAN_MODE){}};struct BleScanFilter{};
 struct BleCentralManager{int startResult=0,stopResult=0,starts=0,stops=0;int StartScan(const BleScanSettings&,const std::vector<BleScanFilter>&){++starts;return startResult;}int StopScan(){++stops;return stopResult;}};
}
'''

CLASS = r'''
class LocatorRequiredDataManager{
public:
 std::mutex bluetoothcallbacksMapMutex_,bluetoothScanOperationMutex_,bluetoothScanStatusMutex_;
 std::map<sptr<IRemoteObject>,std::pair<AppIdentity,sptr<IRemoteObject::DeathRecipient>>> bluetoothcallbacksMap_;
 std::map<sptr<IRemoteObject>,BluetoothSearchFilter> bluetoothSearchFilters_;
 std::shared_ptr<Bluetooth::BleCentralManager> bleCentralManager_=std::make_shared<Bluetooth::BleCentralManager>();
 bool bluetoothScanStatus_=false;std::vector<bool> events;
 static LocatorRequiredDataManager* instance;static LocatorRequiredDataManager* GetInstance(){return instance;}
 LocationErrCode StartBluetoothSearch(const sptr<IBluetoothScanResultCallback>&,const AppIdentity&,const std::vector<std::string>&,bool,int32_t);
 LocationErrCode StopBluetoothSearch(const sptr<IBluetoothScanResultCallback>&,const AppIdentity&);
 void StartScanBluetoothDevice(sptr<IBluetoothScanResultCallback>,AppIdentity);
 void StopScanBluetoothDevice(sptr<IRemoteObject>);
 LocationErrCode StartBluetoothScan();LocationErrCode StoptBluetoothScan();
 bool HasActiveBluetoothRequests();bool GetBluetoothScanStatus();void SetBluetoothScanStatus(bool);
 void RemoveBluetoothScanCallback(sptr<IRemoteObject>);void RemoveBluetoothScanCallbackDeathRecipientByCallback(sptr<IRemoteObject>);
 void HandleRefreshBluetoothRequest();void ReportBluetoothScanResult(const std::unique_ptr<BluetoothScanResult>&);
 void SendStartBluetoothScanEvent(){events.push_back(true);}void SendStopBluetoothScanEvent(){events.push_back(false);}
 void Drain(){auto queued=std::move(events);events.clear();for(bool start:queued)if(start)StartBluetoothScan();else StoptBluetoothScan();}
};
LocatorRequiredDataManager* LocatorRequiredDataManager::instance=nullptr;
enum class LocatorInterfaceCode{START_BLUETOOTH_SEARCH=66};
struct LocatorAbility{
 AppIdentity caller;
 void GetAppIdentityInfo(AppIdentity& value){value=caller;}
 bool CheckRequestAvailable(LocatorInterfaceCode,AppIdentity&){return requestAvailable;}
 ErrCode StartBluetoothSearch(const std::vector<std::string>&,bool,int32_t,const sptr<IBluetoothScanResultCallback>&);
 ErrCode StopBluetoothSearch(const sptr<IBluetoothScanResultCallback>&);
};
'''

MAIN = r'''
int main(){
 LocatorRequiredDataManager manager;LocatorRequiredDataManager::instance=&manager;LocatorAbility service;
 approximate[1]=true;approximate[2]=true;precise[1]=false;precise[2]=false;
 auto a=std::make_shared<TestCallback>(),b=std::make_shared<TestCallback>();
#ifndef BLUETOOTH_ENABLE
 assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_NOT_SUPPORTED);
 assert(service.StopBluetoothSearch(a)==ERRCODE_NOT_SUPPORTED);
 std::cout<<"BLE absent feature: real API reports 801\n";return 0;
#else
 auto emit=[&](std::string id,int64_t rssi){auto value=std::make_unique<BluetoothScanResult>();value->id=id;value->rssi=rssi;manager.ReportBluetoothScanResult(value);};
 auto radio=manager.bleCentralManager_;
 assert(service.StartBluetoothSearch({"AA:BB"},true,-50,a)==0);assert(radio->starts==1&&manager.GetBluetoothScanStatus());
 service.caller.token=2;service.caller.pid=2;service.caller.uid=100002;
 assert(service.StartBluetoothSearch({"CC:DD"},false,0,b)==0);assert(radio->starts==1);
 emit("aa:bb",-49);assert(a->received==1&&b->received==0&&a->payloads.back().rssi==-49);
 emit("AA:BB",-50);emit("AA:BB",-51);emit("OTHER",0);assert(a->received==1);
 emit("cc:dd",-120);assert(b->received==1);
 assert(service.StopBluetoothSearch(a)==LOCATION_ERRCODE_PERMISSION_DENIED);assert(manager.bluetoothcallbacksMap_.size()==2);
 approximate[1]=false;emit("AA:BB",-20);assert(a->received==1);
 service.caller.token=1;service.caller.pid=1;service.caller.uid=100001;
 assert(service.StopBluetoothSearch(a)==0);assert(radio->stops==0); // revocation never prevents release
 ProxyFreezeManager::GetInstance()->frozen.insert(2);emit("CC:DD",-1);assert(b->received==1);ProxyFreezeManager::GetInstance()->frozen.clear();
 currentUser=101;emit("CC:DD",-1);assert(b->received==1);currentUser=100;
 service.caller.token=2;service.caller.pid=2;service.caller.uid=100002;
 assert(service.StopBluetoothSearch(b)==0&&radio->stops==1&&!manager.GetBluetoothScanStatus());assert(a->deaths.empty()&&b->deaths.empty());
 // A queued legacy stop sees the new public subscriber before touching the radio.
 approximate[1]=true;precise[1]=true;AppIdentity legacy;
 manager.StartScanBluetoothDevice(a,legacy);manager.Drain();assert(radio->starts==2);
 manager.StopScanBluetoothDevice(a->AsObject());assert(!manager.events.empty());
 service.caller.token=1;service.caller.pid=1;service.caller.uid=100001;
 assert(service.StartBluetoothSearch({"AA"},false,0,a)==0);int stops=radio->stops;manager.Drain();assert(radio->stops==stops&&manager.GetBluetoothScanStatus());
 assert(service.StopBluetoothSearch(a)==0);assert(!manager.GetBluetoothScanStatus());
 // A stale start has no live subscriber and must not acquire hardware.
 int starts=radio->starts;manager.SendStartBluetoothScanEvent();manager.Drain();assert(radio->starts==starts&&!manager.GetBluetoothScanStatus());
 radio->startResult=-1;assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_SCAN_FAIL);assert(!manager.GetBluetoothScanStatus()&&manager.bluetoothcallbacksMap_.empty()&&a->deaths.empty());radio->startResult=0;
 a->deathAllowed=false;assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_SERVICE_UNAVAILABLE);assert(manager.bluetoothcallbacksMap_.empty());a->deathAllowed=true;
 startHook=false;assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_SCAN_FAIL);startHook=true;
 approximate[1]=false;assert(service.StartBluetoothSearch({"AA"},false,0,a)==LOCATION_ERRCODE_PERMISSION_DENIED);approximate[1]=true;
 service.caller.first=3;approximate[3]=false;assert(service.StartBluetoothSearch({"AA"},false,0,a)==LOCATION_ERRCODE_PERMISSION_DENIED);approximate[3]=true;
 assert(service.StartBluetoothSearch({"AA"},true,std::numeric_limits<int32_t>::min(),a)==0);
 emit("AA",std::numeric_limits<int32_t>::min());assert(a->received==1);emit("AA",-2147483647LL);assert(a->received==2);
 radio->stopResult=-1;assert(service.StopBluetoothSearch(a)==ERRCODE_SERVICE_UNAVAILABLE);assert(manager.GetBluetoothScanStatus());radio->stopResult=0;
 assert(service.StopBluetoothSearch(a)==0&&!manager.GetBluetoothScanStatus()); // retries do reach the outstanding hardware operation
 service.caller.first=0;
 assert(service.StartBluetoothSearch({},false,0,a)==0);emit("AA",0);assert(a->received==2);assert(service.StopBluetoothSearch(a)==0); // empty filter is a real scan with no matches
 auto saved=manager.bleCentralManager_;manager.bleCentralManager_.reset();assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_SCAN_FAIL);manager.bleCentralManager_=saved;
 for(int i=0;i<MAX_CALLBACKS_MAP_NUM;++i){auto cb=std::make_shared<TestCallback>();manager.bluetoothcallbacksMap_.emplace(cb,std::make_pair(legacy,sptr<IRemoteObject::DeathRecipient>{}));}
 assert(service.StartBluetoothSearch({"AA"},false,0,a)==ERRCODE_SCAN_FAIL);assert(manager.bluetoothcallbacksMap_.size()==MAX_CALLBACKS_MAP_NUM);manager.bluetoothcallbacksMap_.clear();
 assert(service.StartBluetoothSearch({"AA"},false,0,a)==0);manager.ReportBluetoothScanResult(nullptr);assert(service.StopBluetoothSearch(a)==0);
 std::cout<<"BLE real functions: exact payload/filter/RSSI, permission/delegation/user/freeze, startup/stop failures, owner and stale scan-task boundaries passed\n";
#endif
}
'''


class BluetoothRuntimeTests(unittest.TestCase):
    def test_execute_backend_and_service(self):
        files = runtime_sources()
        manager = files['services/location_locator/locator/source/locator_required_data_manager.cpp']
        service = files['services/location_locator/locator/source/locator_ability.cpp']
        header = files['services/location_locator/locator/include/locator_required_data_manager.h']
        filter_class = function(header, 'struct BluetoothSearchFilter {').rstrip() + ';\n'
        actual = function(manager, 'static std::string NormalizeBluetoothDeviceId(')
        actual += function(manager, 'bool BluetoothSearchFilter::Matches(')
        for name, result in [
            ('StartBluetoothSearch', 'LocationErrCode'), ('StopBluetoothSearch', 'LocationErrCode'),
            ('StartScanBluetoothDevice', 'void'), ('StopScanBluetoothDevice', 'void'),
            ('RemoveBluetoothScanCallback', 'void'), ('RemoveBluetoothScanCallbackDeathRecipientByCallback', 'void'),
            ('ReportBluetoothScanResult', 'void'), ('StartBluetoothScan', 'LocationErrCode'),
            ('StoptBluetoothScan', 'LocationErrCode'), ('HasActiveBluetoothRequests', 'bool'),
            ('HandleRefreshBluetoothRequest', 'void'), ('GetBluetoothScanStatus', 'bool'), ('SetBluetoothScanStatus', 'void'),
        ]:
            actual += function(manager, f'{result} LocatorRequiredDataManager::{name}(')
        for name in ['StartBluetoothSearch', 'StopBluetoothSearch']:
            actual += function(service, f'ErrCode LocatorAbility::{name}(')
        for feature in [True, False]:
            with self.subTest(bluetooth=feature), tempfile.TemporaryDirectory(prefix='batch-location-ble-') as directory:
                cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
                cpp.write_text(('#define BLUETOOTH_ENABLE\n' if feature else '') + PREAMBLE + filter_class + CLASS + actual + MAIN)
                subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined', str(cpp), '-o', str(exe)], check=True)
                subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
