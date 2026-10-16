#!/usr/bin/env python3
"""Execute the real new icon query and original availability guard; no GNSS emulation."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import runtime_sources

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/location/location/api26_runtime'
FIXTURE = Path(__file__).parent / 'fixtures/batch_location/icon_source.json'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1] + '\n'
    raise AssertionError(signature)


def new_source():
    sources = runtime_sources()
    return '\n'.join(sources[name] for name in [
        'services/location_locator/locator/source/request_manager.cpp',
        'services/location_locator/locator/source/locator_ability.cpp',
        'frameworks/native/locator_sdk/source/locator_impl.cpp',
        'frameworks/js/napi/source/location_napi_adapter.cpp',
    ])


PREAMBLE = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <sys/types.h>
#include <vector>
namespace ffrt { using mutex=std::mutex; }
using ErrCode=int; using LocationErrCode=int;
const int ERRCODE_SUCCESS=0,ERRCODE_SERVICE_UNAVAILABLE=3301000,LOCATION_ERRCODE_SYSTEM_PERMISSION_DENIED=3300202;
const int SKIING=4,ERRCODE_PERMISSION_DENIED=201,ERRCODE_SYSTEM_PERMISSION_DENIED=202,ERRCODE_EDM_POLICY_ABANDON=203,ERRCODE_INVALID_PARAM=401,ERRCODE_NOT_SUPPORTED=801,LOCATION_ERRCODE_MIN=3300000;
const int ENABLED=1,MILLI_PER_SEC=1000,LBS_REQUEST_FAIL_DETAIL=0,ERRCODE_LOCATING_FREEZE=1,LOCATION_ERRCODE_NOT_CURRENT_USER_ID=2,LOCATION_ERRCODE_REQUEST_TIMEOUT=3,LOCATION_LOCATOR_SA_ID=2802;
const std::string GNSS_ABILITY="gps",NETWORK_ABILITY="network",FUSED_ABILITY="fused";
#define LBSLOGD(...) ((void)0)
#define LBSLOGE(...) ((void)0)
void WriteLocationInnerEvent(int,std::initializer_list<std::string>) {}
struct AppIdentity {
    int uid=100001,pid=1; uint32_t token=1,first=0;
    void SetUid(int v){uid=v;} void SetTokenId(uint32_t v){token=v;}
    int GetUid()const{return uid;} uint32_t GetTokenId()const{return token;} uint64_t GetTokenIdEx()const{return token;}
};
int currentUser=100; std::vector<int> activeUsers{100}; int64_t now=100;
std::map<uint32_t,bool> permissions,finePermissions;
bool queryProbe=false;std::mutex* requestLock=nullptr;std::mutex* permissionLock=nullptr;
void assertQueryLocksReleased(){if(queryProbe){assert(requestLock->try_lock());requestLock->unlock();assert(permissionLock->try_lock());permissionLock->unlock();}}
const std::string ACCESS_LOCATION="fine",ACCESS_APPROXIMATELY_LOCATION="approximate";
namespace Security { namespace AccessToken {
constexpr int PERMISSION_DENIED=-1,PERMISSION_GRANTED=0,ERR_PERMISSION_ALREADY_START_USING=1;
enum class ATokenTypeEnum {TOKEN_INVALID,TOKEN_HAP};
std::vector<std::tuple<uint32_t,uint32_t,std::string>> checked;
struct AccessTokenKit {
 static ATokenTypeEnum GetTokenTypeFlag(uint32_t token){return token?ATokenTypeEnum::TOKEN_HAP:ATokenTypeEnum::TOKEN_INVALID;}
 static int VerifyAccessToken(uint32_t token,const std::string& permission){assertQueryLocksReleased();return (permission==ACCESS_LOCATION?finePermissions[token]:permissions[token])?PERMISSION_GRANTED:PERMISSION_DENIED;}
 static int VerifyAccessToken(uint32_t token,uint32_t first,const std::string& permission){checked.emplace_back(token,first,permission);return VerifyAccessToken(token,permission)==PERMISSION_GRANTED&&VerifyAccessToken(first,permission)==PERMISSION_GRANTED?PERMISSION_GRANTED:PERMISSION_DENIED;}
};
}}
struct PrivacyKit {
 static std::map<std::pair<int,std::string>,int> starts,stops;
 static int StartUsingPermission(uint32_t,const std::string& permission,int pid){++starts[{pid,permission}];return 0;}
 static int StopUsingPermission(uint32_t,const std::string& permission,int pid){++stops[{pid,permission}];return 0;}
};
std::map<std::pair<int,std::string>,int> PrivacyKit::starts,PrivacyKit::stops;
std::map<int,bool> switches;
bool systemPermission=true,callerAvailable=true,saAvailable=true;
struct RequestConfig { bool needsFine=false;bool NeedsFinePermission()const{return needsFine;}int sports=0;int GetSportsType(){return sports;}int fix=0,timeout=5000;int64_t timestamp=100; int GetFixNumber(){return fix;}int GetTimeOut(){return timeout;}int64_t GetTimeStamp(){return timestamp;} };
struct Request {
    bool usingPermission=true,usingFine=false,requesting=true; int uid=100001,pid=1;uint32_t token=1,first=0;
    std::shared_ptr<RequestConfig> config=std::make_shared<RequestConfig>();
    bool GetApproximatelyPermState(){return usingPermission;}bool GetLocationPermState(){return usingFine;}void SetLocationPermState(bool state){usingFine=state;}void SetApproximatelyPermState(bool state){usingPermission=state;}int GetPermUsedType(){return 0;}bool GetIsRequesting(){return requesting;}
    std::shared_ptr<RequestConfig> GetRequestConfig(){return config;}int GetUid(){return uid;}int GetPid(){return pid;}
    uint32_t GetTokenId(){return token;}uint32_t GetFirstTokenId(){return first;}
    std::string ToString(){return "request";}std::string GetPackageName(){return "app";}std::string GetUuid(){return "uuid";}
};
struct ProxyFreezeManager {std::set<int> frozen;static ProxyFreezeManager* GetInstance(){static ProxyFreezeManager v;return &v;}bool IsProxyPid(int pid){return frozen.count(pid);}};
struct LocationAccountManager {static LocationAccountManager* GetInstance(){static LocationAccountManager v;return &v;}std::vector<int> GetActiveUserIds(){return activeUsers;}};
struct CommonUtils {
    static int GetUserIdByUid(int uid){return uid/1000;}
    static bool IsAppBelongCurrentAccount(AppIdentity identity){return GetUserIdByUid(identity.uid)==currentUser;}
    static bool IsAppBelongActiveAccounts(AppIdentity identity,std::vector<int> ids){for(int id:ids)if(GetUserIdByUid(identity.uid)==id)return true;return false;}
    static int64_t GetCurrentTime(){return now;}
    static LocationErrCode ErrCodeToLocationErrCode(ErrCode errorCode);
};
struct PermissionManager {
    static bool CheckSystemPermission(uint32_t,uint64_t){return systemPermission;}
    static bool CheckPermission(const std::string&,uint32_t,uint32_t);
    static bool CheckLocationPermission(uint32_t,uint32_t);
    static bool CheckApproximatelyPermission(uint32_t,uint32_t);
};
struct LocationDataRdbManager {static int QuerySwitchStateForUser(int user){assertQueryLocksReleased();return switches[user]?ENABLED:0;}};
enum class LocatorInterfaceCode {GET_LOCATION_ICON_STATUS=65};
class LocatorAbility {
public:
    bool IsFusionFenceLocatingInCurrentAccount(){return false;}
    std::shared_ptr<std::map<std::string,std::list<std::shared_ptr<Request>>>> requests=std::make_shared<std::map<std::string,std::list<std::shared_ptr<Request>>>>();
    std::set<uint32_t> ignored;
    static LocatorAbility* GetInstance(){static LocatorAbility v;return &v;}
    auto GetRequests(){return requests;}
    bool GetLocationSwitchIgnoredFlag(uint32_t token){return ignored.count(token);}
    void GetAppIdentityInfo(AppIdentity& identity){identity=AppIdentity{};}
    bool CheckRequestAvailable(LocatorInterfaceCode,AppIdentity&){return callerAvailable;}
    bool IsHapCaller(uint32_t){return true;}
    int UpdatePermissionUsedRecord(uint32_t,const std::string&,int,int,int){return 0;}
    ErrCode GetLocationIconStatus(int32_t&);
};
class RequestManager {
public:
    static RequestManager* GetInstance(){static RequestManager v;return &v;}
    static ffrt::mutex requestMutex_;ffrt::mutex permissionRecordMutex_,workingPidsCountMutex_;
    std::map<pid_t,int32_t> workingPidsCountMap_,fineWorkingPidsCountMap_;
    bool UpdateUsingPermission(std::shared_ptr<Request>,bool);
    bool UpdateUsingFinePermission(std::shared_ptr<Request>,bool);
    bool UpdateUsingApproximatelyPermission(std::shared_ptr<Request>,bool);
    void IncreaseWorkingPidsCount(pid_t);void DecreaseWorkingPidsCount(pid_t);
    bool IsNeedStartUsingPermission(pid_t);bool IsNeedStopUsingPermission(pid_t);
    bool IsRequestAvailable(std::shared_ptr<Request>&);
    bool IsLocatingInCurrentAccount();
    bool IsSkiingRequestActive(const std::shared_ptr<Request>&);
};
ffrt::mutex RequestManager::requestMutex_;
struct SaLoadWithStatistic {static bool InitLocationSa(int){return saAvailable;}};
class LocatorImpl {public:LocatorAbility* proxy=LocatorAbility::GetInstance();auto GetProxy(){return proxy;}LocationErrCode GetLocationIconStatus(int32_t&);};
std::shared_ptr<LocatorImpl> g_locatorClient=std::make_shared<LocatorImpl>();
struct Env {int error=0;std::vector<std::unique_ptr<int>> handles;};
using napi_env=Env*;using napi_callback_info=void*;using napi_value=int*;
int napi_create_int32(napi_env env,int32_t value,napi_value* result){env->handles.push_back(std::make_unique<int>(value));*result=env->handles.back().get();return 0;}
void HandleSyncErrCode(napi_env env,int code){env->error=code;}
#define NAPI_CALL(env,expr) do {if((expr)!=0)return nullptr;}while(false)
'''

MAIN = r'''
int main(){
    auto locator=LocatorAbility::GetInstance();auto manager=RequestManager::GetInstance();
    requestLock=&manager->requestMutex_;permissionLock=&manager->permissionRecordMutex_;
    Env env;auto query=[&](){env.error=0;queryProbe=true;auto result=GetLocationIconStatus(&env,nullptr);queryProbe=false;return result;};
    auto noIcon=[&](){auto value=query();assert(value && *value==0 && env.error==0);};
    auto activeIcon=[&](){auto value=query();assert(value && *value==1 && env.error==0);};
    switches[100]=true;permissions[1]=true;noIcon();
    auto request=std::make_shared<Request>();(*locator->requests)[GNSS_ABILITY].push_back(request);activeIcon();
    request->usingPermission=false;noIcon();request->usingPermission=true;
    request->requesting=false;noIcon();request->requesting=true;
    ProxyFreezeManager::GetInstance()->frozen.insert(1);noIcon();ProxyFreezeManager::GetInstance()->frozen.clear();
    permissions[1]=false;noIcon();permissions[1]=true;
    switches[100]=false;noIcon();locator->ignored.insert(1);activeIcon();locator->ignored.clear();switches[100]=true;
    activeUsers={100,101};currentUser=101;noIcon();currentUser=100;activeIcon();
    activeUsers={101};noIcon();activeUsers={100};
    request->config->fix=1;request->config->timestamp=90;noIcon();request->config->timestamp=100;activeIcon();request->config->fix=0;
    request->config.reset();noIcon();request->config=std::make_shared<RequestConfig>();
    locator->requests->clear();(*locator->requests)["passive"].push_back(request);noIcon();
    locator->requests->clear();(*locator->requests)[NETWORK_ABILITY].push_back(request);activeIcon();
    locator->requests->clear();(*locator->requests)[FUSED_ABILITY].push_back(request);activeIcon();
    locator->requests->clear();(*locator->requests)[GNSS_ABILITY].push_back(nullptr);noIcon();
    locator->requests.reset();noIcon();
    locator->requests=std::make_shared<std::map<std::string,std::list<std::shared_ptr<Request>>>>();
    auto fine=std::make_shared<Request>();fine->usingPermission=false;finePermissions[1]=true;permissions[1]=false;
    (*locator->requests)[GNSS_ABILITY].push_back(fine);
    assert(manager->UpdateUsingPermission(fine,true) && fine->usingFine && !fine->usingPermission);activeIcon();
    assert(PrivacyKit::starts[std::make_pair(1,ACCESS_LOCATION)]==1);
    auto second=std::make_shared<Request>();second->usingPermission=false;(*locator->requests)[GNSS_ABILITY].push_back(second);
    assert(manager->UpdateUsingPermission(second,true));assert(manager->UpdateUsingPermission(second,true));
    assert(PrivacyKit::starts[std::make_pair(1,ACCESS_LOCATION)]==1);
    assert(manager->UpdateUsingPermission(fine,false));activeIcon();assert(PrivacyKit::stops[std::make_pair(1,ACCESS_LOCATION)]==0);
    assert(manager->UpdateUsingPermission(second,false));noIcon();assert(PrivacyKit::stops[std::make_pair(1,ACCESS_LOCATION)]==1);
    permissions[1]=true;finePermissions[1]=true;fine->config->sports=SKIING;
    assert(manager->UpdateUsingPermission(fine,true)&&fine->usingFine&&!fine->usingPermission);activeIcon();
    assert(manager->IsSkiingRequestActive(fine));fine->requesting=false;assert(!manager->IsSkiingRequestActive(fine));fine->requesting=true;assert(!manager->IsSkiingRequestActive(nullptr));
    assert(manager->UpdateUsingPermission(fine,false));fine->config->sports=0;
    permissions[1]=true;finePermissions[1]=false;
    assert(manager->UpdateUsingPermission(fine,true) && fine->usingPermission && !fine->usingFine);activeIcon();
    finePermissions[1]=true;assert(manager->UpdateUsingPermission(fine,true));activeIcon();
    assert(!fine->usingFine && fine->usingPermission); // both grants keep the established approximate-use scope
    permissions[1]=false;assert(manager->UpdateUsingPermission(fine,true));assert(fine->usingFine && !fine->usingPermission);activeIcon();
    finePermissions[1]=false;noIcon();assert(manager->UpdateUsingPermission(fine,false));
    fine->first=2;finePermissions[1]=true;finePermissions[2]=false;
    assert(!manager->UpdateUsingPermission(fine,true));noIcon();
    finePermissions[2]=true;assert(manager->UpdateUsingPermission(fine,true));activeIcon();
    finePermissions[2]=false;noIcon();assert(manager->UpdateUsingPermission(fine,false));
    bool sawDelegation=false;for(const auto& check:Security::AccessToken::checked)if(std::get<0>(check)==1&&std::get<1>(check)==2)sawDelegation=true;assert(sawDelegation);
    systemPermission=false;assert(!query() && env.error==ERRCODE_SYSTEM_PERMISSION_DENIED);systemPermission=true;
    callerAvailable=false;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);callerAvailable=true;
    saAvailable=false;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);saAvailable=true;
    g_locatorClient->proxy=nullptr;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);g_locatorClient->proxy=locator;
    g_locatorClient.reset();assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);
    (void)manager;
    std::cout<<"Live icon/query/PrivacyKit route: fine/approx/both/revoked/delegated, shared pid, GNSS/network/fused, locks, freeze/account/timeout/switch/service boundaries passed\n";
}
'''


class LocationIconStateTests(unittest.TestCase):
    def test_execute_live_query(self):
        source = new_source()
        original_guard = json.loads(FIXTURE.read_text())['availability_guard']
        permission_functions = json.loads(FIXTURE.read_text())['permission_functions']
        actual = json.loads(FIXTURE.read_text())['common_error_mapping'] + permission_functions + original_guard + ''.join(function(source, signature) for signature in [
            'bool RequestManager::UpdateUsingPermission(', 'bool RequestManager::UpdateUsingFinePermission(',
            'bool RequestManager::UpdateUsingApproximatelyPermission(',
            'void RequestManager::IncreaseWorkingPidsCount(', 'void RequestManager::DecreaseWorkingPidsCount(',
            'bool RequestManager::IsNeedStartUsingPermission(', 'bool RequestManager::IsNeedStopUsingPermission(',
            'bool RequestManager::IsSkiingRequestActive(',
            'bool RequestManager::IsLocatingInCurrentAccount()',
            'ErrCode LocatorAbility::GetLocationIconStatus(',
            'static LocationErrCode LocationRuntimeErrCode(',
            'LocationErrCode LocatorImpl::GetLocationIconStatus(',
            'napi_value GetLocationIconStatus(napi_env env, napi_callback_info info)\n{',
        ])
        with tempfile.TemporaryDirectory(prefix='batch-location-icon-') as directory:
            cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
            cpp.write_text(PREAMBLE + actual + MAIN)
            subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined', str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_transaction_number_is_new_and_stable(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertNotIn(65, fixture['generated_transaction_values'])
        patch = (COMPONENT / '0001-query-live-location-icon-state.patch').read_text()
        self.assertIn('+    [ipccode 65] void GetLocationIconStatus([out] int status);', patch)
        self.assertIn('+    GET_LOCATION_ICON_STATUS = 65', patch)
        self.assertFalse(re.search(r'^-.*\[ipccode \d+\]', patch, re.M))
        sources = runtime_sources()
        frozen = json.loads((ROOT / 'docs/capability-audit/parallel/location/round2-ipc-baseline.json').read_text())
        idl_path = 'frameworks/native/locator_sdk/ILocatorService.idl'
        enum_path = 'interfaces/inner_api/include/locationhub_ipc_interface_code.h'
        idl = {name: int(code) for code, name in re.findall(
            r'\[ipccode (\d+)\] void (\w+)\(', sources[idl_path])}
        codes = {name: int(value) for name, value in re.findall(
            r'\b([A-Z_0-9]+)\s*=\s*(\d+)', function(sources[enum_path], 'enum class LocatorInterfaceCode'))}
        for path, mapping in [(idl_path, idl), (enum_path, codes)]:
            original = frozen['inputs']['base/location/location/' + path]['mapping']
            self.assertEqual(original, {key: mapping[key] for key in original})
        prior = runtime_sources(prefix=2)
        prior_idl = {name: int(code) for code, name in re.findall(
            r'\[ipccode (\d+)\] void (\w+)\(', prior[idl_path])}
        prior_codes = {name: int(value) for name, value in re.findall(
            r'\b([A-Z_0-9]+)\s*=\s*(\d+)', function(prior[enum_path], 'enum class LocatorInterfaceCode'))}
        self.assertEqual(prior_idl, {name: idl[name] for name in prior_idl})
        self.assertEqual(prior_codes, {name: codes[name] for name in prior_codes})
        for name, enum, value in [('GetLocationIconStatus', 'GET_LOCATION_ICON_STATUS', 65),
                                  ('StartBluetoothSearch', 'START_BLUETOOTH_SEARCH', 66),
                                  ('StopBluetoothSearch', 'STOP_BLUETOOTH_SEARCH', 67),
                                  ('StartDistrictLocating', 'START_DISTRICT_LOCATING', 68),
                                  ('StartLocatingWithSportsType', 'START_LOCATING_WITH_SPORTS_TYPE', 69),
                                  ('GetPostProcessingTrack', 'GET_POST_PROCESSING_TRACK', 70),
                                  ('CheckDistrictAccess', 'CHECK_DISTRICT_ACCESS', 71),
                                  ('AddFusionFence', 'ADD_FUSION_FENCE', 72),
                                  ('RemoveFusionFence', 'REMOVE_FUSION_FENCE', 73),
                                  ('IsFusionFenceSupported', 'IS_FUSION_FENCE_SUPPORTED', 74),
                                  ('ReleaseFusionFence', 'RELEASE_FUSION_FENCE', 75)]:
            self.assertEqual(value, idl[name])
            self.assertEqual(value, codes[enum])
            for original in frozen['inputs'].values():
                self.assertNotIn(value, original['mapping'].values())


if __name__ == '__main__':
    unittest.main()
