/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under the Apache License, Version 2.0. */
#ifndef HPAE_CAPTURE_FRAME_ASSEMBLER_H
#define HPAE_CAPTURE_FRAME_ASSEMBLER_H
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>

namespace OHOS { namespace AudioStandard { namespace HPAE {
// Private ordinary-MIC byte queue. HDI calls never execute under this mutex.
// Every read carries the immutable lease acquired before that actual read.
class HpaeCaptureFrameAssembler final {
public:
    uint64_t Begin(size_t outputBytes, size_t sampleFrameBytes, size_t maximumReadBytes)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (outputBytes == 0 || sampleFrameBytes == 0 || maximumReadBytes == 0 ||
            outputBytes % sampleFrameBytes != 0 || maximumReadBytes % sampleFrameBytes != 0) {
            return 0;
        }
        if (outputBytes_ != outputBytes || sampleFrameBytes_ != sampleFrameBytes ||
            maximumReadBytes_ != maximumReadBytes) {
            RetireLocked();
            outputBytes_ = outputBytes;
            sampleFrameBytes_ = sampleFrameBytes;
            maximumReadBytes_ = maximumReadBytes;
        }
        return generation_;
    }

    bool IsCurrent(uint64_t lease) const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return lease != 0 && lease == generation_;
    }

    bool HasFrame(uint64_t lease) const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return lease != 0 && lease == generation_ && outputBytes_ != 0 && bytes_.size() >= outputBytes_;
    }

    bool Append(uint64_t lease, const char *data, size_t size)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (lease == 0 || lease != generation_ || data == nullptr || size == 0 ||
            size > maximumReadBytes_ || sampleFrameBytes_ == 0 || size % sampleFrameBytes_ != 0 ||
            bytes_.size() >= outputBytes_) {
            return false;
        }
        // Before a read we have less than one output frame; this read is bounded
        // by its actual caller capacity. No padding, recovery or time synthesis.
        bytes_.insert(bytes_.end(), data, data + size);
        return true;
    }

    template<class Publish> bool PublishFrame(uint64_t lease, Publish publish)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (lease == 0 || lease != generation_ || outputBytes_ == 0 || bytes_.size() < outputBytes_) {
            return false;
        }
        // Production publish is ONLY ConvertToFloat + OutputPort::WriteDataToOutput,
        // both bounded local operations; no HDI, public callback or lifecycle API.
        // Serializing this commit with Invalidate prevents a retired read publishing.
        publish(bytes_.data());
        bytes_.erase(bytes_.begin(), bytes_.begin() + outputBytes_);
        return true;
    }

    void Invalidate()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        RetireLocked();
    }
private:
    void RetireLocked()
    {
        bytes_.clear();
        if (++generation_ == 0) { ++generation_; }
    }
    mutable std::mutex mutex_;
    uint64_t generation_ = 1;
    size_t outputBytes_ = 0;
    size_t sampleFrameBytes_ = 0;
    size_t maximumReadBytes_ = 0;
    std::vector<char> bytes_;
};
} } }
#endif
