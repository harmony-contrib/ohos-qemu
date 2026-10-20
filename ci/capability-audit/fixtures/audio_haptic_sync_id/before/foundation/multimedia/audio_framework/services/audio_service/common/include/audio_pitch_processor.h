/*
 * Copyright (c) 2026 Huawei Device Co., Ltd.
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

#ifndef OH_AUDIO_PITCH_PROCESSOR_H
#define OH_AUDIO_PITCH_PROCESSOR_H

#include "audio_utils.h"
#include "audio_service_log.h"
#include <vector>
#include <mutex>

#include "audio_effect.h"
namespace OHOS {
namespace AudioStandard {

static const int32_t MAX_PITCH_BUFFER_FACTOR = 3;
static const uint32_t MIN_CHANNELS_SUPPORTED = 1;
static const uint32_t MAX_CHANNELS_SUPPORTED = 2;
static constexpr uint32_t DEFAULT_SAMPLE_RATE_VALUE = 48000;

class AudioPitchProcessor {
public:
    static std::shared_ptr<AudioPitchProcessor> CreateInstance(const AudioStreamInfo &streamInfo);
    AudioPitchProcessor(const AudioStreamInfo &streamInfo);
    ~AudioPitchProcessor();
    
    AudioPitchProcessor(const AudioPitchProcessor&) = delete;
    AudioPitchProcessor& operator=(const AudioPitchProcessor&) = delete;
    
    int32_t PitchAlgoInit();
    int32_t SetPitch(float pitch);
    int32_t ProcessBufferPitch(int8_t *inputBuffer, size_t inputSize,
        int8_t *outputBuffer, size_t &outputSize);
    void PitchAlgoRelease();

private:
    bool IsValidChannelCount() const;
    int32_t Apply(int16_t *inPcm, int16_t *outPcm, int32_t cnt, int32_t &outCnt);
    
    int32_t LoadPitchLibrary();
    int32_t CreatePitchEffect();
    int32_t ConfigurePitchBuffer();

private:
    float curPitch_ = PITCH_DEFAULT;
    uint32_t sampleRate_ = DEFAULT_SAMPLE_RATE_VALUE;
    uint32_t channels_ = MIN_CHANNELS_SUPPORTED;
    AudioSampleFormat format_;
    AudioStreamInfo streamInfo_;

    static void* sharedSoHandle_;
    static AudioEffectLibrary* sharedLibHandle_;
    static std::mutex libMutex_;
    static int32_t libRefCount_;

    AudioEffectHandle algoHandle_ = nullptr;
    
    std::vector<int16_t> internalS16Buffer_;
};

} // namespace AudioStandard
} // namespace OHOS
#endif // OH_AUDIO_PITCH_PROCESSOR_H