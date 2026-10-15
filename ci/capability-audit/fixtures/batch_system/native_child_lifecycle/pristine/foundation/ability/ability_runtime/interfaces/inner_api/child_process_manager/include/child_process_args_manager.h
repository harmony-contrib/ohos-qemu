/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
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

#ifndef OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_MANAGER_H
#define OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_MANAGER_H

#include <map>
#include <memory>
#include <mutex>

#include "native_child_process.h"
#include "singleton.h"

namespace OHOS {
namespace AbilityRuntime {

class ChildProcessArgsManager {
public:
    static ChildProcessArgsManager &GetInstance()
    {
        static ChildProcessArgsManager instance;
        return instance;
    }

    virtual ~ChildProcessArgsManager() = default;

    void SetChildProcessArgs(const NativeChildProcess_Args &args)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        args_ = std::make_shared<NativeChildProcess_Args>(args);
    }

    NativeChildProcess_Args* GetChildProcessArgs()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (args_ == nullptr) {
            return nullptr;
        }
        return args_.get();
    }

private:
    ChildProcessArgsManager() = default;
    DISALLOW_COPY_AND_MOVE(ChildProcessArgsManager);

    std::mutex mutex_;
    std::shared_ptr<NativeChildProcess_Args> args_ = nullptr;
};
} // namespace AbilityRuntime
} // namespace OHOS
#endif // OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_MANAGER_H