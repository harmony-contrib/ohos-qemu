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

#ifndef AUDIO_HAPTIC_VIBRATOR_H
#define AUDIO_HAPTIC_VIBRATOR_H

#include <mutex>
#include <string>

#include "audio_haptic_player.h"

namespace OHOS {
namespace Media {
class AudioHapticVibrator {
public:
    virtual ~AudioHapticVibrator() = default;

    static std::shared_ptr<AudioHapticVibrator> CreateAudioHapticVibrator(AudioHapticPlayer &audioHapticPlayer);

    virtual int32_t PreLoad(const HapticSource &hapticSource, const AudioStandard::StreamUsage &streamUsage) = 0;
    virtual int32_t Release() = 0;
    virtual void ResetStopState() = 0;
    virtual int32_t StartVibrate(const AudioLatencyMode &latencyMode) = 0;
    virtual int32_t SetHapticIntensity(float intensity) = 0;
    virtual int32_t StopVibrate() = 0;
    virtual int32_t GetDelayTime() = 0;
    virtual void EnableHapticsInSilentMode(bool enable) = 0;
    virtual bool IsHapticsCustomSupported() = 0;
    virtual int32_t SetHapticsRamp(int32_t duration, float startIntensity, float endIntensity) = 0;
    virtual int32_t SetHapticsFeature(const HapticsFeature &feature) = 0;
    virtual void SetAudioHapticSyncId(const int32_t &audioHapticSyncId) = 0;

private:
    static std::mutex createVibratorMutex_;
};
} // Media
} // OHOS
#endif // AUDIO_HAPTIC_VIBRATOR_H
