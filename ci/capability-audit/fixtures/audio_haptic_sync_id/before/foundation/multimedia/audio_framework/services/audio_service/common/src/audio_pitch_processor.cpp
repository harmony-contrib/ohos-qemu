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
#ifndef LOG_TAG
#define LOG_TAG "audioPitchProcessor"
#endif

#include "audio_pitch_processor.h"

#include <cstdint>
#include <dlfcn.h>

#include "audio_errors.h"
#include "audio_log_utils.h"
#include "audio_utils.h"

namespace OHOS {
namespace AudioStandard {
namespace {
    const std::string LIB_PITCH_CHANGE = "/system/lib64/libaudio_pitch_change.z.so";
    const std::string PITCH_LIB = "PITCHLIB";
    constexpr uint32_t DEFAULT_CHANNEL_LAYOUT_VALUE = 0;
}

void* AudioPitchProcessor::sharedSoHandle_ = nullptr;
AudioEffectLibrary* AudioPitchProcessor::sharedLibHandle_ = nullptr;
std::mutex AudioPitchProcessor::libMutex_;
int32_t AudioPitchProcessor::libRefCount_ = 0;

std::shared_ptr<AudioPitchProcessor> AudioPitchProcessor::CreateInstance(const AudioStreamInfo &streamInfo)
{
    return std::make_shared<AudioPitchProcessor>(streamInfo);
}

AudioPitchProcessor::AudioPitchProcessor(const AudioStreamInfo &streamInfo)
    : sampleRate_(static_cast<uint32_t>(streamInfo.samplingRate)),
    channels_(static_cast<uint32_t>(streamInfo.channels)),
    format_(streamInfo.format),
    streamInfo_(streamInfo)
{
    if (channels_ < MIN_CHANNELS_SUPPORTED || channels_ > MAX_CHANNELS_SUPPORTED) {
        AUDIO_WARNING_LOG("Unsupported channel count: %{public}u, only support 1 or 2 channels. "
            "PitchAlgoInit will return ERR_NOT_SUPPORTED.", channels_);
    }
}

AudioPitchProcessor::~AudioPitchProcessor()
{
    PitchAlgoRelease();
}

bool AudioPitchProcessor::IsValidChannelCount() const
{
    return channels_ >= MIN_CHANNELS_SUPPORTED && channels_ <= MAX_CHANNELS_SUPPORTED;
}

int32_t AudioPitchProcessor::PitchAlgoInit()
{
    CHECK_AND_RETURN_RET_LOG(IsValidChannelCount(), ERR_NOT_SUPPORTED,
        "Unsupported channel count: %{public}u, only support 1 or 2 channels", channels_);
    
    int32_t ret = LoadPitchLibrary();
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "LoadPitchLibrary fail!");
    
    ret = CreatePitchEffect();
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "CreatePitchEffect fail!");
    
    ret = ConfigurePitchBuffer();
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "ConfigurePitchBuffer fail!");
    
    AUDIO_INFO_LOG("PitchAlgoInit success: sampleRate=%{public}u, channels=%{public}u, refCount=%{public}d",
        sampleRate_, channels_, libRefCount_);
    return SUCCESS;
}

int32_t AudioPitchProcessor::LoadPitchLibrary()
{
    std::lock_guard<std::mutex> lock(libMutex_);
    if (libRefCount_ == 0) {
        sharedSoHandle_ = dlopen(LIB_PITCH_CHANGE.c_str(), RTLD_NOW);
        CHECK_AND_RETURN_RET_LOG(sharedSoHandle_ != nullptr, ERR_NULL_POINTER, "openso fail!");

        sharedLibHandle_ = static_cast<AudioEffectLibrary *>(dlsym(sharedSoHandle_, PITCH_LIB.c_str()));
        if (!sharedLibHandle_) {
            AUDIO_ERR_LOG("load lib symbol fail!");
            dlclose(sharedSoHandle_);
            sharedSoHandle_ = nullptr;
            return ERR_OPERATION_FAILED;
        }
    }
    libRefCount_++;
    return SUCCESS;
}

int32_t AudioPitchProcessor::CreatePitchEffect()
{
    AudioEffectDescriptor descriptor = {
        .libraryName = "audio_pitch_change",
        .effectName = "audio_pitch_change"
    };

    int32_t ret = sharedLibHandle_->createEffect(descriptor, &algoHandle_);
    CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS && algoHandle_ != nullptr, ERR_OPERATION_FAILED, PitchAlgoRelease());
    return SUCCESS;
}

int32_t AudioPitchProcessor::ConfigurePitchBuffer()
{
    AudioBufferConfig bufferConfig;
    bufferConfig.samplingRate = sampleRate_;
    bufferConfig.channels = channels_;
    bufferConfig.format = static_cast<uint8_t>(DATA_FORMAT_S16);
    bufferConfig.channelLayout = DEFAULT_CHANNEL_LAYOUT_VALUE;
    bufferConfig.encoding = ENCODING_PCM;
    
    uint32_t replyData = 0;
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
    AudioEffectTransInfo cmdInfo = {sizeof(AudioBufferConfig), &bufferConfig};
    
    int32_t ret = (*algoHandle_)->command(algoHandle_, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
    CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS, ERR_OPERATION_FAILED, PitchAlgoRelease());
    return SUCCESS;
}

int32_t AudioPitchProcessor::SetPitch(float pitch)
{
    CHECK_AND_RETURN_RET_LOG(IsValidChannelCount(), ERR_NOT_SUPPORTED,
        "Unsupported channel count: %{public}u, only support 1 or 2 channels", channels_);
    
    CHECK_AND_RETURN_RET_LOG(pitch >= MIN_STREAM_PITCH_LEVEL && pitch <= MAX_STREAM_PITCH_LEVEL, ERR_NOT_SUPPORTED,
        "not support pitch %{public}f!", pitch);
    curPitch_ = pitch;
    uint32_t replyData = 0;
    AudioEffectTransInfo replyInfo = {sizeof(uint32_t), &replyData};
    AudioEffectTransInfo cmdInfo = {sizeof(float), &curPitch_};
    
    CHECK_AND_RETURN_RET_LOG(algoHandle_ != nullptr, ERR_OPERATION_FAILED, "algoHandle is null");
    int32_t ret = (*algoHandle_)->command(algoHandle_, EFFECT_CMD_SET_PARAM, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "set pitch fail!");
    
    return SUCCESS;
}

int32_t AudioPitchProcessor::Apply(int16_t *inPcm, int16_t *outPcm, int32_t cnt, int32_t &outCnt)
{
    CHECK_AND_RETURN_RET_LOG(algoHandle_ != nullptr && inPcm && outPcm && cnt > 0,
        ERR_INVALID_PARAM, "Invalid params");
    
    AudioBuffer inBuffer = {
        .frameLength = static_cast<size_t>(cnt),
        .raw = inPcm,
        .metaData = nullptr
    };
    AudioBuffer outBuffer = {
        .frameLength = static_cast<size_t>(outCnt),
        .raw = outPcm,
        .metaData = nullptr
    };
    
    int32_t ret = (*algoHandle_)->process(algoHandle_, &inBuffer, &outBuffer);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "apply pitch fail!");
    outCnt = static_cast<int32_t>(outBuffer.frameLength);
    return SUCCESS;
}

int32_t AudioPitchProcessor::ProcessBufferPitch(int8_t *inputBuffer, size_t inputSize,
    int8_t *outputBuffer, size_t &outputSize)
{
    CHECK_AND_RETURN_RET_LOG(IsValidChannelCount(), ERR_NOT_SUPPORTED,
        "Unsupported channel count: %{public}u, only support 1 or 2 channels", channels_);
    CHECK_AND_RETURN_RET_LOG(inputBuffer != nullptr && inputSize > 0, ERR_INVALID_PARAM, "Invalid input params");
    CHECK_AND_RETURN_RET_LOG(outputBuffer != nullptr, ERR_INVALID_PARAM, "Invalid output buffer");
    CHECK_AND_RETURN_RET_LOG(algoHandle_ != nullptr, ERR_INVALID_PARAM, "Pitch processor not initialized");
    
    uint32_t totalSamples = static_cast<uint32_t>(inputSize / PcmFormatToBits(format_));
    AUDIO_DEBUG_LOG("ProcessBufferPitch: inputSize=%{public}zu, channels=%{public}u, totalSamples=%{public}u",
        inputSize, channels_, totalSamples);
    Trace traceProcess("ProcessBufferPitch: inputSize=" + std::to_string(inputSize) + "channels= " +
        std::to_string(channels_) + "totalSamples= " + std::to_string(totalSamples));
    
    internalS16Buffer_.resize(totalSamples);
    ConvertBufferToS16(reinterpret_cast<const uint8_t*>(inputBuffer), totalSamples,
        internalS16Buffer_.data(), format_);
    
    int32_t maxProcessedSamples = totalSamples * MAX_PITCH_BUFFER_FACTOR;
    std::vector<int16_t> processedBuffer(maxProcessedSamples);
    int32_t outCnt = maxProcessedSamples;
    
    int32_t ret = Apply(internalS16Buffer_.data(), processedBuffer.data(), totalSamples, outCnt);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "Apply failed");
    
    processedBuffer.resize(outCnt);
    
    outputSize = static_cast<size_t>(outCnt) * PcmFormatToBits(format_);
    ConvertBufferFromS16(processedBuffer.data(), outCnt,
        reinterpret_cast<uint8_t*>(outputBuffer), format_);
    
    AUDIO_DEBUG_LOG("ProcessBufferPitch done: outputSize=%{public}zu", outputSize);
    return SUCCESS;
}

void AudioPitchProcessor::PitchAlgoRelease()
{
    if (algoHandle_ != nullptr && sharedLibHandle_ != nullptr) {
        sharedLibHandle_->releaseEffect(algoHandle_);
        algoHandle_ = nullptr;
    }

    std::unique_lock<std::mutex> lock(libMutex_);
    if (libRefCount_ <= 0) {
        return;
    }
    libRefCount_--;
    if (libRefCount_ == 0 && sharedSoHandle_ != nullptr) {
        dlclose(sharedSoHandle_);
        sharedSoHandle_ = nullptr;
        sharedLibHandle_ = nullptr;
    }
    AUDIO_INFO_LOG("PitchAlgoRelease done, refCount=%{public}d", libRefCount_);
}

} // namespace AudioStandard
} // namespace OHOS