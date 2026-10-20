/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
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
#ifndef RENDERER_IN_CLIENT_PRIVATE_H
#define RENDERER_IN_CLIENT_PRIVATE_H

#include <optional>
#include <thread>
#include <mutex>
#include <functional>
#include "bundle_mgr_interface.h"
#include "bundle_mgr_proxy.h"

#include "audio_channel_blend.h"
#include "audio_server_death_recipient.h"
#include "audio_stream_tracker.h"
#include "audio_utils.h"
#include "ipc_stream_listener_impl.h"
#include "ipc_stream_listener_stub.h"
#include "iipc_stream.h"
#include "volume_ramp.h"
#include "volume_tools.h"
#include "callback_handler.h"
#include "audio_speed.h"
#include "audio_pitch_processor.h"
#include "audio_debug_info.h"
#include "audio_spatial_channel_converter.h"
#include "audio_spatialization_types.h"
#include "audio_safe_block_queue.h"
#include "istandard_audio_service.h"
#include "remote_death_recipient.h"

namespace OHOS {
namespace AudioStandard {
namespace {
const int32_t LOG_COUNT_LIMIT = 200;
} // namespace
class SpatializationStateChangeCallbackImpl;

class RendererInClientInner : public RendererInClient, public IStreamListener, public IHandler,
    public std::enable_shared_from_this<RendererInClientInner> {
public:
    RendererInClientInner(AudioStreamType eStreamType, int32_t appUid);
    ~RendererInClientInner();

    // IStreamListener
    int32_t OnOperationHandled(Operation operation, int64_t result) override;

    // IAudioStream
    void SetClientID(int32_t clientPid, int32_t clientUid, uint32_t appTokenId, uint64_t fullTokenId) override;
    void SetClientDeviceId(const std::string &deviceId) override;
    int32_t UpdatePlaybackCaptureConfig(const AudioPlaybackCaptureConfig &config) override;
    int32_t RequestUserPrivacyAuthority(uint32_t sessionId) override;
    int32_t SetInMainThreadState(bool isInMainThread) override;
    void SetPlaybackCaptureStartStateCallback(
        const std::shared_ptr<AudioCapturerOnPlaybackCaptureStartCallback> &callback) override;
    void SetRendererInfo(const AudioRendererInfo &rendererInfo) override;
    void GetRendererInfo(AudioRendererInfo &rendererInfo) override;
    void SetCapturerInfo(const AudioCapturerInfo &capturerInfo) override;
    int32_t SetAudioStreamInfo(const AudioStreamParams info,
        const std::shared_ptr<AudioClientTracker> &proxyObj,
        const AudioPlaybackCaptureConfig &config = AudioPlaybackCaptureConfig()) override;
    int32_t GetAudioStreamInfo(AudioStreamParams &info) override;
    int32_t GetAudioSessionID(uint32_t &sessionID) override;
    void GetAudioPipeType(AudioPipeType &pipeType) override;
    State GetState() override;
    StreamFocusState GetFocusState() override;
    void SetFocusState(StreamFocusState state) override;
    bool GetAudioTime(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    bool GetAudioPosition(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    int32_t GetBufferSize(size_t &bufferSize) override;
    int32_t GetFrameCount(uint32_t &frameCount) override;
    int32_t GetLatency(uint64_t &latency) override;
    int32_t SetAudioStreamType(AudioStreamType audioStreamType) override;
    int32_t SetVolume(float volume) override;
    float GetVolume() override;
    int32_t SetLoudnessGain(float loudnessGain) override;
    float GetLoudnessGain() override;
    int32_t SetDuckVolume(float volume) override;
    float GetDuckVolume() override;
    int32_t SetMute(bool mute, StateChangeCmdType cmdType) override;
    int32_t SetBackMute(bool backMute) override;
    bool GetMute() override;
    int32_t SetMuteHint(bool mute) override;
    int32_t SetRenderRate(AudioRendererRate renderRate) override;
    AudioRendererRate GetRenderRate() override;
    int32_t SetStreamCallback(const std::shared_ptr<AudioStreamCallback> &callback) override;
    int32_t SetRendererFirstFrameWritingCallback(
        const std::shared_ptr<AudioRendererFirstFrameWritingCallback> &callback) override;
    void OnFirstFrameWriting() override;
    int32_t SetSpeed(float speed) override;
    int32_t SetPitch(float pitch) override;
    int32_t SetSonicPitch(float pitch) override;
    float GetSpeed() override;
    int32_t GetAudioDebugInfo(AudioDebugInfo &debugInfo) override;

    // callback mode api
    int32_t SetRenderMode(AudioRenderMode renderMode) override;
    void InitCallbackLoop();
    AudioRenderMode GetRenderMode() override;
    int32_t SetRendererWriteCallback(const std::shared_ptr<AudioRendererWriteCallback> &callback) override;
    int32_t SetCaptureMode(AudioCaptureMode captureMode) override;
    AudioCaptureMode GetCaptureMode() override;
    int32_t SetCapturerReadCallback(const std::shared_ptr<AudioCapturerReadCallback> &callback) override;
    int32_t SetCapturerMetaDataCallback(const std::shared_ptr<AudioCapturerMetaDataCallback> &callback) override;
    int32_t GetBufferDesc(BufferDesc &bufDesc) override;
    int32_t GetBufQueueState(BufferQueueState &bufState) override;
    int32_t Enqueue(const BufferDesc &bufDesc) override;
    int32_t Clear() override;

    int32_t SetLowPowerVolume(float volume) override;
    float GetLowPowerVolume() override;
    int32_t SetOffloadMode(int32_t state, bool isAppBack) override;
    int32_t UnsetOffloadMode() override;
    float GetSingleStreamVolume() override;
    AudioEffectMode GetAudioEffectMode() override;
    int32_t SetAudioEffectMode(AudioEffectMode effectMode) override;
    int64_t GetFramesWritten() override;
    int64_t GetFramesRead() override;
    int32_t SetSourceDuration(int64_t duration) override;

    void SetInnerCapturerState(bool isInnerCapturer) override;
    void SetWakeupCapturerState(bool isWakeupCapturer) override;
    void SetCapturerSource(int capturerSource) override;
    void SetPrivacyType(AudioPrivacyType privacyType) override;

    // Common APIs
    bool StartAudioStream(StateChangeCmdType cmdType = CMD_FROM_CLIENT,
        AudioStreamDeviceChangeReasonExt reason = AudioStreamDeviceChangeReasonExt::ExtEnum::UNKNOWN) override;
    bool PauseAudioStream(StateChangeCmdType cmdType = CMD_FROM_CLIENT) override;
    bool StopAudioStream() override;
    void HandleStopSuccess();
    bool ReleaseAudioStream(bool releaseRunner = true, bool isSwitchStream = false) override;
    bool FlushAudioStream() override;
    void ClearCbBufferQueue();

    // Playback related APIs
    bool DrainAudioStream(bool stopFlag = false) override;
    int32_t Write(uint8_t *buffer, size_t bufferSize) override;
    int32_t Write(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer, size_t metaBufferSize) override;
    void SetPreferredFrameSize(int32_t frameSize, bool isRecreate = false) override;

    // Recording related APIs
    int32_t Read(uint8_t &buffer, size_t userSize, bool isBlockingRead) override;

    uint32_t GetUnderflowCount() override;
    uint32_t GetOverflowCount() override;
    void SetUnderflowCount(uint32_t underflowCount) override;
    void SetOverflowCount(uint32_t overflowCount) override;

    int32_t RegisterRemoteDiedCallback(const std::shared_ptr<RemoteDiedCallback> &callback) override;
    int32_t UnregisterRemoteDiedCallback() override;

    void SetRendererPositionCallback(int64_t markPosition, const std::shared_ptr<RendererPositionCallback> &callback)
        override;
    void UnsetRendererPositionCallback() override;
    void SetRendererPeriodPositionCallback(int64_t periodPosition,
        const std::shared_ptr<RendererPeriodPositionCallback> &callback) override;
    void UnsetRendererPeriodPositionCallback() override;
    void SetCapturerPositionCallback(int64_t markPosition, const std::shared_ptr<CapturerPositionCallback> &callback)
        override;
    void UnsetCapturerPositionCallback() override;
    void SetCapturerPeriodPositionCallback(int64_t periodPosition,
        const std::shared_ptr<CapturerPeriodPositionCallback> &callback) override;
    void UnsetCapturerPeriodPositionCallback() override;
    int32_t SetRendererSamplingRate(uint32_t sampleRate) override;
    uint32_t GetRendererSamplingRate() override;
    int32_t SetBufferSizeInMsec(int32_t bufferSizeInMsec) override;
    int32_t SetChannelBlendMode(ChannelBlendMode blendMode) override;
    int32_t SetVolumeWithRamp(float volume, int32_t duration) override;

    void SetStreamTrackerState(bool trackerRegisteredState) override;
    void GetSwitchInfo(IAudioStream::SwitchInfo& info) override;

    IAudioStream::StreamClass GetStreamClass() override;

    static const sptr<IStandardAudioService> GetAudioServerProxy();
    static void AudioServerDied(pid_t pid, pid_t uid);

    void OnHandle(uint32_t code, int64_t data) override;
    void InitCallbackHandler();
    void SafeSendCallbackEvent(uint32_t eventCode, int64_t data);

    int32_t StateCmdTypeToParams(int64_t &params, State state, StateChangeCmdType cmdType);
    int32_t ParamsToStateCmdType(int64_t params, State &state, StateChangeCmdType &cmdType);

    void SendRenderMarkReachedEvent(int64_t rendererMarkPosition);
    void SendRenderPeriodReachedEvent(int64_t rendererPeriodSize);

    void HandleRendererPositionChanges(size_t bytesWritten);
    void HandleStateChangeEvent(int64_t data);
    void HandleRenderMarkReachedEvent(int64_t rendererMarkPosition);
    void HandleRenderPeriodReachedEvent(int64_t rendererPeriodNumber);

    void OnSpatializationStateChange(const AudioSpatializationState &spatializationState);
    void UpdateLatencyTimestamp(std::string &timestamp, bool isRenderer) override;

    void GetStreamSwitchInfo(SwitchInfo &info);

    bool GetOffloadEnable() override;
    bool GetSpatializationEnabled() override;
    bool GetHighResolutionEnabled() override;

    void SetSilentModeAndMixWithOthers(bool on) override;
    bool GetSilentModeAndMixWithOthers() override;

    bool RestoreAudioStream(bool needStoreState = true) override;
    void JoinCallbackLoop() override;

    int32_t SetDefaultOutputDevice(const DeviceType defaultOutputDevice, bool skipForce = false) override;
    FastStatus GetFastStatus() override;
    void SetFastStatusChangeCallback(const std::function<void(FastStatus)> &callback) override;
    DeviceType GetDefaultOutputDevice() override;
    int32_t GetAudioTimestampInfo(Timestamp &timestamp, Timestamp::Timestampbase base) override;

    void SetSwitchingStatus(bool isSwitching) override;

    void GetRestoreInfo(RestoreInfo &restoreInfo) override;
    void SetRestoreInfo(RestoreInfo &restoreInfo) override;
    RestoreStatus CheckRestoreStatus() override;
    RestoreStatus SetRestoreStatus(RestoreStatus restoreStatus) override;
    void SetSwitchInfoTimestamp(std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePair,
        std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePairWithSpeed) override;
    void FetchDeviceForSplitStream() override;
    void SetCallStartByUserTid(pid_t tid) override;
    void SetCallbackLoopTid(int32_t tid) override;
    int32_t GetCallbackLoopTid() override;
    int32_t SetOffloadDataCallbackState(int32_t cbState) override;
    void NotifyRouteUpdate(uint32_t routeFlag, const std::string &networkId) override;
    bool GetStopFlag() const override;
    void SetAudioHapticsSyncId(const int32_t &audioHapticsSyncId) override;
    int32_t SetRenderTarget(RenderTarget renderTarget) override;
    int32_t SetRenderTarget(RenderTarget renderTarget, int32_t targetUid, uint32_t targetStreamId) override;
    RenderTarget GetRenderTarget() override;
    bool IsRestoreNeeded() override;
    void SetStaticBufferInfo(StaticBufferInfo staticBufferInfo,
        std::shared_ptr<AudioSharedMemory> sharedMemory) override;
    int32_t SetStaticBufferEventCallback(std::shared_ptr<StaticBufferEventCallback> callback) override;
    int32_t SetStaticTriggerRecreateCallback(std::function<void()> sendStaticRecreateFunc) override;
    int32_t SetLoopTimes(int64_t bufferLoopTimes) override;
    void UpdateUnderrunInfo(UnderrunInfoType underrunInfoKey, int32_t underrunInfoVal) override;
    int32_t GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag) override;
    const std::string GetBundleName() override;
    void SetBundleName(std::string &name) override;

    bool ResetStaticPlayPosition() override;
    int32_t ResetNotifyStreamSilentChangeFlag() override;
    void ReportExceptionForInterval();
    void CheckAndReportTimestamp();

    bool IsFastStream() const
    {
        return (rendererInfo_.audioFlag & AUDIO_OUTPUT_FLAG_FAST) != 0;
    }

    bool IsUltraFastStream() const
    {
        return clientConfig_.ultraFastFlag == (ULTRA_REQUESTED | ULTRA_IMPLEMENTED);
    }

    void SetupFastStreamThreadPriority();

    void CheckAndProcessPendingSpanSize();
private:
    void RegisterTracker(const std::shared_ptr<AudioClientTracker> &proxyObj);
    void UpdateTracker(const std::string &updateCase);

    void  FlushBeforeStart();

    int32_t DeinitIpcStream();

    int32_t InitIpcStream();

    void InitDFXOperaiton();

    bool GetHWDecodingTime(Timestamp &timestamp, Timestamp::Timestampbase base);

    int32_t GetRawBuffer(BufferDesc &bufDesc);

    int32_t WriteRawBuffer(BufferDesc &bufferDesc);

    int32_t Write3DADirectBuffer(BufferDesc &bufferDesc);

    const AudioProcessConfig ConstructConfig();

    int32_t InitSharedBuffer();
    int32_t CopyStaticBufferData();

    int32_t WriteCacheData(uint8_t *buffer, size_t bufferSize, bool speedCached, size_t oriBufferSize);

    void SetCacheSize(uint32_t cacheSizeInFrame);
    void InitCallbackBuffer(uint64_t bufferDurationInUs);
    bool IsLowLatencyRenderer() const;
    int32_t GetFastLatency(uint64_t &latency);
    int32_t GetFastLatencyWithFlag(uint64_t &latency, LatencyFlag flag);
    uint64_t GetDefaultCallbackBufferDurationInUs() const;
    int32_t GetBufferWaitTimeoutInMs() const;
    void CallClientHandle();
    bool WriteCallbackFunc();
    // for callback mode. Check status if not running, wait for start or release.
    bool WaitForRunning();
    bool ProcessSpeed(uint8_t *&buffer, size_t &bufferSize, bool &speedCached);
    bool ProcessPitch(uint8_t *&buffer, size_t &bufferSize, bool &pitchCached);
    int32_t ProcessBufferAndWriteCache(uint8_t *buffer, size_t bufferSize, size_t oriBufferSize);
    int32_t WriteInner(uint8_t *buffer, size_t bufferSize);
    int32_t WriteInner(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer, size_t metaBufferSize);
    void WriteMuteDataSysEvent(uint8_t *buffer, size_t bufferSize);
    bool IsMutePlaying();
    void MonitorMutePlay(bool isPlayEnd);
    void ReportWriteMuteEvent(int64_t mutePlayDuration);
    bool IsInvalidBuffer(uint8_t *buffer, size_t bufferSize);
    void DfxWriteInterval();
    void HandleStatusChangeOperation(Operation operation);

    int32_t RegisterSpatializationStateEventListener();

    int32_t UnregisterSpatializationStateEventListener(uint32_t sessionID);

    void FirstFrameProcess();

    void ResetFramePosition();

    int32_t SetInnerVolume(float volume);

    bool IsHighResolution() const noexcept;

    int32_t ProcessWriteInner(BufferDesc &bufferDesc);

    void InitDirectPipeType();

    bool DrainAudioStreamInner(bool stopFlag = false);

    bool ProcessVolume();

    void RegisterThreadPriorityOnStart(StateChangeCmdType cmdType);

    void ResetCallbackLoopTid();

    bool DoHdiSetSpeed(float speed, bool force);

    int32_t SetSpeedInner(float speed);

    void WaitForBufferNeedOperate();

    void UpdatePauseReadIndex();

    void FlushSpeedBuffer();

    bool CheckBufferNeedWrite();

    bool NeedStopFlush();

    bool CheckBufferValid(const BufferDesc &bufDesc);

    void RecordDropPosition(size_t dataLength);

    void GetRendererFirstFrameWritingCallback(IAudioStream::SwitchInfo& info);

    bool CheckStaticAndOperate();

    void CheckOperations();

    void CheckFrozenStateInStaticMode();

    int32_t CallStartWhenInStandby();

    void NotifyStopWaiting();

    void UpdateStopState();

    void NotifyStreamSilentChange();

    void UpdateStreamState(State state);

    void NotifyFastStatusChange(FastStatus status);

    void SendAudioErrorEventAndProcessOther(int32_t uid, int32_t errorCode,
        const std::string &erroDesc, bool isClient, State state);
private:
    AudioStreamType eStreamType_ = AudioStreamType::STREAM_DEFAULT;
    int32_t appUid_ = 0;
    uint32_t sessionId_ = 0;
    int32_t clientPid_ = -1;
    int32_t clientUid_ = -1;
    uint32_t appTokenId_ = 0;
    uint64_t fullTokenId_ = 0;
    int64_t lastTriggerTime_ = 0;
    bool logStopCallCount_ = false;

    std::unique_ptr<AudioStreamTracker> audioStreamTracker_;

    AudioRendererInfo rendererInfo_ = {};
    AudioCapturerInfo capturerInfo_ = {}; // not in use

    AudioPrivacyType privacyType_ = PRIVACY_TYPE_PUBLIC;
    bool streamTrackerRegistered_ = false;

    std::atomic<bool> needSetThreadPriority_ = true;
    RenderTarget renderTarget_ = NORMAL_PLAYBACK;
    AudioStreamParams curStreamParams_ = {0}; // in plan next: replace it with AudioRendererParams
    AudioStreamParams streamParams_ = {0};

    bool isHWDecodingType_ = false;

    // for data process
    bool isBlendSet_ = false;
    AudioBlend audioBlend_;
    VolumeRamp volumeRamp_;

    // callbacks
    std::mutex streamCbMutex_;
    std::weak_ptr<AudioStreamCallback> streamCallback_;
    std::mutex fastStatusChangeCallbackMutex_;
    std::function<void(FastStatus)> fastStatusChangeCallback_;
    std::atomic<FastStatus> fastStatus_ = FASTSTATUS_NORMAL;

    size_t cacheSizeInByte_ = 0;
    uint32_t spanSizeInFrame_ = 0;
    std::atomic<uint32_t> cacheSizeInFrame_ = 0;
    size_t clientSpanSizeInByte_ = 0;
    size_t sizePerFrameInByte_ = 4; // 16bit 2ch as default

    uint32_t bufferSizeInMsec_ = 20; // 20ms
    bool isBufferSizeInMsecSet_ = false;
    std::string dumpOutFile_ = "";
    FILE *dumpOutFd_ = nullptr;
    mutable int64_t volumeDataCount_ = 0;
    std::string logUtilsTag_ = "";

    std::shared_ptr<AudioRendererFirstFrameWritingCallback> firstFrameWritingCb_ = nullptr;
    std::mutex firstFrameWritingMutex_;
    std::atomic<bool> hasFirstFrameWrited_ = false;

    // callback mode releated
    AudioRenderMode renderMode_ = RENDER_MODE_NORMAL;
    std::thread callbackLoop_; // thread for callback to client and write.
    std::mutex loopMutex_;
    int32_t callbackLoopTid_ = -1;
    std::mutex callbackLoopTidMutex_;
    std::condition_variable callbackLoopTidCv_;
    std::atomic<bool> cbThreadReleased_ = true;
    std::mutex writeCbMutex_;
    std::condition_variable cbThreadCv_;
    std::shared_ptr<AudioRendererWriteCallback> writeCb_ = nullptr;
    std::mutex cbBufferMutex_;
    std::condition_variable cbBufferCV_;
    std::unique_ptr<uint8_t[]> cbBuffer_ {nullptr};
    size_t cbBufferSize_ = 0;
    AudioSafeBlockQueue<BufferDesc> cbBufferQueue_; // only one cbBuffer_

    std::atomic<StreamFocusState> streamFocusState_ = FOCUS_INVALID;
    std::mutex focusStatusMutex_;
    std::atomic<State> state_ = INVALID;
    // using this lock when change status_
    std::mutex statusMutex_;
    // for status operation wait and notify
    std::mutex callServerMutex_;
    std::condition_variable callServerCV_;

    Operation notifiedOperation_ = MAX_OPERATION_CODE;
    int64_t notifiedResult_ = 0;

    float lowPowerVolume_ = 1.0;
    float duckVolume_ = 1.0;
    float muteVolume_ = 1.0;
    std::atomic<StateChangeCmdType> muteCmd_ = CMD_FROM_CLIENT;
    float clientVolume_ = 1.0;
    bool silentModeAndMixWithOthers_ = false;

    float loudnessGain_ = 0.0f;

    bool flushAfterStop_ = false;

    uint64_t clientWrittenBytes_ = 0;
    // ipc stream related
    AudioProcessConfig clientConfig_;
    sptr<IpcStreamListenerImpl> listener_ = nullptr;
    sptr<IIpcStream> ipcStream_ = nullptr;
    sptr<IRemoteObject> ipcProxy_ = nullptr;
    std::mutex deathRecipientLock_;
    sptr<RemoteDeathRecipient> deathRecipient_ = nullptr;
    std::shared_ptr<OHAudioBufferBase> clientBuffer_ = nullptr;

    // for static audio renderer
    std::shared_ptr<StaticBufferEventCallback> audioStaticBufferEventCallback_ = nullptr;
    std::function<void()> sendStaticRecreateFunc_ = nullptr;
    StaticBufferInfo staticBufferInfo_{};
    std::shared_ptr<AudioSharedMemory> staticSharedMemory_ = nullptr;
    std::mutex staticBufferMutex_;

    // buffer handle
    std::mutex writeMutex_; // used for prevent multi thread call write

    // Mark reach and period reach callback
    int64_t totalBytesWritten_ = 0;
    std::mutex markReachMutex_;
    bool rendererMarkReached_ = false;
    int64_t rendererMarkPosition_ = 0;
    std::shared_ptr<RendererPositionCallback> rendererPositionCallback_ = nullptr;

    std::mutex periodReachMutex_;
    int64_t rendererPeriodSize_ = 0;
    int64_t rendererPeriodWritten_ = 0;
    std::shared_ptr<RendererPeriodPositionCallback> rendererPeriodPositionCallback_ = nullptr;

    // Event handler
    bool runnerReleased_ = false;
    std::mutex runnerMutex_;
    std::shared_ptr<CallbackHandler> callbackHandler_ = nullptr;

    bool paramsIsSet_ = false;
    AudioRendererRate rendererRate_ = RENDER_RATE_NORMAL;
    AudioEffectMode effectMode_ = EFFECT_DEFAULT;

    std::optional<float> realSpeed_ = std::nullopt;
    float speed_ = 1.0;
    float hdiSpeed_ = 1.0;
    std::unique_ptr<uint8_t[]> speedBuffer_ {nullptr};
    size_t bufferSize_ = 0;
    std::unique_ptr<AudioSpeed> audioSpeed_ = nullptr;
    std::atomic<bool> speedEnable_ = false;
    std::atomic<bool> isHdiSpeed_ = false;
    std::mutex speedMutex_;

    std::shared_ptr<AudioPitchProcessor> pitchProcessor_ = nullptr;
    std::unique_ptr<uint8_t[]> pitchBuffer_ {nullptr};
    float curPitch_ = 1.0f;
    std::mutex pitchMutex_;

    std::unique_ptr<AudioSpatialChannelConverter> converter_;

    std::atomic<int64_t> mutePlayStartTime_ = 0; // realtime
    std::atomic<bool> mutePlaying_ = false;

    bool offloadEnable_ = false;
    uint64_t offloadStartReadPos_ = 0;
    int64_t offloadStartHandleTime_ = 0;
    bool backMute_ = false;

    // for getAudioTimeStampInfo
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePair_ = {
        Timestamp::Timestampbase::BASESIZE, {0, 0}
    };
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePairWithSpeed_ = {
        Timestamp::Timestampbase::BASESIZE, {0, 0}
    };
    std::vector<uint64_t> lastSwitchPosition_ = {0, 0};
    std::vector<uint64_t> lastSwitchPositionWithSpeed_ = {0, 0};
    std::atomic<uint64_t> dropPosition_ = 0;
    std::atomic<uint64_t> dropHdiPosition_ = 0;

    struct WrittenFramesWithSpeed {
        uint64_t writtenFrames = 0;
        float speed = 1.0;
    };
    std::atomic<WrittenFramesWithSpeed> writtenAtSpeedChange_; // afterSpeed
    struct AudioWriteState {
        uint64_t unprocessedFramesBytes_;
        uint64_t totalBytesWrittenAfterFlush_;
        uint64_t perPeriodFrame_;
        AudioWriteState(uint64_t unprocessed = 0, uint64_t written = 0, uint64_t frame = 0)
            : unprocessedFramesBytes_(unprocessed), totalBytesWrittenAfterFlush_(written), perPeriodFrame_(frame) {}
    };
    std::atomic<AudioWriteState> audioWriteState_;
    std::atomic<uint64_t> lastPrintTimestamp_ = 0;

    std::string traceTag_;
    std::string spatializationEnabled_ = "Invalid";
    std::string headTrackingEnabled_ = "Invalid";
    uint32_t spatializationRegisteredSessionID_ = 0;
    bool firstSpatializationRegistered_ = true;
    std::shared_ptr<SpatializationStateChangeCallbackImpl> spatializationStateChangeCallback_ = nullptr;
    std::time_t startMuteTime_ = 0;
    bool isUpEvent_ = false;
    std::shared_ptr<AudioClientTracker> proxyObj_ = nullptr;
    int64_t preWriteEndTime_ = 0;
    int32_t loudVolumeSupportMode_ = 0;

    uint64_t lastFlushReadIndex_ = 0;
    uint64_t lastSpeedFlushReadIndex_ = 0;

    bool isMainUseArk_ = false;

    enum LoudVolumeSupportType {
        LOUD_VOLUME_NOT_SUPPORT = 0,
        LOUD_VOLUME_SUPPORT,
        LOUD_VOLUME_SUPPORT_ONLY_MUSIC,
        LOUD_VOLUME_SUPPORT_ONLY_VOICE,
    };

    enum {
        STATE_CHANGE_EVENT = 0,
        RENDERER_MARK_REACHED_EVENT,
        RENDERER_PERIOD_REACHED_EVENT,
        CAPTURER_PERIOD_REACHED_EVENT,
        CAPTURER_MARK_REACHED_EVENT,
    };

    // note that the starting elements should remain the same as the enum State
    enum : int64_t {
        HANDLER_PARAM_INVALID = -1,
        HANDLER_PARAM_NEW = 0,
        HANDLER_PARAM_PREPARED,
        HANDLER_PARAM_RUNNING,
        HANDLER_PARAM_STOPPED,
        HANDLER_PARAM_RELEASED,
        HANDLER_PARAM_PAUSED,
        HANDLER_PARAM_STOPPING,
        HANDLER_PARAM_RUNNING_FROM_SYSTEM,
        HANDLER_PARAM_PAUSED_FROM_SYSTEM,
    };

    std::mutex setPreferredFrameSizeMutex_;
    std::optional<int32_t> userSettedPreferredFrameSize_ = std::nullopt;

    int32_t sleepCount_ = LOG_COUNT_LIMIT;
    DeviceType defaultOutputDevice_ = DEVICE_TYPE_NONE;

    std::mutex switchingMutex_;
    StreamSwitchingInfo switchingInfo_ {false, INVALID};

    std::mutex lastCallStartByUserTidMutex_;
    std::optional<pid_t> lastCallStartByUserTid_ = std::nullopt;

    std::function<uid_t()> uidGetter_ = [] { return getuid(); };

    std::string bundleName = "";

    std::atomic<bool> needNotifyStreamSilentChange_ = true;
};

class SpatializationStateChangeCallbackImpl : public AudioSpatializationStateChangeCallback {
public:
    SpatializationStateChangeCallbackImpl();
    virtual ~SpatializationStateChangeCallbackImpl();

    void OnSpatializationStateChange(const AudioSpatializationState &spatializationState) override;
    void SetRendererInClientPtr(std::shared_ptr<RendererInClientInner> rendererInClientPtr);
private:
    std::weak_ptr<RendererInClientInner> rendererInClientPtr_;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // RENDERER_IN_SERVER_H
