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

#ifndef AUDIO_RING_CACHE_H
#define AUDIO_RING_CACHE_H

#include "stdint.h"
#include <atomic>
#include <cstddef>
#include <memory>
#include <mutex>

namespace OHOS {
namespace AudioStandard {
// in plan: Using a globally unified buffer description in AudioStandard namesapce.
struct BufferWrap {
    uint8_t *dataPtr = nullptr;
    size_t dataSize = 0;
};
enum RetType : uint32_t {
    OPERATION_SUCCESS = 0,
    OPERATION_FAILED,
    INDEX_OUT_OF_RANGE,
    DATA_INSUFFICIENT,
    INVALID_STATUS,
    INVALID_OPERATION,
    INVALID_PARAMS,
};
struct OptResult {
    RetType ret = INVALID_OPERATION;
    size_t size = 0;
};

/**
 * AudioRingCache itself is thread safe, but you must be careful when combining calls to GetWriteableSize and Enqueue.
 * As the actual writable size may have changed when Enqueue is called. In this case, enqueue will return a error, and
 * you need to handle it. The combination of calling GetReadableSize and Dequeue all also requires handling this issue.
*/
class AudioRingCache {
public:
    static std::unique_ptr<AudioRingCache> Create(size_t cacheSize);
    AudioRingCache(size_t cacheSize);
    ~AudioRingCache();

    OptResult ReConfig(size_t cacheSize, bool copyRemained = true);

    // This operation will clear the buffer and reset inner read/write index.
    void ResetBuffer();

    size_t GetCahceSize();

    // Get the buffer size that can be written. 0 <= WritableSize <= cacheTotalSize_
    OptResult GetWritableSize();

    // Get the buffer size that can be read. 0 <= ReadableSize <= cacheTotalSize_
    OptResult GetReadableSize();

    // Call GetWritableSize first, than call Enqueue with valid buffer size that <= WritableSize.
    // Call Enqueue will move write index ahead.
    OptResult Enqueue(const BufferWrap &buffer);

    // Call GetReadableSize first, than call Dequeue with valid buffer size that <= ReadableSize.
    // Call Dequeue will move read index ahead, together with inner base index ahead.
    OptResult Dequeue(const BufferWrap &buffer);

private:
    bool Init();
    OptResult GetWritableSizeNoLock();
    OptResult GetReadableSizeNoLock();
    OptResult HandleCrossDequeue(size_t tempReadIndex, size_t readableSize, const BufferWrap &buffer);
    void ReIndex();
private:
    std::mutex cacheMutex_;
    std::unique_ptr<uint8_t[]> basePtr_;
    size_t cacheTotalSize_ = 0;

    size_t baseIndex_ = 0;
    size_t writeIndex_ = 0;
    size_t readIndex_ = 0;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // AUDIO_RING_CACHE_H
