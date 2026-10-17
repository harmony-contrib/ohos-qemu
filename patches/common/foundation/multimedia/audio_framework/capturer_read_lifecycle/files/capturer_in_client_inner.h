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
#ifndef CAPTURER_IN_CLIENT_INNER_H
#define CAPTURER_IN_CLIENT_INNER_H

#include "capturer_in_client.h"

#include <atomic>
#include <cstdio>
#include <cinttypes>
#include <condition_variable>
#include <functional>
#include <sstream>
#include <string>
#include <mutex>
#include <thread>
#include <vector>

#include "iservice_registry.h"
#include "system_ability_definition.h"
#include "securec.h"

#include "iipc_stream.h"
#include "istandard_audio_service.h"
#include "audio_capturer_log.h"
#include "audio_errors.h"
#include "volume_tools.h"
#include "audio_ring_cache.h"
#include "audio_utils.h"
#include "audio_policy_manager.h"
#include "audio_server_death_recipient.h"
#include "audio_stream_tracker.h"
#include "audio_process_config.h"
#include "ipc_stream_listener_impl.h"
#include "ipc_stream_listener_stub.h"
#include "callback_handler.h"
#include "audio_safe_block_queue.h"
#include "remote_death_recipient.h"

namespace OHOS {
namespace AudioStandard {

class CapturerInClientInner : public CapturerInClient, public IStreamListener, public IHandler,
    public std::enable_shared_from_this<CapturerInClientInner> {
public:
    CapturerInClientInner(AudioStreamType eStreamType, int32_t appUid);
    ~CapturerInClientInner();

    // IStreamListener
    int32_t OnOperationHandled(Operation operation, int64_t result) override;
    int32_t OnMetaData(const std::vector<uint8_t> &metaData) override;

    void SetClientID(int32_t clientPid, int32_t clientUid, uint32_t appTokenId, uint64_t fullTokenId) override;
    void SetClientDeviceId(const std::string &deviceId) override;

    int32_t UpdatePlaybackCaptureConfig(const AudioPlaybackCaptureConfig &config) override;
    int32_t SetInMainThreadState(bool isInMainThread) override;
    void SetRendererInfo(const AudioRendererInfo &rendererInfo) override;
    void GetRendererInfo(AudioRendererInfo &rendererInfo) override;
    void SetCapturerInfo(const AudioCapturerInfo &capturerInfo) override;
    int32_t GetAudioStreamInfo(AudioStreamParams &info) override;
    int32_t SetAudioStreamInfo(const AudioStreamParams info,
        const std::shared_ptr<AudioClientTracker> &proxyObj,
        const AudioPlaybackCaptureConfig &config = AudioPlaybackCaptureConfig()) override;
    State GetState() override;
    StreamFocusState GetFocusState() override;
    void SetFocusState(StreamFocusState state) override;
    int32_t GetAudioSessionID(uint32_t &sessionID) override;
    void GetAudioPipeType(AudioPipeType &pipeType) override;
    bool GetAudioTime(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    bool GetTimeStampInfo(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    bool GetAudioPosition(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    int32_t GetBufferSize(size_t &bufferSize) override;
    int32_t GetFrameCount(uint32_t &frameCount) override;
    int32_t GetLatency(uint64_t &latency) override;
    int32_t GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag) override;
    int32_t SetAudioStreamType(AudioStreamType audioStreamType) override;
    float GetVolume() override;
    float GetLoudnessGain() override;
    int32_t SetVolume(float volume) override;
    int32_t SetLoudnessGain(float loudnessGain) override;
    int32_t SetDuckVolume(float volume) override;
    float GetDuckVolume() override;
    int32_t SetMute(bool mute, StateChangeCmdType cmdType) override;
    int32_t SetBackMute(bool backMute) override;
    bool GetMute() override;
    int32_t SetMuteHint(bool mute) override;
    int32_t SetRenderRate(AudioRendererRate renderRate) override;
    AudioRendererRate GetRenderRate() override;
    int32_t SetStreamCallback(const std::shared_ptr<AudioStreamCallback> &callback) override;
    int32_t SetSpeed(float speed) override;
    int32_t SetPitch(float pitch) override;
    int32_t SetSonicPitch(float pitch) override;
    float GetSpeed() override;
    int32_t GetAudioDebugInfo(AudioDebugInfo &debugInfo) override;

    // callback mode api
    AudioRenderMode GetRenderMode() override;
    int32_t SetRenderMode(AudioRenderMode renderMode) override;
    int32_t SetRendererWriteCallback(const std::shared_ptr<AudioRendererWriteCallback> &callback) override;
    int32_t SetCaptureMode(AudioCaptureMode captureMode) override;
    void InitCallbackLoop();
    AudioCaptureMode GetCaptureMode() override;
    int32_t SetCapturerReadCallback(const std::shared_ptr<AudioCapturerReadCallback> &callback) override;
    int32_t SetCapturerMetaDataCallback(const std::shared_ptr<AudioCapturerMetaDataCallback> &callback) override;
    int32_t GetBufferDesc(BufferDesc &bufDesc) override;
    int32_t Clear() override;
    int32_t GetBufQueueState(BufferQueueState &bufState) override;
    int32_t Enqueue(const BufferDesc &bufDesc) override;

    int32_t SetLowPowerVolume(float volume) override;
    float GetLowPowerVolume() override;
    int32_t UnsetOffloadMode() override;
    int32_t SetOffloadMode(int32_t state, bool isAppBack) override;
    float GetSingleStreamVolume() override;
    AudioEffectMode GetAudioEffectMode() override;
    int32_t SetAudioEffectMode(AudioEffectMode effectMode) override;
    int64_t GetFramesRead() override;
    int64_t GetFramesWritten() override;

    void SetInnerCapturerState(bool isInnerCapturer) override;
    void SetWakeupCapturerState(bool isWakeupCapturer) override;
    void SetPrivacyType(AudioPrivacyType privacyType) override;
    void SetCapturerSource(int capturerSource) override;

    // Common APIs
    bool StartAudioStream(StateChangeCmdType cmdType = CMD_FROM_CLIENT,
        AudioStreamDeviceChangeReasonExt reason = AudioStreamDeviceChangeReasonExt::ExtEnum::UNKNOWN) override;
    bool PauseAudioStream(StateChangeCmdType cmdType = CMD_FROM_CLIENT) override;
    bool StopAudioStream() override;
    bool FlushAudioStream() override;
    bool ReleaseAudioStream(bool releaseRunner = true, bool isSwitchStream = false) override;
    void JoinCallbackLoop() override;

    // Playback related APIs
    bool DrainAudioStream(bool stopFlag = false) override;
    int32_t Write(uint8_t *buffer, size_t bufferSize) override;
    int32_t Write(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer, size_t metaBufferSize) override;
    void SetPreferredFrameSize(int32_t frameSize, bool isRecreate = false) override;
    void UpdateLatencyTimestamp(std::string &timestamp, bool isRenderer) override;
    int32_t SetRendererFirstFrameWritingCallback(
        const std::shared_ptr<AudioRendererFirstFrameWritingCallback> &callback) override;
    void OnFirstFrameWriting() override;

    // Recording related APIs
    int32_t Read(uint8_t &buffer, size_t userSize, bool isBlockingRead) override;

    // Position and period callbacks
    void SetCapturerPositionCallback(int64_t markPosition,
        const std::shared_ptr<CapturerPositionCallback> &callback) override;
    void UnsetCapturerPositionCallback() override;
    void SetCapturerPeriodPositionCallback(int64_t periodPosition,
        const std::shared_ptr<CapturerPeriodPositionCallback> &callback) override;
    void UnsetCapturerPeriodPositionCallback() override;
    void SetRendererPositionCallback(int64_t markPosition,
        const std::shared_ptr<RendererPositionCallback> &callback) override;
    void UnsetRendererPositionCallback() override;
    void SetRendererPeriodPositionCallback(int64_t periodPosition,
        const std::shared_ptr<RendererPeriodPositionCallback> &callback) override;
    void UnsetRendererPeriodPositionCallback() override;

    uint32_t GetUnderflowCount() override;
    uint32_t GetOverflowCount() override;
    void SetUnderflowCount(uint32_t underflowCount) override;
    void SetOverflowCount(uint32_t overflowCount) override;

    int32_t RegisterRemoteDiedCallback(const std::shared_ptr<RemoteDiedCallback> &callback) override;
    int32_t UnregisterRemoteDiedCallback() override;

    uint32_t GetRendererSamplingRate() override;
    int32_t SetRendererSamplingRate(uint32_t sampleRate) override;
    int32_t SetBufferSizeInMsec(int32_t bufferSizeInMsec) override;
    int32_t SetChannelBlendMode(ChannelBlendMode blendMode) override;
    int32_t SetVolumeWithRamp(float volume, int32_t duration) override;

    void SetStreamTrackerState(bool trackerRegisteredState) override;
    void GetSwitchInfo(IAudioStream::SwitchInfo& info) override;

    IAudioStream::StreamClass GetStreamClass() override;

    void SetSilentModeAndMixWithOthers(bool on) override;

    bool GetSilentModeAndMixWithOthers() override;

    static void AudioServerDied(pid_t pid, pid_t uid);

    void OnHandle(uint32_t code, int64_t data) override;
    void InitCallbackHandler();
    void SafeSendCallbackEvent(uint32_t eventCode, int64_t data);

    void SendCapturerMarkReachedEvent(int64_t capturerMarkPosition);
    void SendCapturerPeriodReachedEvent(int64_t capturerPeriodSize);

    void HandleCapturerPositionChanges(size_t bytesRead);
    void HandleStateChangeEvent(int64_t data);
    void HandleCapturerMarkReachedEvent(int64_t capturerMarkPosition);
    void HandleCapturerPeriodReachedEvent(int64_t capturerPeriodNumber);
    void SendAudioErrorEventAndProcessOther(int32_t uid, int32_t errorCode,
        const std::string &erroDesc, bool isClient, State state);

    static const sptr<IStandardAudioService> GetAudioServerProxy();

    bool GetOffloadEnable() override;
    bool GetSpatializationEnabled() override;
    bool GetHighResolutionEnabled() override;
    int32_t SetDefaultOutputDevice(const DeviceType defaultOutputDevice, bool skipForce = false) override;
    DeviceType GetDefaultOutputDevice() override;
    FastStatus GetFastStatus() override;
    void SetFastStatusChangeCallback(const std::function<void(FastStatus)> &callback) override;
    int32_t GetAudioTimestampInfo(Timestamp &timestamp, Timestamp::Timestampbase base) override;
    void SetSwitchingStatus(bool isSwitching) override;
    void GetRestoreInfo(RestoreInfo &restoreInfo) override;
    void SetRestoreInfo(RestoreInfo &restoreInfo) override;
    RestoreStatus CheckRestoreStatus() override;
    RestoreStatus SetRestoreStatus(RestoreStatus restoreStatus) override;
    void SetSwitchInfoTimestamp(std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePair,
        std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePairWithSpeed) override;
    void FetchDeviceForSplitStream() override;

    bool RestoreAudioStream(bool needStoreState = true) override;

    void SetCallStartByUserTid(pid_t tid) override;
    void SetCallbackLoopTid(int32_t tid) override;
    int32_t GetCallbackLoopTid() override;
    bool GetStopFlag() const override;
    bool IsRestoreNeeded() override;
    int32_t SetRebuildFlag() override;
    int32_t RequestUserPrivacyAuthority(uint32_t sessionId) override;
    void SetPlaybackCaptureStartStateCallback(
        const std::shared_ptr<AudioCapturerOnPlaybackCaptureStartCallback> &callback) override;
    void SetSensitiveRecordPermitCallback(
        const std::shared_ptr<AudioCapturerSensitiveRecordPermitCallback> &callback) override;

    int32_t SetLoopTimes(int64_t bufferLoopTimes) override;
    void SetStaticBufferInfo(StaticBufferInfo staticBufferInfo,
        std::shared_ptr<AudioSharedMemory> sharedMemory) override;
    int32_t SetStaticBufferEventCallback(std::shared_ptr<StaticBufferEventCallback> callback) override;
    int32_t SetStaticTriggerRecreateCallback(std::function<void()> sendStaticRecreateFunc) override;

    const std::string GetBundleName() override;
    void SetBundleName(std::string &name) override;

    bool ResetStaticPlayPosition() override;
    int32_t ResetNotifyStreamSilentChangeFlag() override;
private:
    void RegisterTracker(const std::shared_ptr<AudioClientTracker> &proxyObj);
    void UpdateTracker(const std::string &updateCase);

    int32_t DeinitIpcStream();

    int32_t InitIpcStream(const AudioPlaybackCaptureConfig &filterConfig);

    const AudioProcessConfig ConstructConfig();

    int32_t InitCacheBuffer(size_t targetSize);
    int32_t InitSharedBuffer();
    int32_t FlushRingCache();
    int32_t FlushCbBuffer();
    void InitDfxOperation();

    void GetStreamSwitchInfo(IAudioStream::SwitchInfo& info);
    void NotifyFastStatusChange(FastStatus status);

    int32_t StateCmdTypeToParams(int64_t &params, State state, StateChangeCmdType cmdType);
    int32_t ParamsToStateCmdType(int64_t params, State &state, StateChangeCmdType &cmdType);

    void InitCallbackBuffer(uint64_t bufferDurationInUs);
    bool ReadCallbackFunc();
    // for callback mode. Check status if not running, wait for start or release.
    bool WaitForRunning();

    int32_t HandleCapturerRead(size_t &readSize, size_t &userSize, uint8_t &buffer, bool isBlockingRead);
    // Normal blocking reads carry an immutable local operation generation across waits.
    void RetireNormalReadsLocked(); // statusMutex_ held; never waits for readMutex_.
    bool NormalReadIsCurrent(uint64_t generation) const;
    int32_t HandleNormalCapturerRead(size_t &readSize, size_t userSize, uint8_t &buffer,
        bool isBlockingRead, uint64_t generation);
    bool CommitNormalReadPositionChanges(size_t bytesRead, uint64_t generation,
        int64_t &markPosition, int64_t &periodSize);
    int32_t RegisterCapturerInClientPolicyServerDiedCb();
    int32_t UnregisterCapturerInClientPolicyServerDiedCb();
    void ResetCallbackLoopTid();
    bool GetAudioTimeInner(Timestamp &timestamp, Timestamp::Timestampbase base, int64_t latency);
    void DumpMetadata(const std::vector<uint8_t> &metaData);
    void ReleaseCallbackResources(bool releaseRunner);
    void FinalizeRelease();

    void UpdateStreamState(State state);
    void FillCapturerClientOnlyInfo(AudioDebugInfo &debugInfo);
    void FillCapturerDeviceInfo(AudioDebugInfo &debugInfo, uint32_t sessionId);
    int32_t CheckForSetAudioStreamInfo(const AudioStreamParams info);

private:
    AudioStreamType eStreamType_;
    int32_t appUid_;
    uint32_t sessionId_ = 0;
    int32_t clientUid_ = -1;
    int32_t clientPid_ = -1;
    uint32_t appTokenId_ = 0;
    uint64_t fullTokenId_ = 0;
    std::string deviceId_ = "";

    std::atomic<uint32_t> readLogTimes_ = 0;

    std::unique_ptr<AudioStreamTracker> audioStreamTracker_ = nullptr;
    bool streamTrackerRegistered_ = false;

    AudioRendererInfo rendererInfo_ = {}; // not in use
    AudioCapturerInfo capturerInfo_ = {};

    int32_t bufferSizeInMsec_ = 20; // 20ms

    // callback mode
    AudioCaptureMode capturerMode_ = CAPTURE_MODE_NORMAL;
    std::thread callbackLoop_; // thread for callback to client and write.
    int32_t callbackLoopTid_ = -1;
    std::mutex callbackLoopTidMutex_;
    std::condition_variable callbackLoopTidCv_;
    std::atomic<bool> cbThreadReleased_ = true;
    std::mutex readCbMutex_; // lock for change or use callback
    std::condition_variable cbThreadCv_;
    std::shared_ptr<AudioCapturerReadCallback> readCb_ = nullptr;
    std::mutex metaDataCbMutex_;
    std::shared_ptr<AudioCapturerMetaDataCallback> metaDataCb_ = nullptr;
    std::mutex cbBufferMutex_;
    std::unique_ptr<uint8_t[]> cbBuffer_ {nullptr};
    size_t cbBufferSize_ = 0;
    AudioSafeBlockQueue<BufferDesc> cbBufferQueue_; // only one cbBuffer_

    AudioPlaybackCaptureConfig filterConfig_ = {};
    bool isInnerCapturer_ = false;
    bool isWakeupCapturer_ = false;

    bool needSetThreadPriority_ = true;

    AudioStreamParams streamParams_; // in plan: replace it with AudioCapturerParams

    // callbacks
    std::mutex streamCbMutex_;
    std::weak_ptr<AudioStreamCallback> streamCallback_;
    std::mutex fastStatusChangeCallbackMutex_;
    std::function<void(FastStatus)> fastStatusChangeCallback_;
    std::atomic<FastStatus> fastStatus_ = FASTSTATUS_NORMAL;
    FILE *dumpMetaDataFile_ = nullptr;
    std::string dumpMetaDataFileName_ = "";

    size_t cacheSizeInByte_ = 0;
    uint32_t spanSizeInFrame_ = 0;
    size_t clientSpanSizeInByte_ = 0;
    size_t sizePerFrameInByte_ = 4; // 16bit 2ch as default

    // using this lock when change status_
    std::mutex statusMutex_;
    std::atomic<State> state_ = INVALID;
    std::atomic<uint64_t> normalReadGeneration_ {0};
    std::atomic<StreamFocusState> streamFocusState_ = FOCUS_INVALID;
    std::mutex focusStatusMutex_;
    // for status operation wait and notify
    std::mutex callServerMutex_;
    std::condition_variable callServerCV_;

    Operation notifiedOperation_ = MAX_OPERATION_CODE;
    int64_t notifiedResult_ = 0;

    uint32_t overflowCount_ = 0;
    // ipc stream related
    AudioProcessConfig clientConfig_;
    sptr<IpcStreamListenerImpl> listener_ = nullptr;
    sptr<IIpcStream> ipcStream_ = nullptr;
    sptr<IRemoteObject> ipcProxy_ = nullptr;
    std::mutex deathRecipientLock_;
    sptr<RemoteDeathRecipient> deathRecipient_ = nullptr;
    std::shared_ptr<OHAudioBuffer> clientBuffer_ = nullptr;

    // buffer handle
    std::unique_ptr<AudioRingCache> ringCache_ = nullptr;
    std::mutex readMutex_; // used for prevent multi thread call read

    // Mark reach and period reach callback
    uint64_t totalBytesRead_ = 0;
    std::mutex markReachMutex_;
    bool capturerMarkReached_ = false;
    int64_t capturerMarkPosition_ = 0;
    std::shared_ptr<CapturerPositionCallback> capturerPositionCallback_ = nullptr;

    std::mutex periodReachMutex_;
    int64_t capturerPeriodSize_ = 0;
    int64_t capturerPeriodRead_ = 0;
    std::shared_ptr<CapturerPeriodPositionCallback> capturerPeriodPositionCallback_ = nullptr;

    mutable int64_t volumeDataCount_ = 0;
    std::string logUtilsTag_ = "";
    std::string dumpInFile_ = "";
    FILE *dumpInFd_ = nullptr;

    // Event handler
    bool runnerReleased_ = false;
    std::mutex runnerMutex_;
    std::shared_ptr<CallbackHandler> callbackHandler_ = nullptr;

    std::shared_ptr<AudioClientTracker> proxyObj_ = nullptr;

    bool paramsIsSet_ = false;
    int32_t innerCapId_ = 0;
    std::mutex playbackCaptureStartCallbackMutex_;
    std::shared_ptr<AudioCapturerOnPlaybackCaptureStartCallback> playbackCaptureStartCallback_ = nullptr;
    std::mutex sensitiveRecordPermitCallbackMutex_;
    std::shared_ptr<AudioCapturerSensitiveRecordPermitCallback> sensitiveRecordPermitCallback_ = nullptr;

    std::string bundleName = "";

    enum {
        STATE_CHANGE_EVENT = 0,
        RENDERER_MARK_REACHED_EVENT,
        RENDERER_PERIOD_REACHED_EVENT,
        CAPTURER_PERIOD_REACHED_EVENT,
        CAPTURER_MARK_REACHED_EVENT,
    };

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

    enum :int32_t {
        AUDIOSTREAM_PLAYBACKCAPTURE_START_STATE_SUCCESS = 0,
        AUDIOSTREAM_PLAYBACKCAPTURE_START_STATE_FAILED,
        AUDIOSTREAM_PLAYBACKCAPTURE_START_STATE_NOT_AUTHORIZED,
    };
};
} // namespace AudioStandard
} // namespace OHOS
#endif // CAPTURER_IN_CLIENT_INNER_H
