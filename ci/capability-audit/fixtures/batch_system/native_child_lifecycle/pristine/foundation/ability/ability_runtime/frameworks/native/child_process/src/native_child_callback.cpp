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

#include "native_child_callback.h"
#include "hilog_tag_wrapper.h"
#include "ipc_inner_object.h"
#include "child_process_manager_error_utils.h"

namespace OHOS {
namespace AbilityRuntime {

NativeChildCallback::NativeChildCallback(OH_Ability_OnNativeChildProcessStarted cb)
    : NativeChildNotifyStub(), callback_(cb)
{
}

void NativeChildCallback::OnNativeChildStarted(const sptr<IRemoteObject> &nativeChild)
{
    if (callback_ == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callback_");
        return;
    }

    if (!nativeChild) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null nativeChild");
        return;
    }
    
    TAG_LOGI(AAFwkTag::PROCESSMGR, "Native child process started");
    sptr<IRemoteObject> ipcRemote = nativeChild;
    OHIPCRemoteProxy *ipcProxy = CreateIPCRemoteProxy(ipcRemote);
    if (ipcProxy == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null ipcProxy");
        callback_(NCP_ERR_INTERNAL, nullptr);
        return;
    }

    callback_(static_cast<int32_t>(ChildProcessManagerErrorCode::ERR_OK), ipcProxy);
    callback_ = nullptr;

    ChildCallbackManager::GetInstance().RemoveRemoteObject(this);
}

void NativeChildCallback::OnError(int32_t errCode)
{
    if (callback_ == nullptr) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "null callback_");
        return;
    }

    TAG_LOGI(AAFwkTag::PROCESSMGR, "Native child process start err %{public}d", errCode);
    callback_(errCode, nullptr);
    
    callback_ = nullptr;
    ChildCallbackManager::GetInstance().RemoveRemoteObject(this);
}

int32_t NativeChildCallback::OnNativeChildExit(int32_t pid, int32_t signal)
{
    auto exitCallbacks = GetExitCallbacks();
    for (const auto &exitCallback : exitCallbacks) {
        TAG_LOGI(AAFwkTag::PROCESSMGR,
            "native child process exit, pid:%{public}d, signal:%{public}d", pid, signal);
        exitCallback(pid, signal);
    }
    return NCP_NO_ERROR;
}

void NativeChildCallback::AddExitCallback(OH_Ability_OnNativeChildProcessExit callback)
{
    std::lock_guard lock(exitCallbackListMutex_);
    for (const auto &cb : exitCallbacks_) {
        if (cb == callback) {
            TAG_LOGI(AAFwkTag::PROCESSMGR, "repeated add exit callback");
            return;
        }
    }
    exitCallbacks_.emplace_back(callback);
}

int32_t NativeChildCallback::RemoveExitCallback(OH_Ability_OnNativeChildProcessExit callback)
{
    std::lock_guard lock(exitCallbackListMutex_);
    auto it = std::find(exitCallbacks_.begin(), exitCallbacks_.end(), callback);
    if (it == exitCallbacks_.end()) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "native child exit callback not exist");
        return NCP_ERR_CALLBACK_NOT_EXIST;
    }
    exitCallbacks_.erase(it);
    return NCP_NO_ERROR;
}

bool NativeChildCallback::IsCallbacksEmpty()
{
    std::lock_guard lock(exitCallbackListMutex_);
    return exitCallbacks_.empty();
}

std::list<OH_Ability_OnNativeChildProcessExit> NativeChildCallback::GetExitCallbacks()
{
    std::lock_guard lock(exitCallbackListMutex_);
    return exitCallbacks_;
}
} // namespace AbilityRuntime
} // namespace OHOS
