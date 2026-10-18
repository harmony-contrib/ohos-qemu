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

#include "audio_haptic_common_napi.h"

#include "access_token.h"
#include "accesstoken_kit.h"
#include "ipc_skeleton.h"
#include "tokenid_kit.h"

#include "audio_haptic_log.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticCommonNapi"};
}

namespace OHOS {
namespace Media {
const std::string NAPI_ERR_INPUT_INVALID_INFO = "input parameter check failed";
const std::string NAPI_ERR_OPERATE_NOT_ALLOWED_INFO = "Operate not permit in current state";
const std::string NAPI_ERR_IO_ERROR_INFO = "input or output error";
const std::string NAPI_ERR_SERVICE_DIED_INFO = "service died";
const std::string NAPI_ERR_UNSUPPORTED_FORMAT_INFO = "unsupport format";
const std::string NAPI_ERR_PARAM_OUT_OF_RANGE_INFO = "Parameter out of range";
const std::string NAPI_ERR_NOT_SUPPORTED_INFO = "Function is not supported in current device";
const std::string NAPI_ERR_PERMISSION_DENIED_INFO = "Caller is not a system application";

void AudioHapticCommonNapi::ThrowError(napi_env env, int32_t code)
{
    std::string messageValue = AudioHapticCommonNapi::GetMessageByCode(code);
    napi_throw_error(env, (std::to_string(code)).c_str(), messageValue.c_str());
}

void AudioHapticCommonNapi::ThrowError(napi_env env, int32_t code, const std::string &errMessage)
{
    napi_throw_error(env, (std::to_string(code)).c_str(), errMessage.c_str());
}

void AudioHapticCommonNapi::PromiseReject(napi_env env, napi_deferred deferred,
    const int32_t& errCode, const std::string& errMessage)
{
    napi_value error = nullptr;
    napi_value message = nullptr;
    napi_value code = nullptr;
    napi_create_int32(env, errCode, &code);
    napi_create_string_utf8(env, errMessage.c_str(), NAPI_AUTO_LENGTH, &message);
    napi_create_error(env, nullptr, message, &error);
    napi_set_named_property(env, error, "code", code);
    napi_reject_deferred(env, deferred, error);
}

void AudioHapticCommonNapi::PromiseReject(napi_env env, napi_deferred deferred, int32_t errCode)
{
    std::string messageValue = AudioHapticCommonNapi::GetMessageByCode(errCode);
    AudioHapticCommonNapi::PromiseReject(env, deferred, errCode, messageValue);
}

bool AudioHapticCommonNapi::InitNormalFunc(napi_env env, napi_callback_info info,
    void** native, napi_value* argv, size_t paramLength)
{
    napi_value thisVar = nullptr;
    size_t argc = paramLength;
    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    if (status != napi_ok || thisVar == nullptr) {
        MEDIA_LOGE("napi_get_cb_info fail");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return false;
    }

    if (argc != paramLength) {
        MEDIA_LOGE("invalid parameters");
        std::string logMsg = "requires " + std::to_string(paramLength) + " parameters";
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, logMsg);
        return false;
    }

    status = napi_unwrap(env, thisVar, native);
    if (status != napi_ok || *native == nullptr) {
        MEDIA_LOGE("Failed to unwrap object");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return false;
    }
    return true;
}

bool AudioHapticCommonNapi::InitPromiseFunc(napi_env env, napi_callback_info info,
    AsyncContext* asyncContext, napi_value* promise, size_t paramLength)
{
    if (asyncContext == nullptr) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return false;
    }
    napi_create_promise(env, &asyncContext->deferred, promise);
    napi_value thisVar = nullptr;
    size_t argc = paramLength;
    napi_status status = napi_get_cb_info(env, info, &argc, asyncContext->argv, &thisVar, nullptr);
    if (status != napi_ok || thisVar == nullptr) {
        MEDIA_LOGE("napi_get_cb_info fail");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_SERVICE_DIED);
        return false;
    }

    if (argc != paramLength) {
        MEDIA_LOGE("invalid parameters");
        std::string logMsg = "requires " + std::to_string(paramLength) + " parameters";
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, logMsg);
        return false;
    }
    status = napi_unwrap(env, thisVar, &asyncContext->objectInfo);
    if (status != napi_ok) {
        MEDIA_LOGE("Failed to unwrap object");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_SERVICE_DIED);
        return false;
    }
    return true;
}

bool AudioHapticCommonNapi::VerifyVibratePermission()
{
    const auto token = static_cast<Security::AccessToken::AccessTokenID>(IPCSkeleton::GetSelfTokenID());
    return token != 0 && Security::AccessToken::AccessTokenKit::VerifyAccessToken(token,
        "ohos.permission.VIBRATE") == Security::AccessToken::PERMISSION_GRANTED;
}

bool AudioHapticCommonNapi::VerifySelfSystemPermission()
{
    Security::AccessToken::FullTokenID selfTokenID = IPCSkeleton::GetSelfTokenID();
    return Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(selfTokenID);
}

std::string AudioHapticCommonNapi::GetMessageByCode(int32_t &code)
{
    std::string errMessage;
    switch (code) {
        case NAPI_ERR_VIBRATE_PERMISSION_DENIED:
            errMessage = "Permission denied: ohos.permission.VIBRATE";
            break;
        case NAPI_ERR_INPUT_INVALID:
            errMessage = NAPI_ERR_INPUT_INVALID_INFO;
            break;
        case NAPI_ERR_OPERATE_NOT_ALLOWED:
            errMessage = NAPI_ERR_OPERATE_NOT_ALLOWED_INFO;
            break;
        case NAPI_ERR_IO_ERROR:
            errMessage = NAPI_ERR_IO_ERROR_INFO;
            break;
        case NAPI_ERR_SERVICE_DIED:
            errMessage = NAPI_ERR_SERVICE_DIED_INFO;
            break;
        case NAPI_ERR_UNSUPPORTED_FORMAT:
            errMessage = NAPI_ERR_UNSUPPORTED_FORMAT_INFO;
            break;
        case NAPI_ERR_PARAM_OUT_OF_RANGE:
            errMessage = NAPI_ERR_PARAM_OUT_OF_RANGE_INFO;
            break;
        case NAPI_ERR_NOT_SUPPORTED:
            errMessage = NAPI_ERR_NOT_SUPPORTED_INFO;
            break;
        case NAPI_ERR_PERMISSION_DENIED:
            errMessage = NAPI_ERR_PERMISSION_DENIED_INFO;
            break;
        default:
            errMessage = NAPI_ERR_OPERATE_NOT_ALLOWED_INFO;
            code = NAPI_ERR_OPERATE_NOT_ALLOWED;
            break;
    }
    return errMessage;
}

std::string AudioHapticCommonNapi::GetStringArgument(napi_env env, napi_value value)
{
    std::string strValue = "";
    size_t bufLength = 0;
    napi_status status = napi_get_value_string_utf8(env, value, nullptr, 0, &bufLength);
    if (status == napi_ok && bufLength > 0 && bufLength < PATH_MAX) {
        char *buffer = static_cast<char *>(malloc((bufLength + 1) * sizeof(char)));
        CHECK_AND_RETURN_RET_LOG(buffer != nullptr, strValue, "GetStringArgument: no memory");
        status = napi_get_value_string_utf8(env, value, buffer, bufLength + 1, &bufLength);
        if (status == napi_ok) {
            MEDIA_LOGI("GetStringArgument: argument = %{public}s", buffer);
            strValue = buffer;
        }
        free(buffer);
        buffer = nullptr;
    }
    return strValue;
}
} // namespace Media
} // namespace OHOS