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
#ifndef LOG_TAG
#define LOG_TAG "AudioSpeed"
#endif

#include "audio_speed.h"
#include "audio_common_log.h"
#include "audio_utils.h"
#include "audio_errors.h"
#include "sonic.h"

namespace OHOS {
namespace AudioStandard {

static constexpr float SLOW_PLAY_1_8_SPEED = 0.125f;

AudioSpeed::AudioSpeed(size_t rate, size_t format, size_t channels, int32_t maxSpeedBufferSize)
    :rate_(rate), format_(format), channels_(channels),  maxSpeedBufferSize_(maxSpeedBufferSize)
{
    AUDIO_INFO_LOG("AudioSpeed construct");
    Init();
    streamParam_ = {};
}

AudioSpeed::~AudioSpeed()
{
    AUDIO_INFO_LOG("~AudioSpeed destroy");
    if (sonicStream_ != nullptr) {
        sonicDestroyStream(sonicStream_);
        sonicStream_ = nullptr;
        AUDIO_INFO_LOG("Sonic stream destroy");
    }
}

int32_t AudioSpeed::Init()
{
    sonicStream_ = sonicCreateStream(rate_, channels_);
    CHECK_AND_RETURN_RET_LOG(sonicStream_ != nullptr, ERROR, "sonicCreateStream failed.");
    LoadChangeSpeedFunc();

    return SUCCESS;
}

int32_t AudioSpeed::LoadChangeSpeedFunc()
{
    switch (format_) {
        case SAMPLE_U8:
            formatSize_ = 1; // size is 1
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedFor8Bit(buffer, bufferSize, outBuffer, outBufferSize);
                };
            break;
        case SAMPLE_S16LE:
            formatSize_ = 2; // size is 2
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedFor16Bit(buffer, bufferSize, outBuffer, outBufferSize);
                };
            break;
        case SAMPLE_S24LE:
            formatSize_ = 3; // size is 3
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedFor24Bit(buffer, bufferSize, outBuffer, outBufferSize);
                };
            break;
        case SAMPLE_S32LE:
            formatSize_ = 4; // size is 4
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedFor32Bit(buffer, bufferSize, outBuffer, outBufferSize);
                };
            break;
        case SAMPLE_F32LE:
            formatSize_ = 4; // size is 4
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedForFloat(reinterpret_cast<float*>(buffer), bufferSize,
                        reinterpret_cast<float*>(outBuffer.get()), outBufferSize);
                };
            break;
        default:
            formatSize_ = 2; // size is 2
            ChangeSpeedFunc = [this] (uint8_t *buffer, int32_t bufferSize,
                std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)-> int32_t {
                    return this->ChangeSpeedFor16Bit(buffer, bufferSize, outBuffer, outBufferSize);
                };
    }
    AUDIO_INFO_LOG("load change speed func for format %{public}zu", format_);
    return SUCCESS;
}

int32_t AudioSpeed::SetSpeed(float speed)
{
    AUDIO_INFO_LOG("SetSpeed %{public}f", speed);
    speed_ = speed;
    sonicSetSpeed(sonicStream_, speed_);
    return SUCCESS;
}

int32_t AudioSpeed::SetPitch(float pitch)
{
    AUDIO_INFO_LOG("SetPitch %{public}f", pitch);
    sonicSetPitch(sonicStream_, pitch);
    sonicSetRate(sonicStream_, 1.0f);
    return SUCCESS;
}

float AudioSpeed::GetPitchForSpeed(float speed)
{
    float noPitchPoint = 0.5f;
    float pitch = SPEED_NORMAL;
    if (speed > noPitchPoint) {
        pitch = SPEED_NORMAL;
    } else {
        pitch = (speed - SLOW_PLAY_1_8_SPEED) * (SPEED_NORMAL - SLOW_PLAY_1_8_SPEED) /
            (noPitchPoint - SLOW_PLAY_1_8_SPEED) + SLOW_PLAY_1_8_SPEED;
    }
    AUDIO_INFO_LOG("final pitch is %{public}f for speed %{public}f", pitch, speed);
    return pitch;
}

float AudioSpeed::GetSpeed()
{
    return speed_;
}

int32_t AudioSpeed::ChangeSpeedFor8Bit(uint8_t *buffer, int32_t bufferSize,
    std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)
{
    Trace trace("AudioSpeed::ChangeSpeedFor8Bit");
    int32_t numSamples = bufferSize / static_cast<int32_t>(formatSize_ * channels_);
    int32_t res = sonicWriteUnsignedCharToStream(sonicStream_, static_cast<unsigned char*>(buffer), numSamples);
    CHECK_AND_RETURN_RET_LOG(res == 1, 0, "sonic write unsigned char to stream failed.");

    int32_t outSamples = sonicReadUnsignedCharFromStream(sonicStream_,
        static_cast<unsigned char*>(outBuffer.get()), maxSpeedBufferSize_);
    CHECK_AND_RETURN_RET_LOG(outSamples != 0, bufferSize, "sonic stream is not full continue to write.");

    outBufferSize = outSamples * static_cast<int32_t>(formatSize_ * channels_);
    return bufferSize;
}

int32_t AudioSpeed::ChangeSpeedFor16Bit(uint8_t *buffer, int32_t bufferSize,
    std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)
{
    Trace trace("AudioSpeed::ChangeSpeedFor16Bit");
    int32_t numSamples = bufferSize / static_cast<int32_t>(formatSize_ * channels_);
    int32_t res = sonicWriteShortToStream(sonicStream_, reinterpret_cast<short*>(buffer), numSamples);
    CHECK_AND_RETURN_RET_LOG(res == 1, 0, "sonic write short to stream failed.");

    int32_t outSamples = sonicReadShortFromStream(sonicStream_, reinterpret_cast<short*>(outBuffer.get()),
        maxSpeedBufferSize_);
    CHECK_AND_RETURN_RET_LOG(outSamples != 0, bufferSize, "sonic stream is not full continue to write.");

    outBufferSize = outSamples * static_cast<int32_t>(formatSize_ * channels_);
    return bufferSize;
}

int32_t AudioSpeed::ChangeSpeedFor24Bit(uint8_t *buffer, int32_t bufferSize,
    std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)
{
    Trace trace("AudioSpeed::ChangeSpeedFor24Bit");
    if (bufferSize <= 0 || bufferSize > maxSpeedBufferSize_) {
        AUDIO_ERR_LOG("BufferSize is illegal:%{public}d", bufferSize);
        return ERR_MEMORY_ALLOC_FAILED;
    }
    float *bitTofloat = new (std::nothrow) float[bufferSize];
    if (bitTofloat == nullptr) {
        AUDIO_ERR_LOG("bitTofloat nullptr, No memory");
        return ERR_MEMORY_ALLOC_FAILED;
    }
    ConvertFrom24BitToFloat(bufferSize / formatSize_, buffer, bitTofloat);

    float *speedBuf = new (std::nothrow) float[maxSpeedBufferSize_];
    if (speedBuf == nullptr) {
        AUDIO_ERR_LOG("speedBuf nullptr, No memory");
        delete [] bitTofloat;
        return ERR_MEMORY_ALLOC_FAILED;
    }
    int32_t ret = ChangeSpeedForFloat(bitTofloat, bufferSize, speedBuf, outBufferSize);

    ConvertFromFloatTo24Bit(outBufferSize / formatSize_, speedBuf, outBuffer.get());

    delete [] bitTofloat;
    delete [] speedBuf;
    return ret;
}

int32_t AudioSpeed::ChangeSpeedFor32Bit(uint8_t *buffer, int32_t bufferSize,
    std::unique_ptr<uint8_t []> &outBuffer, int32_t &outBufferSize)
{
    Trace trace("AudioSpeed::ChangeSpeedFor32Bit");
    if (bufferSize <= 0 || bufferSize > maxSpeedBufferSize_) {
        AUDIO_ERR_LOG("BufferSize is illegal:%{public}d", bufferSize);
        return ERR_MEMORY_ALLOC_FAILED;
    }
    float *bitTofloat = new (std::nothrow) float[bufferSize];
    if (bitTofloat == nullptr) {
        AUDIO_ERR_LOG("bitTofloat nullptr, No memory");
        return ERR_MEMORY_ALLOC_FAILED;
    }
    ConvertFrom32BitToFloat(bufferSize / formatSize_, reinterpret_cast<int32_t *>(buffer), bitTofloat);

    float *speedBuf = new (std::nothrow) float[maxSpeedBufferSize_];
    if (speedBuf == nullptr) {
        AUDIO_ERR_LOG("speedBuf nullptr, No memory");
        delete [] bitTofloat;
        return ERR_MEMORY_ALLOC_FAILED;
    }
    int32_t ret = ChangeSpeedForFloat(bitTofloat, bufferSize, speedBuf, outBufferSize);

    ConvertFromFloatTo32Bit(outBufferSize / formatSize_, speedBuf, reinterpret_cast<int32_t *>(outBuffer.get()));

    delete [] bitTofloat;
    delete [] speedBuf;
    return ret;
}

int32_t AudioSpeed::ChangeSpeedForFloat(float *buffer, int32_t bufferSize,
    float* outBuffer, int32_t &outBufferSize)
{
    Trace trace("AudioSpeed::ChangeSpeedForFloat");
    int32_t numSamples = bufferSize / static_cast<int32_t>(formatSize_ * channels_);
    int32_t res = static_cast<int32_t>(sonicWriteFloatToStream(sonicStream_, buffer, numSamples));
    CHECK_AND_RETURN_RET_LOG(res == 1, 0, "sonic write float to stream failed.");
    int32_t outSamples = sonicReadFloatFromStream(sonicStream_, outBuffer, maxSpeedBufferSize_);
    outBufferSize = outSamples * static_cast<int32_t>(formatSize_ * channels_);
    return bufferSize;
}

int32_t AudioSpeed::Flush()
{
    Trace trace("AudioSpeed::Flush");
    sonicFlushStream(sonicStream_);
    std::unique_ptr<uint8_t[]> tmpBuffer = std::make_unique<uint8_t[]>(maxSpeedBufferSize_);

    int samplesWritten = 0;
    const size_t channelMultiplier = static_cast<size_t>(channels_);
    do {
        switch (format_) {
            case SAMPLE_U8:
                samplesWritten = sonicReadUnsignedCharFromStream(sonicStream_,
                    reinterpret_cast<uint8_t*>(tmpBuffer.get()),
                    maxSpeedBufferSize_ / channelMultiplier);
                break;
            case SAMPLE_S24LE:
            case SAMPLE_S32LE:
            case SAMPLE_F32LE:
                samplesWritten = sonicReadFloatFromStream(sonicStream_,
                    reinterpret_cast<float*>(tmpBuffer.get()),
                    maxSpeedBufferSize_ / (channelMultiplier * sizeof(float)));
                break;
            case SAMPLE_S16LE:
                samplesWritten = sonicReadShortFromStream(sonicStream_,
                    reinterpret_cast<short*>(tmpBuffer.get()),
                    maxSpeedBufferSize_ / (channelMultiplier * sizeof(short)));
                break;
            default:
                AUDIO_ERR_LOG("invalid format_");
                samplesWritten = 0;
                break;
        }
    } while (samplesWritten > 0);
    return SUCCESS;
}
} // namespace AudioStandard
} // namespace OHOS
