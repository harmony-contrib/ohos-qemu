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

#ifndef OHOS_ABILITY_RUNTIME_NATIVE_CHILD_CALLBACK_H
#define OHOS_ABILITY_RUNTIME_NATIVE_CHILD_CALLBACK_H

#include "native_child_notify_stub.h"
#include "native_child_process.h"
#include "child_callback_manager.h"
#include <list>

namespace OHOS {
namespace AbilityRuntime {

class NativeChildCallback : public OHOS::AppExecFwk::NativeChildNotifyStub {
public:
    explicit NativeChildCallback(OH_Ability_OnNativeChildProcessStarted cb);
    ~NativeChildCallback() = default;

    void OnNativeChildStarted(const sptr<IRemoteObject> &nativeChild) override;
    void OnError(int32_t errCode) override;
    int32_t OnNativeChildExit(int32_t pid, int32_t signal) override;

    bool IsCallbacksEmpty();
    void AddExitCallback(OH_Ability_OnNativeChildProcessExit callback);
    int32_t RemoveExitCallback(OH_Ability_OnNativeChildProcessExit callback);
    std::list<OH_Ability_OnNativeChildProcessExit> GetExitCallbacks();

private:
    OH_Ability_OnNativeChildProcessStarted callback_ = nullptr;
    std::mutex exitCallbackListMutex_;
    std::list<OH_Ability_OnNativeChildProcessExit> exitCallbacks_;
};

} // namespace AbilityRuntime
} // namespace OHOS

#endif // OHOS_ABILITY_RUNTIME_NATIVE_CHILD_CALLBACK_H
