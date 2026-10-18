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

#include "audio_haptic_player_napi.h"
#include "audio_haptic_player_impl.h"

#include "audio_haptic_log.h"

namespace {

const std::string AUDIO_INTERRUPT_CALLBACK_NAME = "audioInterrupt";
const std::string END_OF_STREAM_CALLBACK_NAME = "endOfStream";
const double PRECISION = 100.00;

constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticPlayerNapi"};
}

namespace OHOS {
namespace Media {
const std::string AUDIO_HAPTIC_PLAYER_NAPI_CLASS_NAME = "AudioHapticPlayer";
thread_local napi_ref AudioHapticPlayerNapi::sConstructor_ = nullptr;
std::shared_ptr<AudioHapticPlayer> AudioHapticPlayerNapi::sAudioHapticPlayer_ = nullptr;

AudioHapticPlayerNapi::AudioHapticPlayerNapi() : env_(nullptr) {}

AudioHapticPlayerNapi::~AudioHapticPlayerNapi() = default;

napi_value AudioHapticPlayerNapi::Init(napi_env env, napi_value exports)
{
    napi_status status;
    napi_value ctorObj;
    int32_t refCount = 1;

    napi_property_descriptor audioHapticPlayerProp[] = {
        DECLARE_NAPI_FUNCTION("isMuted", IsMuted),
        DECLARE_NAPI_FUNCTION("start", Start),
        DECLARE_NAPI_FUNCTION("stop", Stop),
        DECLARE_NAPI_FUNCTION("release", Release),
        DECLARE_NAPI_FUNCTION("on", On),
        DECLARE_NAPI_FUNCTION("off", Off),
        DECLARE_NAPI_FUNCTION("setVolume", SetVolume),
        DECLARE_NAPI_FUNCTION("setHapticsIntensity", SetHapticsIntensity),
        DECLARE_NAPI_FUNCTION("enableHapticsInSilentMode", EnableHapticsInSilentMode),
        DECLARE_NAPI_FUNCTION("isHapticsIntensityAdjustmentSupported", IsHapticsIntensityAdjustmentSupported),
        DECLARE_NAPI_FUNCTION("setLoop", SetLoop),
        DECLARE_NAPI_FUNCTION("setHapticsRamp", SetHapticsRamp),
        DECLARE_NAPI_FUNCTION("isHapticsRampSupported", IsHapticsRampSupported),
    };

    status = napi_define_class(env, AUDIO_HAPTIC_PLAYER_NAPI_CLASS_NAME.c_str(), NAPI_AUTO_LENGTH, Constructor,
        nullptr, sizeof(audioHapticPlayerProp) / sizeof(audioHapticPlayerProp[0]), audioHapticPlayerProp, &ctorObj);
    if (status == napi_ok) {
        if (napi_create_reference(env, ctorObj, refCount, &sConstructor_) == napi_ok) {
            status = napi_set_named_property(env, exports, AUDIO_HAPTIC_PLAYER_NAPI_CLASS_NAME.c_str(), ctorObj);
            if (status == napi_ok) {
                return exports;
            }
        }
    }

    return nullptr;
}

napi_value AudioHapticPlayerNapi::Constructor(napi_env env, napi_callback_info info)
{
    napi_status status;
    napi_value result = nullptr;
    napi_value thisVar = nullptr;

    napi_get_undefined(env, &result);
    status = napi_get_cb_info(env, info, nullptr, nullptr, &thisVar, nullptr);
    if (status == napi_ok && thisVar != nullptr) {
        std::unique_ptr<AudioHapticPlayerNapi> obj = std::make_unique<AudioHapticPlayerNapi>();
        if (obj != nullptr) {
            obj->env_ = env;
            if (obj->sAudioHapticPlayer_ != nullptr) {
                obj->audioHapticPlayer_ = move(obj->sAudioHapticPlayer_);
            } else {
                MEDIA_LOGE("Failed to create sAudioHapticPlayer_ instance.");
                return result;
            }

            if (obj->audioHapticPlayer_ != nullptr && obj->callbackNapi_ == nullptr) {
                obj->callbackNapi_ = std::make_shared<AudioHapticPlayerCallbackNapi>(env);
                CHECK_AND_RETURN_RET_LOG(obj->callbackNapi_ != nullptr, result, "No memory");
                int32_t ret = obj->audioHapticPlayer_->SetAudioHapticPlayerCallback(obj->callbackNapi_);
                // The actual AudioHapticPlayerFactory constructs AudioHapticPlayerImpl
                // for both latency branches. No RTTI or public-vtable extension.
                std::static_pointer_cast<AudioHapticPlayerImpl>(obj->audioHapticPlayer_)->
                    SetPublicationCallback(obj->callbackNapi_);
                MEDIA_LOGI("AHPublication stage=napi-bind wrapper=%{public}p player=%{public}p callback=%{public}p",
                    obj.get(), std::static_pointer_cast<AudioHapticPlayerImpl>(obj->audioHapticPlayer_).get(),
                    obj->callbackNapi_.get());
                MEDIA_LOGI("Constructor: SetAudioHapticPlayerCallback %{public}s",
                    ret == 0 ? "succeess" : "failed");
            }

            status = napi_wrap(env, thisVar, reinterpret_cast<void*>(obj.get()),
                AudioHapticPlayerNapi::Destructor, nullptr, nullptr);
            if (status == napi_ok) {
                obj.release();
                return thisVar;
            } else {
                MEDIA_LOGE("Failed to wrap the native audioHapticPlayer object with JS.");
            }
        }
    }

    return result;
}

void AudioHapticPlayerNapi::Destructor(napi_env env, void *nativeObject, void *finalize_hint)
{
    AudioHapticPlayerNapi *audioHapticPlayerHelper = reinterpret_cast<AudioHapticPlayerNapi*>(nativeObject);
    if (audioHapticPlayerHelper != nullptr) {
        audioHapticPlayerHelper->~AudioHapticPlayerNapi();
    }
}

napi_value AudioHapticPlayerNapi::CreatePlayerInstance(napi_env env,
    std::shared_ptr<AudioHapticPlayer> &audioHapticPlayer)
{
    napi_status status;
    napi_value result = nullptr;
    napi_value ctor;

    status = napi_get_reference_value(env, sConstructor_, &ctor);
    if (status == napi_ok) {
        sAudioHapticPlayer_ = audioHapticPlayer;
        status = napi_new_instance(env, ctor, 0, nullptr, &result);
        if (status == napi_ok) {
            return result;
        } else {
            MEDIA_LOGE("CreatePlayerInstance: New instance could not be obtained.");
        }
    }

    napi_get_undefined(env, &result);
    return result;
}

napi_value AudioHapticPlayerNapi::IsHapticsRampSupported(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    if (!AudioHapticCommonNapi::VerifySelfSystemPermission()) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_PERMISSION_DENIED);
        return result;
    }

    void *native = nullptr;
    napi_value argv[ARGS_ONE] = {0};
    if (!AudioHapticCommonNapi::InitNormalFunc(env, info, &native, argv, ARGS_ZERO)) {
        return result;
    }

    auto *audioHapticPlayerNapi = reinterpret_cast<AudioHapticPlayerNapi *>(native);
    if (audioHapticPlayerNapi == nullptr || audioHapticPlayerNapi->audioHapticPlayer_ == nullptr) {
        MEDIA_LOGE("IsHapticsIntensityAdjustmentSupported: unwrap failure!");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return result;
    }
    bool isSupported = audioHapticPlayerNapi->audioHapticPlayer_->IsHapticsRampSupported();

    napi_get_boolean(env, isSupported, &result);
    return result;
}

napi_value AudioHapticPlayerNapi::IsHapticsIntensityAdjustmentSupported(napi_env env,
                                                                        napi_callback_info info)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    if (!AudioHapticCommonNapi::VerifySelfSystemPermission()) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_PERMISSION_DENIED);
        return result;
    }

    void *native = nullptr;
    napi_value argv[ARGS_ONE] = {0};
    if (!AudioHapticCommonNapi::InitNormalFunc(env, info, &native, argv, ARGS_ZERO)) {
        return result;
    }

    auto *audioHapticPlayerNapi = reinterpret_cast<AudioHapticPlayerNapi *>(native);
    if (audioHapticPlayerNapi == nullptr || audioHapticPlayerNapi->audioHapticPlayer_ == nullptr) {
        MEDIA_LOGE("IsHapticsIntensityAdjustmentSupported: unwrap failure!");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return result;
    }
    bool isSupported = audioHapticPlayerNapi->audioHapticPlayer_->IsHapticsIntensityAdjustmentSupported();

    napi_get_boolean(env, isSupported, &result);
    return result;
}

napi_value AudioHapticPlayerNapi::EnableHapticsInSilentMode(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    if (!AudioHapticCommonNapi::VerifySelfSystemPermission()) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_PERMISSION_DENIED);
        return result;
    }

    void *native = nullptr;
    napi_value argv[ARGS_ONE] = {0};
    if (!AudioHapticCommonNapi::InitNormalFunc(env, info, &native, argv, ARGS_ONE)) {
        return result;
    }

    auto *audioHapticPlayerNapi = reinterpret_cast<AudioHapticPlayerNapi *>(native);
    if (audioHapticPlayerNapi == nullptr || audioHapticPlayerNapi->audioHapticPlayer_ == nullptr) {
        MEDIA_LOGE("EnableHapticsInSilentMode: unwrap failure!");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_SERVICE_DIED);
        return result;
    }

    bool enable = false;
    if (napi_get_value_bool(env, argv[PARAM0], &enable) != napi_ok) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "input param is invalid");
        return result;
    }

    int32_t ret = audioHapticPlayerNapi->audioHapticPlayer_->EnableHapticsInSilentMode(enable);
    if (ret == NAPI_ERR_OPERATE_NOT_ALLOWED) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
        return result;
    }
    return result;
}

napi_value AudioHapticPlayerNapi::IsMuted(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_get_boolean(env, false, &result);

    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result, "IsMuted: napi_get_cb_info fail");
    if (argc != ARGS_ONE) {
        MEDIA_LOGE("IsMuted: requires 1 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "mandatory parameters are left unspecified");
        return result;
    }

    void *native = nullptr;
    status = napi_unwrap(env, thisVar, &native);
    auto *audioHapticPlayerNapi = reinterpret_cast<AudioHapticPlayerNapi *>(native);
    if (status != napi_ok || audioHapticPlayerNapi == nullptr) {
        MEDIA_LOGE("IsMuted: unwrap failure!");
        return result;
    }

    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, argv[PARAM0], &valueType);
    int32_t jsAudioHapticType = -1;
    if (valueType == napi_number) {
        napi_get_value_int32(env, argv[PARAM0], &jsAudioHapticType);
    }
    if (!IsLegalAudioHapticType(jsAudioHapticType)) {
        MEDIA_LOGE("IsMuted: the param type mismatch");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID,
            "parameter verification failed: The param of type must be enum AudioHapticType");
        return result;
    }

    AudioHapticType audioHapticType = static_cast<AudioHapticType>(jsAudioHapticType);
    bool isMuted = audioHapticPlayerNapi->audioHapticPlayer_->IsMuted(audioHapticType);
    napi_get_boolean(env, isMuted, &result);

    return result;
}

bool AudioHapticPlayerNapi::IsLegalAudioHapticType(int32_t audioHapticType)
{
    switch (audioHapticType) {
        case AUDIO_HAPTIC_TYPE_AUDIO:
        case AUDIO_HAPTIC_TYPE_HAPTIC:
            return true;
        default:
            break;
    }
    MEDIA_LOGE("IsLegalAudioHapticType: audioHapticType %{public}d is invalid", audioHapticType);
    return false;
}

bool AudioHapticPlayerNapi::IsLegalVolumeOrIntensity(double number)
{
    return number >= 0.0 && number <= 1.0;
}

bool AudioHapticPlayerNapi::JudgeVolume(napi_env env, std::unique_ptr<VolumeContext>& asyncContext)
{
    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, asyncContext->argv[PARAM0], &valueType);
    double volume = -1.00;
    if (valueType == napi_number) {
        napi_get_value_double(env, asyncContext->argv[PARAM0], &volume);
    }
    if (!IsLegalVolumeOrIntensity(volume)) {
        MEDIA_LOGE("SetVolume: the param is invalid");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_PARAM_OUT_OF_RANGE);
        return false;
    }

    asyncContext->volume = static_cast<float>(std::round(volume * PRECISION) / PRECISION);
    return true;
}

bool AudioHapticPlayerNapi::JudgeIntensity(napi_env env, std::unique_ptr<VibrationContext>& asyncContext)
{
    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, asyncContext->argv[PARAM0], &valueType);
    double intensity = -1.00;
    if (valueType == napi_number) {
        napi_get_value_double(env, asyncContext->argv[PARAM0], &intensity);
    }
    if (!IsLegalVolumeOrIntensity(intensity)) {
        MEDIA_LOGE("SetIntensity: the param is invalid");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_PARAM_OUT_OF_RANGE);
        return false;
    }

    asyncContext->intensity = static_cast<float>(std::round(intensity * PRECISION) / PRECISION);
    return true;
}

bool AudioHapticPlayerNapi::JudgeRamp(napi_env env, std::unique_ptr<RampContext> &asyncContext)
{
    if (napi_get_value_int32(env, asyncContext->argv[PARAM0], &asyncContext->duration) != napi_ok) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "invalid duration");
        return false;
    }
    int32_t notLessThanDurationMs = 100;
    if (asyncContext->duration < notLessThanDurationMs) {
        MEDIA_LOGE("SetHapticsRamp: the duration is invalid");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            NAPI_ERR_PARAM_OUT_OF_RANGE, "duration not less than 100 ms");
        return false;
    }

    double startIntensity = 0.00;
    if (napi_get_value_double(env, asyncContext->argv[PARAM1], &startIntensity) != napi_ok) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "invalid startIntensity");
        return false;
    }
    if (!IsLegalVolumeOrIntensity(startIntensity)) {
        MEDIA_LOGE("SetHapticsRamp: startIntensity is invalid");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            NAPI_ERR_PARAM_OUT_OF_RANGE, "startIntensity's value ranges from 0.00 to 1.00");
        return false;
    }
    asyncContext->startIntensity = static_cast<float>(std::round(startIntensity * PRECISION) / PRECISION);

    double endIntensity = 0.00;
    if (napi_get_value_double(env, asyncContext->argv[PARAM2], &endIntensity) != napi_ok) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "invalid endIntensity");
        return false;
    }
    if (!IsLegalVolumeOrIntensity(endIntensity)) {
        MEDIA_LOGE("SetHapticsRamp: endIntensity is invalid");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            NAPI_ERR_PARAM_OUT_OF_RANGE, "endIntensity's value ranges from 0.00 to 1.00");
        return false;
    }
    asyncContext->endIntensity = static_cast<float>(std::round(endIntensity * PRECISION) / PRECISION);

    return true;
}

void AudioHapticPlayerNapi::CommonAsyncCallbackComp(napi_env env, napi_status status, void *data)
{
    auto context = static_cast<AudioHapticPlayerAsyncContext *>(data);
    napi_value result[2] = {};

    napi_get_undefined(env, &result[PARAM1]);
    if (!context->status) {
        napi_get_undefined(env, &result[PARAM0]);
    } else {
        // Preserve the actual native failure as the standard public numeric
        // BusinessError, including invalid-operation after Release.
        int32_t errorCode = NAPI_ERR_OPERATE_NOT_ALLOWED;
        if (context->status == MSERR_OPEN_FILE_FAILED) { errorCode = NAPI_ERR_IO_ERROR; }
        else if (context->status == MSERR_SERVICE_DIED) { errorCode = NAPI_ERR_SERVICE_DIED; }
        else if (context->status == MSERR_UNSUPPORT_FILE) { errorCode = NAPI_ERR_UNSUPPORTED_FORMAT; }
        napi_value message = nullptr;
        napi_value code = nullptr;
        int32_t messageCode = errorCode;
        const std::string errorMessage = AudioHapticCommonNapi::GetMessageByCode(messageCode);
        napi_create_string_utf8(env, errorMessage.c_str(), NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, nullptr, message, &result[PARAM0]);
        napi_create_int32(env, errorCode, &code);
        napi_set_named_property(env, result[PARAM0], "code", code);
    }

    if (context->deferred) {
        if (!context->status) {
            napi_resolve_deferred(env, context->deferred, result[PARAM1]);
        } else {
            napi_reject_deferred(env, context->deferred, result[PARAM0]);
        }
    }
    napi_delete_async_work(env, context->work);

    delete context;
    context = nullptr;
}

napi_value AudioHapticPlayerNapi::SetHapticsIntensity(napi_env env, napi_callback_info info)
{
    std::unique_ptr<VibrationContext> asyncContext = std::make_unique<VibrationContext>();
    napi_value promise = nullptr;
    if (!AudioHapticCommonNapi::InitPromiseFunc(env, info, asyncContext.get(), &promise, ARGS_ONE)) {
        return promise;
    }
    if (!AudioHapticCommonNapi::VerifySelfSystemPermission()) {
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_PERMISSION_DENIED);
        return promise;
    }
    if (!JudgeIntensity(env, asyncContext)) {
        return promise;
    }

    napi_value funcName = nullptr;
    napi_create_string_utf8(env, "SetVibrationIntensity", NAPI_AUTO_LENGTH, &funcName);
    napi_status status = napi_create_async_work(env, nullptr, funcName,
        [](napi_env env, void *data) {
            auto context = static_cast<VibrationContext*>(data);
            AudioHapticPlayerNapi* object = reinterpret_cast<AudioHapticPlayerNapi*>(context->objectInfo);
            if (object == nullptr || object->audioHapticPlayer_ == nullptr) {
                context->result = NAPI_ERR_SERVICE_DIED;
            } else {
                context->result = object->audioHapticPlayer_->SetHapticIntensity(context->intensity * PRECISION);
            }
        },
        [](napi_env env, napi_status status, void *data) {
            auto context = static_cast<VibrationContext*>(data);
            if (context->deferred) {
                if (context->result == 0) {
                    napi_value result;
                    napi_get_undefined(env, &result);
                    napi_resolve_deferred(env, context->deferred, result);
                } else {
                    AudioHapticCommonNapi::PromiseReject(env, context->deferred, context->result);
                }
            }
            napi_delete_async_work(env, context->work);
            delete context;
            context = nullptr;
        }, static_cast<void*>(asyncContext.get()), &asyncContext->work);
    if (status != napi_ok) {
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, status, "Failed to get create async work");
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return promise;
}

napi_value AudioHapticPlayerNapi::SetVolume(napi_env env, napi_callback_info info)
{
    std::unique_ptr<VolumeContext> asyncContext = std::make_unique<VolumeContext>();
    napi_value promise = nullptr;
    if (!AudioHapticCommonNapi::InitPromiseFunc(env, info, asyncContext.get(), &promise, ARGS_ONE)) {
        return promise;
    }

    if (!JudgeVolume(env, asyncContext)) {
        return promise;
    }

    napi_value funcName = nullptr;
    napi_create_string_utf8(env, "SetVolume", NAPI_AUTO_LENGTH, &funcName);
    napi_status status = napi_create_async_work(
        env,
        nullptr,
        funcName,
        [](napi_env env, void *data) {
            auto context = static_cast<VolumeContext*>(data);
            AudioHapticPlayerNapi* object = reinterpret_cast<AudioHapticPlayerNapi*>(context->objectInfo);

            context->result = object->audioHapticPlayer_->SetVolume(context->volume);
        },
        [](napi_env env, napi_status status, void *data) {
            auto context = static_cast<VolumeContext*>(data);
            if (context->deferred) {
                if (context->result == 0) {
                    napi_value result;
                    napi_get_undefined(env, &result);
                    napi_resolve_deferred(env, context->deferred, result);
                } else {
                    AudioHapticCommonNapi::PromiseReject(env, context->deferred,
                        context->result, "Failed to set volume");
                }
            }
            napi_delete_async_work(env, context->work);
            delete context;
            context = nullptr;
        },
        static_cast<void*>(asyncContext.get()),
        &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("Start: Failed to get create async work");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            status, "Failed to get create async work");
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return promise;
}

napi_value AudioHapticPlayerNapi::SetHapticsRamp(napi_env env, napi_callback_info info)
{
    std::unique_ptr<RampContext> asyncContext = std::make_unique<RampContext>();
    napi_value promise = nullptr;
    if (!AudioHapticCommonNapi::InitPromiseFunc(env, info, asyncContext.get(), &promise, ARGS_THREE)) {
        return promise;
    }
    if (!AudioHapticCommonNapi::VerifySelfSystemPermission()) {
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_PERMISSION_DENIED);
        return promise;
    }
    if (!JudgeRamp(env, asyncContext)) {
        return promise;
    }
    napi_value funcName = nullptr;
    napi_create_string_utf8(env, "SetHapticsRamp", NAPI_AUTO_LENGTH, &funcName);
    napi_status status = napi_create_async_work(env, nullptr, funcName,
        [](napi_env env, void *data) {
            auto context = static_cast<RampContext*>(data);
            AudioHapticPlayerNapi* object = reinterpret_cast<AudioHapticPlayerNapi*>(context->objectInfo);
            if (object != nullptr && object->audioHapticPlayer_ != nullptr) {
                context->result = object->audioHapticPlayer_->SetHapticsRamp(context->duration,
                    context->startIntensity * PRECISION, context->endIntensity * PRECISION);
            }
        },
        [](napi_env env, napi_status status, void *data) {
            auto context = static_cast<RampContext*>(data);
            if (context->deferred) {
                if (context->result == 0) {
                    napi_value result;
                    napi_get_undefined(env, &result);
                    napi_resolve_deferred(env, context->deferred, result);
                } else {
                    AudioHapticCommonNapi::PromiseReject(env, context->deferred, context->result);
                }
            }
            napi_delete_async_work(env, context->work);
            delete context;
            context = nullptr;
        }, static_cast<void*>(asyncContext.get()), &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("Start: Failed to get create async work");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, status, "Failed to get create async work");
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }
    return promise;
}

napi_value AudioHapticPlayerNapi::SetLoop(napi_env env, napi_callback_info info)
{
    std::unique_ptr<LoopContext> asyncContext = std::make_unique<LoopContext>();
    napi_value promise = nullptr;
    if (!AudioHapticCommonNapi::InitPromiseFunc(env, info, asyncContext.get(), &promise, ARGS_ONE)) {
        return promise;
    }

    if (napi_get_value_bool(env, asyncContext->argv[PARAM0], &asyncContext->loop) != napi_ok) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "input param is invalid");
        return promise;
    }

    napi_value funcName = nullptr;
    napi_create_string_utf8(env, "SetLoop", NAPI_AUTO_LENGTH, &funcName);
    napi_status status = napi_create_async_work(env, nullptr, funcName,
        [](napi_env env, void *data) {
            auto context = static_cast<LoopContext*>(data);
            AudioHapticPlayerNapi* object = reinterpret_cast<AudioHapticPlayerNapi*>(context->objectInfo);
            if (object != nullptr && object->audioHapticPlayer_ != nullptr) {
                context->result = object->audioHapticPlayer_->SetLoop(context->loop);
            }
        },
        [](napi_env env, napi_status status, void *data) {
            auto context = static_cast<LoopContext*>(data);
            if (context->deferred) {
                if (context->result == 0) {
                    napi_value result;
                    napi_get_undefined(env, &result);
                    napi_resolve_deferred(env, context->deferred, result);
                } else {
                    AudioHapticCommonNapi::PromiseReject(env, context->deferred, context->result);
                }
            }
            napi_delete_async_work(env, context->work);
            delete context;
            context = nullptr;
        }, static_cast<void*>(asyncContext.get()), &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("Start: Failed to get create async work");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            status, "Failed to get create async work");
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return promise;
}

napi_value AudioHapticPlayerNapi::Start(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result, "Start: napi_get_cb_info fail");
    if (argc != 0) {
        MEDIA_LOGE("Start: requires 0 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    std::unique_ptr<AudioHapticPlayerAsyncContext> asyncContext = std::make_unique<AudioHapticPlayerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    if (status == napi_ok && asyncContext->objectInfo != nullptr) {
        napi_create_promise(env, &asyncContext->deferred, &result);
        napi_create_string_utf8(env, "Start", NAPI_AUTO_LENGTH, &resource);
        status = napi_create_async_work(env, nullptr, resource,
            [](napi_env env, void *data) {
                AudioHapticPlayerAsyncContext *context = static_cast<AudioHapticPlayerAsyncContext*>(data);
                context->status = context->objectInfo->audioHapticPlayer_->Start();
            },
            CommonAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
        if (status != napi_ok) {
            MEDIA_LOGE("Start: Failed to get create async work");
            napi_get_undefined(env, &result);
        } else {
            napi_queue_async_work(env, asyncContext->work);
            asyncContext.release();
        }
    }

    return result;
}

napi_value AudioHapticPlayerNapi::Stop(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result, "Stop: napi_get_cb_info fail");
    if (argc != 0) {
        MEDIA_LOGE("Stop: requires 0 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    std::unique_ptr<AudioHapticPlayerAsyncContext> asyncContext = std::make_unique<AudioHapticPlayerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    if (status == napi_ok && asyncContext->objectInfo != nullptr) {
        napi_create_promise(env, &asyncContext->deferred, &result);
        napi_create_string_utf8(env, "Stop", NAPI_AUTO_LENGTH, &resource);
        status = napi_create_async_work(env, nullptr, resource,
            [](napi_env env, void *data) {
                AudioHapticPlayerAsyncContext *context = static_cast<AudioHapticPlayerAsyncContext*>(data);
                context->status = context->objectInfo->audioHapticPlayer_->Stop();
            },
            CommonAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
        if (status != napi_ok) {
            MEDIA_LOGE("Stop: Failed to get create async work");
            napi_get_undefined(env, &result);
        } else {
            napi_queue_async_work(env, asyncContext->work);
            asyncContext.release();
        }
    }

    return result;
}

napi_value AudioHapticPlayerNapi::Release(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result, "Release: napi_get_cb_info fail");
    if (argc != 0) {
        MEDIA_LOGE("Release: requires 0 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    std::unique_ptr<AudioHapticPlayerAsyncContext> asyncContext = std::make_unique<AudioHapticPlayerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    if (status == napi_ok && asyncContext->objectInfo != nullptr) {
        napi_create_promise(env, &asyncContext->deferred, &result);
        napi_create_string_utf8(env, "Release", NAPI_AUTO_LENGTH, &resource);
        status = napi_create_async_work(env, nullptr, resource,
            [](napi_env env, void *data) {
                AudioHapticPlayerAsyncContext *context = static_cast<AudioHapticPlayerAsyncContext*>(data);
                context->status = context->objectInfo->audioHapticPlayer_->Release();
            },
            CommonAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
        if (status != napi_ok) {
            MEDIA_LOGE("Release: Failed to get create async work");
            napi_get_undefined(env, &result);
        } else {
            napi_queue_async_work(env, asyncContext->work);
            asyncContext.release();
        }
    }

    return result;
}

napi_value AudioHapticPlayerNapi::On(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {nullptr};
    napi_value jsThis = nullptr;
    napi_status status = napi_get_cb_info(env, info, &argc, argv, &jsThis, nullptr);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && jsThis != nullptr, result, "On: napi_get_cb_info fail");
    if (argc != ARGS_TWO) {
        MEDIA_LOGE("On: requires 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    napi_valuetype argvType = napi_undefined;
    napi_typeof(env, argv[PARAM0], &argvType);
    if (argvType != napi_string) {
        MEDIA_LOGE("On: the first parameter must be napi_string");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }
    std::string callbackName = AudioHapticCommonNapi::GetStringArgument(env, argv[0]);
    MEDIA_LOGI("On: callbackName: %{public}s", callbackName.c_str());

    napi_typeof(env, argv[PARAM1], &argvType);
    if (argvType != napi_function) {
        MEDIA_LOGE("On: the second parameter must be napi_function");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    return RegisterCallback(env, jsThis, argv, callbackName);
}

napi_value AudioHapticPlayerNapi::RegisterCallback(napi_env env, napi_value jsThis, napi_value* argv,
    const std::string& cbName)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    AudioHapticPlayerNapi *audioHapticPlayerNapi = nullptr;
    napi_status status = napi_unwrap(env, jsThis, reinterpret_cast<void **>(&audioHapticPlayerNapi));
    if (status != napi_ok || audioHapticPlayerNapi == nullptr || audioHapticPlayerNapi->audioHapticPlayer_ == nullptr) {
        MEDIA_LOGE("RegisterCallback: Failed to get audioHapticPlayer_");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
        return result;
    }

    if (!cbName.compare(AUDIO_INTERRUPT_CALLBACK_NAME) ||
        !cbName.compare(END_OF_STREAM_CALLBACK_NAME)) {
        result = RegisterAudioHapticPlayerCallback(env, argv, cbName, audioHapticPlayerNapi);
    } else {
        MEDIA_LOGE("RegisterCallback: the callback name: %{public}s is not supported", cbName.c_str());
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    return result;
}

napi_value AudioHapticPlayerNapi::RegisterAudioHapticPlayerCallback(napi_env env, napi_value* argv,
    const std::string& cbName, AudioHapticPlayerNapi *audioHapticPlayerNapi)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    if (audioHapticPlayerNapi->callbackNapi_ == nullptr) {
        MEDIA_LOGE("RegisterAudioHapticPlayerCallback: callbackNapi_ is null");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
        return result;
    }
    audioHapticPlayerNapi->callbackNapi_->SaveCallbackReference(cbName, argv[PARAM1]);

    return result;
}

napi_value AudioHapticPlayerNapi::Off(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {nullptr};
    napi_value jsThis = nullptr;
    napi_status status = napi_get_cb_info(env, info, &argc, argv, &jsThis, nullptr);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && jsThis != nullptr, result, "Off: napi_get_cb_info fail");
    if (argc != ARGS_ONE && argc != ARGS_TWO) {
        MEDIA_LOGE("Off: requires 1 or 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    napi_valuetype argvType = napi_undefined;
    napi_typeof(env, argv[PARAM0], &argvType);
    if (argvType != napi_string) {
        MEDIA_LOGE("Off: the parameter must be napi_string");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }
    std::string callbackName = AudioHapticCommonNapi::GetStringArgument(env, argv[0]);
    MEDIA_LOGI("Off: callbackName: %{public}s", callbackName.c_str());

    return UnregisterCallback(env, jsThis, callbackName);
}

napi_value AudioHapticPlayerNapi::UnregisterCallback(napi_env env, napi_value jsThis, const std::string &cbName)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    AudioHapticPlayerNapi *audioHapticPlayerNapi = nullptr;
    napi_status status = napi_unwrap(env, jsThis, reinterpret_cast<void **>(&audioHapticPlayerNapi));
    if (status != napi_ok || audioHapticPlayerNapi == nullptr || audioHapticPlayerNapi->audioHapticPlayer_ == nullptr) {
        MEDIA_LOGE("UnregisterCallback: Failed to get audioHapticPlayer_");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
        return result;
    }

    if (!cbName.compare(AUDIO_INTERRUPT_CALLBACK_NAME) ||
        !cbName.compare(END_OF_STREAM_CALLBACK_NAME)) {
        result = UnregisterAudioHapticPlayerCallback(env, cbName, audioHapticPlayerNapi);
    } else {
        MEDIA_LOGE("UnregisterCallback: the callback name: %{public}s is not supported", cbName.c_str());
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    return result;
}

napi_value AudioHapticPlayerNapi::UnregisterAudioHapticPlayerCallback(napi_env env, const std::string& cbName,
    AudioHapticPlayerNapi *audioHapticPlayerNapi)
{
    napi_value result = nullptr;
    napi_get_undefined(env, &result);

    if (audioHapticPlayerNapi->callbackNapi_ == nullptr) {
        MEDIA_LOGE("RegisterAudioHapticPlayerCallback: callbackNapi_ is null");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
        return result;
    }
    audioHapticPlayerNapi->callbackNapi_->RemoveCallbackReference(cbName);

    return result;
}
} // namespace Media
} // namespace OHOS