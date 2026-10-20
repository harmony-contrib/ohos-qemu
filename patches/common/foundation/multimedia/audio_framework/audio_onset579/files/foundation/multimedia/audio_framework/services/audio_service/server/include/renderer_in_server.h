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

#ifndef RENDERER_IN_SERVER_H
#define RENDERER_IN_SERVER_H

#include <atomic>
#include <mutex>
#include <optional>
#include "i_renderer_stream.h"
#include "i_stream_listener.h"
#include "oh_audio_buffer.h"
#include "i_stream_manager.h"
#include "audio_effect.h"
#include "player_dfx_writer.h"
#include "audio_ring_cache.h"
#include "audio_utils.h"
#include "audio_stream_monitor.h"
#include "audio_stream_checker.h"
#include "audio_static_buffer_processor.h"
#include "audio_static_buffer_provider.h"
#include "async_action_handler.h"

namespace OHOS {
namespace AudioStandard {

struct RendererLatestInfoForWorkgroup {
    IStatus status;
    bool isInSilentState;
    bool silentModeAndMixWithOthers;
    bool lastWriteStandbyEnableStatus;
    float streamVolume;
    float systemVolume;
};
class RendererInServer;

class NotifyStandbyAction : public AsyncActionHandler::AsyncAction {
public:
    NotifyStandbyAction(uint32_t sessionId, bool isStandbyOn)
        : sessionId_(sessionId), isStandbyOn_(isStandbyOn) {}
    void Exec() override;
private:
    uint32_t sessionId_;
    bool isStandbyOn_;
};

// Async action to notify silent state change
class NotifySilentStateAction : public AsyncActionHandler::AsyncAction {
public:
    // For SetClientVolume: carry actual volume value
    NotifySilentStateAction(uint32_t sessionId, bool isInSilentState, float volume)
        : sessionId_(sessionId), isInSilentState_(isInSilentState),
          volume_(volume), isMuteUpdate_(false) {}

    // For SetSilentModeAndMixWithOthers: mute-only update, no volume value needed
    NotifySilentStateAction(uint32_t sessionId, bool isInSilentState)
        : sessionId_(sessionId), isInSilentState_(isInSilentState),
          volume_(0.0f), isMuteUpdate_(true) {}

    void Exec() override;
private:
    uint32_t sessionId_;
    bool isInSilentState_;
    float volume_;
    bool isMuteUpdate_;
};

class StreamCallbacks : public IStatusCallback, public IWriteCallback {
public:
    StreamCallbacks(uint32_t streamIndex, std::weak_ptr<RendererInServer> renderer);
    virtual ~StreamCallbacks();
    void OnStatusUpdate(IOperation operation) override;
    int32_t OnWriteData(size_t length) override;
    int32_t OnWriteData(int8_t *inputData, size_t requestDataLen) override;
    int32_t GetAvailableSize(size_t &length) override;
    std::unique_ptr<AudioRingCache>& GetDupRingBuffer();
    void SetFirstWriteDataFlag(bool isFirstWriteDataFlag);
private:
    bool CheckIsWriteFirst() const noexcept;
private:
    uint32_t streamIndex_ = 0;
    std::weak_ptr<RendererInServer> renderer_;
    int32_t recoveryAntiShakeBufferCount_ = 0;
    FILE *dumpDupOut_ = nullptr;
    std::string dumpDupOutFileName_ = "";
    std::unique_ptr<AudioRingCache> dupRingBuffer_ = nullptr;
    std::atomic<bool> isFirstWriteDataFlag_ = true;
    std::mutex dupMutex_;
};

class RendererInServer : public IStatusCallback, public IWriteCallback,
    public std::enable_shared_from_this<RendererInServer> {
public:
    RendererInServer(AudioProcessConfig processConfig, std::weak_ptr<IStreamListener> streamListener);
    virtual ~RendererInServer();
    void OnStatusUpdate(IOperation operation) override;
    void OnStatusUpdateExt(IOperation operation, std::shared_ptr<IStreamListener> stateListener);
    void HandleOperationFlushed();
    void HandleOperationStarted();
    int32_t OnWriteData(size_t length) override;
    int32_t OnWriteData(int8_t *inputData, size_t requestDataLen) override;
    int32_t OnWriteDataNoWake(int8_t *inputData, size_t requestDataLen) override;
    void WakeClientFutex() override;
    int32_t GetAvailableSize(size_t &length) override;

    int32_t ResolveBuffer(std::shared_ptr<OHAudioBuffer> &buffer);
    int32_t GetSessionId(uint32_t &sessionId);
    int32_t Start(bool hasNoCallback);
    int32_t Pause();
    void HandleDupStreamPause();
    void HandleDualTonePause();
    int32_t Flush();
    int32_t Drain(bool stopFlag = false);
    int32_t Stop();
    int32_t Release(bool isSwitchStream = false);

    int32_t GetAudioTime(uint64_t &framePos, uint64_t &timestamp);
    int32_t GetAudioPosition(uint64_t &framePos, uint64_t &timestamp, uint64_t &latency, int32_t base);
    int32_t GetSpeedPosition(uint64_t &framePos, uint64_t &timestamp, uint64_t &latency, int32_t base);
    int32_t GetLatency(uint64_t &latency);
    int32_t SetRate(int32_t rate);
    int32_t SetLowPowerVolume(float volume);
    int32_t GetLowPowerVolume(float &volume);
    int32_t SetAudioEffectMode(int32_t effectMode);
    int32_t GetAudioEffectMode(int32_t &effectMode);
    int32_t SetPrivacyType(int32_t privacyType);
    int32_t GetPrivacyType(int32_t &privacyType);

    int32_t SetOffloadMode(int32_t state, bool isAppBack);
    int32_t UnsetOffloadMode();
    int32_t SetSpeed(float speed);
    int32_t SetPitch(float pitch);
    int32_t SetOffloadDataCallbackState(int32_t state);
    int32_t GetOffloadApproximatelyCacheTime(uint64_t &timestamp, uint64_t &paWriteIndex,
        uint64_t &cacheTimeDsp, uint64_t &cacheTimePa);
    int32_t UpdateSpatializationState(bool spatializationEnabled, bool headTrackingEnabled);
    void CheckAndWriterRenderStreamStandbySysEvent(bool standbyEnable);
    void OnCheckActiveMusicTime(const std::string &reason);

    int32_t GetStandbyStatus(bool &isStandby, int64_t &enterStandbyTime);

    int32_t Init();
    int32_t ConfigServerBuffer();
    int32_t InitBufferStatus();
    int32_t RequestHandleData(uint64_t syncFramePts, uint32_t size);
    int32_t UpdateWriteIndex();
    BufferDesc DequeueBuffer(size_t length);
    void VolumeHandle(BufferDesc &desc);
    int32_t WriteData();
    void WriteEmptyData();
    int32_t DrainAudioBuffer();

    // for inner-cap
    int32_t EnableInnerCap(int32_t innerCapId);
    int32_t DisableInnerCap(int32_t innerCapId);
    int32_t InitDupStream(int32_t innerCapId);
    int32_t CreateDupRender(int32_t innerCapId, CaptureInfo &capInfo);
    void AddDupStreamVolume(uint32_t dupStreamIndex);
    int32_t GetInnerCapPrebuf();
    int32_t DisableAllInnerCap();
    std::unique_ptr<AudioRingCache>& GetDupRingBuffer();

    // for dual tone
    int32_t EnableDualTone(const std::string &dupSinkName);
    int32_t DisableDualTone();

    int32_t GetStreamManagerType() const noexcept;
    int32_t SetSilentModeAndMixWithOthers(bool on);
    int32_t SetClientVolume();
    int32_t SetLoudnessGain(float loudnessGain);
    int32_t SetMute(bool isMute);
    int32_t SetDuckFactor(float duckFactor, uint32_t durationMs);
    int32_t SetDefaultOutputDevice(const DeviceType defaultOutputDevice, bool skipForce = false);
    int32_t SetSourceDuration(int64_t duration);

    void OnDataLinkConnectionUpdate(IOperation operation);
    int32_t GetActualStreamManagerType() const noexcept;

    bool Dump(std::string &dumpString);
    bool DumpNormal(std::string &dumpString);
    bool DumpVoipAndDirect(std::string &dumpString);
    void DumpStreamInfo(std::string &dumpString);
    void DumpStatusInfo(std::string &dumpString);
    void SetNonInterruptMute(const bool muteFlag);
    RestoreStatus RestoreSession(RestoreInfo restoreInfo);
    int32_t StopSession();
    void dualToneStreamInStart();
    bool CollectInfosForWorkgroup(float systemVolume);
    void InitDupBuffer(int32_t innerCapId);

    int32_t ResolveBufferBaseAndGetServerSpanSize(std::shared_ptr<OHAudioBufferBase> &buffer,
        uint32_t &spanSizeInFrame, uint64_t &engineTotalSizeInFrame);
    int32_t RefreshServerBufferForSpanSizeUpdate(std::shared_ptr<IStreamListener> stateListener);
    int32_t GetRendererFlagsByRoute(uint32_t routeFlag);

    int32_t SetAudioHapticsSyncId(int32_t audioHapticsSyncId);

    int32_t InitSoftLink(int32_t innerCapId);
    int32_t DestroySoftLink(int32_t innerCapId);
    int32_t InitSoftLinkVolume(std::shared_ptr<HPAE::IHpaeSoftLink> softLinkPtr);
    void RemoveIdForInjector();
    int32_t CheckPermission(RenderTarget target);
    int32_t SetTarget(RenderTarget target, int32_t targetUid, uint32_t targetStreamId, int32_t &ret);
    int32_t WriteDataInStaticMode(int8_t *inputData, size_t requestDataLen);
    int32_t SetLoopTimes(int64_t bufferLoopTimes);
    int32_t UpdateUnderrunInfo(uint32_t underrunInfoKey, int32_t underrunInfoVal);
    int32_t GetStaticBufferInfo(StaticBufferInfo &staticBufferInfo);
    int32_t ResetStaticPlayPosition();

    int32_t GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag);
    bool IsWriteFirst() const noexcept;
    int32_t CalculateCacheCount(uint32_t cacheSizeInFrame, uint32_t &cacheCount);
    void ReportExceptionForOffload();
public:
    uint64_t onsetRenderer579_ = 0;
    AudioProcessConfig processConfig_;
private:
    void OnStatusUpdateSub(IOperation operation);
    void OnStatusUpdateSubs(IOperation operation);
    void HandleOperationUnderrun();
    void HandleOperationUnderflow();
    bool IsHighResolution() const noexcept;
    void WriteMuteDataSysEvent(BufferDesc &bufferDesc);
    bool IsInvalidBuffer(uint8_t *buffer, size_t bufferSize);
    int32_t ConfigFixedSizeBuffer();
    void ReportDataToResSched(std::unordered_map<std::string, std::string> payload, uint32_t type);
    void OtherStreamEnqueue(const BufferDesc &bufferDesc);
    void DoFadingOut(RingBufferWrapper& bufferDesc);
    int32_t SetStreamVolumeInfoForEnhanceChain();
    void StandByCheck();
    bool ShouldEnableStandBy();
    int32_t OffloadSetVolumeInner();
    int32_t StartInner(bool hasNoCallback);
    int32_t ValidateStartState();
    int32_t ValidateAndSetupBufferForStart();
    void UpdateStartTimeInfo();
    int32_t StopInner();
    int32_t HandleStopDuringStandby();
    int32_t Standby(bool isStandbyOn);
    int64_t GetLastAudioDuration();
    void InnerCaptureOtherStream(const BufferDesc &bufferDesc, CaptureInfo &captureInfo, int32_t innerCapId);
    void InnerCaptureEnqueueBuffer(const BufferDesc &bufferDesc, CaptureInfo &captureInfo, int32_t innerCapId);
    int32_t CreateDupBufferInner(int32_t innerCapId);
    int32_t WriteDupBufferInner(const BufferDesc &bufferDesc, int32_t innerCapId);
    void WriteSilenceDupBuffer(const BufferDesc &bufferDesc, BufferWrap &bufferWrap, int32_t innerCapId);
    void ReConfigDupStreamCallback();
    int32_t StandbyForStop();
    int32_t StartInnerDuringStandby();
    int32_t PauseDuringStandby();
    void StartStreamByType();
    void RecordStandbyTime(bool isStandby, bool isStart);
    void UpdateLatestForWorkgroup(float systemVolume);
    int32_t DisableInnerCapHandle(int32_t innerCapId);
    int32_t InitDupStreamVolume(uint32_t dupStreamIndex);
    int32_t FlushOhAudioBuffer();
    BufferDesc PrepareOutputBuffer(const RingBufferWrapper& ringBufferDesc);
    int32_t CopyDataToInputBuffer(int8_t* inputData, size_t requestDataLen,
        const RingBufferWrapper& ringBufferDesc);
    int32_t Write3DAModeData(uint64_t currentReadFrame, uint64_t currentWriteFrame);
    void ProcessFadeOutIfNeeded(RingBufferWrapper& ringBufferDesc, uint64_t currentReadFrame,
        uint64_t currentWriteFrame, size_t requestDataInFrame);
    void ProcessManagerType();
    void HandleOperationPaused(std::shared_ptr<IStreamListener> stateListener);
    void HandleOperationStopped(RendererStage stage);
    void UpdateStreamStatusByRendererState();
    bool IsMovieOffloadStream();
    bool IsMovieStream();
    template <typename T>
    void SetSoftLinkFunc(T&& softLinkFunc);
    bool IsEnabledAndValidSoftLink(SoftLinkInfo& softLinkInfo);
    bool IsEnabledAndValidDupStream(CaptureInfo& captureInfo);
    void HandleOffloadStream(const int32_t captureId, const CaptureInfo& captureInfo);
    void UpdateStreamInfo();
    void RemoveStreamInfo();
    void OnWriteDataFinish();
    void InitLatencyMeasurement();
    void DetectLatency(uint8_t *inputData, size_t requestDataLen);
    void PauseInner();
    void UpdateFlushStatus();
    void FlushInnerCapStreams();
    void FlushDualToneStream();
    void ClearInnerCapBufferForInject();
    void InitDupBufferInner(int32_t innerCapId);
    int32_t OnWriteDataInternal(int8_t *inputData, size_t requestDataLen, bool wakeFutex);

    // only for a2dp offload
    void WaitForDataConnection();

    int32_t DisableDualToneInner();
    void PreDualToneBufferSilenceForOffload();

    int32_t WriteData(int8_t *inputData, size_t requestDataLen, bool wakeFutex = true);
    void PauseDirectStream();

    int32_t CreateServerBuffer();
    int32_t ProcessAndSetStaticBuffer();
    int32_t SelectModeAndWriteData(int8_t *inputData, size_t requestDataLen, bool wakeFutex);
    void MarkStaticFadeOut();
    void MarkStaticFadeIn(bool isRefresh);
    void HandleIsWriteFirst(bool isWriteFirst);
    void HandleStreamUnderrun();
    bool CheckIsUnderrun(uint64_t currentReadFrame, uint64_t currentWriteFrame);
    void ReleasePostProcess();

    int32_t PostSilentAction(std::shared_ptr<AsyncActionHandler::AsyncAction> action);
private:
    std::mutex statusLock_;
    std::condition_variable statusCv_;
    std::shared_ptr<IRendererStream> stream_ = nullptr;
    uint32_t streamIndex_ = -1;
    std::string traceTag_;
    mutable int64_t volumeDataCount_ = 0;
    std::atomic<IStatus> status_ = I_STATUS_IDLE;
    bool offloadEnable_ = false;
    std::atomic<bool> hasSessionEffect_ = false;
    std::atomic<bool> standByEnable_ = false;
    std::atomic<bool> muteFlag_ = false;

    // for inner-cap
    std::mutex dupMutex_;
    std::mutex softLinkMutex_;
    size_t dupTotalSizeInFrame_ = 0;
    size_t dupSpanSizeInFrame_ = 0;
    size_t dupSpanSizeInByte_ = 0;
    size_t dupByteSizePerFrame_ = 0;
    FILE *dumpDupIn_ = nullptr;
    std::string dumpDupInFileName_ = "";
    std::map<int32_t, std::shared_ptr<StreamCallbacks>> innerCapIdToDupStreamCallbackMap_;
    std::unordered_map<int32_t, CaptureInfo> captureInfos_;
    std::unique_ptr<AudioRingCache> dupRingBuffer_ = nullptr;

    // for dual sink tone
    std::mutex dualToneMutex_;
    std::atomic<bool> isDualToneEnabled_ = false;
    std::optional<std::string> dupSinkName_ = std::nullopt;
    uint32_t dualToneStreamIndex_ = 0;
    std::shared_ptr<IRendererStream> dualToneStream_ = nullptr;
    std::atomic<size_t> writeCount_ = 0;

    std::weak_ptr<IStreamListener> streamListener_;
    size_t engineTotalSizeInFrame_ = 0;
    size_t bufferTotalSizeInFrame_ = 0;
    size_t spanSizeInFrame_ = 0;
    size_t spanSizeInByte_ = 0;
    size_t byteSizePerFrame_ = 0;
    bool isBufferConfiged_  = false;
    std::atomic<bool> isInited_ = false;
    std::shared_ptr<OHAudioBufferBase> audioServerBuffer_ = nullptr;
    std::atomic<size_t> needForceWrite_ = 0;
    bool afterDrain = false;
    float lowPowerVolume_ = 1.0f;
    std::atomic<bool> isMuted_ = false;
    bool isNeedFade_ = false;
    float oldAppliedVolume_ = MAX_FLOAT_VOLUME;
    std::mutex updateIndexLock_;
    std::atomic<int64_t> startedTime_ = 0;
    int64_t pausedTime_ = 0;
    int64_t flushedTime_ = 0;
    int64_t drainedTime_ = 0;
    uint32_t underrunCount_ = 0;
    std::atomic<uint32_t> standByCounter_ = 0;
    int64_t enterStandbyTime_ = 0;
    int64_t lastWriteTime_ = 0;
    bool resetTime_ = false;
    uint64_t resetTimestamp_ = 0;
    std::mutex writeLock_;
    FILE *dumpC2S_ = nullptr; // client to server dump file
    std::string dumpFileName_ = "";
    ManagerType managerType_;
    std::atomic<bool> silentModeAndMixWithOthers_ = false;
    bool isHWDecodingType_ = false;
    std::time_t startMuteTime_ = 0;
    bool isInSilentState_ = false;
    std::mutex fadeoutLock_;
    int32_t fadeoutFlag_ = 0;
    int32_t effectModeWhenDual_ = EFFECT_DEFAULT;
    std::map<int32_t, int32_t> renderEmptyCountForInnerCapToInnerCapIdMap_;
    IOperation offloadState_;

    // only read & write in CheckAndWriterRenderStreamStandbySysEvent
    bool lastWriteStandbyEnableStatus_ = false;
    std::set<int32_t> innerCapIds;

    int64_t lastStartTime_{};
    int64_t lastStopTime_{};
    int64_t lastWriteFrame_{};
    int64_t lastWriteMuteFrame_{};
    int64_t sourceDuration_ = -1;
    std::unique_ptr<PlayerDfxWriter> playerDfx_;
    std::shared_ptr<AudioStreamChecker> audioStreamChecker_ = nullptr;

    // audio haptics play sync param id
    std::atomic<int32_t> audioHapticsSyncId_ = 0;

    bool latestForWorkgroupInited_ = false;
    struct RendererLatestInfoForWorkgroup latestForWorkgroup_;

    float loudnessGain_ = 0.0f;

    // Only use in Writedate(). Protect by writeMutex_.
    std::vector<uint8_t> rendererTmpBuffer_;
    std::unordered_map<int32_t, SoftLinkInfo> softLinkInfos_;
    FILE *dumpSoftLink = nullptr;
    uint32_t audioCheckFreq_ = 0;
    std::atomic<uint32_t> checkCount_ = 0;

    RenderTarget lastTarget_ = NORMAL_PLAYBACK;
    bool isDataLinkConnected_ = true;
    std::mutex dataConnectionMutex_;
    std::condition_variable dataConnectionCV_;

    float sonicPitch_ = 1.0f;
    float pitch_ = 1.0f;
    float speed_ = 1.0f;
    AudioRendererRate audioRenderRate_ = RENDER_RATE_NORMAL;
    std::shared_ptr<AudioStaticBufferProcessor> staticBufferProcessor_ = nullptr;
    std::shared_ptr<AudioStaticBufferProvider> staticBufferProvider_ = nullptr;
    std::shared_ptr<SignalDetectAgent> signalDetectAgent_ = nullptr;
    std::unordered_map<int32_t, std::atomic<size_t>> innerCapFirstWriteMap_;
    bool isNonStandardSampleRate_ = false;
    bool isWriteFirst_ = false;
    std::atomic<bool> isOffloadJankReport = false;
    std::shared_ptr<AsyncActionHandler> asyncHandler_ = nullptr;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // RENDERER_IN_SERVER_H
