/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "native_child_process.h"
#include <map>
#include <mutex>
#include <regex>
#include "app_mgr_client.h"
#include "child_process_configs.h"
#include "hilog_tag_wrapper.h"
#include "native_child_callback.h"
#include "child_process_args_manager.h"
#include "child_process_manager.h"
#include "child_callback_manager.h"
#include "child_process_manager_error_utils.h"

using namespace OHOS;
using namespace OHOS::AbilityRuntime;

namespace {
constexpr size_t MAX_KEY_SIZE = 20;
constexpr size_t MAX_FD_SIZE = 16;
constexpr int32_t MAX_PROCESS_NAME_LENGTH = 64;
std::mutex g_callbackStubMutex;
std::mutex g_callbackSerialMutex;
sptr<OHOS::AbilityRuntime::NativeChildCallback> g_callbackStub = nullptr;
} // Anonymous namespace

Ability_ChildProcessConfigs* OH_Ability_CreateChildProcessConfigs()
{
    std::unique_ptr<Ability_ChildProcessConfigs> configs = std::make_unique<Ability_ChildProcessConfigs>();
    return configs.release();
}

Ability_NativeChildProcess_ErrCode OH_Ability_DestroyChildProcessConfigs(Ability_ChildProcessConfigs* configs)
{
    if(configs == nullptr){
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null Ability_ChildProcessConfigs");
        return NCP_ERR_INVALID_PARAM;
    }
    delete configs;
    configs = nullptr;
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_ChildProcessConfigs_SetIsolationMode(
    Ability_ChildProcessConfigs* configs, NativeChildProcess_IsolationMode isolationMode)
{
    if(configs == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Ability_ChildProcessConfigs");
        return NCP_ERR_INVALID_PARAM;
    }
    configs->isolationMode = isolationMode;
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_ChildProcessConfigs_SetProcessName(Ability_ChildProcessConfigs* configs,
    const char* processName)
{
    if (configs == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Ability_ChildProcessConfigs");
        return NCP_ERR_INVALID_PARAM;
    }
    if (processName == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null processName");
        return NCP_ERR_INVALID_PARAM;
    }
    int32_t processNameLen = strlen(processName);
    if(processNameLen == 0) {
        TAG_LOGE(AAFwkTag::APPKIT, "processName is 0");
        return NCP_ERR_INVALID_PARAM;
    }
    if (processNameLen > MAX_PROCESS_NAME_LENGTH) {
        TAG_LOGE(AAFwkTag::APPKIT, "processName is larger than 64");
        return NCP_ERR_INVALID_PARAM; 
    }
    try {
        std::regex regex("^[a-zA-Z0-9_]+$");
        if (!regex_match(processName, regex)) {
            TAG_LOGE(AAFwkTag::APPKIT, "Wrong processName");
            return NCP_ERR_INVALID_PARAM;
        }
    } catch(...) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "regex error");
        return NCP_ERR_INVALID_PARAM;
    }
    configs->processName = std::string(processName);
    return NCP_NO_ERROR;
}

int OH_Ability_CreateNativeChildProcess(const char* libName, OH_Ability_OnNativeChildProcessStarted onProcessStarted)
{
    if (libName == nullptr || *libName == '\0' || onProcessStarted == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null libname or callback");
        return NCP_ERR_INVALID_PARAM;
    }

    std::string strLibName(libName);
    if (strLibName.find("../") != std::string::npos) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "relative path not allow");
        return NCP_ERR_INVALID_PARAM;
    }

    sptr<IRemoteObject> callbackStub(new (std::nothrow) NativeChildCallback(onProcessStarted));
    if (!callbackStub) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callbackStub");
        return NCP_ERR_INTERNAL;
    }

    auto cpmErr = ChildProcessManager::GetInstance().CreateNativeChildProcessByAppSpawnFork(strLibName, callbackStub);
    if (cpmErr != ChildProcessManagerErrorCode::ERR_OK) {
        return ChildProcessManagerErrorUtil::CvtChildProcessManagerErrCode(cpmErr);
    }

    ChildCallbackManager::GetInstance().AddRemoteObject(callbackStub);
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_CreateNativeChildProcessWithConfigs(const char* libName,
    Ability_ChildProcessConfigs* configs, OH_Ability_OnNativeChildProcessStarted onProcessStarted)
{
    if (libName == nullptr || *libName == '\0' || onProcessStarted == nullptr || configs == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null libname or callback or configs");
        return NCP_ERR_INVALID_PARAM;
    }

    std::string strLibName(libName);
    if (strLibName.find("../") != std::string::npos) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "relative path not allow");
        return NCP_ERR_INVALID_PARAM;
    }

    sptr<IRemoteObject> callbackStub(new (std::nothrow) NativeChildCallback(onProcessStarted));
    if (!callbackStub) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callbackStub");
        return NCP_ERR_INTERNAL;
    }

    auto isolationMode = configs->isolationMode == NCP_ISOLATION_MODE_ISOLATED;
    auto cpmErr = ChildProcessManager::GetInstance().CreateNativeChildProcessByAppSpawnFork(strLibName,
        callbackStub, configs->processName, isolationMode, configs->isIsolationUid);
    if (cpmErr != ChildProcessManagerErrorCode::ERR_OK) {
        return ChildProcessManagerErrorUtil::CvtChildProcessManagerErrCode(cpmErr);
    }

    ChildCallbackManager::GetInstance().AddRemoteObject(callbackStub);
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode ConvertNativeChildProcessArgs(NativeChildProcess_Args &args,
    AppExecFwk::ChildProcessArgs &childArgs)
{
    std::map<std::string, int32_t> fds;
    NativeChildProcess_Fd* cur = args.fdList.head;
    while (cur != nullptr) {
        if (!cur->fdName) {
            TAG_LOGE(AAFwkTag::PROCESSMGR, "fdName null");
            return NCP_ERR_INVALID_PARAM;
        }
        std::string key(cur->fdName);
        if (key.size() > MAX_KEY_SIZE) {
            TAG_LOGE(AAFwkTag::PROCESSMGR, "fd name too long");
            return NCP_ERR_INVALID_PARAM;
        }
        fds.emplace(key, cur->fd);
        cur = cur->next;
    }
    if (fds.size() > MAX_FD_SIZE) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "too many fds");
        return NCP_ERR_INVALID_PARAM;
    }
    childArgs.fds = fds;
    if (args.entryParams != nullptr && *(args.entryParams) != '\0') {
        std::string entryParams(args.entryParams);
        childArgs.entryParams = entryParams;
    }
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_StartNativeChildProcess(const char* entry,
    NativeChildProcess_Args args, NativeChildProcess_Options options, int32_t *pid)
{
    if (entry == nullptr || *entry == '\0') {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "Invalid entry");
        return NCP_ERR_INVALID_PARAM;
    }
    std::string entryName(entry);
    if (entryName.find(":") == std::string::npos) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "entry point misses a colon");
        return NCP_ERR_INVALID_PARAM;
    }
    if (pid == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "pid null");
        return NCP_ERR_INVALID_PARAM;
    }

    AppExecFwk::ChildProcessArgs childArgs;
    auto errCode = ConvertNativeChildProcessArgs(args, childArgs);
    if (errCode != NCP_NO_ERROR) {
        return errCode;
    }
    AppExecFwk::ChildProcessOptions childProcessOptions;
    childProcessOptions.isolationMode = options.isolationMode == NCP_ISOLATION_MODE_ISOLATED;
    int32_t childProcessType = AppExecFwk::CHILD_PROCESS_TYPE_NATIVE_ARGS;

    auto cpmErr = ChildProcessManager::GetInstance().StartChildProcessWithArgs(entryName,
        *pid, childProcessType, childArgs, childProcessOptions);
    if (cpmErr != ChildProcessManagerErrorCode::ERR_OK) {
        return ChildProcessManagerErrorUtil::CvtChildProcessManagerErrCode(cpmErr);
    }
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_StartNativeChildProcessWithConfigs(
    const char* entry, NativeChildProcess_Args args, Ability_ChildProcessConfigs* configs, int32_t *pid)
{
    if (entry == nullptr || *entry == '\0' || configs == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "Invalid entry or configs");
        return NCP_ERR_INVALID_PARAM;
    }
    std::string entryName(entry);
    if (entryName.find(":") == std::string::npos) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "entry point misses a colon");
        return NCP_ERR_INVALID_PARAM;
    }
    if (pid == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "pid null");
        return NCP_ERR_INVALID_PARAM;
    }

    AppExecFwk::ChildProcessArgs childArgs;
    auto errCode = ConvertNativeChildProcessArgs(args, childArgs);
    if (errCode != NCP_NO_ERROR) {
        return errCode;
    }
    AppExecFwk::ChildProcessOptions childProcessOptions;
    childProcessOptions.isolationMode = configs->isolationMode == NCP_ISOLATION_MODE_ISOLATED;
    childProcessOptions.isolationUid = configs->isIsolationUid;
    childProcessOptions.customProcessName = configs->processName;
    int32_t childProcessType = AppExecFwk::CHILD_PROCESS_TYPE_NATIVE_ARGS;

    auto cpmErr = ChildProcessManager::GetInstance().StartChildProcessWithArgs(entryName,
        *pid, childProcessType, childArgs, childProcessOptions);
    if (cpmErr != ChildProcessManagerErrorCode::ERR_OK) {
        return ChildProcessManagerErrorUtil::CvtChildProcessManagerErrCode(cpmErr);
    }
    return NCP_NO_ERROR;
}

NativeChildProcess_Args* OH_Ability_GetCurrentChildProcessArgs()
{
    NativeChildProcess_Args* result = ChildProcessArgsManager::GetInstance().GetChildProcessArgs();
    if (result == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "GetChildProcessArgs null");
    }
    return result;
}

sptr<OHOS::AbilityRuntime::NativeChildCallback> GetGlobalNativeChildCallbackStub()
{
    std::lock_guard<std::mutex> lock(g_callbackStubMutex);
    return g_callbackStub;
}

void SetGlobalNativeChildCallbackStub(sptr<OHOS::AbilityRuntime::NativeChildCallback> local)
{
    std::lock_guard<std::mutex> lock(g_callbackStubMutex);
    g_callbackStub = local;
}

Ability_NativeChildProcess_ErrCode OH_Ability_RegisterNativeChildProcessExitCallback(
    OH_Ability_OnNativeChildProcessExit onProcessExit)
{
    if (onProcessExit == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callback func pointer");
        return NCP_ERR_INVALID_PARAM;
    }

    std::lock_guard<std::mutex> lock(g_callbackSerialMutex);
    auto localCallbackStub = GetGlobalNativeChildCallbackStub();
    if (localCallbackStub != nullptr) {
        localCallbackStub->AddExitCallback(onProcessExit);
        return NCP_NO_ERROR;
    }

    localCallbackStub = sptr<NativeChildCallback>::MakeSptr(nullptr);
    if (!localCallbackStub) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callbackStub");
        return NCP_ERR_INTERNAL;
    }
    SetGlobalNativeChildCallbackStub(localCallbackStub);
    localCallbackStub->AddExitCallback(onProcessExit);
    auto ret = DelayedSingleton<OHOS::AppExecFwk::AppMgrClient>::GetInstance()->RegisterNativeChildExitNotify(
        localCallbackStub);
    if (ret != NCP_NO_ERROR) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "register native child exit notify failed, %{public}d", ret);
        SetGlobalNativeChildCallbackStub(nullptr);
        return NCP_ERR_INTERNAL;
    }

    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_UnregisterNativeChildProcessExitCallback(
    OH_Ability_OnNativeChildProcessExit onProcessExit)
{
    if (onProcessExit == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callback func pointer");
        return NCP_ERR_INVALID_PARAM;
    }

    std::lock_guard<std::mutex> lock(g_callbackSerialMutex);
    sptr<OHOS::AbilityRuntime::NativeChildCallback> localCallbackStub = GetGlobalNativeChildCallbackStub();
    if (localCallbackStub == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callbackStub");
        return NCP_ERR_CALLBACK_NOT_EXIST;
    }

    auto ret = localCallbackStub->RemoveExitCallback(onProcessExit);
    if (ret ==  NCP_ERR_CALLBACK_NOT_EXIST) {
        return static_cast<Ability_NativeChildProcess_ErrCode>(ret);
    }
    if (localCallbackStub->IsCallbacksEmpty()) {
        auto ret = DelayedSingleton<OHOS::AppExecFwk::AppMgrClient>::GetInstance()->UnregisterNativeChildExitNotify(
            localCallbackStub);
        if (ret != NCP_NO_ERROR) {
            TAG_LOGE(AAFwkTag::PROCESSMGR, "unregister native child exit notify failed, %{public}d", ret);
            return NCP_ERR_INTERNAL;
        }
        SetGlobalNativeChildCallbackStub(nullptr);
    }

    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_ChildProcessConfigs_SetIsolationUid(
    Ability_ChildProcessConfigs* configs, bool isolationUid)
{
    if (configs == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null Ability_ChildProcessConfigs");
        return NCP_ERR_INVALID_PARAM;
    }
    configs->isIsolationUid = isolationUid;
    return NCP_NO_ERROR;
}

Ability_NativeChildProcess_ErrCode OH_Ability_KillChildProcess(int32_t pid)
{
    auto cpmErr = ChildProcessManager::GetInstance().KillChildProcessByPid(pid);
    if (cpmErr != ChildProcessManagerErrorCode::ERR_OK) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "kill child process by pid, pid:%{public}d, error: %{public}d", pid, cpmErr);
        return ChildProcessManagerErrorUtil::CvtChildProcessManagerErrCode(cpmErr);
    }
    return NCP_NO_ERROR;
}

bool OH_Ability_IsNativeChildProcessSupported()
{
    bool result = ChildProcessManager::GetInstance().IsNativeChildProcessSupported();
    TAG_LOGD(AAFwkTag::PROCESSMGR, "IsNativeChildProcessSupported: %{public}d", result);
    return result;
}