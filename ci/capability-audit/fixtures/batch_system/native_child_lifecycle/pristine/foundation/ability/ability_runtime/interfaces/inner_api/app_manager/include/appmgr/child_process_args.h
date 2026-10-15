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

#ifndef OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_H
#define OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_H

#include <map>
#include <string>

#include "parcel.h"

namespace OHOS {
namespace AppExecFwk {
constexpr int32_t CHILD_PROCESS_ARGS_FDS_MAX_COUNT = 16;
constexpr int32_t CHILD_PROCESS_ARGS_FD_KEY_MAX_LENGTH = 20;
struct ChildProcessArgs : public Parcelable {
    std::string entryParams;
    std::map<std::string, int32_t> fds;

    bool ReadFromParcel(Parcel &parcel);
    virtual bool Marshalling(Parcel &parcel) const override;
    static ChildProcessArgs *Unmarshalling(Parcel &parcel);
    static bool CheckFdKeyLength(const std::string &key);
    bool CheckFdsSize() const;
    bool CheckFdsKeyLength() const;
};
}  // namespace AppExecFwk
}  // namespace OHOS
#endif  // OHOS_ABILITY_RUNTIME_CHILD_PROCESS_ARGS_H
