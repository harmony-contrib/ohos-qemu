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
#ifndef RING_BUFFER_WRAPPER_H
#define RING_BUFFER_WRAPPER_H

#include "audio_errors.h"
#include "audio_log.h"
#include "securec.h"

namespace OHOS {
namespace AudioStandard {
/* If buflength is 0, buffer must be nullptr;
   conversely, if buffer is nullptr, buflength must be 0.
   Otherwise, the behavior is undefined. */
struct BasicBufferDesc {
    uint8_t *buffer = nullptr;
    size_t bufLength = 0;

    bool IsLegal() const
    {
        if ((buffer == nullptr) && (bufLength == 0)) {
            return true;
        }

        if ((buffer != nullptr) && (bufLength > 0)) {
            return true;
        }

        return false;
    }

    bool IsBufferOverlap(const BasicBufferDesc &inBuffer) const
    {
        if ((buffer == nullptr) || (inBuffer.buffer == nullptr)) {
            return false;
        }

        if ((buffer >= (inBuffer.buffer + inBuffer.bufLength)) || (inBuffer.buffer >= buffer + bufLength)) {
            return false;
        }

        return true;
    }

    int32_t SeekFromStart(size_t offset)
    {
        if (offset > bufLength) {
            return ERR_INVALID_PARAM;
        }

        bufLength -= offset;

        if (bufLength == 0) {
            buffer = nullptr;
        } else {
            buffer += offset;
        }
        return SUCCESS;
    }
};

/**
 * Precondition: dataLength must not exceed the total buffer capacity
 * (sum of all bufLength).
 * The two memory blocks must not overlap in any part of their address ranges.
 * If first buffer is null, second is null.
 * Violation results in undefined behavior.
 */
struct RingBufferWrapper {
    static inline constexpr size_t DESC_SIZE = 2;

    std::array<BasicBufferDesc, DESC_SIZE> basicBufferDescs = {};
    size_t dataLength = 0;

    size_t GetBufferSize() const
    {
        size_t size = 0;
        for (const auto &[buffer, bufLength] : basicBufferDescs) {
            size += bufLength;
        }
        return size;
    }

    bool IsLegal() const
    {
        if ((!basicBufferDescs[0].IsLegal()) || (!basicBufferDescs[1].IsLegal())) {
            return false;
        }

        if (basicBufferDescs[0].IsBufferOverlap(basicBufferDescs[1])) {
            return false;
        }

        if (dataLength > GetBufferSize()) {
            return false;
        }

        if ((basicBufferDescs[0].buffer) == nullptr && (basicBufferDescs[1].buffer != nullptr)) {
            return false;
        }

        return true;
    }

    void Reset()
    {
        dataLength = 0;
        for (auto &[buffer, bufLength] : basicBufferDescs) {
            buffer = nullptr;
            bufLength = 0;
        }
    }

    void SetBuffersValueWithBufLen(int8_t ch) const
    {
        for (auto &[buffer, bufLength] : basicBufferDescs) {
            if (buffer != nullptr && bufLength != 0) {
                memset_s(buffer, bufLength, ch, bufLength);
            }
        }
    }

    void SetBuffersValueWithSpecifyDataLen(int8_t ch) const
    {
        size_t remainSize = dataLength;
        for (auto &[buffer, bufLength] : basicBufferDescs) {
            size_t setSize = std::min(remainSize, bufLength);
            remainSize -= setSize;
            if (buffer != nullptr && bufLength != 0 && setSize != 0) {
                auto ret = memset_s(buffer, bufLength, ch, setSize);
                if (ret != EOK) [[unlikely]] {
                    AUDIO_ERR_LOG("memset err :%{public}d", ret);
                }
            }
        }
    }

    int32_t SeekFromStart(size_t offset)
    {
        if (offset > GetBufferSize()) {
            return ERR_INVALID_PARAM;
        }

        size_t remainSeek = offset;
        dataLength <= offset ? dataLength = 0 : dataLength -= offset;

        for (auto &basicBuffer : basicBufferDescs) {
            size_t seekSize = std::min(remainSeek, basicBuffer.bufLength);
            basicBuffer.SeekFromStart(seekSize);
            remainSeek -= seekSize;
        }

        if (basicBufferDescs[0].bufLength == 0) {
            std::swap(basicBufferDescs[0], basicBufferDescs[1]);
        }
        return SUCCESS;
    }

    int32_t CopyInputBufferValueToCurBuffer(const RingBufferWrapper &buffer)
    {
        if (GetBufferSize() < buffer.dataLength) {
            return ERR_INVALID_PARAM;
        }

        RingBufferWrapper dstBuffer(*this);
        RingBufferWrapper srcBuffer(buffer);
        dstBuffer.dataLength = buffer.dataLength;

        size_t remainSize = buffer.dataLength;
        while (remainSize > 0) {
            auto copySize = std::min({srcBuffer.basicBufferDescs[0].bufLength, dstBuffer.basicBufferDescs[0].bufLength,
                remainSize});
            remainSize -= copySize;

            if (copySize == 0) [[unlikely]] {
                // This branch should never be executed under any valid conditions. Consider let it crash?
                AUDIO_ERR_LOG("copySize is 0");
                return ERR_INVALID_PARAM;
            }
            auto ret = memcpy_s(dstBuffer.basicBufferDescs[0].buffer, dstBuffer.basicBufferDescs[0].bufLength,
                srcBuffer.basicBufferDescs[0].buffer, copySize);
            if (ret != EOK) [[unlikely]] {
                AUDIO_ERR_LOG("memcpy err :%{public}d", ret);
            }
            dstBuffer.SeekFromStart(copySize);
            srcBuffer.SeekFromStart(copySize);
        }

        dataLength = buffer.dataLength;
        return SUCCESS;
    }
};
} // namespace AudioStandard
} // namespace OHOS
#endif // RING_BUFFER_WRAPPER_H
