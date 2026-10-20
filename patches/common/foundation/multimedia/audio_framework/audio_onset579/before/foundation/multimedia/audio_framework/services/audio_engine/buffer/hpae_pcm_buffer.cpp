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

#ifndef LOG_TAG
#define LOG_TAG "HpaePcmBuffer"
#endif

#include "securec.h"
#include "simd_utils.h"
#include "hpae_pcm_buffer.h"
#include "audio_engine_log.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
HpaePcmBuffer::HpaePcmBuffer(PcmBufferInfo &pcmBufferInfo) : pcmBufferInfo_(pcmBufferInfo)
{
    InitPcmProcess();
}

HpaePcmBuffer &HpaePcmBuffer::operator=(const HpaePcmBuffer &other)
{
    if (this != &other) {
        pcmBufferInfo_ = other.pcmBufferInfo_;
        InitPcmProcess();
        int32_t ret = memcpy_s(GetPcmDataBuffer(), bufferByteSize_, other.GetPcmDataBuffer(), bufferByteSize_);
        if (ret != 0) {
            AUDIO_ERR_LOG("memcpy failed when copy PcmBuffer");
        }
    }
    return *this;
}

HpaePcmBuffer::HpaePcmBuffer(HpaePcmBuffer &&other)
{
    pcmBufferInfo_ = other.pcmBufferInfo_;
    bufferByteSize_ = other.bufferByteSize_;
    bufferFloatSize_ = other.bufferFloatSize_;
    dataByteSize_ = other.dataByteSize_;
    pcmDataBuffer_ = std::move(other.pcmDataBuffer_);
    pcmProcessVec_ = std::move(other.pcmProcessVec_);
    other.pcmBufferInfo_.frames = 0;
    other.bufferByteSize_ = 0;
    other.bufferFloatSize_ = 0;
    other.dataByteSize_ = 0;
}

void HpaePcmBuffer::InitPcmProcess()
{
    size_t ch = GetChannelCount();
    size_t frameLen = GetFrameLen();
    size_t frames = GetFrames();
    size_t addBytes = MEMORY_ALIGN_BYTE_NUM - (frameLen * sizeof(float) * ch) % MEMORY_ALIGN_BYTE_NUM;
    size_t dataSize = frameLen * sizeof(float) * ch;
    frameByteSize_ = frameLen * sizeof(float) * ch + addBytes;
    frameFloatSize_ = frameByteSize_ / sizeof(float);
    bufferByteSize_ = frameByteSize_ * frames;
    bufferFloatSize_ = frameFloatSize_ * frames;
    dataByteSize_ = dataSize * frames;
    frameSample_ = frameLen * ch;
    pcmDataBuffer_.resize(bufferFloatSize_);
    readPos_.store(0);
    writePos_.store(0);
    curFrames_.store(0);
    pcmProcessVec_.clear();
    pcmProcessVec_.reserve(frames);
    float *itr = pcmDataBuffer_.data();
    for (size_t i = 0; i < frames; ++i) {
        pcmProcessVec_.push_back(HpaePcmProcess(itr, frameSample_));
        itr += frameFloatSize_;
    }
}

HpaePcmBuffer &HpaePcmBuffer::operator+=(HpaePcmBuffer &other)
{
    for (size_t i = 0; i < pcmProcessVec_.size(); ++i) {
        pcmProcessVec_[i] += other[i];
    }
    return *this;
}

HpaePcmBuffer &HpaePcmBuffer::operator-=(HpaePcmBuffer &other)
{
    for (size_t i = 0; i < pcmProcessVec_.size(); ++i) {
        pcmProcessVec_[i] -= other[i];
    }
    return *this;
}

HpaePcmBuffer &HpaePcmBuffer::operator*=(HpaePcmBuffer &other)
{
    for (size_t i = 0; i < pcmProcessVec_.size(); ++i) {
        pcmProcessVec_[i] *= other[i];
    }
    return *this;
}

HpaePcmBuffer &HpaePcmBuffer::operator=(const std::vector<std::vector<float>> &other)
{
    for (size_t i = 0; i < other.size() && i < pcmProcessVec_.size(); ++i) {
        if (IsMultiFrames()) {
            if (curFrames_.load() < GetFrames()) {
                pcmProcessVec_[i + writePos_.load()] = other[i];
                writePos_.store((writePos_.load() + 1) % GetFrames());
                curFrames_.fetch_add(1);
            } else {
                AUDIO_WARNING_LOG("HpaePcmBuffer::operator=, frames is full index = %{public}zu", i);
            }
        } else {
            pcmProcessVec_[i] = other[i];
        }
    }
    return *this;
}

HpaePcmBuffer &HpaePcmBuffer::operator=(const std::vector<float> &other)
{
    if (IsMultiFrames()) {
        if (curFrames_.load() < GetFrames()) {
            pcmProcessVec_[writePos_.load()] = other;
            writePos_.store((writePos_.load() + 1) % GetFrames());
            curFrames_.fetch_add(1);
        } else {
            AUDIO_WARNING_LOG("HpaePcmBuffer::operator=, frames is full");
        }
    } else {
        pcmProcessVec_[0] = other;
    }
    return *this;
}

void HpaePcmBuffer::Reset()
{
    for (HpaePcmProcess &pcmProc : pcmProcessVec_) {
        pcmProc.Reset();
    }
    readPos_.store(0);
    writePos_.store(0);
    curFrames_.store(0);
}

bool HpaePcmBuffer::GetFrameData(std::vector<float> &frameData)
{
    if (!IsMultiFrames()) {
        return false;
    }

    if (curFrames_.load() <= 0) {
        AUDIO_WARNING_LOG("GetFrameData vector frames is empty");
        return false;
    }
    int32_t ret = memcpy_s(frameData.data(),
        sizeof(float) * frameData.size(),
        pcmProcessVec_[readPos_.load()].Begin(),
        frameSample_ * sizeof(float));
    if (ret != 0) {
        return false;
    }
    readPos_.store((readPos_.load() + 1) % GetFrames());
    curFrames_.fetch_sub(1);
    return true;
}
// frameData is not MultiFrames
bool HpaePcmBuffer::GetFrameData(HpaePcmBuffer &frameData)
{
    if (!IsMultiFrames() || frameData.IsMultiFrames()) {
        return false;
    }

    if (curFrames_.load() <= 0) {
        AUDIO_WARNING_LOG("GetFrameData HpaePcmBuffer frames is empty");
        return false;
    }
    int32_t ret = memcpy_s(frameData.GetPcmDataBuffer(),
        sizeof(float) * frameData.Size(),
        pcmProcessVec_[readPos_.load()].Begin(),
        frameSample_ * sizeof(float));
    if (ret != 0) {
        return false;
    }
    readPos_.store((readPos_.load() + 1) % GetFrames());
    curFrames_.fetch_sub(1);
    return true;
}

bool HpaePcmBuffer::PushFrameData(std::vector<float> &frameData)
{
    if (!IsMultiFrames()) {
        return false;
    }

    if (curFrames_.load() >= GetFrames()) {
        AUDIO_WARNING_LOG("PushFrameData vector frames is full");
        return false;
    }
    int32_t ret = memcpy_s(pcmProcessVec_[writePos_.load()].Begin(), frameByteSize_,
        frameData.data(), sizeof(float) * frameData.size());
    if (ret != 0) {
        AUDIO_ERR_LOG("memcpy failed when PushFrameData");
        return false;
    }
    writePos_.store((writePos_.load() + 1) % GetFrames());
    curFrames_.fetch_add(1);
    return true;
}

bool HpaePcmBuffer::PushFrameData(HpaePcmBuffer &frameData)
{
    if (!IsMultiFrames() || frameData.IsMultiFrames()) {
        return false;
    }

    if (curFrames_.load() >= GetFrames()) {
        AUDIO_WARNING_LOG("PushFrameData HpaePcmBuffer frames is full");
        return false;
    }
    int32_t ret = memcpy_s(pcmProcessVec_[writePos_.load()].Begin(), frameByteSize_,
        frameData.GetPcmDataBuffer(), frameData.Size());
    if (ret != 0) {
        AUDIO_ERR_LOG("memcpy failed when PushFrameData");
        return false;
    }
    writePos_.store((writePos_.load() + 1) % GetFrames());
    curFrames_.fetch_add(1);
    return true;
}

bool HpaePcmBuffer::StoreFrameData(HpaePcmBuffer &frameData)
{
    if (!IsMultiFrames() || frameData.IsMultiFrames()) {
        return false;
    }

    int32_t ret = memcpy_s(pcmProcessVec_[writePos_.load()].Begin(), frameByteSize_,
        frameData.GetPcmDataBuffer(), frameData.Size());
    if (ret != 0) {
        AUDIO_ERR_LOG("memcpy failed when StoreFrameData");
        return false;
    }
    writePos_.store((writePos_.load() + 1) % GetFrames());
    readPos_.store((readPos_.load() + 1) % GetFrames());
    return true;
}

size_t HpaePcmBuffer::RewindBuffer(size_t frames)
{
    if (!IsMultiFrames()) {
        return 0;
    }
    frames = curFrames_.load() + frames > GetFrames() ? GetFrames() - curFrames_.load() : frames;
    readPos_.store((readPos_.load() - frames + GetFrames()) % GetFrames());
    curFrames_.fetch_add(frames);
    return frames;
}

bool HpaePcmBuffer::UpdateReadPos(size_t readPos)
{
    readPos_.store(readPos);
    return true;
}

bool HpaePcmBuffer::UpdateWritePos(size_t writePos)
{
    writePos_.store(writePos);
    return true;
}

void HpaePcmBuffer::SetBufferState(uint32_t state)
{
    pcmBufferInfo_.state = state;
}

size_t HpaePcmBuffer::GetCurFrames() const
{
    return curFrames_.load();
}

void HpaePcmBuffer::SetBufferValid(bool valid)
{
    pcmBufferInfo_.state = valid ?
        (pcmBufferInfo_.state & ~PCM_BUFFER_STATE_INVALID) :
        (pcmBufferInfo_.state | PCM_BUFFER_STATE_INVALID);
}

void HpaePcmBuffer::SetBufferSilence(bool silence)
{
    pcmBufferInfo_.state = silence ?
        (pcmBufferInfo_.state | PCM_BUFFER_STATE_SILENCE) :
        (pcmBufferInfo_.state & ~PCM_BUFFER_STATE_SILENCE);
}
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS