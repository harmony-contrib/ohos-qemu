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
#define LOG_TAG "AudioRingCache"
#endif

#include "audio_ring_cache.h"
#include "audio_service_log.h"

#include "securec.h"

namespace OHOS {
namespace AudioStandard {
namespace {
static const size_t MAX_CACHE_SIZE = 16 * 1024 * 1024; // 16M
static const size_t BASE_INDEX_FENCE = SIZE_MAX - 2 * MAX_CACHE_SIZE;
}
AudioRingCache::AudioRingCache(size_t cacheSize) : cacheTotalSize_(cacheSize)
{
    AUDIO_INFO_LOG("AudioRingCache() with cacheSize:%{public}zu", cacheSize);
}

AudioRingCache::~AudioRingCache()
{
    AUDIO_DEBUG_LOG("~AudioRingCache()");
}

// Init is private and called in Create, not need lock. Call Init with lock in ReConfig
bool AudioRingCache::Init()
{
    if (cacheTotalSize_ > MAX_CACHE_SIZE) {
        AUDIO_ERR_LOG("Init failed: size too large:%{public}zu", cacheTotalSize_);
        return false;
    }
    baseIndex_ = 0;
    writeIndex_ = 0;
    readIndex_ = 0;
    basePtr_ = std::make_unique<uint8_t[]>(cacheTotalSize_);
    if (basePtr_ == nullptr) {
        AUDIO_ERR_LOG("Init failed, get memory failed size is:%{public}zu", cacheTotalSize_);
        return false;
    }
    if (memset_s(basePtr_.get(), cacheTotalSize_, 0, cacheTotalSize_) != EOK) {
        AUDIO_ERR_LOG("Init call memeset_s failed.");
        return false;
    }
    return true;
}

std::unique_ptr<AudioRingCache> AudioRingCache::Create(size_t cacheSize)
{
    if (cacheSize > MAX_CACHE_SIZE) {
        AUDIO_ERR_LOG("Create failed: size too large:%{public}zu", cacheSize);
        return nullptr;
    }
    std::unique_ptr<AudioRingCache> ringCache = std::make_unique<AudioRingCache>(cacheSize);

    if (ringCache->Init() != true) {
        AUDIO_ERR_LOG("Create failed: Init failed");
        return nullptr;
    }
    return ringCache;
}

OptResult AudioRingCache::ReConfig(size_t cacheSize, bool copyRemained)
{
    AUDIO_INFO_LOG("ReConfig with cacheSize:%{public}zu", cacheSize);
    OptResult result;
    result.ret = OPERATION_SUCCESS;
    result.size = cacheSize;
    if (cacheSize > MAX_CACHE_SIZE) {
        result.ret = INDEX_OUT_OF_RANGE;
        AUDIO_ERR_LOG("ReConfig failed: size too large:%{public}zu", cacheSize);
        return result;
    }
    if (!copyRemained) {
        cacheTotalSize_ = cacheSize;
        std::lock_guard<std::mutex> lock(cacheMutex_); // need lock as we operation buffer in Init
        if (Init() != true) {
            result.ret = OPERATION_FAILED;
            return result;
        }
        AUDIO_INFO_LOG("ReConfig success cacheSize:%{public}zu", cacheSize);
        return result;
    }
    // if need copyRemained, we should check the cacheSize >= remained size.
    result = GetReadableSize();
    if (result.ret != OPERATION_SUCCESS || result.size > cacheSize) {
        AUDIO_ERR_LOG("ReConfig in copyRemained failed ret:%{public}d size :%{public}zu", result.ret, cacheSize);
        return result;
    }
    std::unique_ptr<uint8_t[]> temp = std::make_unique<uint8_t[]>(result.size);
    result = Dequeue({temp.get(), result.size});
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, result,
        "ReConfig dequeue failed ret:%{public}d", result.ret);
    std::unique_lock<std::mutex> uniqueLock(cacheMutex_);
    cacheTotalSize_ = cacheSize;
    if (Init() != true) {
        result.ret = OPERATION_FAILED;
        return result;
    }
    uniqueLock.unlock(); // unlock as Enqueue will lock
    result = Enqueue({temp.get(), result.size});

    return result;
}

void AudioRingCache::ResetBuffer()
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    baseIndex_ = 0;
    writeIndex_ = 0;
    readIndex_ = 0;
    if (memset_s(basePtr_.get(), cacheTotalSize_, 0, cacheTotalSize_) != EOK) {
        AUDIO_ERR_LOG("ResetBuffer call memeset_s failed.");
    }
}

size_t AudioRingCache::GetCahceSize()
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    return cacheTotalSize_;
}

OptResult AudioRingCache::GetWritableSize()
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    return GetWritableSizeNoLock();
}

// call this with cacheMutex_
OptResult AudioRingCache::GetWritableSizeNoLock()
{
    OptResult result;
    if (writeIndex_ < readIndex_ || writeIndex_ - readIndex_ > cacheTotalSize_) {
        result.ret = INVALID_STATUS;
        result.size = 0;
        AUDIO_ERR_LOG("GetWritableSize failed: writeIndex_[%{public}zu] readIndex_[%{public}zu]",
            writeIndex_, readIndex_);
        return result;
    }
    result.size = cacheTotalSize_ - (writeIndex_ - readIndex_);
    result.ret = OPERATION_SUCCESS;
    return result;
}

OptResult AudioRingCache::GetReadableSize()
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    return GetReadableSizeNoLock();
}

// call this with cacheMutex_
OptResult AudioRingCache::GetReadableSizeNoLock()
{
    OptResult result;
    if (writeIndex_ < readIndex_ || writeIndex_ - readIndex_ > cacheTotalSize_) {
        result.ret = INVALID_STATUS;
        result.size = 0;
        AUDIO_ERR_LOG("GetReadableSize failed: writeIndex_[%{public}zu] readIndex_[%{public}zu]",
            writeIndex_, readIndex_);
        return result;
    }
    result.size = writeIndex_ - readIndex_;
    result.ret = OPERATION_SUCCESS;
    return result;
}

OptResult AudioRingCache::Enqueue(const BufferWrap &buffer)
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    OptResult result;
    // params check
    if (buffer.dataPtr == nullptr || buffer.dataSize > MAX_CACHE_SIZE || buffer.dataSize == 0) {
        result.ret = INVALID_PARAMS;
        AUDIO_ERR_LOG("Enqueue failed: BufferWrap is null or size %{public}zu is too large", buffer.dataSize);
        return result;
    }

    // Get writable size here,do not directly call GetWriteableSize() as it will cause a deadlock.
    result = GetWritableSizeNoLock();
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, result, "Enqueue failed to get writeable size.");
    size_t writableSize = result.size;

    if (buffer.dataSize > writableSize) {
        result = {INDEX_OUT_OF_RANGE, writableSize};
        AUDIO_WARNING_LOG("Enqueue find buffer not enough, writableSize:%{public}zu , enqueue size:%{public}zu",
            writableSize, buffer.dataSize);
        return result;
    }
    // buffer.dataSize <= writableSize, let's do memory copy.
    // judge if cross buffer
    size_t tempWriteIndex = writeIndex_ + buffer.dataSize;
    if (writeIndex_ < baseIndex_ + cacheTotalSize_ && tempWriteIndex > baseIndex_ + cacheTotalSize_) {
        size_t headSize = baseIndex_ + cacheTotalSize_ - writeIndex_;
        size_t tailSize = tempWriteIndex - (baseIndex_ + cacheTotalSize_);
        void *headPtr = static_cast<void *>(basePtr_.get() + (writeIndex_ - baseIndex_));
        void *tailPtr = static_cast<void *>(basePtr_.get());
        if ((memcpy_s(headPtr, headSize, static_cast<void *>(buffer.dataPtr), headSize)) == EOK &&
            memcpy_s(tailPtr, tailSize, static_cast<void *>(buffer.dataPtr + headSize), tailSize) == EOK) {
            writeIndex_ = tempWriteIndex; // move write index
            result = {OPERATION_SUCCESS, buffer.dataSize};
            return result;
        }
        result = {OPERATION_FAILED, writableSize};
        AUDIO_ERR_LOG("Enqueue memcpy_s failed: writeIndex_[%{public}zu] baseIndex_[%{public}zu] buffer.dataSize"
            "[%{public}zu]", writeIndex_, baseIndex_, buffer.dataSize);
        return result;
    }
    // not cross
    size_t offset = writeIndex_ >= baseIndex_ + cacheTotalSize_ ? (writeIndex_ - baseIndex_ - cacheTotalSize_) :
        (writeIndex_ - baseIndex_);
    void *writePtr = static_cast<void *>(basePtr_.get() + offset);
    if ((memcpy_s(writePtr, cacheTotalSize_ - offset, static_cast<void *>(buffer.dataPtr), buffer.dataSize)) == EOK) {
        writeIndex_ = tempWriteIndex; // move write index
        result = {OPERATION_SUCCESS, buffer.dataSize};
        return result;
    }
    AUDIO_ERR_LOG("Enqueue memcpy_s failed: writeIndex_[%{public}zu] baseIndex_[%{public}zu] buffer.dataSize"
        "[%{public}zu]", writeIndex_, baseIndex_, buffer.dataSize);
    result = {OPERATION_FAILED, writableSize};
    return result;
}

void AudioRingCache::ReIndex()
{
    AUDIO_INFO_LOG("ReIndex baseIndex[%{public}zu] readIndex[%{public}zu] writeIndex[%{public}zu]", baseIndex_,
        readIndex_, writeIndex_);
    writeIndex_ -= baseIndex_;
    readIndex_ -= baseIndex_;
    baseIndex_ = 0;
}
OptResult AudioRingCache::HandleCrossDequeue(size_t tempReadIndex, size_t readableSize, const BufferWrap &buffer)
{
    OptResult result;
    // cross
    size_t headSize = baseIndex_ + cacheTotalSize_ - readIndex_;
    size_t tailSize = tempReadIndex - (baseIndex_ + cacheTotalSize_);
    void *headPtr = static_cast<void *>(basePtr_.get() + (readIndex_ - baseIndex_));
    void *tailPtr = static_cast<void *>(basePtr_.get());
    if (memcpy_s(static_cast<void *>(buffer.dataPtr), headSize, headPtr, headSize) != EOK ||
        memcpy_s(static_cast<void *>(buffer.dataPtr + headSize), tailSize, tailPtr, tailSize) != EOK) {
        result = {OPERATION_FAILED, readableSize};
        AUDIO_ERR_LOG("Dequeue memcpy_s failed: readIndex[%{public}zu] baseIndex_[%{public}zu] buffer.dataSize"
            "[%{public}zu]", readIndex_, baseIndex_, buffer.dataSize);
        return result;
    }
    if (memset_s(headPtr, headSize, 0, headSize) != EOK) {
        AUDIO_ERR_LOG("reset headPtr fail.");
    }
    if (memset_s(tailPtr, tailSize, 0, tailSize) != EOK) {
        AUDIO_ERR_LOG("reset headPtr fail.");
    }

    readIndex_ = tempReadIndex; // move write index
    baseIndex_ += cacheTotalSize_; // move base index
    if (baseIndex_ >= BASE_INDEX_FENCE) {
        ReIndex();
    }
    result = {OPERATION_SUCCESS, buffer.dataSize};
    return result;
}

OptResult AudioRingCache::Dequeue(const BufferWrap &buffer)
{
    std::lock_guard<std::mutex> lock(cacheMutex_);
    OptResult result;
    // params check
    if (buffer.dataPtr == nullptr || buffer.dataSize > MAX_CACHE_SIZE) {
        result.ret = INVALID_PARAMS;
        AUDIO_ERR_LOG("Dequeue failed: BufferWrap is null or size %{public}zu is too large", buffer.dataSize);
        return result;
    }

    result = GetReadableSizeNoLock();
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, result, "Dequeue failed to get readable size.");
    size_t readableSize = result.size;
    if (buffer.dataSize > readableSize) {
        result = {INVALID_OPERATION, readableSize};
        AUDIO_WARNING_LOG("Dequeue find buffer not enough, readableSize:%{public}zu , Dequeue size:%{public}zu",
            readableSize, buffer.dataSize);
        return result;
    }

    // buffer.dataSize <= readableSize, let's do memory copy.
    // judge if cross buffer
    size_t tempReadIndex = readIndex_ + buffer.dataSize;
    if (tempReadIndex > baseIndex_ + cacheTotalSize_) {
        return HandleCrossDequeue(tempReadIndex, readableSize, buffer);
    }

    // not cross
    void *readPtr = static_cast<void *>(basePtr_.get() + readIndex_ - baseIndex_);
    if ((memcpy_s(static_cast<void *>(buffer.dataPtr), buffer.dataSize, readPtr, buffer.dataSize)) != EOK) {
        AUDIO_ERR_LOG("Dequeue memcpy_s failed: readIndex_[%{public}zu] baseIndex_[%{public}zu] buffer.dataSize"
            "[%{public}zu]", readIndex_, baseIndex_, buffer.dataSize);
        result = {OPERATION_FAILED, readableSize};
        return result;
    }
    if (memset_s(readPtr, buffer.dataSize, 0, buffer.dataSize) != EOK) {
        AUDIO_ERR_LOG("reset readPtr fail.");
    }
    if (tempReadIndex - baseIndex_ == cacheTotalSize_) {
        baseIndex_ += cacheTotalSize_;
    }
    readIndex_ = tempReadIndex; // move read index
    if (baseIndex_ >= BASE_INDEX_FENCE) {
        ReIndex();
    }
    result = {OPERATION_SUCCESS, buffer.dataSize};
    return result;
}
} // namespace AudioStandard
} // namespace OHOS
