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

#include "child_process_args.h"

#include "hilog_tag_wrapper.h"
#include "message_parcel.h"
#include "parcel_macro_base.h"
#include "string_ex.h"

namespace OHOS {
namespace AppExecFwk {
bool ChildProcessArgs::ReadFromParcel(Parcel &parcel)
{
    entryParams = Str16ToStr8(parcel.ReadString16());

    int32_t fdsSize = parcel.ReadInt32();
    if (fdsSize > CHILD_PROCESS_ARGS_FDS_MAX_COUNT) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "fds count must <= %{public}d.", CHILD_PROCESS_ARGS_FDS_MAX_COUNT);
        return false;
    }
    auto messageParcel = static_cast<MessageParcel*>(&parcel);
    if (messageParcel == nullptr) {
        TAG_LOGE(AAFwkTag::APPMGR, "static cast messageParcel failed");
        return false;
    }
    for (int32_t i = 0; i < fdsSize; i++) {
        std::string key = Str16ToStr8(parcel.ReadString16());
        if (!CheckFdKeyLength(key)) {
            return false;
        }
        int32_t fd = messageParcel->ReadFileDescriptor();
        fds.emplace(key, fd);
    }
    return true;
}

ChildProcessArgs *ChildProcessArgs::Unmarshalling(Parcel &parcel)
{
    ChildProcessArgs *obj = new (std::nothrow) ChildProcessArgs();
    if (obj && !obj->ReadFromParcel(parcel)) {
        TAG_LOGW(AAFwkTag::APPMGR, "read from parcel failed");
        delete obj;
        obj = nullptr;
    }
    return obj;
}

bool ChildProcessArgs::Marshalling(Parcel &parcel) const
{
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(entryParams));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, fds.size());
    auto messageParcel = static_cast<MessageParcel*>(&parcel);
    if (messageParcel == nullptr) {
        TAG_LOGW(AAFwkTag::APPMGR, "static cast messageParcel failed");
        return false;
    }
    if (!CheckFdsSize()) {
        return false;
    }
    for (auto &item : fds) {
        if (!CheckFdKeyLength(item.first)) {
            return false;
        }
        WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(item.first));
        if (!messageParcel->WriteFileDescriptor(item.second)) {
            TAG_LOGE(AAFwkTag::APPMGR, "WriteFileDescriptor failed, fd:%{private}d", item.second);
            return false;
        }
    }
    return true;
}

bool ChildProcessArgs::CheckFdsSize() const
{
    TAG_LOGD(AAFwkTag::APPMGR, "CheckFdsSize: %{public}zu", fds.size());
    if (fds.size() > CHILD_PROCESS_ARGS_FDS_MAX_COUNT) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "fds count must <= %{public}d.", CHILD_PROCESS_ARGS_FDS_MAX_COUNT);
        return false;
    }
    return true;
}

bool ChildProcessArgs::CheckFdsKeyLength() const
{
    for (auto iter = fds.begin(); iter != fds.end(); iter++) {
        if (!CheckFdKeyLength(iter->first)) {
            return false;
        }
    }
    return true;
}

bool ChildProcessArgs::CheckFdKeyLength(const std::string &key)
{
    if (key.length() > CHILD_PROCESS_ARGS_FD_KEY_MAX_LENGTH) {
        TAG_LOGE(AAFwkTag::PROCESSMGR, "fd key length must <= %{public}d, key:%{public}s",
            CHILD_PROCESS_ARGS_FD_KEY_MAX_LENGTH, key.c_str());
        return false;
    }
    return true;
}
}  // namespace AppExecFwk
}  // namespace OHOS
