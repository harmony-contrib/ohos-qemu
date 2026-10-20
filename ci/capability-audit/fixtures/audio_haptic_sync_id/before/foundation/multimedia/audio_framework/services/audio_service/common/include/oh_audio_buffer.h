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

#ifndef OH_AUDIO_BUFFER_H
#define OH_AUDIO_BUFFER_H

#include <atomic>
#include <string>
#include <type_traits>
#include <optional>

#include "message_parcel.h"

#include "audio_info.h"
#include "ring_buffer_wrapper.h"
#include "audio_shared_memory.h"
#include "futex_tool.h"

namespace OHOS {
namespace AudioStandard {
const size_t BASIC_SYNC_INFO_SIZE = 8; // sizeof(uint32_t) * 2
static constexpr int INVALID_BUFFER_FD = -1;
static constexpr int INVALID_FD = -1;
using OnIndexChange = std::function<bool(void)>;

// client or server.
enum AudioBufferHolder : uint32_t {
    // normal stream, Client buffer created when readFromParcel
    AUDIO_CLIENT = 0,
    // normal stream, Server buffer shared with Client
    AUDIO_SERVER_SHARED,
    // normal stream, Server buffer shared with hdi
    AUDIO_SERVER_ONLY,
    // Server buffer shared with hdi and has sync info
    AUDIO_SERVER_ONLY_WITH_SYNC,
    // Independent stream
    AUDIO_SERVER_INDEPENDENT,
};

enum StreamStatus : uint32_t {
    STREAM_IDEL = 0,
    STREAM_STARTING,
    STREAM_RUNNING,
    STREAM_PAUSING,
    STREAM_PAUSED,
    STREAM_STOPPING,
    STREAM_STOPPED,
    STREAM_RELEASED,
    STREAM_STAND_BY,
    STREAM_INVALID
};

enum BufferPosition : uint32_t {
    BUFFER_IN_CLIENT = 0,
    BUFFER_IN_SERVER
};

/**
 * totalSizeInFrame = spanCount * spanSizeInFrame
 *
 * 0 <= write - base < 2 * totalSize
 * 0 <= read - base < 1 * totalSize
 * 0 <= write - read < 1 * totalSize
 */
struct BasicBufferInfo {
    uint32_t totalSizeInFrame;
    uint32_t byteSizePerFrame;

    std::atomic<uint32_t> futexObj;

    std::atomic<StreamStatus> streamStatus;

    // basic read/write postion
    std::atomic<uint64_t> basePosInFrame;
    std::atomic<uint64_t> curWriteFrame;
    std::atomic<uint64_t> curReadFrame;

    std::atomic<uint32_t> underrunCount;

    std::atomic<uint64_t> handlePos;
    std::atomic<int64_t> handleTime;

    std::atomic<uint64_t> position;
    std::atomic<uint64_t> timeStamp;

    std::atomic<float> streamVolume;

    std::atomic<uint32_t> beginDurationMs;
    std::atomic<uint32_t> durationMs;
    std::atomic<float> duckFactor;
    std::atomic<float> oldDuckFactor;
    std::atomic<float> lastEventFactor;
    std::atomic<uint32_t> lastEventTime;

    std::atomic<float> muteFactor;
    std::atomic<RestoreStatus> restoreStatus = NO_NEED_FOR_RESTORE;
    std::atomic<bool> isNeedStop = false;

    RestoreInfo restoreInfo;

    // only for static renderer
    std::atomic<bool> isStatic;
    std::atomic<int64_t> clientLastProcessTime;
    std::atomic<bool> isFirstFrame;

    std::atomic<uint64_t> bufferEndCallbackSendTimes;
    std::atomic<bool> needSendLoopEndCallback;

    std::atomic<size_t> curStaticDataPos;
    std::atomic<int64_t> currentLoopTimes;

    std::atomic<uint64_t> pendingSpanSize;
    std::atomic<uint64_t> pendingEngineSize;
    std::atomic<uint32_t> pendingRouteFlag;
};
static_assert(std::is_standard_layout<BasicBufferInfo>::value == true, "is not standard layout!");
static_assert(std::is_trivially_copyable<BasicBufferInfo>::value == true, "is not trivially copyable!");

enum SpanStatus : uint32_t {
    SPAN_IDEL = 0,
    SPAN_WRITTING,
    SPAN_WRITE_DONE,
    SPAN_READING,
    SPAN_READ_DONE,
    SPAN_INVALID
};

// one span represents a collection of audio sampling data for a short period of time
struct SpanInfo {
    std::atomic<SpanStatus> spanStatus;
    uint64_t offsetInFrame = 0;

    int64_t writeStartTime;
    int64_t writeDoneTime;

    int64_t readStartTime;
    int64_t readDoneTime;

    // volume info for each span
    bool isMute;
    int32_t volumeStart;
    int32_t volumeEnd;
};

class OHAudioBufferBase : public Parcelable {
public:
    friend class OHAudioBuffer;

    struct InitializationInfo {
        AudioBufferHolder bufferHolder;
        uint32_t totalSizeInFrame;
        uint32_t byteSizePerFrame;
        int dataFd;
        int infoFd;
    };

    OHAudioBufferBase(AudioBufferHolder bufferHolder, uint32_t totalSizeInFrame, uint32_t byteSizePerFrame);

    // create OHAudioBufferBase locally or remotely
    static std::shared_ptr<OHAudioBufferBase> CreateFromLocal(uint32_t totalSizeInFrame,
        uint32_t byteSizePerFrame);
    static std::shared_ptr<OHAudioBufferBase> CreateFromRemote(uint32_t totalSizeInFrame,
        uint32_t byteSizePerFrame, AudioBufferHolder holder, int dataFd, int infoFd = INVALID_BUFFER_FD);

    bool Marshalling(Parcel &parcel) const override;
    static OHAudioBufferBase *Unmarshalling(Parcel &parcel);

    uint32_t GetSessionId();
    int32_t SetSessionId(uint32_t sessionId);

    AudioBufferHolder GetBufferHolder();

    int32_t GetSizeParameter(uint32_t &totalSizeInFrame, uint32_t &byteSizePerFrame);
    uint32_t GetTotalSizeInFrame();

    std::atomic<StreamStatus> *GetStreamStatus();

    uint32_t GetUnderrunCount();

    bool SetUnderrunCount(uint32_t count);

    bool GetHandleInfo(uint64_t &frames, int64_t &nanoTime);

    void SetHandleInfo(uint64_t frames, int64_t nanoTime);

    float GetStreamVolume();
    bool SetStreamVolume(float streamVolume);

    float GetDuckFactor();
    bool SetDuckFactor(float duckFactor, uint32_t durationMs);

    float GetMuteFactor();
    bool SetMuteFactor(float muteFactor);

    // hdi use one span as one frame
    uint32_t GetSyncWriteFrame();
    bool SetSyncWriteFrame(uint32_t writeFrame);
    uint32_t GetSyncReadFrame();
    bool SetSyncReadFrame(uint32_t readFrame);

    int32_t GetWritableDataFrames();
    int32_t GetReadableDataFrames();

    int32_t ResetCurReadWritePos(uint64_t readFrame, uint64_t writeFrame, bool wakeFutex = true);

    uint64_t GetCurWriteFrame();
    uint64_t GetCurReadFrame();
    uint64_t GetBasePosInFrame();

    int32_t SetCurWriteFrame(uint64_t writeFrame, bool wakeFutex = true);
    int32_t SetCurReadFrame(uint64_t readFrame, bool wakeFutex = true);

    int32_t GetBufferByOffset(size_t offset, size_t dataLength, RingBufferWrapper &buffer);
    int32_t TryGetContinuousBufferByOffset(size_t offset, size_t dataLength, BufferDesc &bufferDesc);

    int32_t GetBufferByFrame(uint64_t beginPosInFrame, uint64_t sizeInFrame, RingBufferWrapper &buffer);

    int32_t GetOffsetByFrame(uint64_t posInFrame, size_t &offset);
    int32_t GetOffsetByFrameForWrite(uint64_t writePosInFrame, size_t &offset);
    int32_t GetOffsetByFrameForRead(uint64_t readPosInFrame, size_t &offset);

    int32_t GetAllWritableBufferFromPosFrame(uint64_t writePosInFrame, RingBufferWrapper &buffer);
    int32_t GetAllReadableBufferFromPosFrame(uint64_t readPosInFrame, RingBufferWrapper &buffer);

    int32_t GetAllWritableBuffer(RingBufferWrapper &buffer);
    int32_t GetAllReadableBuffer(RingBufferWrapper &buffer);

    int32_t GetRawBuffer(uint32_t size, BufferDesc &bufferDesc);

    int64_t GetLastWrittenTime();
    void SetLastWrittenTime(int64_t time);

    std::atomic<uint32_t> *GetFutex();
    uint8_t *GetDataBase();
    size_t GetDataSize();
    RestoreStatus CheckRestoreStatus();
    RestoreStatus SetRestoreStatus(RestoreStatus restoreStatus);
    void GetRestoreInfo(RestoreInfo &restoreInfo);
    void SetRestoreInfo(RestoreInfo restoreInfo);

    void GetTimeStampInfo(uint64_t &position, uint64_t &timeStamp);
    void SetTimeStampInfo(uint64_t position, uint64_t timeStamp);

    void SetStopFlag(bool isNeedStop);
    bool GetStopFlag() const;

    FutexCode WaitFor(int64_t timeoutInNs, const OnIndexChange &pred);

    void WakeFutex(uint32_t wakeVal = IS_READY);

    RestoreStatus GetRestoreStatus();

    // for sharedbuffer in static mode
    void IncreaseBufferEndCallbackSendTimes();
    void DecreaseBufferEndCallbackSendTimes();
    void ResetBufferEndCallbackSendTimes();
    void SetIsNeedSendLoopEndCallback(bool value);
    void SetIsFirstFrame(bool value);
    void SetStaticPlayPosition(int64_t curLoopTimes, size_t curStaticDataPos);
    void GetStaticPlayPosition(int64_t &curLoopTimes, size_t &curStaticDataPos);

    bool IsNeedSendBufferEndCallback();
    bool IsNeedSendLoopEndCallback();
    bool IsFirstFrame();

    void SetStaticMode(bool state);
    bool GetStaticMode();

    bool CheckFrozenAndSetLastProcessTime(BufferPosition bufferPosition);

    void SetPendingSpanSize(uint64_t spanSize, uint64_t engineSize, uint32_t routeFlag);
    uint64_t GetAndClearPendingSpanSize(uint64_t &engineSize, uint32_t &routeFlag);
    bool HasPendingSpanSize() const;
    void ClearPendingSpanSize();

private:
    int32_t SizeCheck();

    int32_t Init(int dataFd, int infoFd, size_t statusInfoExtSize);

    void* GetStatusInfoExtPtr();

    InitializationInfo GetInitializationInfo();

    void InitBasicBufferInfo();

    void WakeFutexIfNeed(uint32_t wakeVal = IS_READY);

    float GetFactorFromRamp();

    uint32_t sessionId_ = 0;

    AudioBufferHolder bufferHolder_;

    uint32_t totalSizeInFrame_;
    uint32_t byteSizePerFrame_;

    // available only in single process
    int64_t lastWrittenTime_ = 0;

    // calculated in advance
    size_t totalSizeInByte_ = 0;

    // for render or capturer
    AudioMode audioMode_;

     // for StatusInfo buffer
    std::shared_ptr<AudioSharedMemory> statusInfoMem_ = nullptr;
    BasicBufferInfo *basicBufferInfo_ = nullptr;

    // for audio data buffer
    std::shared_ptr<AudioSharedMemory> dataMem_ = nullptr;
    uint8_t *dataBase_ = nullptr;
    volatile uint32_t *syncReadFrame_ = nullptr;
    volatile uint32_t *syncWriteFrame_ = nullptr;
};

class OHAudioBuffer : public Parcelable {
public:
    OHAudioBuffer(AudioBufferHolder bufferHolder, uint32_t totalSizeInFrame, uint32_t spanSizeInFrame,
        uint32_t byteSizePerFrame);
    ~OHAudioBuffer();

    // create OHAudioBuffer locally or remotely
    static std::shared_ptr<OHAudioBuffer> CreateFromLocal(uint32_t totalSizeInFrame, uint32_t spanSizeInFrame,
        uint32_t byteSizePerFrame);
    static std::shared_ptr<OHAudioBuffer> CreateFromRemote(uint32_t totalSizeInFrame, uint32_t spanSizeInFrame,
        uint32_t byteSizePerFrame, AudioBufferHolder holder, int dataFd, int infoFd = INVALID_BUFFER_FD);

    // idl
    bool Marshalling(Parcel &parcel) const override;
    static OHAudioBuffer *Unmarshalling(Parcel &parcel);

    AudioBufferHolder GetBufferHolder();

    int32_t GetSizeParameter(uint32_t &totalSizeInFrame, uint32_t &spanSizeInFrame, uint32_t &byteSizePerFrame);

    std::atomic<StreamStatus> *GetStreamStatus();

    uint32_t GetUnderrunCount();

    bool SetUnderrunCount(uint32_t count);

    bool GetHandleInfo(uint64_t &frames, int64_t &nanoTime);

    void SetHandleInfo(uint64_t frames, int64_t nanoTime);

    float GetStreamVolume();
    bool SetStreamVolume(float streamVolume);

    float GetDuckFactor();
    bool SetDuckFactor(float duckFactor, uint32_t durationMs);

    float GetMuteFactor();
    bool SetMuteFactor(float muteFactor);

    int32_t GetWritableDataFrames();

    int32_t ResetCurReadWritePos(uint64_t readFrame, uint64_t writeFrame, bool wakeFutex = true);

    uint64_t GetCurWriteFrame();
    uint64_t GetCurReadFrame();

    int32_t SetCurWriteFrame(uint64_t writeFrame, bool wakeFutex = true);
    int32_t SetCurReadFrame(uint64_t readFrame, bool wakeFutex = true);

    uint32_t GetSessionId();
    int32_t SetSessionId(uint32_t sessionId);

    int32_t GetWriteBuffer(uint64_t writePosInFrame, BufferDesc &bufferDesc);

    int32_t GetReadbuffer(uint64_t readPosInFrame, BufferDesc &bufferDesc);

    SpanInfo *GetSpanInfo(uint64_t posInFrame);
    SpanInfo *GetSpanInfoByIndex(uint32_t spanIndex);

    uint32_t GetSpanCount();

    int64_t GetLastWrittenTime();
    void SetLastWrittenTime(int64_t time);

    // hdi use one span as one frame
    uint32_t GetSyncWriteFrame();
    bool SetSyncWriteFrame(uint32_t writeFrame);
    uint32_t GetSyncReadFrame();
    bool SetSyncReadFrame(uint32_t readFrame);

    std::atomic<uint32_t> *GetFutex();
    uint8_t *GetDataBase();
    size_t GetDataSize();
    RestoreStatus CheckRestoreStatus();
    RestoreStatus SetRestoreStatus(RestoreStatus restoreStatus);
    RestoreStatus GetRestoreStatus();
    void GetRestoreInfo(RestoreInfo &restoreInfo);
    void SetRestoreInfo(RestoreInfo restoreInfo);

    void GetTimeStampInfo(uint64_t &position, uint64_t &timeStamp);
    void SetTimeStampInfo(uint64_t position, uint64_t timeStamp);

    void SetStopFlag(bool isNeedStop);
    bool GetStopFlag() const;

    FutexCode WaitFor(int64_t timeoutInNs, const OnIndexChange &pred);

    void WakeFutex(uint32_t wakeVal = IS_READY);

    void SetPendingSpanSize(uint64_t spanSize, uint64_t engineSize, uint32_t routeFlag);
    uint64_t GetAndClearPendingSpanSize(uint64_t &engineSize, uint32_t &routeFlag);
    bool HasPendingSpanSize() const;
    void ClearPendingSpanSize();

private:
    int32_t Init(int dataFd, int infoFd);
    int32_t SizeCheck();

    bool CheckWriteOrReadFrame(uint64_t writeOrReadFrame);

    mutable OHAudioBufferBase ohAudioBufferBase_;

    struct SpanBasicInfo {
        SpanBasicInfo(uint32_t spanSizeInFrame, uint32_t totalSizeInFrame,
            uint32_t byteSizePerFrame) : spanSizeInFrame_(spanSizeInFrame),
            spanSizeInByte_(spanSizeInFrame * byteSizePerFrame),
            spanConut_(spanSizeInFrame == 0 ? 0 : totalSizeInFrame / spanSizeInFrame)
        {}

        int32_t SizeCheck(uint32_t totalSizeInFrame) const;
        uint32_t spanSizeInFrame_;
        size_t spanSizeInByte_;
        uint32_t spanConut_;
    };
    SpanBasicInfo spanBasicInfo_;

    SpanInfo *spanInfoList_ = nullptr;
};

} // namespace AudioStandard
} // namespace OHOS
#endif // OH_AUDIO_BUFFER_H
