/*
 * Copyright (c) 2023-2024 Huawei Device Co., Ltd.
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

#include "child_process_info.h"

#include "hilog_tag_wrapper.h"
#include "nlohmann/json.hpp"
#include "parcel_macro.h"
#include "string_ex.h"

namespace OHOS {
namespace AppExecFwk {
bool ChildProcessInfo::ReadFromParcel(Parcel &parcel)
{
    int32_t pidData;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, pidData);
    pid = static_cast<int32_t>(pidData);

    int32_t hostPidData;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, hostPidData);
    hostPid = static_cast<int32_t>(hostPidData);

    int32_t uidData;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, uidData);
    uid = static_cast<int32_t>(uidData);

    int32_t hostUidData;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, hostUidData);
    hostUid = static_cast<int32_t>(hostUidData);

    int32_t userIdData;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, userIdData);
    userId = static_cast<int32_t>(userIdData);

    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, childProcessType);

    bundleName = Str16ToStr8(parcel.ReadString16());
    processName = Str16ToStr8(parcel.ReadString16());
    srcEntry = Str16ToStr8(parcel.ReadString16());
    entryFunc = Str16ToStr8(parcel.ReadString16());
    entryParams = Str16ToStr8(parcel.ReadString16());
    jitEnabled = parcel.ReadBool();
    isDebugApp = parcel.ReadBool();
    isStartWithDebug = parcel.ReadBool();
    isStartWithNative = parcel.ReadBool();
    isStaticChildProcess = parcel.ReadBool();
    bool hasBundleInfo = parcel.ReadBool();
    if (hasBundleInfo) {
        bundleInfo.reset(parcel.ReadParcelable<BundleInfo>());
    }

    int32_t hspListSize = 0;
    READ_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, hspListSize);
    CONTAINER_SECURITY_VERIFY(parcel, hspListSize, &hspList);
    for (auto i = 0; i < hspListSize; i++) {
        std::unique_ptr<BaseSharedBundleInfo> baseShareBundleInfo(parcel.ReadParcelable<BaseSharedBundleInfo>());
        if (!baseShareBundleInfo) {
            TAG_LOGE(AAFwkTag::APPMGR, "read base shared bundle info failed");
            return false;
        }
        hspList.emplace_back(*baseShareBundleInfo);
    }

    return true;
}

ChildProcessInfo *ChildProcessInfo::Unmarshalling(Parcel &parcel)
{
    ChildProcessInfo *info = new (std::nothrow) ChildProcessInfo();
    if (info && !info->ReadFromParcel(parcel)) {
        TAG_LOGW(AAFwkTag::APPMGR, "read from parcel failed");
        delete info;
        info = nullptr;
    }
    return info;
}

bool ChildProcessInfo::Marshalling(Parcel &parcel) const
{
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(pid));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(hostPid));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(uid));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(hostUid));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(userId));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, static_cast<int32_t>(childProcessType));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(bundleName));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(processName));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(srcEntry));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(entryFunc));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(String16, parcel, Str8ToStr16(entryParams));
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, jitEnabled);
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, isDebugApp);
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, isStartWithDebug);
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, isStartWithNative);
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, isStaticChildProcess);
    bool hasBundleInfo = bundleInfo != nullptr;
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Bool, parcel, hasBundleInfo);
    if (hasBundleInfo) {
        WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Parcelable, parcel, bundleInfo.get());
    }
    WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Int32, parcel, hspList.size());
    for (auto &baseSharedBundleInfo : hspList) {
        WRITE_PARCEL_AND_RETURN_FALSE_IF_FAIL(Parcelable, parcel, &baseSharedBundleInfo);
    }
    return true;
}
}  // namespace AppExecFwk
}  // namespace OHOS
