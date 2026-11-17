/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
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

#ifndef AUDIO_LIMITER_H
#define AUDIO_LIMITER_H
#if !defined(DISABLE_SIMD) && \
    (defined(__aarch64__) || (defined(__arm__) && defined(__ARM_NEON__)))
// enable arm Simd
#include <arm_neon.h>
#define USE_ARM_NEON 1
#else
// disable SIMD.
#define USE_ARM_NEON 0
#endif

#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include "audio_onset579.h"

namespace OHOS {
namespace AudioStandard {

class AudioLimiter {
public:
    AudioLimiter(int32_t sinkIndex);
    ~AudioLimiter();
    int32_t SetConfig(int32_t inputFrameBytes, int32_t bytePerSample, int32_t sampleRate, int32_t channels);
    int32_t Process(int32_t inputSampleCount, float *inBuffer, float *outBuffer);
    uint32_t GetLatency();
    int32_t ProcessObserved579(int32_t count, float *in, float *out,
        const Onset579::Spans &origins, Onset579::Spans &output);

private:
    float CalculateEnvelopeEnergy(float *inBuffer);
    void ApplyGainToFrame(float *inBuffer, float *outBuffer, float &lastGain, float deltaGain);
    void ProcessAlgo(float *inBuffer, float *outBuffer);
    int32_t ValidateConfigParams(int32_t inputFrameBytes, int32_t bytePerSample, int32_t sampleRate,
        int32_t channels, int32_t &newAlgoFrameLen);
    int32_t AllocateHistoryBuffer(int32_t newAlgoFrameLen);
    void OpenDumpFiles(int32_t sampleRate, int32_t channels);
    void CalculateEnvelopeStereo(float *inBuffer, float &maxEnvelopeLevel);
    void CalculateEnvelopeMono(float *inBuffer, float &maxEnvelopeLevel);
    void ApplyGainStereo(float *inBuffer, float *outBuffer, float &lastGain, float deltaGain);
    void ApplyGainMono(float *inBuffer, float *outBuffer, float &lastGain, float deltaGain);
    uint32_t latency_;
    int32_t sinkIndex_;
    int32_t algoFrameLen_;
    int32_t format_;
    float nextLev_;
    float curMaxLev_;
    float threshold_;
    float gain_;
    float levelAttack_;
    float levelRelease_;
    float gainAttack_;
    float gainRelease_;
    Onset579::Spans history579_;
    std::vector<float> bufHis_;
    uint32_t sampleRate_;
    uint32_t channels_;
    FILE *dumpFileInput_ = nullptr;
    FILE *dumpFileOutput_ = nullptr;
    std::string dumpFileNameIn_ = "";
    std::string dumpFileNameOut_ = "";
};

}  // namespace AudioStandard
}  // namespace OHOS
#endif  // AUDIO_LIMITER_H