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
#define LOG_TAG "OHAudioBuffer"
#endif

#include "oh_audio_buffer.h"

#include <cinttypes>
#include <climits>
#include <memory>
#include <sys/mman.h>
#include "ashmem.h"

#include "audio_errors.h"
#include "audio_service_log.h"
#include "futex_tool.h"
#include "audio_utils.h"
#include "audio_parcel_helper.h"

namespace {
static constexpr int MINFD = 2;
}

namespace OHOS {
namespace AudioStandard {

class ScopedFd {
public:
    explicit ScopedFd(int fd) : fd_(fd) {}
    ~ScopedFd()
    {
        if (fd_ > MINFD) {
            CloseFd(fd_);
        }
    }
private:
    int fd_ = -1;
};

OHAudioBuffer::OHAudioBuffer(AudioBufferHolder bufferHolder, uint32_t totalSizeInFrame, uint32_t spanSizeInFrame,
    uint32_t byteSizePerFrame) : ohAudioBufferBase_(bufferHolder, totalSizeInFrame, byteSizePerFrame),
    spanBasicInfo_(spanSizeInFrame, totalSizeInFrame, byteSizePerFrame),
    spanInfoList_(nullptr)
{
    AUDIO_DEBUG_LOG("ctor with holder:%{public}d", bufferHolder);
}

OHAudioBuffer::~OHAudioBuffer()
{
    AUDIO_DEBUG_LOG("enter ~OHAudioBuffer()");
    spanInfoList_ = nullptr;
}

int32_t OHAudioBuffer::SpanBasicInfo::SizeCheck(uint32_t totalSizeInFrame) const
{
    if (spanSizeInFrame_ == 0 || spanSizeInByte_ == 0 || spanConut_ == 0) {
        AUDIO_ERR_LOG("failed: invalid var.");
        return ERR_INVALID_PARAM;
    }

    if (totalSizeInFrame < spanSizeInFrame_ || ((spanConut_ * spanSizeInFrame_) != totalSizeInFrame)) {
        AUDIO_ERR_LOG("failed: invalid size.");
        return ERR_INVALID_PARAM;
    }

    return SUCCESS;
}

int32_t OHAudioBuffer::SizeCheck()
{
    auto ret = spanBasicInfo_.SizeCheck(ohAudioBufferBase_.GetTotalSizeInFrame());
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "failed: invalid");

    return SUCCESS;
}

int32_t OHAudioBuffer::Init(int dataFd, int infoFd)
{
    int32_t ret = SizeCheck();
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_INVALID_PARAM, "failed: invalid size.");

    auto spanCount = spanBasicInfo_.spanConut_;
    size_t statusInfoExtSize = spanCount * sizeof(SpanInfo);
    ret = ohAudioBufferBase_.Init(dataFd, infoFd, statusInfoExtSize);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_INVALID_PARAM, "init base failed.");

    spanInfoList_ = reinterpret_cast<SpanInfo *>(ohAudioBufferBase_.GetStatusInfoExtPtr());
    CHECK_AND_RETURN_RET_LOG(spanInfoList_ != nullptr, ERR_INVALID_PARAM, "spaninfolist nullptr");

    AudioBufferHolder bufferHolder = ohAudioBufferBase_.GetBufferHolder();
    if (bufferHolder == AUDIO_SERVER_SHARED || bufferHolder == AUDIO_SERVER_ONLY ||bufferHolder ==
            AUDIO_SERVER_ONLY_WITH_SYNC) {
        for (uint32_t i = 0; i < spanCount; i++) {
            spanInfoList_[i].spanStatus.store(SPAN_INVALID);
        }
    }

    AUDIO_DEBUG_LOG("Init done.");
    return SUCCESS;
}

std::shared_ptr<OHAudioBuffer> OHAudioBuffer::CreateFromLocal(uint32_t totalSizeInFrame,
    uint32_t spanSizeInFrame, uint32_t byteSizePerFrame)
{
    AUDIO_DEBUG_LOG("totalSizeInFrame %{public}u, spanSizeInFrame %{public}u, byteSizePerFrame"
        " %{public}u", totalSizeInFrame, spanSizeInFrame, byteSizePerFrame);

    AudioBufferHolder bufferHolder = AudioBufferHolder::AUDIO_SERVER_SHARED;
    std::shared_ptr<OHAudioBuffer> buffer = std::make_shared<OHAudioBuffer>(bufferHolder, totalSizeInFrame,
        spanSizeInFrame, byteSizePerFrame);
    CHECK_AND_RETURN_RET_LOG(buffer->Init(INVALID_FD, INVALID_FD) == SUCCESS,
        nullptr, "failed to init.");
    return buffer;
}

std::shared_ptr<OHAudioBuffer> OHAudioBuffer::CreateFromRemote(uint32_t totalSizeInFrame,
    uint32_t spanSizeInFrame, uint32_t byteSizePerFrame, AudioBufferHolder bufferHolder,
    int dataFd, int infoFd)
{
    AUDIO_DEBUG_LOG("dataFd %{public}d, infoFd %{public}d", dataFd, infoFd);

    int minfd = 2; // ignore stdout, stdin and stderr.
    CHECK_AND_RETURN_RET_LOG(dataFd > minfd, nullptr, "invalid dataFd: %{public}d", dataFd);

    if (infoFd != INVALID_FD) {
        CHECK_AND_RETURN_RET_LOG(infoFd > minfd, nullptr, "invalid infoFd: %{public}d", infoFd);
    }
    std::shared_ptr<OHAudioBuffer> buffer = std::make_shared<OHAudioBuffer>(bufferHolder, totalSizeInFrame,
        spanSizeInFrame, byteSizePerFrame);
    if (buffer->Init(dataFd, infoFd) != SUCCESS) {
        AUDIO_ERR_LOG("failed to init.");
        return nullptr;
    }
    return buffer;
}

bool OHAudioBuffer::Marshalling(Parcel &parcel) const
{
    AudioBufferHolder bufferHolder = ohAudioBufferBase_.GetBufferHolder();
    CHECK_AND_RETURN_RET_LOG(bufferHolder == AudioBufferHolder::AUDIO_SERVER_SHARED ||
        bufferHolder == AudioBufferHolder::AUDIO_SERVER_INDEPENDENT,
        false, "buffer holder error:%{public}d", bufferHolder);
    MessageParcel &messageParcel = static_cast<MessageParcel &>(parcel);

    auto initInfo = ohAudioBufferBase_.GetInitializationInfo();

    return messageParcel.WriteUint32(bufferHolder) &&
        messageParcel.WriteUint32(initInfo.totalSizeInFrame) &&
        messageParcel.WriteUint32(spanBasicInfo_.spanSizeInFrame_) &&
        messageParcel.WriteUint32(initInfo.byteSizePerFrame) &&
        messageParcel.WriteFileDescriptor(initInfo.dataFd) &&
        messageParcel.WriteFileDescriptor(initInfo.infoFd);
}

OHAudioBuffer *OHAudioBuffer::Unmarshalling(Parcel &parcel)
{
    MessageParcel &messageParcel = static_cast<MessageParcel &>(parcel);
    uint32_t holder = messageParcel.ReadUint32();
    AudioBufferHolder bufferHolder = static_cast<AudioBufferHolder>(holder);
    if (bufferHolder != AudioBufferHolder::AUDIO_SERVER_SHARED &&
        bufferHolder != AudioBufferHolder::AUDIO_SERVER_INDEPENDENT) {
        AUDIO_ERR_LOG("ReadFromParcel buffer holder error:%{public}d", bufferHolder);
        return nullptr;
    }

    bufferHolder = bufferHolder == AudioBufferHolder::AUDIO_SERVER_SHARED ?
         AudioBufferHolder::AUDIO_CLIENT : bufferHolder;
    uint32_t totalSizeInFrame = messageParcel.ReadUint32();
    uint32_t spanSizeInFrame = messageParcel.ReadUint32();
    uint32_t byteSizePerFrame = messageParcel.ReadUint32();

    int dataFd = messageParcel.ReadFileDescriptor();
    int infoFd = messageParcel.ReadFileDescriptor();
    ScopedFd dataFdHandle(dataFd);
    ScopedFd infoFdHandle(infoFd);

    AUDIO_DEBUG_LOG("dataFd %{public}d, infoFd %{public}d", dataFd, infoFd);
    CHECK_AND_RETURN_RET_LOG(dataFd > MINFD, nullptr, "invalid dataFd: %{public}d", dataFd);
    CHECK_AND_RETURN_RET_LOG(infoFd == INVALID_FD || infoFd > MINFD, nullptr, "invalid infoFd: %{public}d", infoFd);

    auto buffer = new(std::nothrow) OHAudioBuffer(bufferHolder, totalSizeInFrame,
        spanSizeInFrame, byteSizePerFrame);
    if (buffer == nullptr || buffer->Init(dataFd, infoFd) != SUCCESS ||
        buffer->ohAudioBufferBase_.basicBufferInfo_ == nullptr) {
        AUDIO_ERR_LOG("buffer init failed.");
        if (buffer != nullptr) delete buffer;
        return nullptr;
    }

    if ((totalSizeInFrame != buffer->ohAudioBufferBase_.basicBufferInfo_->totalSizeInFrame) ||
        (byteSizePerFrame != buffer->ohAudioBufferBase_.basicBufferInfo_->byteSizePerFrame)) {
        AUDIO_WARNING_LOG("data in shared memory diff.");
    }
    return buffer;
}


AudioBufferHolder OHAudioBuffer::GetBufferHolder()
{
    return ohAudioBufferBase_.GetBufferHolder();
}

int32_t OHAudioBuffer::GetSizeParameter(uint32_t &totalSizeInFrame, uint32_t &spanSizeInFrame,
    uint32_t &byteSizePerFrame)
{
    ohAudioBufferBase_.GetSizeParameter(totalSizeInFrame, byteSizePerFrame);
    spanSizeInFrame = spanBasicInfo_.spanSizeInFrame_;

    return SUCCESS;
}

std::atomic<StreamStatus> *OHAudioBuffer::GetStreamStatus()
{
    return ohAudioBufferBase_.GetStreamStatus();
}


float OHAudioBuffer::GetStreamVolume()
{
    return ohAudioBufferBase_.GetStreamVolume();
}

bool OHAudioBuffer::SetStreamVolume(float streamVolume)
{
    return ohAudioBufferBase_.SetStreamVolume(streamVolume);
}

float OHAudioBuffer::GetMuteFactor()
{
    return ohAudioBufferBase_.GetMuteFactor();
}

bool OHAudioBuffer::SetMuteFactor(float muteFactor)
{
    return ohAudioBufferBase_.SetMuteFactor(muteFactor);
}

float OHAudioBuffer::GetDuckFactor()
{
    return ohAudioBufferBase_.GetDuckFactor();
}

bool OHAudioBuffer::SetDuckFactor(float duckFactor, uint32_t durationMs)
{
    return ohAudioBufferBase_.SetDuckFactor(duckFactor, durationMs);
}

uint32_t OHAudioBuffer::GetUnderrunCount()
{
    return ohAudioBufferBase_.GetUnderrunCount();
}

bool OHAudioBuffer::SetUnderrunCount(uint32_t count)
{
    return ohAudioBufferBase_.SetUnderrunCount(count);
}

bool OHAudioBuffer::GetHandleInfo(uint64_t &frames, int64_t &nanoTime)
{
    return ohAudioBufferBase_.GetHandleInfo(frames, nanoTime);
}

void OHAudioBuffer::SetHandleInfo(uint64_t frames, int64_t nanoTime)
{
    ohAudioBufferBase_.SetHandleInfo(frames, nanoTime);
}

int32_t OHAudioBuffer::GetWritableDataFrames()
{
    return ohAudioBufferBase_.GetWritableDataFrames();
}

int32_t OHAudioBuffer::ResetCurReadWritePos(uint64_t readFrame, uint64_t writeFrame, bool wakeFutex)
{
    return ohAudioBufferBase_.ResetCurReadWritePos(readFrame, writeFrame, wakeFutex);
}

bool OHAudioBuffer::CheckWriteOrReadFrame(uint64_t writeOrReadFrame)
{
    uint32_t spanSizeInFrame = spanBasicInfo_.spanSizeInFrame_;

    if ((spanSizeInFrame == 0) || ((writeOrReadFrame % spanSizeInFrame) != 0)) {
        AUDIO_ERR_LOG("spanSizeInFrame: %{public}u writeOrReadFrame: %{public}" PRIu64 "", spanSizeInFrame,
            writeOrReadFrame);
        return false;
    }

    return true;
}

uint64_t OHAudioBuffer::GetCurWriteFrame()
{
    return ohAudioBufferBase_.GetCurWriteFrame();
}

uint64_t OHAudioBuffer::GetCurReadFrame()
{
    return ohAudioBufferBase_.GetCurReadFrame();
}

int32_t OHAudioBuffer::SetCurWriteFrame(uint64_t writeFrame, bool wakeFutex)
{
    CHECK_AND_RETURN_RET_LOG(CheckWriteOrReadFrame(writeFrame), ERR_INVALID_PARAM,
        "Invalid writeFrame: %{public}" PRIu64 "", writeFrame);
    return ohAudioBufferBase_.SetCurWriteFrame(writeFrame, wakeFutex);
}

int32_t OHAudioBuffer::SetCurReadFrame(uint64_t readFrame, bool wakeFutex)
{
    CHECK_AND_RETURN_RET_LOG(CheckWriteOrReadFrame(readFrame), ERR_INVALID_PARAM,
        "Invalid readFrame: %{public}" PRIu64 "", readFrame);
    return ohAudioBufferBase_.SetCurReadFrame(readFrame, wakeFutex);
}

uint32_t OHAudioBuffer::GetSessionId()
{
    return ohAudioBufferBase_.GetSessionId();
}

int32_t OHAudioBuffer::SetSessionId(uint32_t sessionId)
{
    return ohAudioBufferBase_.SetSessionId(sessionId);
}

int32_t OHAudioBuffer::GetWriteBuffer(uint64_t writePosInFrame, BufferDesc &bufferDesc)
{
    size_t offset;
    int32_t ret = ohAudioBufferBase_.GetOffsetByFrameForWrite(writePosInFrame, offset);
    if (ret != SUCCESS) {
        return ret;
    }

    auto spanSizeInByte = spanBasicInfo_.spanSizeInByte_;
    size_t fixedOffset = (offset / spanSizeInByte) * spanSizeInByte;

    return ohAudioBufferBase_.TryGetContinuousBufferByOffset(fixedOffset, spanSizeInByte, bufferDesc);
}

int32_t OHAudioBuffer::GetReadbuffer(uint64_t readPosInFrame, BufferDesc &bufferDesc)
{
    size_t offset;
    int32_t ret = ohAudioBufferBase_.GetOffsetByFrameForRead(readPosInFrame, offset);
    if (ret != SUCCESS) {
        return ret;
    }

    auto spanSizeInByte = spanBasicInfo_.spanSizeInByte_;
    size_t fixedOffset = (offset / spanSizeInByte) * spanSizeInByte;

    return ohAudioBufferBase_.TryGetContinuousBufferByOffset(fixedOffset, spanSizeInByte, bufferDesc);
}

SpanInfo *OHAudioBuffer::GetSpanInfo(uint64_t posInFrame)
{
    uint64_t basePos = ohAudioBufferBase_.GetBasePosInFrame();
    uint32_t totalSizeInFrame = ohAudioBufferBase_.GetTotalSizeInFrame();
    uint64_t maxPos = basePos + totalSizeInFrame + totalSizeInFrame;
    CHECK_AND_RETURN_RET_LOG((basePos <= posInFrame && posInFrame < maxPos), nullptr, "posInFrame %{public}" PRIu64" "
        "out of range, basePos %{public}" PRIu64", maxPos %{public}" PRIu64".", posInFrame, basePos, maxPos);

    uint64_t deltaToBase = posInFrame - basePos;
    if (deltaToBase >= totalSizeInFrame) {
        deltaToBase -= totalSizeInFrame;
    }
    CHECK_AND_RETURN_RET_LOG(deltaToBase < UINT32_MAX && deltaToBase < totalSizeInFrame, nullptr,"invalid "
        "deltaToBase, posInFrame %{public}"  PRIu64" basePos %{public}" PRIu64".", posInFrame, basePos);

    auto spanSizeInFrame = spanBasicInfo_.spanSizeInFrame_;
    if (spanSizeInFrame > 0) {
        uint32_t spanIndex = deltaToBase / spanSizeInFrame;
        auto spanCount = spanBasicInfo_.spanConut_;
        CHECK_AND_RETURN_RET_LOG(spanIndex < spanCount, nullptr, "invalid spanIndex:%{public}d", spanIndex);
        return &spanInfoList_[spanIndex];
    }
    return nullptr;
}

SpanInfo *OHAudioBuffer::GetSpanInfoByIndex(uint32_t spanIndex)
{
    auto spanCount = spanBasicInfo_.spanConut_;
    CHECK_AND_RETURN_RET_LOG(spanIndex < spanCount, nullptr, "invalid spanIndex:%{public}d", spanIndex);
    return &spanInfoList_[spanIndex];
}

uint32_t OHAudioBuffer::GetSpanCount()
{
    return spanBasicInfo_.spanConut_;
}

int64_t OHAudioBuffer::GetLastWrittenTime()
{
    return ohAudioBufferBase_.GetLastWrittenTime();
}

void OHAudioBuffer::SetLastWrittenTime(int64_t time)
{
    ohAudioBufferBase_.SetLastWrittenTime(time);
}

uint32_t OHAudioBuffer::GetSyncWriteFrame()
{
    return ohAudioBufferBase_.GetSyncWriteFrame();
}

bool OHAudioBuffer::SetSyncWriteFrame(uint32_t writeFrame)
{
    return ohAudioBufferBase_.SetSyncWriteFrame(writeFrame);
}

uint32_t OHAudioBuffer::GetSyncReadFrame()
{
    return ohAudioBufferBase_.GetSyncReadFrame();
}

bool OHAudioBuffer::SetSyncReadFrame(uint32_t readFrame)
{
    return ohAudioBufferBase_.SetSyncReadFrame(readFrame);
}

std::atomic<uint32_t> *OHAudioBuffer::GetFutex()
{
    return ohAudioBufferBase_.GetFutex();
}

uint8_t *OHAudioBuffer::GetDataBase()
{
    return ohAudioBufferBase_.GetDataBase();
}

size_t OHAudioBuffer::GetDataSize()
{
    return ohAudioBufferBase_.GetDataSize();
}

void OHAudioBuffer::GetRestoreInfo(RestoreInfo &restoreInfo)
{
    ohAudioBufferBase_.GetRestoreInfo(restoreInfo);
}

void OHAudioBuffer::SetRestoreInfo(RestoreInfo restoreInfo)
{
    ohAudioBufferBase_.SetRestoreInfo(restoreInfo);
}

void OHAudioBuffer::GetTimeStampInfo(uint64_t &position, uint64_t &timeStamp)
{
    ohAudioBufferBase_.GetTimeStampInfo(position, timeStamp);
}

void OHAudioBuffer::SetTimeStampInfo(uint64_t position, uint64_t timeStamp)
{
    ohAudioBufferBase_.SetTimeStampInfo(position, timeStamp);
}

// Compare and swap restore status. If current restore status is NEED_RESTORE, turn it into RESTORING
// to avoid multiple restore.
RestoreStatus OHAudioBuffer::CheckRestoreStatus()
{
    return ohAudioBufferBase_.CheckRestoreStatus();
}

// Allow client to set restore status to NO_NEED_FOR_RESTORE if unnecessary restore happens. Restore status
// can be set to NEED_RESTORE only when it is currently NO_NEED_FOR_RESTORE(and vice versa).
RestoreStatus OHAudioBuffer::SetRestoreStatus(RestoreStatus restoreStatus)
{
    return ohAudioBufferBase_.SetRestoreStatus(restoreStatus);
}

RestoreStatus OHAudioBuffer::GetRestoreStatus()
{
    return ohAudioBufferBase_.GetRestoreStatus();
}

void OHAudioBuffer::SetStopFlag(bool isNeedStop)
{
    ohAudioBufferBase_.SetStopFlag(isNeedStop);
}

bool OHAudioBuffer::GetStopFlag() const
{
    return ohAudioBufferBase_.GetStopFlag();
}

FutexCode OHAudioBuffer::WaitFor(int64_t timeoutInNs, const OnIndexChange &pred)
{
    return ohAudioBufferBase_.WaitFor(timeoutInNs, pred);
}

void OHAudioBuffer::WakeFutex(uint32_t wakeVal)
{
    ohAudioBufferBase_.WakeFutex(wakeVal);
}

void OHAudioBuffer::SetPendingSpanSize(uint64_t spanSize, uint64_t engineSize, uint32_t routeFlag)
{
    ohAudioBufferBase_.SetPendingSpanSize(spanSize, engineSize, routeFlag);
}

uint64_t OHAudioBuffer::GetAndClearPendingSpanSize(uint64_t &engineSize, uint32_t &routeFlag)
{
    return ohAudioBufferBase_.GetAndClearPendingSpanSize(engineSize, routeFlag);
}

bool OHAudioBuffer::HasPendingSpanSize() const
{
    return ohAudioBufferBase_.HasPendingSpanSize();
}

void OHAudioBuffer::ClearPendingSpanSize()
{
    ohAudioBufferBase_.ClearPendingSpanSize();
}

} // namespace AudioStandard
} // namespace OHOS
