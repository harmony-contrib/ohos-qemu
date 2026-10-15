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

#include "child_callback_manager.h"

namespace OHOS {
namespace AbilityRuntime {

ChildCallbackManager &ChildCallbackManager::GetInstance()
{
    static ChildCallbackManager instance;
    return instance;
}

void ChildCallbackManager::AddRemoteObject(sptr<IRemoteObject> nativeCallback)
{
    std::lock_guard<std::mutex> lock(mutex_);
    callbackStubs_.emplace(nativeCallback);
}

void ChildCallbackManager::RemoveRemoteObject(sptr<IRemoteObject> nativeCallback)
{
    if (nativeCallback) {
        std::lock_guard<std::mutex> lock(mutex_);
        callbackStubs_.erase(nativeCallback);
    }
}

} // namespace AbilityRuntime
} // namespace OHOS