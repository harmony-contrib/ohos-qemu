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

#ifndef HPAE_PCM_BUFFER_H
#define HPAE_PCM_BUFFER_H
#include <vector>
#include <type_traits>
#include <memory>
#include <algorithm>
#include "audio_stream_info.h"
#include "audio_info.h"
#include "hpae_pcm_process.h"
namespace OHOS {
namespace AudioStandard {
namespace HPAE {
constexpr size_t MEMORY_ALIGN_BYTE_NUM = 64;

enum HpaeSourceBufferType {
    HPAE_SOURCE_BUFFER_TYPE_DEFAULT,
    HPAE_SOURCE_BUFFER_TYPE_MIC,
    HPAE_SOURCE_BUFFER_TYPE_EC,
    HPAE_SOURCE_BUFFER_TYPE_MICREF,
    HPAE_SOURCE_BUFFER_TYPE_INJECTOR,
};

enum PcmBufferState : uint32_t {
    PCM_BUFFER_STATE_INVALID = 1, // bit 0
    PCM_BUFFER_STATE_SILENCE = 2, // bit 1
};

// redefine allocator to ensure memory alignment
template <typename T, size_t Alignment>
class AlignedAllocator : public std::allocator<T> {
public:
    using pointer = T *;
    using size_type = size_t;

    pointer Allocate(size_type n)
    {
        void *ptr = std::aligned_alloc(Alignment, n * sizeof(T));
        return static_cast<pointer>(ptr);
    }

    void DeAllocate(pointer p, size_type n)
    {
        std::free(p);
    }
};

struct PcmBufferInfo {
    PcmBufferInfo(uint32_t ch1, uint32_t frameLen1, uint32_t rate1)
        : ch(ch1), frameLen(frameLen1), rate(rate1)
    {}
    PcmBufferInfo(uint32_t ch1, uint32_t frameLen1, uint32_t rate1, uint64_t channelLayout1)
        : ch(ch1), frameLen(frameLen1), rate(rate1), channelLayout(channelLayout1)
    {}
    PcmBufferInfo(uint32_t ch1, uint32_t frameLen1, uint32_t rate1, uint64_t channelLayout1,
        uint32_t frames1)
        : ch(ch1), frameLen(frameLen1), rate(rate1), channelLayout(channelLayout1), frames(frames1)
    {}
    PcmBufferInfo() = default;
    uint32_t ch;
    uint32_t frameLen;
    uint32_t rate;
    uint64_t channelLayout = 0;
    uint32_t frames = 1;
    bool isMultiFrames = false;
    uint32_t state = 0;
};

// todo: multithread access?
class HpaePcmBuffer {
public:
    HpaePcmBuffer() = delete;
    explicit HpaePcmBuffer(PcmBufferInfo &pcmBufferInfo);
    HpaePcmBuffer(HpaePcmBuffer &&other);
    HpaePcmBuffer(const HpaePcmBuffer &other) = delete;
    ~HpaePcmBuffer()
    {
    }
    HpaePcmBuffer &operator=(const HpaePcmBuffer &other);
    HpaePcmBuffer &operator=(HpaePcmBuffer &&other) = delete;

    PcmBufferInfo GetPcmBufferInfo() const
    {
        return pcmBufferInfo_;
    }

    uint32_t GetChannelCount() const
    {
        return pcmBufferInfo_.ch;
    }

    uint32_t GetFrameLen() const
    {
        return pcmBufferInfo_.frameLen;
    }

    uint32_t GetSampleRate() const
    {
        return pcmBufferInfo_.rate;
    }

    bool IsMultiFrames() const
    {
        return pcmBufferInfo_.isMultiFrames;
    }

    bool IsValid() const
    {
        return (pcmBufferInfo_.state & PCM_BUFFER_STATE_INVALID) == 0;
    }

    bool IsSilence() const
    {
        return (pcmBufferInfo_.state & PCM_BUFFER_STATE_SILENCE) != 0;
    }

    uint32_t GetBufferState() const
    {
        return pcmBufferInfo_.state;
    }

    uint64_t GetChannelLayout() const
    {
        return pcmBufferInfo_.channelLayout;
    }

    void ReConfig(const PcmBufferInfo &pcmBufferInfo)
    {
        pcmBufferInfo_ = pcmBufferInfo;
        InitPcmProcess();
    }

    bool GetFrameData(std::vector<float> &frameData);
    bool GetFrameData(HpaePcmBuffer &frameData);
    bool PushFrameData(std::vector<float> &frameData);
    bool PushFrameData(HpaePcmBuffer &frameData);
    // store history frame for offload
    bool StoreFrameData(HpaePcmBuffer &frameData);
    // rewind history frame for offload, return frames that rewinded
    size_t RewindBuffer(size_t frames);

    HpaePcmProcess &operator[](size_t index)
    {
        return pcmProcessVec_[index];
    }

    const HpaePcmProcess &operator[](size_t index) const
    {
        return pcmProcessVec_[index];
    }

    size_t Size() const
    {
        return bufferByteSize_;
    }

    size_t DataSize() const
    {
        return dataByteSize_;
    }

    size_t GetFrames() const
    {
        return pcmBufferInfo_.frames;
    }

    size_t GetReadPos() const
    {
        return readPos_.load();
    }

    size_t GetWritePos() const
    {
        return writePos_.load();
    }

    bool UpdateReadPos(size_t readPos);
    bool UpdateWritePos(size_t writePos);
    void SetBufferValid(bool valid);
    void SetBufferSilence(bool silence);
    void SetBufferState(uint32_t state);
    size_t GetCurFrames() const;

    HpaePcmBuffer &operator=(const std::vector<std::vector<float>> &other);
    HpaePcmBuffer &operator=(const std::vector<float> &other);

    HpaePcmBuffer &operator+=(HpaePcmBuffer &other);
    HpaePcmBuffer &operator-=(HpaePcmBuffer &other);
    HpaePcmBuffer &operator*=(HpaePcmBuffer &other);
    void Reset();

    std::vector<HpaePcmProcess>::iterator begin()
    {
        return pcmProcessVec_.begin();
    }

    std::vector<HpaePcmProcess>::iterator end()
    {
        return pcmProcessVec_.end();
    }

    std::vector<HpaePcmProcess>::const_iterator begin() const
    {
        return pcmProcessVec_.begin();
    }

    std::vector<HpaePcmProcess>::const_iterator end() const
    {
        return pcmProcessVec_.end();
    }

    float *GetPcmDataBuffer()
    {
        return pcmDataBuffer_.data();
    }

    const float *GetPcmDataBuffer() const
    {
        return pcmDataBuffer_.data();
    }

    size_t GetFrameSample()
    {
        return frameSample_;
    }

    HpaeSourceBufferType GetSourceBufferType()
    {
        return sourceBufferType_;
    }

    void SetSourceBufferType(HpaeSourceBufferType type)
    {
        sourceBufferType_ = type;
    }

    SplitStreamType GetSplitStreamType() const
    {
        return splitStreamType_;
    }

    void SetSplitStreamType(SplitStreamType type)
    {
        splitStreamType_ = type;
    }

    void SetAudioStreamType(AudioStreamType type)
    {
        streamType_ = type;
    }

    AudioStreamType GetAudioStreamType() const
    {
        return streamType_;
    }

    void SetAudioStreamUsage(StreamUsage usage)
    {
        streamUsage_ = usage;
    }

    StreamUsage GetAudioStreamUsage() const
    {
        return streamUsage_;
    }

private:
    void InitPcmProcess();

    // todo: add err to deal with operator override
    std::vector<float, AlignedAllocator<float, MEMORY_ALIGN_BYTE_NUM>> pcmDataBuffer_;
    size_t bufferFloatSize_;
    size_t bufferByteSize_;
    size_t frameFloatSize_;
    size_t frameByteSize_;
    size_t frameSample_;
    size_t dataByteSize_;
    std::atomic<size_t> readPos_;
    std::atomic<size_t> writePos_;
    std::atomic<size_t> curFrames_;
    std::vector<HpaePcmProcess> pcmProcessVec_;
    PcmBufferInfo pcmBufferInfo_;
    HpaeSourceBufferType sourceBufferType_ = HPAE_SOURCE_BUFFER_TYPE_DEFAULT;
    SplitStreamType splitStreamType_ = STREAM_TYPE_DEFAULT;
    AudioStreamType streamType_ = STREAM_DEFAULT;
    StreamUsage streamUsage_ = STREAM_USAGE_INVALID;
};
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
#endif