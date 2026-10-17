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

#ifndef AUDIO_HAPTIC_SOUND_H
#define AUDIO_HAPTIC_SOUND_H

#include <mutex>
#include <string>

#include "audio_haptic_manager.h"

namespace OHOS {
namespace Media {
class AudioHapticSoundCallback {
public:
    virtual ~AudioHapticSoundCallback() = default;

    virtual void OnEndOfStream() = 0;
    virtual void OnError(int32_t errorCode) = 0;
    virtual void OnFirstFrameWriting(uint64_t latency) = 0;
    virtual void OnInterrupt(const AudioStandard::InterruptEvent &interruptEvent) = 0;
};

class AudioHapticSound {
public:
    virtual ~AudioHapticSound() = default;

    static std::shared_ptr<AudioHapticSound> CreateAudioHapticSound(const AudioLatencyMode &latencyMode,
        const AudioSource& audioSource, const bool &muteAudio, const AudioStandard::StreamUsage &streamUsage,
        const bool &parallelPlayFlag = false, const int32_t &rendererFlags = 0);

    virtual int32_t PrepareSound() = 0;
    virtual int32_t StartSound(const int32_t &audioHapticSyncId = 0) = 0;
    virtual int32_t StopSound() = 0;
    virtual int32_t ReleaseSound() = 0;
    virtual int32_t SetVolume(float volume) = 0;
    virtual int32_t SetLoop(bool loop) = 0;
    virtual int32_t GetAudioCurrentTime() = 0;
    virtual int32_t SetAudioHapticSoundCallback(const std::shared_ptr<AudioHapticSoundCallback> &callback) = 0;

private:
    static std::mutex createAudioHapticSoundMutex_;
};
} // Media
} // OHOS
#endif // AUDIO_HAPTIC_SOUND_H
