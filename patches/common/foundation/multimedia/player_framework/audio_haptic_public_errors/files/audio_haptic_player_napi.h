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

#ifndef AUDIO_HAPTIC_PLAYER_NAPI_H
#define AUDIO_HAPTIC_PLAYER_NAPI_H

#include <map>

#include "audio_info.h"
#include "napi/native_api.h"
#include "napi/native_node_api.h"

#include "audio_haptic_common_napi.h"
#include "audio_haptic_player.h"
#include "audio_haptic_player_callback_napi.h"
#include "media_errors.h"
#include "audio_haptic_log.h"

namespace OHOS {
namespace Media {
extern const std::string AUDIO_HAPTIC_PLAYER_NAPI_CLASS_NAME;

struct VolumeContext : public AsyncContext {
    float volume = 1.0f;
    int32_t result = -1;
};

struct VibrationContext : public AsyncContext {
    float intensity = 1.0f;
    int32_t result = -1;
};

struct LoopContext : public AsyncContext {
    bool loop = false;
    int32_t result = -1;
};

struct RampContext : public AsyncContext {
    int32_t duration = 0;
    float startIntensity = 0.0f;
    float endIntensity = 0.0f;
    int32_t result = -1;
};

class AudioHapticPlayerNapi {
public:
    static napi_value Init(napi_env env, napi_value exports);
    static napi_value CreatePlayerInstance(napi_env env, std::shared_ptr<AudioHapticPlayer> &audioHapticPlayer);

    AudioHapticPlayerNapi();
    ~AudioHapticPlayerNapi();

private:
    static void Destructor(napi_env env, void *nativeObject, void *finalizeHint);
    static napi_value Constructor(napi_env env, napi_callback_info info);
    static napi_value IsMuted(napi_env env, napi_callback_info info);
    static napi_value Start(napi_env env, napi_callback_info info);
    static napi_value Stop(napi_env env, napi_callback_info info);
    static napi_value Release(napi_env env, napi_callback_info info);
    static napi_value On(napi_env env, napi_callback_info info);
    static napi_value Off(napi_env env, napi_callback_info info);
    static napi_value SetVolume(napi_env env, napi_callback_info info);
    static napi_value SetHapticsIntensity(napi_env env, napi_callback_info info);
    static napi_value EnableHapticsInSilentMode(napi_env env, napi_callback_info info);
    static napi_value IsHapticsIntensityAdjustmentSupported(napi_env env, napi_callback_info info);
    static napi_value SetLoop(napi_env env, napi_callback_info info);
    static napi_value IsHapticsRampSupported(napi_env env, napi_callback_info info);
    static napi_value SetHapticsRamp(napi_env env, napi_callback_info info);

    static napi_value RegisterCallback(napi_env env, napi_value jsThis, napi_value* argv, const std::string& cbName);
    static napi_value RegisterAudioHapticPlayerCallback(napi_env env, napi_value* argv, const std::string& cbName,
        AudioHapticPlayerNapi *audioHapticPlayerNapi);
    static napi_value UnregisterCallback(napi_env env, napi_value jsThis, const std::string& cbName);
    static napi_value UnregisterAudioHapticPlayerCallback(napi_env env, const std::string& cbName,
        AudioHapticPlayerNapi *audioHapticPlayerNapi);

    static void CommonAsyncCallbackComp(napi_env env, napi_status status, void *data);

    static bool IsLegalAudioHapticType(int32_t audioHapticType);
    static bool IsLegalVolumeOrIntensity(double volume);
    static bool JudgeVolume(napi_env env, std::unique_ptr<VolumeContext>& asyncContext);
    static bool JudgeIntensity(napi_env env, std::unique_ptr<VibrationContext>& asyncContext);
    static bool JudgeRamp(napi_env env, std::unique_ptr<RampContext> &asyncContext);

    napi_env env_;
    std::shared_ptr<AudioHapticPlayer> audioHapticPlayer_;
    std::shared_ptr<AudioHapticPlayerCallbackNapi> callbackNapi_ = nullptr;

    static thread_local napi_ref sConstructor_;
    static std::shared_ptr<AudioHapticPlayer> sAudioHapticPlayer_;
};

struct AudioHapticPlayerAsyncContext {
    napi_env env;
    napi_async_work work;
    napi_deferred deferred;
    // Preserve the native MSERR_* value; zero alone means success.
    int32_t status = MSERR_OK;
    AudioHapticPlayerNapi *objectInfo;
};
} // namespace Media
} // namespace OHOS
#endif // AUDIO_HAPTIC_PLAYER_NAPI_H