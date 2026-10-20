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

#ifndef HPAE_RENDERER_STREAM_IMPL_H
#define HPAE_RENDERER_STREAM_IMPL_H

#include <mutex>
#include <condition_variable>
#include <shared_mutex>
#include <atomic>
#include <future>
#include "i_renderer_stream.h"
#include "audio_ring_cache.h"

namespace OHOS {
namespace AudioStandard {
enum HpaeRendererStreamTimestampTag {
    GET_REMOTE_OFFLOAD_SPEED_POSITION,
    GET_CURRENT_POSITION,
    GET_LATENCY,
    ON_DEVICE_CLASS_CHANGE,
    TIMESTAMP_TAG_NUM,
};

struct PositionData {
    uint64_t framePosition = 0;
    uint64_t timestamp = 0;
    uint64_t latency = 0;
    int64_t lastCallTime = 0;
};

class HpaeRendererStreamImpl : public std::enable_shared_from_this<HpaeRendererStreamImpl>,
                               public IStreamStatusCallback,
                               public IStreamCallback,
                               public IRendererStream {
public:
    HpaeRendererStreamImpl(AudioProcessConfig processConfig, bool isMoveAble, const std::string &deviceName,
        bool isCallbackMode = true, size_t preBufSizeInBytes = 0);
    ~HpaeRendererStreamImpl();
    int32_t InitParams(const std::string &deviceName = "");
    int32_t Start() override;
    int32_t StartWithSyncId(const int32_t &syncId) override;
    int32_t Pause(bool isStandby = false) override;
    int32_t Flush() override;
    int32_t Drain(bool stopFlag = false) override;
    int32_t Stop() override;
    int32_t Release() override;
    int32_t GetStreamFramesWritten(uint64_t &framesWritten) override;
    int32_t GetCurrentTimeStamp(uint64_t &timestamp) override;
    int32_t GetCurrentPosition(uint64_t &framePosition, uint64_t &timestamp, uint64_t &latency, int32_t base) override;
    int32_t GetSpeedPosition(uint64_t &framePosition, uint64_t &timestamp, uint64_t &latency, int32_t base) override;
    int32_t GetLatency(uint64_t &latency) override;
    int32_t SetRate(int32_t rate) override;
    int32_t SetAudioEffectMode(int32_t effectMode) override;
    int32_t GetAudioEffectMode(int32_t &effectMode) override;
    int32_t SetPrivacyType(int32_t privacyType) override;
    int32_t GetPrivacyType(int32_t &privacyType) override;
    int32_t SetSpeed(float speed) override;

    void RegisterStatusCallback(const std::weak_ptr<IStatusCallback> &callback) override;
    void RegisterWriteCallback(const std::weak_ptr<IWriteCallback> &callback) override;
    BufferDesc DequeueBuffer(size_t length) override;
    int32_t EnqueueBuffer(const BufferDesc &bufferDesc) override;
    int32_t GetMinimumBufferSize(size_t &minBufferSize) const override;
    void GetByteSizePerFrame(size_t &byteSizePerFrame) const override;
    void GetSpanSizePerFrame(size_t &spanSizeInFrame) const override;
    void SetStreamIndex(uint32_t index) override;
    uint32_t GetStreamIndex() override;
    void AbortCallback(int32_t abortTimes) override;
    // offload
    int32_t SetOffloadMode(int32_t state, bool isAppBack) override;
    int32_t UnsetOffloadMode() override;
    int32_t GetOffloadApproximatelyCacheTime(uint64_t &timestamp, uint64_t &paWriteIndex,
        uint64_t &cacheTimeDsp, uint64_t &cacheTimePa) override;
    int32_t OffloadSetVolume() override;
    int32_t SetOffloadDataCallbackState(int32_t state) override;
    size_t GetWritableSize() override;
    int32_t UpdateMaxLength(uint32_t maxLength) override;
    // offload end

    int32_t UpdateSpatializationState(bool spatializationEnabled, bool headTrackingEnabled) override;
    int32_t Peek(std::vector<char> *audioBuffer, int32_t &index) override;
    int32_t ReturnIndex(int32_t index) override;
    AudioProcessConfig GetAudioProcessConfig() const noexcept override;
    int32_t SetClientVolume(float clientVolume) override;
    int32_t SetLoudnessGain(float loudnessGain) override;
    void BlockStream() noexcept override;
    int32_t OnStreamData(AudioCallBackStreamInfo& callBackStremInfo) override;
    void OnStatusUpdate(IOperation operation, uint32_t streamIndex) override;

    bool OnQueryUnderrun() override;
    void SetSendDataEnabled(bool enabled) override;

    int32_t GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag) override;
    void OnNotifyHdiData(const std::pair<uint64_t, TimePoint> &hdiPos) override;
    void TriggerClientWake() override;
    void TriggerAppsUidUpdate() override;
    uint32_t GetRouteFlag() const noexcept override;
private:
    int32_t UpdateSpanSize(uint32_t spanSizeInFrame);
    void SyncOffloadMode();
    void InitRingBuffer();
    int32_t WriteDataFromRingBuffer(bool forceData, int8_t *inputData, size_t &requestDataLen);
    uint32_t GetA2dpOffloadLatency(); // unit ms
    uint32_t GetNearlinkLatency(); // unit ms
    uint32_t GetSinkLatency(); // unit ms
    int32_t GetSinkLatencyInner(uint32_t &sinkLatency);
    static int32_t GetSinkLatencyInner(const std::string &deviceClass, const std::string &deviceNetId,
        uint32_t &sinkLatency);
    void GetLatencyInner(uint64_t &timestamp, uint64_t &latencyUs, int32_t base);
    void OnDeviceClassChange(const AudioCallBackStreamInfo &callBackStreamInfo);
    int32_t GetRemoteOffloadSpeedPosition(uint64_t &framePosition, uint64_t &timestamp, uint64_t &latency);
    bool WaitFirstStreamData();
    void NotifyFirstStreamData();
    int32_t FetchSinkLatency(uint32_t &sinkLatency);
    void ResetSinkLatencyFetcher(const AudioCallBackStreamInfo &callBackStreamInfo);
    int32_t GetA2dpOffloadLatencyInner(uint32_t &sinkLatency);
    uint64_t GetOffloadLatency();
    bool InitLatencyInfo(const AudioCallBackStreamInfo &callBackStreamInfo);
    void UpdateInnerCapWriteState(bool isWriteFirst);

    uint32_t streamIndex_ = static_cast<uint32_t>(-1); // invalid index
    AudioProcessConfig processConfig_;
    std::weak_ptr<IStatusCallback> statusCallback_;
    std::weak_ptr<IWriteCallback> writeCallback_;
    State state_ = INVALID;

    size_t byteSizePerFrame_ = 0;
    size_t spanSizeInFrame_ = 0;
    size_t minBufferSize_ = 0;
    uint64_t expectedPlaybackDurationMs_ = 0;

    int32_t renderRate_ = 0;
    int32_t effectMode_ = -1;
    int32_t privacyType_ = 0;

    float powerVolumeFactor_ = 1.0f;
    // Only for debug
    int32_t abortFlag_ = 0;
    // offload
    std::atomic<bool> offloadEnable_ = false;
    std::atomic<int32_t> offloadStatePolicy_ = OFFLOAD_DEFAULT;
    // offload end
    float clientVolume_ = 1.0f;

    // latency position timeStamp
    std::shared_mutex latencyMutex_; // lock for variables related to position, latency, timestamp
    uint64_t framePosition_ = 0;
    uint64_t lastFramePosition_ = 0;
    uint64_t lastHdiFramePosition_ = 0;
    uint64_t rewindTime_ = 0;
    std::vector<uint64_t> timestamp_ = {Timestamp::Timestampbase::BASESIZE, 0};
    uint64_t latency_ = 0;
    uint64_t framesWritten_ = 0;
    std::atomic<uint64_t> lastPrintTimestamp_ = 0;
    std::atomic<int64_t> lastLogTimestampArr_[TIMESTAMP_TAG_NUM];

    std::mutex sinkLatencyFetcherMutex_;
    std::function<int32_t (uint32_t &)> sinkLatencyFetcher_;

    std::string deviceClass_;
    std::string deviceNetId_;
    // record latency

    // buffer mode, write or callback
    bool isCallbackMode_ = true; // true is callback buffer mode, false is write buffer mode
    bool isMoveAble_ = true;
    std::unique_ptr<AudioRingCache> ringBuffer_ = nullptr; // used by write buffer mode
    size_t ringBufferCapacityInBytes_ = 0;
    FILE *dumpEnqueueIn_ = nullptr;
    const size_t preBufSizeInBytes_ = 0;
    std::atomic<bool> preBufDone_ = false;
    // buffer mode, write or callback end

    std::atomic<size_t> mutePaddingFrames_ = 0;
    bool noWaitDataFlag_ = true;

    std::vector<PositionData> currentPositionData_ = {Timestamp::Timestampbase::BASESIZE, PositionData{}};
    std::vector<PositionData> speedPositionData_ = {Timestamp::Timestampbase::BASESIZE, PositionData{}};

    uint32_t usedSampleRate_ = 0;

    std::mutex firstStreamDataMutex_;
    std::condition_variable firstStreamDataCv_;
    std::atomic<bool> firstStreamDataReceived_ = false;
    std::atomic<bool> sendDataEnabled_ = true;

    std::pair<uint64_t, TimePoint> hdiPos_ = std::make_pair(0, std::chrono::high_resolution_clock::now());
    uint64_t writePos_ = 0;
    float speed_ = 1.0f;
    bool isWriteFirst_ = false;
    bool delayedWake_ = false;
    std::atomic<uint32_t> routeFlag_ = 0;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // pro_renderer_stream_impl_H
