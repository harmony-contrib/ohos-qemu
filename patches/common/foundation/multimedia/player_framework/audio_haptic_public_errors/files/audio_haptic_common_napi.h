/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
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

#ifndef AUDIO_HAPTIC_COMMON_NAPI_H
#define AUDIO_HAPTIC_COMMON_NAPI_H

#include <string>

#include "napi/native_api.h"
#include "napi/native_node_api.h"

namespace OHOS {
namespace Media {
const int32_t  NAPI_ERR_VIBRATE_PERMISSION_DENIED = 201;
const int32_t  NAPI_ERR_INPUT_INVALID = 401;
const int32_t  NAPI_ERR_OPERATE_NOT_ALLOWED = 5400102;
const int32_t  NAPI_ERR_IO_ERROR = 5400103;
const int32_t  NAPI_ERR_SERVICE_DIED = 5400105;
const int32_t  NAPI_ERR_UNSUPPORTED_FORMAT = 5400106;
const int32_t  NAPI_ERR_PARAM_OUT_OF_RANGE = 5400108;
const int32_t  NAPI_ERR_PERMISSION_DENIED = 202;
const int32_t  NAPI_ERR_NOT_SUPPORTED = 801;

/* Constants for array index */
const int32_t PARAM0 = 0;
const int32_t PARAM1 = 1;
const int32_t PARAM2 = 2;

/* Constants for array size */
const int32_t ARGS_ZERO = 0;
const int32_t ARGS_ONE = 1;
const int32_t ARGS_TWO = 2;
const int32_t ARGS_THREE = 3;

struct AsyncContext {
    napi_async_work work;
    napi_deferred deferred = nullptr;
    napi_value argv[ARGS_THREE] = {0};
    void* objectInfo = nullptr;
};

class AudioHapticCommonNapi {
public:
    AudioHapticCommonNapi() = delete;
    ~AudioHapticCommonNapi() = delete;
    static void ThrowError(napi_env env, int32_t code);
    static void ThrowError(napi_env env, int32_t code, const std::string &errMessage);
    static std::string GetMessageByCode(int32_t &code);
    static std::string GetStringArgument(napi_env env, napi_value value);
    static void PromiseReject(napi_env env, napi_deferred deferred,
        const int32_t &errCode, const std::string &errMessage);
    static void PromiseReject(napi_env env, napi_deferred deferred, int32_t errCode);
    static bool InitPromiseFunc(napi_env env, napi_callback_info info,
        AsyncContext* asyncContext, napi_value* promise, size_t paramLength);
    static bool VerifySelfSystemPermission();
    static bool VerifyVibratePermission();
    static bool InitNormalFunc(napi_env env, napi_callback_info info,
        void **native, napi_value *argv, size_t paramLength);
};

struct AutoRef {
    AutoRef(napi_env env, napi_ref cb)
        : env_(env), cb_(cb)
    {
    }
    ~AutoRef()
    {
        if (env_ != nullptr && cb_ != nullptr) {
            (void)napi_delete_reference(env_, cb_);
        }
    }
    napi_env env_;
    napi_ref cb_;
};
} // namespace Media
} // namespace OHOS
#endif // AUDIO_HAPTIC_COMMON_NAPI_H