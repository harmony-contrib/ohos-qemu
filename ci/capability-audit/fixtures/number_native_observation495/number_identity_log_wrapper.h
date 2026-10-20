/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023. All rights reserved.
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

#ifndef OHOS_NUMBER_IDENTITY_LOG_WRAPPER_H
#define OHOS_NUMBER_IDENTITY_LOG_WRAPPER_H

#include <string>

#include "hilog/log.h"

namespace OHOS {
namespace Telephony {

#ifndef NUMBER_IDENTITY_LOG_TAG
#define NUMBER_IDENTITY_LOG_TAG "NumberIdentity"
#endif

static constexpr OHOS::HiviewDFX::HiLogLabel NUMBER_IDENTITY_LABEL = { LOG_CORE, LOG_DOMAIN, NUMBER_IDENTITY_LOG_TAG };

#ifndef NUMBER_IDENTITY_DEBUG

#define PRINT_NUMBER_IDENTITY_LOG(level, fmt, ...)                                                                     \
    (void)HILOG_IMPL(                                                                                                  \
        LOG_CORE, level, LOG_DOMAIN, NUMBER_IDENTITY_LOG_TAG, "[%{public}s]" fmt, __FUNCTION__, ##__VA_ARGS__)

#else // defined NUMBER_IDENTITY_DEBUG
// Gets the raw file name of the file.
// This function is a function executed by the compiler, that is,
// it has been executed at compile time. When the program runs,
// it directly refers to the value calculated by this function
// and does not consume CPU for calculation.
inline constexpr const char *GetRawFileName(const char *path)
{
    char ch = '/';
    const char *start = path;
    // get the end of the string
    while (*start++) {
        ;
    }
    while (--start != path && *start != ch) {
        ;
    }

    return (*start == ch) ? ++start : path;
}

#define PRINT_NUMBER_IDENTITY_LOG(level, fmt, ...)                                                                     \
    (void)HILOG_IMPL(LOG_CORE, level, LOG_DOMAIN, NUMBER_IDENTITY_LOG_TAG,                                             \
        "[%{public}s-(%{public}s:%{public}d)] " fmt, __FUNCTION__, GetRawFileName(__FILE__), __LINE__, ##__VA_ARGS__)

#endif

#define NUMBER_IDENTITY_LOGE(fmt, ...) (void)PRINT_NUMBER_IDENTITY_LOG(LOG_ERROR, fmt, ##__VA_ARGS__)
#define NUMBER_IDENTITY_LOGW(fmt, ...) (void)PRINT_NUMBER_IDENTITY_LOG(LOG_WARN, fmt, ##__VA_ARGS__)
#define NUMBER_IDENTITY_LOGI(fmt, ...) (void)PRINT_NUMBER_IDENTITY_LOG(LOG_INFO, fmt, ##__VA_ARGS__)
#define NUMBER_IDENTITY_LOGF(fmt, ...) (void)PRINT_NUMBER_IDENTITY_LOG(LOG_FATAL, fmt, ##__VA_ARGS__)
#define NUMBER_IDENTITY_LOGD(fmt, ...) (void)PRINT_NUMBER_IDENTITY_LOG(LOG_DEBUG, fmt, ##__VA_ARGS__)

} // namespace Telephony
} // namespace OHOS
#endif // OHOS_NUMBER_IDENTITY_LOG_WRAPPER_H
