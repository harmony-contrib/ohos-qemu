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

#include "audio_haptic_manager_napi.h"

#include "audio_haptic_file_descriptor_napi.h"
#include "audio_haptic_player_napi.h"

#include "audio_haptic_log.h"

namespace {
const int32_t SIZE = 1024;

const int ERROR = -1;
const int SUCCESS = 0;

constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticManagerNapi"};
}

namespace OHOS {
namespace Media {
const std::string AUDIO_HAPTIC_MANAGER_NAPI_CLASS_NAME = "AudioHapticManager";
const std::map<std::string, AudioLatencyMode> audioLatencyModeMap = {
    {"AUDIO_LATENCY_MODE_NORMAL", AUDIO_LATENCY_MODE_NORMAL},
    {"AUDIO_LATENCY_MODE_FAST", AUDIO_LATENCY_MODE_FAST}
};
const std::map<std::string, AudioHapticType> audioHapticTypeMap = {
    {"AUDIO_HAPTIC_TYPE_AUDIO", AUDIO_HAPTIC_TYPE_AUDIO},
    {"AUDIO_HAPTIC_TYPE_HAPTIC", AUDIO_HAPTIC_TYPE_HAPTIC}
};
thread_local napi_ref AudioHapticManagerNapi::sConstructor_ = nullptr;
thread_local napi_ref AudioHapticManagerNapi::sAudioLatencyMode_ = nullptr;
thread_local napi_ref AudioHapticManagerNapi::sAudioHapticType_ = nullptr;

AudioHapticManagerNapi::AudioHapticManagerNapi()
    : env_(nullptr), audioHapticMgrClient_(nullptr) {}

AudioHapticManagerNapi::~AudioHapticManagerNapi() = default;

napi_status AudioHapticManagerNapi::AddNamedProperty(napi_env env, napi_value object, const std::string name,
    int32_t enumValue)
{
    napi_status status;
    napi_value napiValue;

    status = napi_create_int32(env, enumValue, &napiValue);
    if (status == napi_ok) {
        status = napi_set_named_property(env, object, name.c_str(), napiValue);
    }

    return status;
}

napi_value AudioHapticManagerNapi::CreateAudioLatencyModeObject(napi_env env)
{
    napi_value result = nullptr;
    napi_status status;
    std::string propName;
    int32_t refCount = 1;

    status = napi_create_object(env, &result);
    if (status == napi_ok) {
        for (auto &iter: audioLatencyModeMap) {
            propName = iter.first;
            status = AddNamedProperty(env, result, propName, iter.second);
            if (status != napi_ok) {
                MEDIA_LOGE("CreateAudioLatencyModeObject: Failed to add named prop!");
                break;
            }
            propName.clear();
        }
        if (status == napi_ok) {
            status = napi_create_reference(env, result, refCount, &sAudioLatencyMode_);
            if (status == napi_ok) {
                return result;
            }
        }
    }
    napi_get_undefined(env, &result);

    return result;
}

napi_value AudioHapticManagerNapi::CreateAudioHapticTypeObject(napi_env env)
{
    napi_value result = nullptr;
    napi_status status = napi_create_object(env, &result);
    if (status == napi_ok) {
        std::string propName;
        for (auto &iter: audioHapticTypeMap) {
            propName = iter.first;
            status = AddNamedProperty(env, result, propName, iter.second);
            if (status != napi_ok) {
                MEDIA_LOGE("CreateAudioHapticTypeObject: Failed to add named prop!");
                break;
            }
            propName.clear();
        }
        if (status == napi_ok) {
            int32_t refCount = 1;
            status = napi_create_reference(env, result, refCount, &sAudioHapticType_);
            if (status == napi_ok) {
                return result;
            }
        }
    }
    napi_get_undefined(env, &result);

    return result;
}

napi_value AudioHapticManagerNapi::Init(napi_env env, napi_value exports)
{
    napi_status status;
    napi_value ctorObj;
    int32_t refCount = 1;

    napi_property_descriptor audioHapticMgrProp[] = {
        DECLARE_NAPI_FUNCTION("registerSource", RegisterSource),
        DECLARE_NAPI_FUNCTION("registerSourceFromFd", RegisterSourceFromFd),
        DECLARE_NAPI_FUNCTION("unregisterSource", UnregisterSource),
        DECLARE_NAPI_FUNCTION("setAudioLatencyMode", SetAudioLatencyMode),
        DECLARE_NAPI_FUNCTION("setStreamUsage", SetStreamUsage),
        DECLARE_NAPI_FUNCTION("createPlayer", CreatePlayer),
    };

    napi_property_descriptor staticProp[] = {
        DECLARE_NAPI_STATIC_FUNCTION("getAudioHapticManager", GetAudioHapticManager),
        DECLARE_NAPI_PROPERTY("AudioLatencyMode", CreateAudioLatencyModeObject(env)),
        DECLARE_NAPI_PROPERTY("AudioHapticType", CreateAudioHapticTypeObject(env)),
    };

    status = napi_define_class(env, AUDIO_HAPTIC_MANAGER_NAPI_CLASS_NAME.c_str(), NAPI_AUTO_LENGTH, Construct,
        nullptr, sizeof(audioHapticMgrProp) / sizeof(audioHapticMgrProp[0]), audioHapticMgrProp, &ctorObj);
    if (status == napi_ok) {
        if (napi_create_reference(env, ctorObj, refCount, &sConstructor_) == napi_ok) {
            if (napi_set_named_property(env, exports,
                AUDIO_HAPTIC_MANAGER_NAPI_CLASS_NAME.c_str(), ctorObj) == napi_ok &&
                napi_define_properties(env, exports,
                sizeof(staticProp) / sizeof(staticProp[0]), staticProp) == napi_ok) {
                    return exports;
            }
        }
    }

    return nullptr;
}

napi_value AudioHapticManagerNapi::Construct(napi_env env, napi_callback_info info)
{
    napi_status status;
    napi_value result = nullptr;
    napi_value thisVar = nullptr;

    napi_get_undefined(env, &result);
    status = napi_get_cb_info(env, info, nullptr, nullptr, &thisVar, nullptr);
    if (status == napi_ok && thisVar != nullptr) {
        std::unique_ptr<AudioHapticManagerNapi> obj = std::make_unique<AudioHapticManagerNapi>();
        if (obj != nullptr) {
            obj->env_ = env;
            obj->audioHapticMgrClient_ = AudioHapticManagerFactory::CreateAudioHapticManager();
            if (obj->audioHapticMgrClient_ == nullptr) {
                MEDIA_LOGE("Failed to create audioHapticMgrClient_ instance.");
                return result;
            }

            status = napi_wrap(env, thisVar, reinterpret_cast<void*>(obj.get()),
                AudioHapticManagerNapi::Destructor, nullptr, nullptr);
            if (status == napi_ok) {
                obj.release();
                return thisVar;
            } else {
                MEDIA_LOGE("Failed to wrap the native AudioHapticManager object with JS.");
            }
        }
    }

    return result;
}

void AudioHapticManagerNapi::Destructor(napi_env env, void *nativeObject, void *finalizeHint)
{
    AudioHapticManagerNapi *audioHapticManagerhelper = reinterpret_cast<AudioHapticManagerNapi*>(nativeObject);
    if (audioHapticManagerhelper != nullptr) {
        audioHapticManagerhelper->~AudioHapticManagerNapi();
    }
}

napi_value AudioHapticManagerNapi::GetAudioHapticManager(napi_env env, napi_callback_info info)
{
    napi_status status;
    napi_value result = nullptr;
    napi_value ctor;

    status = napi_get_reference_value(env, sConstructor_, &ctor);
    if (status == napi_ok) {
        status = napi_new_instance(env, ctor, 0, nullptr, &result);
        if (status == napi_ok) {
            return result;
        } else {
            MEDIA_LOGE("GetAudioHapticManager: new instance can not be obtained.");
        }
    }

    napi_get_undefined(env, &result);
    return result;
}

napi_value AudioHapticManagerNapi::RegisterSourceFromFd(napi_env env, napi_callback_info info)
{
    std::unique_ptr<RegisterFromFdContext> asyncContext = std::make_unique<RegisterFromFdContext>();
    napi_value promise = nullptr;
    if (!AudioHapticCommonNapi::InitPromiseFunc(env, info, asyncContext.get(), &promise, ARGS_TWO)) {
        return promise;
    }

    AudioHapticFileDescriptor audioFd;
    if (GetAudioHapticFileDescriptorValue(env, asyncContext->argv[PARAM0], audioFd) != SUCCESS) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "Invalid first parameter");
        return promise;
    }
    asyncContext->audioFd = audioFd;

    AudioHapticFileDescriptor hapticFd;
    if (GetAudioHapticFileDescriptorValue(env, asyncContext->argv[PARAM1], hapticFd) != SUCCESS) {
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "Invalid second parameter");
        return promise;
    }
    asyncContext->hapticFd = hapticFd;

    napi_value funcName = nullptr;
    napi_create_string_utf8(env, "RegisterSourceFromFd", NAPI_AUTO_LENGTH, &funcName);
    napi_status status = napi_create_async_work(
        env,
        nullptr,
        funcName,
        AsyncRegisterSourceFromFd,
        RegisterSourceFromFdAsyncCallbackComp,
        static_cast<void*>(asyncContext.get()),
        &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("Failed to get create async work");
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred,
            status, "Failed to get create async work");
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return promise;
}

void AudioHapticManagerNapi::AsyncRegisterSourceFromFd(napi_env env, void *data)
{
    RegisterFromFdContext *context = static_cast<RegisterFromFdContext *>(data);
    AudioHapticManagerNapi* object = reinterpret_cast<AudioHapticManagerNapi*>(context->objectInfo);
    if (context->audioFd.fd == -1 || context->hapticFd.fd == -1) {
        context->sourceID = ERROR;
    } else {
        context->sourceID = object->audioHapticMgrClient_->
            RegisterSourceFromFd(context->audioFd, context->hapticFd);
    }
}

void AudioHapticManagerNapi::RegisterSourceFromFdAsyncCallbackComp(napi_env env, napi_status status, void *data)
{
    RegisterFromFdContext *context = static_cast<RegisterFromFdContext *>(data);
    napi_value result = nullptr;

    if (context->deferred) {
        if (context->sourceID > ERROR) {
            napi_create_int32(env, context->sourceID, &result);
            napi_resolve_deferred(env, context->deferred, result);
        } else {
            AudioHapticCommonNapi::PromiseReject(env, context->deferred,
                context->sourceID, "RegisterSourceFromFd Error: Operation is not supported or failed");
        }
    }
    napi_delete_async_work(env, context->work);

    delete context;
    context = nullptr;
}

int32_t AudioHapticManagerNapi::GetAudioHapticFileDescriptorValue(napi_env env, napi_value object,
    AudioHapticFileDescriptor& audioHapticFd)
{
    napi_value property = nullptr;
    bool exists = false;
    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, object, &valueType);
    CHECK_AND_RETURN_RET_LOG(valueType == napi_object, ERROR, "type mismatch");

    auto status = napi_get_named_property(env, object, "fd", &property);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok, ERROR, "No property: fd");
    status = napi_get_value_int32(env, property, &(audioHapticFd.fd));
    CHECK_AND_RETURN_RET_LOG(status == napi_ok, ERROR, "Invalid value: fd");

    if (napi_has_named_property(env, object, "length", &exists) == napi_ok && exists) {
        if (napi_get_named_property(env, object, "length", &property) == napi_ok) {
            status = napi_get_value_int64(env, property, &(audioHapticFd.length));
            CHECK_AND_RETURN_RET_LOG(status == napi_ok, ERROR, "Invalid value: length");
        }
    }

    if (napi_has_named_property(env, object, "offset", &exists) == napi_ok && exists) {
        if (napi_get_named_property(env, object, "offset", &property) == napi_ok) {
            status = napi_get_value_int64(env, property, &(audioHapticFd.offset));
            CHECK_AND_RETURN_RET_LOG(status == napi_ok, ERROR, "Invalid value: offset");
        }
    }

    return SUCCESS;
}

napi_value AudioHapticManagerNapi::RegisterSource(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {0};
    char buffer[SIZE];
    napi_value thisVar = nullptr;
    size_t res = 0;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result, "RegisterSource: napi_get_cb_info fail");
    if (argc != ARGS_TWO) {
        MEDIA_LOGE("RegisterSource: requires 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "mandatory parameters are left unspecified");
        return result;
    }

    std::unique_ptr<AudioHapticManagerAsyncContext> asyncContext = std::make_unique<AudioHapticManagerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && asyncContext->objectInfo != nullptr, result,
        "RegisterSource: Failed to unwrap object");

    for (size_t i = PARAM0; i < argc; i++) {
        napi_valuetype valueType = napi_undefined;
        napi_typeof(env, argv[i], &valueType);
        if (i == PARAM0 && valueType == napi_string) {
            napi_get_value_string_utf8(env, argv[i], buffer, SIZE, &res);
            asyncContext->audioUri = std::string(buffer);
        } else if (i == PARAM1 && valueType == napi_string) {
            napi_get_value_string_utf8(env, argv[i], buffer, SIZE, &res);
            asyncContext->hapticUri = std::string(buffer);
        } else {
            MEDIA_LOGE("RegisterSource: the param type mismatch");
            AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID,
                "incorrect parameter types: The type of audioUri and hapticUri must be string");
            return result;
        }
    }
    napi_create_promise(env, &asyncContext->deferred, &result);

    napi_create_string_utf8(env, "RegisterSource", NAPI_AUTO_LENGTH, &resource);
    status = napi_create_async_work(env, nullptr, resource, AsyncRegisterSource,
        RegisterSourceAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("Failed to get create async work");
        napi_get_undefined(env, &result);
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return result;
}

void AudioHapticManagerNapi::AsyncRegisterSource(napi_env env, void *data)
{
    AudioHapticManagerAsyncContext *context = static_cast<AudioHapticManagerAsyncContext *>(data);
    if (context->audioUri.empty() || context->hapticUri.empty()) {
        context->status = ERROR;
    } else {
        context->sourceID = context->objectInfo->audioHapticMgrClient_->
            RegisterSource(context->audioUri, context->hapticUri);
        context->status = SUCCESS;
    }
}

void AudioHapticManagerNapi::RegisterSourceAsyncCallbackComp(napi_env env, napi_status status, void *data)
{
    auto context = static_cast<AudioHapticManagerAsyncContext *>(data);
    napi_value result[2] = {};

    if (!context->status) {
        napi_get_undefined(env, &result[PARAM0]);
        napi_create_int32(env, context->sourceID, &result[PARAM1]);
    } else {
        napi_value message = nullptr;
        napi_create_string_utf8(env, "RegisterSource Error: Operation is not supported or failed",
            NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, nullptr, message, &result[PARAM0]);
        napi_get_undefined(env, &result[PARAM1]);
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

napi_value AudioHapticManagerNapi::UnregisterSource(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && thisVar != nullptr, result,
        "UnregisterSource: Failed to retrieve details about the callback");
    if (argc != ARGS_ONE) {
        MEDIA_LOGE("UnregisterSource: requires 1 parameter");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "mandatory parameters are left unspecified");
        return result;
    }

    std::unique_ptr<AudioHapticManagerAsyncContext> asyncContext = std::make_unique<AudioHapticManagerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    if (status == napi_ok && asyncContext->objectInfo != nullptr) {
        napi_valuetype valueType = napi_undefined;
        napi_typeof(env, argv[PARAM0], &valueType);
        if (valueType == napi_number) {
            napi_get_value_int32(env, argv[PARAM0], &asyncContext->sourceID);
        } else {
            MEDIA_LOGE("UnregisterSource: the param type mismatch");
            AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID,
                "incorrect parameter types: The type of id must be number");
            return result;
        }
        napi_create_promise(env, &asyncContext->deferred, &result);

        napi_create_string_utf8(env, "UnregisterSource", NAPI_AUTO_LENGTH, &resource);
        status = napi_create_async_work(env, nullptr, resource,
            [](napi_env env, void *data) {
                AudioHapticManagerAsyncContext *context = static_cast<AudioHapticManagerAsyncContext*>(data);
                context->status = context->objectInfo->audioHapticMgrClient_->UnregisterSource(context->sourceID);
            },
            UnregisterSourceAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
        if (status != napi_ok) {
            MEDIA_LOGE("GetRingtoneUri: Failed to get create async work");
            napi_get_undefined(env, &result);
        } else {
            napi_queue_async_work(env, asyncContext->work);
            asyncContext.release();
        }
    }

    return result;
}

void AudioHapticManagerNapi::UnregisterSourceAsyncCallbackComp(napi_env env, napi_status status, void *data)
{
    auto context = static_cast<AudioHapticManagerAsyncContext *>(data);
    napi_value result[2] = {};

    napi_get_undefined(env, &result[PARAM1]);
    if (!context->status) {
        napi_get_undefined(env, &result[PARAM0]);
    } else {
        napi_value message = nullptr;
        napi_create_string_utf8(env, "UnregisterSource Error: Operation is not supported or failed",
            NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, nullptr, message, &result[PARAM0]);
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

napi_value AudioHapticManagerNapi::SetAudioLatencyMode(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;

    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {0};
    napi_value thisVar = nullptr;
    void *data;
    napi_get_cb_info(env, info, &argc, argv, &thisVar, &data);
    if (argc != ARGS_TWO) {
        MEDIA_LOGE("SetAudioLatencyMode: requires 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    void *native = nullptr;
    napi_status status = napi_unwrap(env, thisVar, &native);
    auto *audioHapticManagerNapi = reinterpret_cast<AudioHapticManagerNapi *>(native);
    if (status != napi_ok || audioHapticManagerNapi == nullptr) {
        MEDIA_LOGE("SetAudioLatencyMode: unwrap failure!");
        return result;
    }

    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, argv[PARAM0], &valueType);
    if (valueType != napi_number) {
        MEDIA_LOGE("SetAudioLatencyMode: the param type mismatch");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }
    int32_t sourceID = 0;
    napi_get_value_int32(env, argv[PARAM0], &sourceID);

    napi_typeof(env, argv[PARAM1], &valueType);
    if (valueType != napi_number) {
        MEDIA_LOGE("SetAudioLatencyMode: the param type mismatch");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }
    int32_t latencyMode = 0;
    napi_get_value_int32(env, argv[PARAM1], &latencyMode);
    if (!IsLegalAudioLatencyMode (latencyMode)) {
        MEDIA_LOGE("SetAudioLatencyMode: the value of latencyMode is invalid");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID);
        return result;
    }

    int32_t setResult = audioHapticManagerNapi->audioHapticMgrClient_->
        SetAudioLatencyMode(sourceID, static_cast<AudioLatencyMode>(latencyMode));
    if (setResult != SUCCESS) {
        MEDIA_LOGE("SetAudioLatencyMode: Failed to set audio latency mode");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
    }
    return result;
}

bool AudioHapticManagerNapi::IsLegalAudioLatencyMode(int32_t latencyMode)
{
    switch (latencyMode) {
        case AUDIO_LATENCY_MODE_NORMAL:
        case AUDIO_LATENCY_MODE_FAST:
            return true;
        default:
            break;
    }
    MEDIA_LOGE("IsLegalAudioLatencyMode: latencyMode %{public}d is invalid", latencyMode);
    return false;
}

napi_value AudioHapticManagerNapi::SetStreamUsage(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;

    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {0};
    napi_value thisVar = nullptr;
    void *data;
    napi_get_cb_info(env, info, &argc, argv, &thisVar, &data);
    if (argc != ARGS_TWO) {
        MEDIA_LOGE("SetStreamUsage: requires 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "mandatory parameters are left unspecified");
        return result;
    }

    void *native = nullptr;
    napi_status status = napi_unwrap(env, thisVar, &native);
    auto *audioHapticManagerNapi = reinterpret_cast<AudioHapticManagerNapi *>(native);
    if (status != napi_ok || audioHapticManagerNapi == nullptr) {
        MEDIA_LOGE("SetStreamUsage: unwrap failure!");
        return result;
    }

    napi_valuetype valueType = napi_undefined;
    napi_typeof(env, argv[PARAM0], &valueType);
    if (valueType != napi_number) {
        MEDIA_LOGE("SetStreamUsage: the param type mismatch");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "the type of id must be number");
        return result;
    }
    int32_t sourceID = 0;
    napi_get_value_int32(env, argv[PARAM0], &sourceID);

    napi_typeof(env, argv[PARAM1], &valueType);
    if (valueType != napi_number) {
        MEDIA_LOGE("SetStreamUsage: the param type mismatch");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "the type of usage must be number");
        return result;
    }
    int32_t streamUsage = 0;
    napi_get_value_int32(env, argv[PARAM1], &streamUsage);
    if (!IsLegalAudioStreamUsage (streamUsage)) {
        MEDIA_LOGE("SetStreamUsage: the value of streamUsage is invalid");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID,
            "the param of usage must be enum audio.StreamUsage");
        return result;
    }

    int32_t setResult = audioHapticManagerNapi->audioHapticMgrClient_->
        SetStreamUsage(sourceID, static_cast<AudioStandard::StreamUsage>(streamUsage));
    if (setResult != SUCCESS) {
        MEDIA_LOGE("SetStreamUsage: Failed to set audio stream usage");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_OPERATE_NOT_ALLOWED);
    }
    return result;
}

bool AudioHapticManagerNapi::IsLegalAudioStreamUsage(int32_t streamUsage)
{
    switch (streamUsage) {
        case AudioStandard::STREAM_USAGE_MUSIC:
        case AudioStandard::STREAM_USAGE_VOICE_COMMUNICATION:
        case AudioStandard::STREAM_USAGE_VOICE_ASSISTANT:
        case AudioStandard::STREAM_USAGE_ALARM:
        case AudioStandard::STREAM_USAGE_VOICE_MESSAGE:
        case AudioStandard::STREAM_USAGE_RINGTONE:
        case AudioStandard::STREAM_USAGE_NOTIFICATION:
        case AudioStandard::STREAM_USAGE_ACCESSIBILITY:
        case AudioStandard::STREAM_USAGE_SYSTEM:
        case AudioStandard::STREAM_USAGE_MOVIE:
        case AudioStandard::STREAM_USAGE_GAME:
        case AudioStandard::STREAM_USAGE_AUDIOBOOK:
        case AudioStandard::STREAM_USAGE_NAVIGATION:
        case AudioStandard::STREAM_USAGE_DTMF:
        case AudioStandard::STREAM_USAGE_ENFORCED_TONE:
            return true;
        default:
            break;
    }
    MEDIA_LOGE("IsLegalAudioStreamUsage: streamUsage %{public}d is invalid", streamUsage);
    return false;
}

napi_value AudioHapticManagerNapi::CreatePlayer(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    napi_value property = nullptr;
    napi_value resource = nullptr;
    size_t argc = ARGS_TWO;
    napi_value argv[ARGS_TWO] = {0};
    napi_value thisVar = nullptr;

    napi_status status = napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr);
    napi_get_undefined(env, &result);
    CHECK_AND_RETURN_RET_LOG((status == napi_ok && thisVar != nullptr), result, "napi_get_cb_info failed");
    if (argc != ARGS_ONE && argc != ARGS_TWO) {
        MEDIA_LOGE("CreatePlayer: requires 1 parameter or 2 parameters");
        AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID, "mandatory parameters are left unspecified");
        return result;
    }

    std::unique_ptr<AudioHapticManagerAsyncContext> asyncContext = std::make_unique<AudioHapticManagerAsyncContext>();
    status = napi_unwrap(env, thisVar, reinterpret_cast<void**>(&asyncContext->objectInfo));
    CHECK_AND_RETURN_RET_LOG(status == napi_ok && asyncContext->objectInfo != nullptr, result, "objectInfo invalid");

    for (size_t i = PARAM0; i < argc; i++) {
        napi_valuetype valueType = napi_undefined;
        napi_typeof(env, argv[i], &valueType);
        if (i == PARAM0 && valueType == napi_number) {
            napi_get_value_int32(env, argv[i], &asyncContext->sourceID);
        } else if (i == PARAM1 && valueType == napi_object) {
            if (napi_get_named_property(env, argv[PARAM1], "muteAudio", &property) == napi_ok) {
                napi_get_value_bool(env, property, &(asyncContext->playerOptions.muteAudio));
            }
            if (napi_get_named_property(env, argv[PARAM1], "muteHaptics", &property) == napi_ok) {
                napi_get_value_bool(env, property, &(asyncContext->playerOptions.muteHaptics));
            }
        } else {
            MEDIA_LOGE("CreatePlayer: the param type mismatch");
            AudioHapticCommonNapi::ThrowError(env, NAPI_ERR_INPUT_INVALID,
                "incorrect parameter types: The type of id must be number; The type of options must be object");
            return result;
        }
    }
    // The public SDK contract requires VIBRATE at createPlayer, including a
    // muted player. Query the real current process token before native creation
    // or preload; never rely on a later asynchronous vibrator-service failure.
    napi_create_promise(env, &asyncContext->deferred, &result);
    if (!AudioHapticCommonNapi::VerifyVibratePermission()) {
        AudioHapticCommonNapi::PromiseReject(env, asyncContext->deferred, NAPI_ERR_VIBRATE_PERMISSION_DENIED);
        return result;
    }


    napi_create_string_utf8(env, "CreatePlayer", NAPI_AUTO_LENGTH, &resource);
    status = napi_create_async_work(env, nullptr, resource, AsyncCreatePlayer,
        CreatePlayerAsyncCallbackComp, static_cast<void*>(asyncContext.get()), &asyncContext->work);
    if (status != napi_ok) {
        MEDIA_LOGE("CreatePlayer: Failed to get create async work");
        napi_get_undefined(env, &result);
    } else {
        napi_queue_async_work(env, asyncContext->work);
        asyncContext.release();
    }

    return result;
}

void AudioHapticManagerNapi::AsyncCreatePlayer(napi_env env, void *data)
{
    AudioHapticManagerAsyncContext *context = static_cast<AudioHapticManagerAsyncContext *>(data);
    std::shared_ptr<AudioHapticPlayer> audioHapticPlayer =
        context->objectInfo->audioHapticMgrClient_->CreatePlayer(context->sourceID, context->playerOptions);
    if (audioHapticPlayer != nullptr) {
        int32_t result = audioHapticPlayer->Prepare();
        if (result == MSERR_OK) {
            context->audioHapticPlayer = audioHapticPlayer;
            context->status = SUCCESS;
            return;
        }
        // Fail to prepare the audio haptic player. Throw err.
        if (result == MSERR_OPEN_FILE_FAILED) {
            context->errCode = NAPI_ERR_IO_ERROR;
        } else if (result == MSERR_UNSUPPORT_FILE) {
            context->errCode = NAPI_ERR_UNSUPPORTED_FORMAT;
        } else {
            context->errCode = NAPI_ERR_OPERATE_NOT_ALLOWED;
        }
    } else {
        context->errCode = NAPI_ERR_OPERATE_NOT_ALLOWED;
    }
    context->audioHapticPlayer = nullptr;
    context->status = ERROR;
    context->errMessage = AudioHapticCommonNapi::GetMessageByCode(context->errCode);
}

void AudioHapticManagerNapi::CreatePlayerAsyncCallbackComp(napi_env env, napi_status status, void *data)
{
    auto context = static_cast<AudioHapticManagerAsyncContext *>(data);
    napi_value result[2] = {};
    napi_value playerResult = nullptr;

    if (context->audioHapticPlayer != nullptr) {
        playerResult = AudioHapticPlayerNapi::CreatePlayerInstance(env, context->audioHapticPlayer);
        if (playerResult == nullptr) {
            napi_value message = nullptr;
            napi_create_string_utf8(env, "CreatePlayer Error: Operation is not supported or failed",
                NAPI_AUTO_LENGTH, &message);
            napi_create_error(env, nullptr, message, &result[PARAM0]);
            napi_value code = nullptr;
            napi_create_int32(env, NAPI_ERR_OPERATE_NOT_ALLOWED, &code);
            napi_set_named_property(env, result[PARAM0], "code", code);
            context->status = ERROR;
            napi_get_undefined(env, &result[PARAM1]);
        } else {
            napi_get_undefined(env, &result[PARAM0]);
            result[PARAM1] = playerResult;
        }
    } else {
        MEDIA_LOGE("CreatePlayer: Failed to create audio haptic player!");
        napi_value message = nullptr;
        napi_value code = nullptr;
        napi_create_string_utf8(env, context->errMessage.c_str(), NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, nullptr, message, &result[PARAM0]);
        napi_create_int32(env, context->errCode, &code);
        napi_set_named_property(env, result[PARAM0], "code", code);
        napi_get_undefined(env, &result[PARAM1]);
    }

    if (context->deferred) {
        if (context->status == SUCCESS) {
            napi_resolve_deferred(env, context->deferred, result[PARAM1]);
        } else {
            napi_reject_deferred(env, context->deferred, result[PARAM0]);
        }
    }
    napi_delete_async_work(env, context->work);

    delete context;
    context = nullptr;
}

static napi_value Init(napi_env env, napi_value exports)
{
    AudioHapticManagerNapi::Init(env, exports);
    AudioHapticPlayerNapi::Init(env, exports);
    AudioHapticPlayerOptionsNapi::Init(env, exports);

    return exports;
}

/*
 * module define
 */
static napi_module g_module = {
    .nm_version = 1,
    .nm_flags = 0,
    .nm_filename = nullptr,
    .nm_register_func = Init,
    .nm_modname = "multimedia.audioHaptic",
    .nm_priv = (reinterpret_cast<void*>(0)),
    .reserved = {0}
};

/*
 * module register
 */
extern "C" __attribute__((constructor)) void RegisterModule(void)
{
    napi_module_register(&g_module);
}
} // namespace Media
} // namespace OHOS