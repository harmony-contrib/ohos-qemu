#!/usr/bin/env python3
"""Execute the real new icon query and original availability guard; no GNSS emulation."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

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
    patch = (COMPONENT / '0001-query-live-location-icon-state.patch').read_text()
    return ''.join(line[1:] if line.startswith(('+', ' ')) else line if line == '\n' else ''
                   for line in patch.splitlines(keepends=True) if not line.startswith(('+++', '---', '@@')))


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
#include <vector>
namespace ffrt { using mutex=std::mutex; }
using ErrCode=int; using LocationErrCode=int;
const int ERRCODE_SUCCESS=0,ERRCODE_SERVICE_UNAVAILABLE=3301000,LOCATION_ERRCODE_SYSTEM_PERMISSION_DENIED=3300202;
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
std::map<uint32_t,bool> permissions;
std::map<int,bool> switches;
bool systemPermission=true,callerAvailable=true,saAvailable=true;
struct RequestConfig { int fix=0,timeout=5000;int64_t timestamp=100; int GetFixNumber(){return fix;}int GetTimeOut(){return timeout;}int64_t GetTimeStamp(){return timestamp;} };
struct Request {
    bool usingPermission=true,requesting=true; int uid=100001,pid=1;uint32_t token=1;
    std::shared_ptr<RequestConfig> config=std::make_shared<RequestConfig>();
    bool GetApproximatelyPermState(){return usingPermission;}bool GetIsRequesting(){return requesting;}
    std::shared_ptr<RequestConfig> GetRequestConfig(){return config;}int GetUid(){return uid;}int GetPid(){return pid;}
    uint32_t GetTokenId(){return token;}uint32_t GetFirstTokenId(){return 0;}
    std::string ToString(){return "request";}std::string GetPackageName(){return "app";}std::string GetUuid(){return "uuid";}
};
struct ProxyFreezeManager {std::set<int> frozen;static ProxyFreezeManager* GetInstance(){static ProxyFreezeManager v;return &v;}bool IsProxyPid(int pid){return frozen.count(pid);}};
struct LocationAccountManager {static LocationAccountManager* GetInstance(){static LocationAccountManager v;return &v;}std::vector<int> GetActiveUserIds(){return activeUsers;}};
struct CommonUtils {
    static int GetUserIdByUid(int uid){return uid/1000;}
    static bool IsAppBelongCurrentAccount(AppIdentity identity){return GetUserIdByUid(identity.uid)==currentUser;}
    static bool IsAppBelongActiveAccounts(AppIdentity identity,std::vector<int> ids){for(int id:ids)if(GetUserIdByUid(identity.uid)==id)return true;return false;}
    static int64_t GetCurrentTime(){return now;}
    static LocationErrCode ErrCodeToLocationErrCode(int code){return code;}
};
struct PermissionManager {
    static bool CheckSystemPermission(uint32_t,uint64_t){return systemPermission;}
    static bool CheckLocationPermission(uint32_t,uint32_t){return false;}
    static bool CheckApproximatelyPermission(uint32_t token,uint32_t){return permissions[token];}
};
struct LocationDataRdbManager {static int QuerySwitchStateForUser(int user){return switches[user]?ENABLED:0;}};
enum class LocatorInterfaceCode {GET_LOCATION_ICON_STATUS=65};
class LocatorAbility {
public:
    std::shared_ptr<std::map<std::string,std::list<std::shared_ptr<Request>>>> requests=std::make_shared<std::map<std::string,std::list<std::shared_ptr<Request>>>>();
    std::set<uint32_t> ignored;
    static LocatorAbility* GetInstance(){static LocatorAbility v;return &v;}
    auto GetRequests(){return requests;}
    bool GetLocationSwitchIgnoredFlag(uint32_t token){return ignored.count(token);}
    void GetAppIdentityInfo(AppIdentity& identity){identity=AppIdentity{};}
    bool CheckRequestAvailable(LocatorInterfaceCode,AppIdentity&){return callerAvailable;}
    ErrCode GetLocationIconStatus(int32_t&);
};
class RequestManager {
public:
    static RequestManager* GetInstance(){static RequestManager v;return &v;}
    static ffrt::mutex requestMutex_;ffrt::mutex permissionRecordMutex_;
    bool IsRequestAvailable(std::shared_ptr<Request>&);
    bool IsLocatingInCurrentAccount();
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
    Env env;auto query=[&](){env.error=0;return GetLocationIconStatus(&env,nullptr);};
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
    systemPermission=false;assert(!query() && env.error==LOCATION_ERRCODE_SYSTEM_PERMISSION_DENIED);systemPermission=true;
    callerAvailable=false;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);callerAvailable=true;
    saAvailable=false;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);saAvailable=true;
    g_locatorClient->proxy=nullptr;assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);g_locatorClient->proxy=locator;
    g_locatorClient.reset();assert(!query() && env.error==ERRCODE_SERVICE_UNAVAILABLE);
    (void)manager;
    std::cout<<"Live icon query: GNSS/network/fused, privacy-use, freeze, account, timeout, permission, switch, passive, service boundaries passed\n";
}
'''


class LocationIconStateTests(unittest.TestCase):
    def test_execute_live_query(self):
        source = new_source()
        original_guard = json.loads(FIXTURE.read_text())['availability_guard']
        actual = original_guard + ''.join(function(source, signature) for signature in [
            'bool RequestManager::IsLocatingInCurrentAccount()',
            'ErrCode LocatorAbility::GetLocationIconStatus(',
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


if __name__ == '__main__':
    unittest.main()
