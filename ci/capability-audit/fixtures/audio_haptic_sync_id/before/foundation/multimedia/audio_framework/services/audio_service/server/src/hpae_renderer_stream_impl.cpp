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
#ifndef LOG_TAG
#define LOG_TAG "HpaeRendererStreamImpl"
#endif

#ifdef FEATURE_POWER_MANAGER
#include "power_mgr_client.h"
#endif

#include "hpae_renderer_stream_impl.h"
#include "sink/i_audio_render_sink.h"
#include "manager/hdi_adapter_manager.h"
#include <chrono>
#include <thread>
#include "safe_map.h"
#include "audio_errors.h"
#include "audio_utils.h"
#include "i_hpae_manager.h"
#include "audio_stream_info.h"
#include "audio_effect_map.h"
#include "mixer_utils.h"
#include "policy_handler.h"
#include "audio_engine_log.h"
#include "core_service_handler.h"
#include "audio_stream_enum.h"
#include "audio_volume.h"
#include "volume_tools.h"
#include "audio_sink_latency_fetcher.h"
#include "boot_animation_state_info.h"
#include "util/id_handler.h"

using namespace OHOS::AudioStandard::HPAE;

namespace OHOS {
namespace AudioStandard {

static constexpr int32_t MIN_BUFFER_SIZE = 2;
static constexpr float FRAME_LEN_2_5MS_IN_MS = 2.5f;
static constexpr uint64_t FRAME_LEN_5MS = 5;
static constexpr uint64_t FRAME_LEN_10MS = 10;
static constexpr uint64_t FRAME_LEN_20MS = 20;
static constexpr uint64_t FRAME_LEN_40MS = 40;
static constexpr uint64_t FIXED_LATENCY_IN_MS = 40;
static constexpr uint64_t PRINT_TIMESTAMP_INTERVAL_NS = 1000000000;
static const std::string DEVICE_CLASS_OFFLOAD = "offload";
static const std::string DEVICE_CLASS_REMOTE_OFFLOAD = "remote_offload";
static const std::string DEVICE_CLASS_A2DP = "a2dp";
static std::shared_ptr<IAudioRenderSink> GetRenderSinkInstance(std::string deviceClass, std::string deviceNetId);
static inline FadeType GetFadeType(uint64_t expectedPlaybackDurationMs);
HpaeRendererStreamImpl::HpaeRendererStreamImpl(AudioProcessConfig processConfig, bool isMoveAble,
    const std::string &deviceName, bool isCallbackMode, size_t preBufSizeInBytes)
    : preBufSizeInBytes_(preBufSizeInBytes)
{
    processConfig_ = processConfig;
    usedSampleRate_ = processConfig.streamInfo.customSampleRate == 0 ?
        static_cast<uint32_t>(processConfig.streamInfo.samplingRate) : processConfig.streamInfo.customSampleRate;
    
    if (processConfig_.rendererInfo.audioFlag == AUDIO_OUTPUT_FLAG_FAST &&
        processConfig_.isInnerCapturer == false && deviceName != "FastDpRendererSink" && isCallbackMode) {
        if (IsUltraFastStreamAndRoute(processConfig_.ultraFastFlag)) {
            spanSizeInFrame_ = static_cast<size_t>(FRAME_LEN_2_5MS_IN_MS * usedSampleRate_ / AUDIO_MS_PER_S);
            AUDIO_INFO_LOG("ultra fast for spanSizeInFrame_ to 2.5ms: %{public}zu", spanSizeInFrame_);
        } else {
            spanSizeInFrame_ = FRAME_LEN_5MS * usedSampleRate_ / AUDIO_MS_PER_S;
            AUDIO_INFO_LOG("fast for spanSizeInFrame_ to 5ms: %{public}zu", spanSizeInFrame_);
        }
    } else {
        spanSizeInFrame_ = FRAME_LEN_20MS * usedSampleRate_ / AUDIO_MS_PER_S;
        AUDIO_INFO_LOG("RendererStream: unified 20ms span, usedSampleRate=%{public}u, spanSizeInFrame=%{public}zu",
            usedSampleRate_, spanSizeInFrame_);
    }
    if ((processConfig_.rendererInfo.audioFlag == AUDIO_OUTPUT_FLAG_FAST ||
        processConfig_.rendererInfo.audioFlag == AUDIO_OUTPUT_FLAG_VOIP_FAST ||
        processConfig_.rendererInfo.ultraFastFlag != ULTRA_NONE) &&
        processConfig_.isInnerCapturer == false) {
        delayedWake_ = true;
    }
    byteSizePerFrame_ = (processConfig.streamInfo.channels *
        static_cast<size_t>(GetSizeFromFormat(processConfig.streamInfo.format)));
    minBufferSize_ = MIN_BUFFER_SIZE * byteSizePerFrame_ * spanSizeInFrame_;
    if (byteSizePerFrame_ == 0 || usedSampleRate_ == 0) {
        expectedPlaybackDurationMs_ = 0;
    } else {
        expectedPlaybackDurationMs_ =
            (processConfig.rendererInfo.expectedPlaybackDurationBytes * AUDIO_MS_PER_S / byteSizePerFrame_) /
                usedSampleRate_;
    }
    isCallbackMode_ = isCallbackMode;
    isMoveAble_ = isMoveAble;
    if (!isCallbackMode_) {
        InitRingBuffer();
    }
}
HpaeRendererStreamImpl::~HpaeRendererStreamImpl()
{
    AUDIO_INFO_LOG("destructor %{public}u", streamIndex_);
    if (dumpEnqueueIn_ != nullptr) {
    DumpFileUtil::CloseDumpFile(&dumpEnqueueIn_);
    }
}

int32_t HpaeRendererStreamImpl::InitParams(const std::string &deviceName)
{
    HpaeStreamInfo streamInfo;
    streamInfo.channels = processConfig_.streamInfo.channels;
    streamInfo.samplingRate = processConfig_.streamInfo.samplingRate;
    streamInfo.customSampleRate = processConfig_.streamInfo.customSampleRate;
    streamInfo.format = processConfig_.streamInfo.format;
    streamInfo.channelLayout = processConfig_.streamInfo.channelLayout;
    if (streamInfo.channelLayout == CH_LAYOUT_UNKNOWN) {
        AudioChannelLayout layout;
        SetDefaultChannelLayout(static_cast<AudioChannel>(streamInfo.channels), layout);
        streamInfo.channelLayout = layout;
    }
    streamInfo.frameLen = spanSizeInFrame_;
    streamInfo.sessionId = processConfig_.originalSessionId;
    streamInfo.streamType = processConfig_.streamType;
    streamInfo.fadeType = GetFadeType(expectedPlaybackDurationMs_);
    streamInfo.streamClassType = HPAE_STREAM_CLASS_TYPE_PLAY;
    streamInfo.uid = processConfig_.appInfo.appUid;
    streamInfo.pid = processConfig_.appInfo.appPid;
    streamInfo.tokenId = processConfig_.appInfo.appTokenId;
    effectMode_ = processConfig_.rendererInfo.effectMode;
    streamInfo.effectInfo.effectMode = (effectMode_ != EFFECT_DEFAULT && effectMode_ != EFFECT_NONE) ? EFFECT_DEFAULT :
        static_cast<AudioEffectMode>(effectMode_);
    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
    streamInfo.effectInfo.effectScene = static_cast<AudioEffectScene>(GetKeyFromValue(
        audioSupportedSceneTypes, processConfig_.rendererInfo.sceneType));
    streamInfo.effectInfo.systemVolumeType = VolumeUtils::GetVolumeTypeFromStreamType(processConfig_.streamType);
    streamInfo.effectInfo.streamUsage = processConfig_.rendererInfo.streamUsage;
    streamInfo.sourceType = processConfig_.isInnerCapturer == true ? SOURCE_TYPE_PLAYBACK_CAPTURE : SOURCE_TYPE_INVALID;
    streamInfo.deviceName = deviceName;
    streamInfo.isMoveAble = isMoveAble_;
    streamInfo.keepRunning = processConfig_.rendererInfo.keepRunning;
    streamInfo.isLoopback = processConfig_.rendererInfo.isLoopback;
    streamInfo.privacyType = processConfig_.privacyType;
    AUDIO_INFO_LOG("channels %{public}u channelLayout %{public}" PRIu64 " samplingRate %{public}u format %{public}u "
        "frameLen %{public}zu streamType %{public}u sessionId %{public}u streamClassType %{public}u "
        "sourceType %{public}d fadeType %{public}d", streamInfo.channels, streamInfo.channelLayout,
        streamInfo.customSampleRate == 0 ? streamInfo.samplingRate : streamInfo.customSampleRate, streamInfo.format,
        streamInfo.frameLen, streamInfo.streamType, streamInfo.sessionId, streamInfo.streamClassType,
        streamInfo.sourceType, streamInfo.fadeType);
    auto &hpaeManager = IHpaeManager::GetHpaeManager();
    int32_t ret = hpaeManager.CreateStream(streamInfo);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_INVALID_PARAM, "CreateStream is error");

    // Register Callback
    ret = hpaeManager.RegisterStatusCallback(HPAE_STREAM_CLASS_TYPE_PLAY, streamInfo.sessionId, shared_from_this());
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_INVALID_PARAM, "RegisterStatusCallback is error");
    ret = hpaeManager.RegisterWriteCallback(streamInfo.sessionId, shared_from_this());
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_INVALID_PARAM, "RegisterWriteCallback is error");
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Start()
{
    AUDIO_INFO_LOG("[%{public}u] Enter", streamIndex_);
    Trace trace("HpaeRendererStreamImpl::Start[" + std::to_string(streamIndex_) + "]");
    preBufDone_.store(false);
    ClockTime::GetAllTimeStamp(timestamp_);
    int32_t ret = IHpaeManager::GetHpaeManager().Start(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
    if (processConfig_.streamInfo.customSampleRate != 0) {
        noWaitDataFlag_ = false;
    }
    std::string tempStringSessionId = std::to_string(streamIndex_);
    IHpaeManager::GetHpaeManager().AddStreamVolumeToEffect(tempStringSessionId, clientVolume_);
    CoreServiceHandler::GetInstance().RecordBootStateTime(static_cast<int32_t>(
        BootAnimationState::PREE_AUDIO_START), processConfig_.appInfo.appUid, ClockTime::GetCurMilli());
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::StartWithSyncId(const int32_t &syncId)
{
    AUDIO_INFO_LOG("[%{public}u] Enter syncId: %{public}d", streamIndex_, syncId);
    preBufDone_.store(false);
    ClockTime::GetAllTimeStamp(timestamp_);
    int32_t ret = IHpaeManager::GetHpaeManager().StartWithSyncId(HPAE_STREAM_CLASS_TYPE_PLAY,
        processConfig_.originalSessionId, syncId);
    if (processConfig_.streamInfo.customSampleRate != 0) {
        noWaitDataFlag_ = false;
    }
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Pause(bool isStandby)
{
    AUDIO_INFO_LOG("[%{public}u] Enter isStandby:%{public}d", streamIndex_, isStandby);
    Trace trace("HpaeRendererStreamImpl::Pause[" + std::to_string(streamIndex_) + "]");
    int32_t ret = IHpaeManager::GetHpaeManager().Pause(HPAE_STREAM_CLASS_TYPE_PLAY,
        processConfig_.originalSessionId, isStandby);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Flush()
{
    AUDIO_INFO_LOG("[%{public}u] Enter", streamIndex_);
    Trace trace("HpaeRendererStreamImpl::Flush[" + std::to_string(streamIndex_) + "]");
    int32_t ret = IHpaeManager::GetHpaeManager().Flush(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Drain(bool stopFlag)
{
    AUDIO_INFO_LOG("[%{public}u] Enter %{public}d", streamIndex_, stopFlag);
    Trace trace("HpaeRendererStreamImpl::Drain[" + std::to_string(streamIndex_) + "]");
    preBufDone_.store(true);
    int32_t ret = IHpaeManager::GetHpaeManager().Drain(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Stop()
{
    AUDIO_INFO_LOG("[%{public}u] Enter", streamIndex_);
    Trace trace("HpaeRendererStreamImpl::Stop[" + std::to_string(streamIndex_) + "]");
    int32_t ret = IHpaeManager::GetHpaeManager().Stop(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    state_ = STOPPING;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::Release()
{
    if (state_ == RUNNING) {
        AUDIO_ERR_LOG("%{public}u Release state_ is RUNNING", processConfig_.originalSessionId);
        IHpaeManager::GetHpaeManager().Stop(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
    }
    AUDIO_INFO_LOG("[%{public}u] Enter", streamIndex_);
    int32_t ret = IHpaeManager::GetHpaeManager().DestroyStream(HPAE_STREAM_CLASS_TYPE_PLAY,
        processConfig_.originalSessionId);
    std::string tempStringSessionId = std::to_string(streamIndex_);
    IHpaeManager::GetHpaeManager().DeleteStreamVolumeToEffect(tempStringSessionId);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    state_ = RELEASED;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetStreamFramesWritten(uint64_t &framesWritten)
{
    framesWritten = framesWritten_;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetCurrentTimeStamp(uint64_t &timestamp)
{
    std::shared_lock<std::shared_mutex> lock(latencyMutex_);
    timestamp = timestamp_[Timestamp::Timestampbase::MONOTONIC];
    return SUCCESS;
}

uint32_t HpaeRendererStreamImpl::GetA2dpOffloadLatency()
{
    std::string deviceClass;
    std::string deviceNetId;
    {
        std::shared_lock<std::shared_mutex> lock(latencyMutex_);
        deviceClass = deviceClass_;
        deviceNetId = deviceNetId_;
    }
    std::shared_ptr<IAudioRenderSink> audioRendererSink = GetRenderSinkInstance(deviceClass, deviceNetId);
    CHECK_AND_RETURN_RET(audioRendererSink != nullptr && audioRendererSink->IsInA2dpOffload(), 0);

    Trace trace("HpaeRendererStreamImpl::GetA2dpOffloadLatency");
    uint32_t a2dpOffloadLatency = 0;
    uint64_t a2dpOffloadSendDataSize = 0;
    uint32_t a2dpOffloadTimestamp = 0;
    auto& handle = CoreServiceHandler::GetInstance();
    int32_t ret = handle.A2dpOffloadGetRenderPosition(
        a2dpOffloadLatency, a2dpOffloadSendDataSize, a2dpOffloadTimestamp);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("A2dpOffloadGetRenderPosition failed!");
    }
    return a2dpOffloadLatency;
}

uint32_t HpaeRendererStreamImpl::GetNearlinkLatency()
{
    Trace trace("HpaeRendererStreamImpl::GetNearlinkLatency");
    uint32_t nearlinkLatency = 0;
    auto &handler = PolicyHandler::GetInstance();
    int32_t ret = handler.NearlinkGetRenderPosition(nearlinkLatency);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, 0, "NearlinkGetRenderPosition failed");

    return nearlinkLatency;
}

uint32_t HpaeRendererStreamImpl::GetSinkLatency()
{
    Trace trace("HpaeRendererStreamImpl::GetSinkLatency");
    uint32_t sinkLatency = 0;
    int32_t ret = GetSinkLatencyInner(sinkLatency);
    if (ret != SUCCESS) {
        AUDIO_WARNING_LOG("GetSinkLatencyInner failed, ret %{public}d", ret);
        sinkLatency = 0;
    }
    return sinkLatency;
}

int32_t HpaeRendererStreamImpl::GetSinkLatencyInner(uint32_t &sinkLatency)
{
    std::string deviceClass;
    std::string deviceNetId;
    {
        std::shared_lock<std::shared_mutex> lock(latencyMutex_);
        deviceClass = deviceClass_;
        deviceNetId = deviceNetId_;
        if (offloadEnable_) {
            sinkLatency = GetOffloadLatency();
            return SUCCESS;
        }
    }
    return GetSinkLatencyInner(deviceClass, deviceNetId, sinkLatency);
}

int32_t HpaeRendererStreamImpl::GetSinkLatencyInner(const std::string &deviceClass,
    const std::string &deviceNetId, uint32_t &sinkLatency)
{
    sinkLatency = 0;
    std::shared_ptr<IAudioRenderSink> audioRendererSink = GetRenderSinkInstance(deviceClass, deviceNetId);
    CHECK_AND_RETURN_RET_LOG(audioRendererSink != nullptr, ERR_INVALID_OPERATION,
        "audioRendererSink is null, deviceClass %{public}s", deviceClass.c_str());
    int32_t ret = audioRendererSink->GetLatency(sinkLatency);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "audioRendererSink GetLatency failed");
    auto compensation = (deviceClass == DEVICE_CLASS_A2DP) * FIXED_LATENCY_IN_MS;
    sinkLatency = sinkLatency >= compensation ? sinkLatency - compensation :sinkLatency;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetRemoteOffloadSpeedPosition(uint64_t &framePosition, uint64_t &timestamp,
    uint64_t &latency)
{
    std::shared_lock<std::shared_mutex> lock(latencyMutex_);
    // latencyMutex_ begin
    CHECK_AND_RETURN_RET(deviceClass_ == DEVICE_CLASS_REMOTE_OFFLOAD, ERR_NOT_SUPPORTED);

    std::shared_ptr<IAudioRenderSink> sink = GetRenderSinkInstance(deviceClass_, deviceNetId_);
    CHECK_AND_RETURN_RET_LOG(sink != nullptr, ERR_INVALID_OPERATION, "audioRendererSink is null");
    uint64_t framesUS;
    int64_t timeSec;
    int64_t timeNSec;
    int32_t ret = sink->GetHdiPresentationPosition(framesUS, timeSec, timeNSec);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "get position fail");

    uint32_t curLatencyUS = 0;
    ret = sink->GetHdiLatency(curLatencyUS);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "get latency fail");

    // Here, latency and sampling count are calculated, and latency is exposed to the client as 0.
    latency = static_cast<uint64_t>(curLatencyUS) * usedSampleRate_ / AUDIO_US_PER_S;

    uint64_t frames = framesUS * usedSampleRate_ / AUDIO_US_PER_S;
    framePosition = lastHdiFramePosition_ + frames;
    timestamp = static_cast<uint64_t>(ClockTime::GetCurNano());
    bool checkResult = ClockTime::CheckTimeInterval(lastLogTimestampArr_[GET_REMOTE_OFFLOAD_SPEED_POSITION],
        PRINT_TIMESTAMP_INTERVAL_NS);
    AUDIO_LIMIT_INFO_LOG(checkResult, "framesUS: %{public}" PRIu64 ", frames: %{public}" PRIu64
        ", framePosition: %{public}" PRIu64 ", curLatencyUS: %{public}u, latency: %{public}" PRIu64, framesUS, frames,
        framePosition, curLatencyUS, latency);
    // latencyMutex_ end
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetSpeedPosition(uint64_t &framePosition, uint64_t &timestamp,
    uint64_t &latency, int32_t base)
{
    int32_t ret = GetRemoteOffloadSpeedPosition(framePosition, timestamp, latency);
    CHECK_AND_RETURN_RET(ret == ERR_NOT_SUPPORTED, ret);

    int64_t now = ClockTime::GetCurNano();
    int32_t baseUsed = base >= 0 && base < Timestamp::Timestampbase::BASESIZE ?
        base : Timestamp::Timestampbase::MONOTONIC;
    auto &positionData = speedPositionData_[baseUsed];
    uint64_t latencyUs = 0;
    GetLatencyInner(timestamp, latencyUs, base);

    std::shared_lock<std::shared_mutex> lock(latencyMutex_);
    // latencyMutex_ begin
    latencyUs += latency_;
    AUDIO_DEBUG_LOG("pipe latency: %{public}" PRIu64, latency_);
    framePosition = lastHdiFramePosition_ + framePosition_ - lastFramePosition_;
    uint64_t mutePaddingFrames = mutePaddingFrames_.load();
    framePosition = (framePosition > mutePaddingFrames) ? (framePosition - mutePaddingFrames) : 0;
    latency = latencyUs * static_cast<uint64_t>(usedSampleRate_) / AUDIO_US_PER_S;
    // latencyMutex_ end
    positionData.framePosition = framePosition;
    positionData.timestamp = timestamp;
    positionData.latency = latency;
    positionData.lastCallTime = now;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetCurrentPosition(uint64_t &framePosition, uint64_t &timestamp,
    uint64_t &latency, int32_t base)
{
    int64_t now = ClockTime::GetCurNano();
    int32_t baseUsed = base >= 0 && base < Timestamp::Timestampbase::BASESIZE ?
        base : Timestamp::Timestampbase::MONOTONIC;
    auto &positionData = currentPositionData_[baseUsed];
    uint64_t latencyUs = 0;
    GetLatencyInner(timestamp, latencyUs, base);
    std::shared_lock<std::shared_mutex> lock(latencyMutex_);
    // latencyMutex_ begin
    latencyUs += latency_;
    AUDIO_DEBUG_LOG("pipe latency: %{public}" PRIu64, latency_);
    latency = latencyUs * static_cast<uint64_t>(usedSampleRate_) / AUDIO_US_PER_S;
    framePosition = framePosition_;
    uint64_t mutePaddingFrames = mutePaddingFrames_.load();
    framePosition = (framePosition > mutePaddingFrames) ? (framePosition - mutePaddingFrames) : 0;
    bool checkResult = ClockTime::CheckTimeInterval(lastLogTimestampArr_[GET_CURRENT_POSITION],
        PRINT_TIMESTAMP_INTERVAL_NS);
    AUDIO_LIMIT_INFO_LOG(checkResult, "Latency info: framePosition: %{public}" PRIu64 ", latency %{public}" PRIu64,
        framePosition, latency);
    // latencyMutex_ end
    positionData.framePosition = framePosition;
    positionData.timestamp = timestamp;
    positionData.latency = latency;
    positionData.lastCallTime = now;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetLatency(uint64_t &latency)
{
    uint64_t timestamp = 0;
    std::shared_ptr<IAudioRenderSink> audioRendererSink;
    int32_t base = Timestamp::Timestampbase::MONOTONIC;
    GetLatencyInner(timestamp, latency, base);
    std::shared_lock<std::shared_mutex> lock(latencyMutex_);
    // latencyMutex_ begin
    latency += latency_;
    bool checkResult = ClockTime::CheckTimeInterval(lastLogTimestampArr_[GET_LATENCY], PRINT_TIMESTAMP_INTERVAL_NS);
    AUDIO_LIMIT_INFO_LOG(checkResult, "pipe latency: %{public}" PRIu64, latency_);
    // latencyMutex_ end
    return SUCCESS;
}

bool HpaeRendererStreamImpl::WaitFirstStreamData()
{
    if (firstStreamDataReceived_.load(std::memory_order_acquire)) {
        return true;
    }
    std::unique_lock<std::mutex> readyLock(firstStreamDataMutex_);
    return firstStreamDataCv_.wait_for(readyLock, std::chrono::seconds(1), [this]() {
        return firstStreamDataReceived_.load(std::memory_order_acquire);
    });
}

void HpaeRendererStreamImpl::NotifyFirstStreamData()
{
    if (firstStreamDataReceived_.load(std::memory_order_relaxed)) {
        return;
    }
    std::lock_guard<std::mutex> readyLock(firstStreamDataMutex_);
    firstStreamDataReceived_.store(true, std::memory_order_release);
    firstStreamDataCv_.notify_all();
}

int32_t HpaeRendererStreamImpl::GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag)
{
    uint64_t retLatency = 0;
    bool needHardware = (flag & LATENCY_FLAG_HARDWARE) != 0;
    bool needEngine = (flag & LATENCY_FLAG_ENGINE) != 0;
    if (needHardware || needEngine) {
        bool ready = WaitFirstStreamData();
        CHECK_AND_RETURN_RET_LOG(ready, ERR_OPERATION_FAILED,
            "GetLatencyWithFlag wait latency timeout, stream %{public}u", streamIndex_);
    }

    if (needHardware) {
        uint32_t sinkLatency = 0;
        int32_t ret = FetchSinkLatency(sinkLatency);
        CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "FetchSinkLatency failed");
        uint32_t a2dpOffloadLatency = GetA2dpOffloadLatency();
        uint32_t nearlinkLatency = GetNearlinkLatency();
        retLatency = static_cast<uint64_t>(sinkLatency) * AUDIO_US_PER_MS;
        retLatency += static_cast<uint64_t>(a2dpOffloadLatency) * AUDIO_US_PER_MS;
        retLatency += static_cast<uint64_t>(nearlinkLatency) * AUDIO_US_PER_MS;
    }

    if (needEngine) {
        std::shared_lock<std::shared_mutex> lock(latencyMutex_);
        // latencyMutex_ begin
        retLatency += latency_;
        AUDIO_DEBUG_LOG("pipe latency: %{public}" PRIu64, latency_);
        // latencyMutex_ begin
    }

    latency = retLatency;
    return SUCCESS;
}

void HpaeRendererStreamImpl::GetLatencyInner(uint64_t &timestamp, uint64_t &latencyUs, int32_t base)
{
    int32_t baseUsed = base >= 0 && base < Timestamp::Timestampbase::BASESIZE ?
        base : Timestamp::Timestampbase::MONOTONIC;
    uint32_t sinkLatency = GetSinkLatency();
    uint32_t a2dpOffloadLatency = GetA2dpOffloadLatency();
    uint32_t nearlinkLatency = GetNearlinkLatency();
    uint64_t framePosition = 0;

    latencyUs = sinkLatency * AUDIO_US_PER_MS;
    latencyUs += a2dpOffloadLatency * AUDIO_US_PER_MS;
    latencyUs += nearlinkLatency * AUDIO_US_PER_MS;
    std::vector<uint64_t> timestampCurrent = {0};
    ClockTime::GetAllTimeStamp(timestampCurrent);
    timestamp = timestampCurrent[baseUsed];

    {
        // latencyMutex_ begin
        std::shared_lock<std::shared_mutex> lock(latencyMutex_);
        framePosition = framePosition_;
        // latencyMutex_ end
    }

    if (lastPrintTimestamp_.load() + PRINT_TIMESTAMP_INTERVAL_NS < timestampCurrent[0]) {
        AUDIO_INFO_LOG("Latency info: framePosition: %{public}" PRIu64 ", latencyUs %{public}" PRIu64
            ", base %{public}d, timestamp %{public}" PRIi64
            ", sink latency: %{public}u ms, a2dp offload latency: %{public}u ms, nearlink latency: %{public}u ms",
            framePosition, latencyUs, base, timestamp, sinkLatency, a2dpOffloadLatency, nearlinkLatency);
        lastPrintTimestamp_.store(timestampCurrent[0]);
    } else {
        AUDIO_DEBUG_LOG("Latency info: framePosition: %{public}" PRIu64 ", latencyUs %{public}" PRIu64
            ", base %{public}d, timestamp %{public}" PRIu64
            ", sink latency: %{public}u ms, a2dp offload latency: %{public}u ms, nearlink latency: %{public}u ms",
            framePosition, latencyUs, base, timestamp, sinkLatency, a2dpOffloadLatency, nearlinkLatency);
    }
}

int32_t HpaeRendererStreamImpl::SetRate(int32_t rate)
{
    AUDIO_INFO_LOG("SetRate in");
    renderRate_ = rate;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::SetAudioEffectMode(int32_t effectMode)
{
    AUDIO_INFO_LOG("effectMode: %{public}d", effectMode);
    int32_t ret = IHpaeManager::GetHpaeManager().SetAudioEffectMode(processConfig_.originalSessionId, effectMode);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    effectMode_ = effectMode;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetAudioEffectMode(int32_t &effectMode)
{
    effectMode = effectMode_;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::SetPrivacyType(int32_t privacyType)
{
    AUDIO_DEBUG_LOG("privacyType: %{public}d", privacyType);
    privacyType_ = privacyType;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetPrivacyType(int32_t &privacyType)
{
    privacyType = privacyType_;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::SetSpeed(float speed)
{
    AUDIO_INFO_LOG("[%{public}u] Enter", streamIndex_);
    IHpaeManager::GetHpaeManager().SetSpeed(processConfig_.originalSessionId, speed);
    speed_ = speed;
    return SUCCESS;
}

void HpaeRendererStreamImpl::RegisterStatusCallback(const std::weak_ptr<IStatusCallback> &callback)
{
    AUDIO_DEBUG_LOG("RegisterStatusCallback in");
    statusCallback_ = callback;
}

void HpaeRendererStreamImpl::RegisterWriteCallback(const std::weak_ptr<IWriteCallback> &callback)
{
    AUDIO_DEBUG_LOG("RegisterWriteCallback in");
    writeCallback_ = callback;
}

void HpaeRendererStreamImpl::OnDeviceClassChange(const AudioCallBackStreamInfo &callBackStreamInfo)
{
    bool needLog = false;
    // only handle DEVICE_CLASS_REMOTE_OFFLOAD -> other class or other class -> DEVICE_CLASS_REMOTE_OFFLOAD
    if ((deviceClass_ == DEVICE_CLASS_REMOTE_OFFLOAD ||
        callBackStreamInfo.deviceClass == DEVICE_CLASS_REMOTE_OFFLOAD) &&
        deviceClass_ != callBackStreamInfo.deviceClass) {
        uint64_t newFramePosition = callBackStreamInfo.framePosition;

        // from normal to remote offload
        if (callBackStreamInfo.deviceClass == DEVICE_CLASS_REMOTE_OFFLOAD) {
            uint64_t duration = newFramePosition > lastFramePosition_ ? newFramePosition - lastFramePosition_ :
                lastFramePosition_ - newFramePosition;
            lastHdiFramePosition_ = newFramePosition > lastFramePosition_ ? lastHdiFramePosition_ + duration :
                (lastHdiFramePosition_ > duration ? lastHdiFramePosition_ - duration : 0);
        }
        // Device type switch, replace lastFramePosition_
        lastFramePosition_ = callBackStreamInfo.framePosition;
        needLog = true;
    }

    // If hdiFramePosition has a value, it indicates that the remote offload device has performed a flush.
    // The value of hdiFramePosition needs to be accumulated into lastHdiFramePosition_
    if (callBackStreamInfo.hdiFramePosition > 0) {
        lastHdiFramePosition_ +=
            // from time (us) to sample
            callBackStreamInfo.hdiFramePosition * usedSampleRate_ / AUDIO_US_PER_S +
            callBackStreamInfo.rewindTime * usedSampleRate_ / AUDIO_US_PER_S;
        needLog = true;
    }
    if (needLog) {
        bool checkResult = ClockTime::CheckTimeInterval(lastLogTimestampArr_[ON_DEVICE_CLASS_CHANGE],
            PRINT_TIMESTAMP_INTERVAL_NS);
        AUDIO_LIMIT_INFO_LOG(checkResult, "lastFramePosition: %{public}" PRIu64
            ", lastHdiFramePosition: %{public}" PRIu64, lastFramePosition_, lastHdiFramePosition_);
    }
}

void HpaeRendererStreamImpl::ResetSinkLatencyFetcher(const AudioCallBackStreamInfo &callBackStreamInfo)
{
    uint32_t renderId = HdiAdapterManager::GetInstance().GetRenderIdByDeviceClass(
        callBackStreamInfo.deviceClass, callBackStreamInfo.deviceNetId, false);
    auto fetcher = SinkLatencyFetcherManager::GetInstance().EnsureFetcher(renderId);
    CHECK_AND_RETURN_LOG(fetcher, "sinkLatencyFetcher is null, renderId %{public}u", renderId);
    std::lock_guard<std::mutex> lock(sinkLatencyFetcherMutex_);
    sinkLatencyFetcher_ = fetcher;
}

bool HpaeRendererStreamImpl::InitLatencyInfo(const AudioCallBackStreamInfo &callBackStreamInfo)
{
    bool needResetSinkLatencyFetcher = !firstStreamDataReceived_.load(std::memory_order_relaxed);
    {
        std::unique_lock<std::shared_mutex> lock(latencyMutex_);
        OnDeviceClassChange(callBackStreamInfo);
        framePosition_ = callBackStreamInfo.framePosition;
        timestamp_ = callBackStreamInfo.timestamp;
        latency_ = callBackStreamInfo.latency;
        framesWritten_ = callBackStreamInfo.framesWritten;
        needResetSinkLatencyFetcher |=
            (deviceClass_ != callBackStreamInfo.deviceClass || deviceNetId_ != callBackStreamInfo.deviceNetId);
        deviceClass_ = callBackStreamInfo.deviceClass;
        deviceNetId_ = callBackStreamInfo.deviceNetId;
        writePos_ = callBackStreamInfo.writePos_;
    }
    return needResetSinkLatencyFetcher;
}

int32_t HpaeRendererStreamImpl::OnStreamData(AudioCallBackStreamInfo &callBackStreamInfo)
{
    UpdateInnerCapWriteState(callBackStreamInfo.isWriteFirst_);
    bool needResetSinkLatencyFetcher = InitLatencyInfo(callBackStreamInfo);
    if (needResetSinkLatencyFetcher) {
        ResetSinkLatencyFetcher(callBackStreamInfo);
    }
    NotifyFirstStreamData();
    CHECK_AND_RETURN_RET(callBackStreamInfo.needData, SUCCESS);
    CHECK_AND_RETURN_RET_LOG(sendDataEnabled_.load(), ERR_OPERATION_FAILED,
        "Send data disabled, sessionId %{public}u", streamIndex_);
    if (isCallbackMode_) { // callback buffer
        auto requestDataLen = callBackStreamInfo.requestDataLen;
        auto writeCallback = writeCallback_.lock();
        CHECK_AND_RETURN_RET(writeCallback != nullptr, ERROR);
        writeCallback->GetAvailableSize(requestDataLen);
        requestDataLen = std::min(requestDataLen, callBackStreamInfo.requestDataLen);
        size_t mutePaddingSize = 0;
        if (callBackStreamInfo.requestDataLen > requestDataLen) {
            mutePaddingSize = callBackStreamInfo.requestDataLen - requestDataLen;
            int chToFill = (processConfig_.streamInfo.format == SAMPLE_U8) ? 0x7f : 0;
            memset_s(callBackStreamInfo.inputData + requestDataLen,
                mutePaddingSize, chToFill, mutePaddingSize);
            requestDataLen = callBackStreamInfo.forceData && noWaitDataFlag_ ? requestDataLen : 0;
        }
        callBackStreamInfo.requestDataLen = requestDataLen;
        int32_t ret = callBackStreamInfo.isLowLatency ?
            writeCallback->OnWriteDataNoWake(callBackStreamInfo.inputData, requestDataLen) :
            writeCallback->OnWriteData(callBackStreamInfo.inputData, requestDataLen);
        CHECK_AND_RETURN_RET(ret == SUCCESS, ret);
        noWaitDataFlag_ = true;
        size_t mutePaddingFrames = (byteSizePerFrame_ == 0) ? 0 : (mutePaddingSize / byteSizePerFrame_);
        CHECK_AND_RETURN_RET(mutePaddingFrames != 0, SUCCESS);
        mutePaddingFrames_.fetch_add(mutePaddingFrames);
        Trace trace("HpaeRendererStreamImpl::underrun mute frames " + std::to_string(mutePaddingFrames));
        AUDIO_INFO_LOG("Padding mute frames %{public}zu, sessionId %{public}u", mutePaddingFrames, streamIndex_);
    } else { // write buffer
        return WriteDataFromRingBuffer(callBackStreamInfo.forceData,
            callBackStreamInfo.inputData, callBackStreamInfo.requestDataLen);
    }
    return SUCCESS;
}

BufferDesc HpaeRendererStreamImpl::DequeueBuffer(size_t length)
{
    BufferDesc bufferDesc;
    return bufferDesc;
}

int32_t HpaeRendererStreamImpl::EnqueueBuffer(const BufferDesc &bufferDesc)
{
    CHECK_AND_RETURN_RET_LOG(!isCallbackMode_, ERROR, "Not write buffer mode");
    CHECK_AND_RETURN_RET_LOG(ringBuffer_ != nullptr, ERROR, "RingBuffer is nullptr");

    size_t targetSize = bufferDesc.bufLength;
    OptResult result = ringBuffer_->GetWritableSize();
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR,
        "Get writable size failed, ret:%{public}d size:%{public}zu", result.ret, result.size);

    size_t writableSize = result.size;
    if (targetSize > writableSize) {
        AUDIO_ERR_LOG("overflow, targetSize: %{public}zu, writableSize: %{public}zu",
            targetSize, writableSize);
    }

    size_t writeSize = std::min(writableSize, targetSize);
    BufferWrap bufferWrap = {bufferDesc.buffer, writeSize};
    result = ringBuffer_->Enqueue(bufferWrap);
    if (result.ret != OPERATION_SUCCESS) {
        AUDIO_ERR_LOG("failed, ret:%{public}d size:%{public}zu", result.ret, result.size);
        return ERROR;
    }
    DumpFileUtil::WriteDumpFile(dumpEnqueueIn_, bufferDesc.buffer, writeSize);
    return writeSize; // success return written in length
}

int32_t HpaeRendererStreamImpl::GetMinimumBufferSize(size_t &minBufferSize) const
{
    minBufferSize = minBufferSize_;
    return SUCCESS;
}

void HpaeRendererStreamImpl::GetByteSizePerFrame(size_t &byteSizePerFrame) const
{
    byteSizePerFrame = byteSizePerFrame_;
}

void HpaeRendererStreamImpl::GetSpanSizePerFrame(size_t &spanSizeInFrame) const
{
    spanSizeInFrame = spanSizeInFrame_;
}

void HpaeRendererStreamImpl::SetStreamIndex(uint32_t index)
{
    AUDIO_INFO_LOG("Using index/sessionId %{public}u", index);
    streamIndex_ = index;
}

uint32_t HpaeRendererStreamImpl::GetStreamIndex()
{
    return streamIndex_;
}

void HpaeRendererStreamImpl::AbortCallback(int32_t abortTimes)
{
    abortFlag_ += abortTimes;
}

// offload

size_t HpaeRendererStreamImpl::GetWritableSize()
{
    return 0;
}

int32_t HpaeRendererStreamImpl::OffloadSetVolume()
{
    if (!offloadEnable_) {
        return ERR_OPERATION_FAILED;
    }
    struct VolumeValues volumes = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
    std::string deviceClass;
    std::string deviceNetId;
    {
        std::unique_lock<std::shared_mutex> lock(latencyMutex_);
        deviceClass = deviceClass_;
        deviceNetId = deviceNetId_;
    }
    CHECK_AND_RETURN_RET_LOG((deviceClass == DEVICE_CLASS_REMOTE_OFFLOAD || deviceClass == DEVICE_CLASS_OFFLOAD),
        SUCCESS, "not offload sink, skip");
    AudioStreamType streamType = processConfig_.streamType;
    std::string volumeDeviceClass = deviceClass == DEVICE_CLASS_REMOTE_OFFLOAD ? "remote" : "offload";
    uint32_t renderId = HdiAdapterManager::GetInstance().GetRenderIdByDeviceClass(volumeDeviceClass, deviceNetId);
    float volume = AudioVolume::GetInstance()->GetVolume(streamIndex_, streamType, renderId, &volumes);
    AUDIO_INFO_LOG("sessionID %{public}u, renderId %{public}d, volume: %{public}f, durationMs: %{public}u",
        streamIndex_, renderId, volume, volumes.durationMs);
    AudioVolume::GetInstance()->SetHistoryVolume(streamIndex_, volume);
    AudioVolume::GetInstance()->Monitor(streamIndex_, true);
    std::shared_ptr<IAudioRenderSink> audioRendererSinkInstance = GetRenderSinkInstance(deviceClass, deviceNetId);
    if (audioRendererSinkInstance == nullptr) {
        AUDIO_ERR_LOG("Renderer is null.");
        return ERROR;
    }
    int32_t result = SUCCESS;
    if (volumes.durationMs != 0) {
        result = audioRendererSinkInstance->SetVolumeWithRamp(volume, volume, volumes.durationMs);
    } else {
        result = audioRendererSinkInstance->SetVolume(volume, volume);
    }
    return result;
}

int32_t HpaeRendererStreamImpl::SetOffloadDataCallbackState(int32_t state)
{
    AUDIO_INFO_LOG("state: %{public}d", state);
    if (!offloadEnable_) {
        return ERR_OPERATION_FAILED;
    }
    return IHpaeManager::GetHpaeManager().SetOffloadRenderCallbackType(processConfig_.originalSessionId, state);
}

int32_t HpaeRendererStreamImpl::UpdateSpatializationState(bool spatializationEnabled, bool headTrackingEnabled)
{
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::GetOffloadApproximatelyCacheTime(uint64_t &timestamp, uint64_t &paWriteIndex,
    uint64_t &cacheTimeDsp, uint64_t &cacheTimePa)
{
    if (!offloadEnable_) {
        return ERR_OPERATION_FAILED;
    }
    cacheTimePa = 0;
    return GetCurrentPosition(paWriteIndex, timestamp, cacheTimeDsp, Timestamp::Timestampbase::MONOTONIC);
}

void HpaeRendererStreamImpl::SyncOffloadMode()
{
    std::shared_ptr<IStatusCallback> statusCallback = statusCallback_.lock();
    if (statusCallback != nullptr) {
        if (offloadEnable_) {
            statusCallback->OnStatusUpdate(OPERATION_SET_OFFLOAD_ENABLE);
        } else {
            statusCallback->OnStatusUpdate(OPERATION_UNSET_OFFLOAD_ENABLE);
        }
    }
}

int32_t HpaeRendererStreamImpl::SetOffloadMode(int32_t state, bool isAppBack)
{
#ifdef FEATURE_POWER_MANAGER
    static const std::set<PowerMgr::PowerState> screenOffTable = {
        PowerMgr::PowerState::INACTIVE, PowerMgr::PowerState::STAND_BY,
        PowerMgr::PowerState::DOZE, PowerMgr::PowerState::SLEEP,
        PowerMgr::PowerState::HIBERNATE,
    };
    AudioOffloadType statePolicy = OFFLOAD_DEFAULT;
    statePolicy = screenOffTable.count(static_cast<PowerMgr::PowerState>(state)) ?
        OFFLOAD_INACTIVE_BACKGROUND : OFFLOAD_ACTIVE_FOREGROUND;

    AUDIO_INFO_LOG("calling set stream offloadMode PowerState: %{public}d, isAppBack: %{public}d", state, isAppBack);

    if (offloadStatePolicy_.load() == statePolicy && offloadEnable_) {
        return SUCCESS;
    }

    offloadEnable_ = true;
    SyncOffloadMode();
    auto ret = IHpaeManager::GetHpaeManager().SetOffloadPolicy(processConfig_.originalSessionId, statePolicy);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED,
        "SetOffloadPolicy failed, errcode is %{public}d", ret);
    offloadStatePolicy_.store(statePolicy);
    std::shared_ptr<IStatusCallback> statusCallback = statusCallback_.lock();
        if (statusCallback != nullptr) {
            statusCallback->OnStatusUpdate(statePolicy == OFFLOAD_INACTIVE_BACKGROUND ?
                OFFLOAD_INACTIVE_BACKGROUND_RUNNING : OFFLOAD_ACTIVE_FOREGROUND_RUNNING);
        }
#else
    AUDIO_INFO_LOG("not available, FEATURE_POWER_MANAGER no define");
#endif
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::UnsetOffloadMode()
{
    offloadEnable_ = false;
    SyncOffloadMode();
    IHpaeManager::GetHpaeManager().SetOffloadPolicy(processConfig_.originalSessionId, OFFLOAD_DEFAULT);
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::UpdateMaxLength(uint32_t maxLength)
{
    size_t bufferSize = maxLength * spanSizeInFrame_ * byteSizePerFrame_;
    AUDIO_INFO_LOG("bufferSize: %{public}zu, spanSizeInFrame: %{public}zu, byteSizePerFrame: %{public}zu,"
        "maxLength:%{public}u", bufferSize, spanSizeInFrame_, byteSizePerFrame_, maxLength);
    CHECK_AND_RETURN_RET_LOG(ringBuffer_ != nullptr, SUCCESS, "ring buffer is nullptr!");
    size_t ringBufferSize = ringBuffer_->GetCahceSize();
    CHECK_AND_RETURN_RET(ringBufferSize != bufferSize, SUCCESS);
    ringBuffer_->ReConfig(bufferSize, false);
    return SUCCESS;
}

AudioProcessConfig HpaeRendererStreamImpl::GetAudioProcessConfig() const noexcept
{
    return processConfig_;
}

int32_t HpaeRendererStreamImpl::Peek(std::vector<char> *audioBuffer, int32_t &index)
{
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::ReturnIndex(int32_t index)
{
    return SUCCESS;
}

void HpaeRendererStreamImpl::BlockStream() noexcept
{
    return;
}
// offload end

int32_t HpaeRendererStreamImpl::SetClientVolume(float clientVolume)
{
    if (clientVolume < MIN_FLOAT_VOLUME || clientVolume > MAX_FLOAT_VOLUME) {
        AUDIO_ERR_LOG("invalid clientVolume %{public}f", clientVolume);
        return ERR_INVALID_PARAM;
    }
    AUDIO_PRERELEASE_LOGI("clientVolume %{public}f", clientVolume);
    int32_t ret = IHpaeManager::GetHpaeManager().SetClientVolume(processConfig_.originalSessionId, clientVolume);
    std::string tempStringSessionId = std::to_string(processConfig_.originalSessionId);
    IHpaeManager::GetHpaeManager().AddStreamVolumeToEffect(tempStringSessionId, clientVolume);
    if (ret != 0) {
        AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
        return ERR_INVALID_PARAM;
    }
    clientVolume_ = clientVolume;
    return SUCCESS;
}

int32_t HpaeRendererStreamImpl::SetLoudnessGain(float loudnessGain)
{
    AUDIO_INFO_LOG("loudnessGain: %{public}f", loudnessGain);
    int32_t ret = IHpaeManager::GetHpaeManager().SetLoudnessGain(processConfig_.originalSessionId, loudnessGain);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERR_INVALID_PARAM, "ErrorCode: %{public}d", ret);
    return SUCCESS;
}

void HpaeRendererStreamImpl::InitRingBuffer()
{
    static constexpr int32_t DEFAULT_SPAN_SIZE = 2;
    size_t bufferSize = (MAX_CBBUF_IN_USEC * DEFAULT_SPAN_SIZE + MIN_CBBUF_IN_USEC) *
        usedSampleRate_ / AUDIO_US_PER_S * byteSizePerFrame_;
    bufferSize = std::max(bufferSize, spanSizeInFrame_ * byteSizePerFrame_ * static_cast<size_t>(FRAME_LEN_20MS));
    ringBufferCapacityInBytes_ = bufferSize;
    AUDIO_INFO_LOG("bufferSize: %{public}zu, spanSizeInFrame: %{public}zu, byteSizePerFrame: %{public}zu,"
        "reservedCapacity:%{public}zu", bufferSize, spanSizeInFrame_, byteSizePerFrame_, ringBufferCapacityInBytes_);
    // create ring buffer
    ringBuffer_ = AudioRingCache::Create(bufferSize);
    if (ringBuffer_ == nullptr) {
        AUDIO_ERR_LOG("Create ring buffer failed!");
    }

    std::string dumpEnqueueInFileName = std::to_string(processConfig_.originalSessionId) + "_dual_in_" +
        std::to_string(usedSampleRate_) + "_" +
        std::to_string(processConfig_.streamInfo.channels) + "_" +
        std::to_string(processConfig_.streamInfo.format) + ".pcm";
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpEnqueueInFileName, &dumpEnqueueIn_);
}

int32_t HpaeRendererStreamImpl::WriteDataFromRingBuffer(bool forceData, int8_t *inputData, size_t &requestDataLen)
{
    CHECK_AND_RETURN_RET_LOG(inputData != nullptr, ERROR, "inputData is nullptr");
    CHECK_AND_RETURN_RET_LOG(ringBuffer_ != nullptr, ERROR, "RingBuffer is nullptr");
    OptResult result = ringBuffer_->GetReadableSize();
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR,
        "RingBuffer get readable size failed, size is:%{public}zu", result.size);
    if (preBufSizeInBytes_ > 0 && !preBufDone_.load()) {
        if (result.size < preBufSizeInBytes_) {
            AUDIO_INFO_LOG("preBuf not ready, readable:%{public}zu preBuf:%{public}zu, sessionId %{public}u",
                result.size, preBufSizeInBytes_, streamIndex_);
            return ERROR;
        }
        preBufDone_.store(true);
    }
    CHECK_AND_RETURN_RET_LOG(result.size != 0, ERROR,
        "Readable size is invalid, result.size:%{public}zu, requestDataLen:%{public}zu, buffer underflow.",
        result.size, requestDataLen);
    size_t mutePaddingSize = 0;
    if (requestDataLen > result.size) {
        mutePaddingSize = requestDataLen - result.size;
        CHECK_AND_RETURN_RET_LOG(forceData, ERROR, "not enough data");
        int chToFill = (processConfig_.streamInfo.format == SAMPLE_U8) ? 0x7f : 0;
        memset_s(inputData + result.size, mutePaddingSize, chToFill, mutePaddingSize);
    }
    AUDIO_DEBUG_LOG("requestDataLen is:%{public}zu readSize is:%{public}zu", requestDataLen, result.size);
    requestDataLen = std::min(requestDataLen, result.size);
    result = ringBuffer_->Dequeue({reinterpret_cast<uint8_t *>(inputData), requestDataLen});
    CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "RingBuffer dequeue failed");
    size_t mutePaddingFrames = (byteSizePerFrame_ == 0) ? 0 : (mutePaddingSize / byteSizePerFrame_);
    CHECK_AND_RETURN_RET(mutePaddingFrames != 0, SUCCESS);
    mutePaddingFrames_.fetch_add(mutePaddingFrames);
    AUDIO_INFO_LOG("Padding mute frames %{public}zu, sessionId %{public}u", mutePaddingFrames, streamIndex_);
    return SUCCESS;
}

void HpaeRendererStreamImpl::OnStatusUpdate(IOperation operation, uint32_t streamIndex)
{
    if (operation == OPERATION_UPDATE_SPANSIZE) {
        uint32_t spanSizeInFrame = 0;
        int32_t ret = IHpaeManager::GetHpaeManager().GetStreamSpanSize(HPAE_STREAM_CLASS_TYPE_PLAY,
            processConfig_.originalSessionId, spanSizeInFrame);
        CHECK_AND_RETURN_LOG(ret == SUCCESS, "GetStreamSpanSize failed:%{public}d", ret);
        uint32_t routeFlag = 0;
        ret = IHpaeManager::GetHpaeManager().GetStreamRouteFlag(HPAE_STREAM_CLASS_TYPE_PLAY,
            processConfig_.originalSessionId, routeFlag);
        if (ret == SUCCESS) {
            routeFlag_.store(routeFlag);
        }
        AUDIO_INFO_LOG("OnStatusUpdate recv span update, streamIndex:%{public}u sessionId:%{public}u span:%{public}u "
            "routeFlag:%{public}u", streamIndex_, processConfig_.originalSessionId, spanSizeInFrame, routeFlag);
        ret = UpdateSpanSize(spanSizeInFrame);
        CHECK_AND_RETURN_LOG(ret == SUCCESS, "UpdateSpanSize failed:%{public}d", ret);
    }
    auto statusCallback = statusCallback_.lock();
    if (statusCallback) {
        statusCallback->OnStatusUpdate(operation);
    }
}

int32_t HpaeRendererStreamImpl::UpdateSpanSize(uint32_t spanSizeInFrame)
{
    CHECK_AND_RETURN_RET_LOG(spanSizeInFrame != 0, ERR_INVALID_PARAM, "spanSizeInFrame is 0");
    if (spanSizeInFrame_ == spanSizeInFrame) {
        AUDIO_DEBUG_LOG("UpdateSpanSize unchanged, sessionId:%{public}u span:%{public}u",
            processConfig_.originalSessionId, spanSizeInFrame);
        return SUCCESS;
    }
    AUDIO_INFO_LOG("UpdateSpanSize change, sessionId:%{public}u oldSpan:%{public}zu newSpan:%{public}u "
        "oldMinBuf:%{public}zu", processConfig_.originalSessionId, spanSizeInFrame_, spanSizeInFrame, minBufferSize_);
    spanSizeInFrame_ = spanSizeInFrame;
    minBufferSize_ = MIN_BUFFER_SIZE * byteSizePerFrame_ * spanSizeInFrame_;
    if (ringBuffer_ != nullptr) {
        size_t requiredSize = std::max(ringBufferCapacityInBytes_,
            spanSizeInFrame_ * byteSizePerFrame_ * static_cast<size_t>(20));
        if (ringBuffer_->GetCahceSize() != requiredSize) {
            AUDIO_INFO_LOG("UpdateSpanSize reconfig ringBuffer, sessionId:%{public}u old:%{public}zu new:%{public}zu",
                processConfig_.originalSessionId, ringBuffer_->GetCahceSize(), requiredSize);
            ringBuffer_->ReConfig(requiredSize, true);
        }
        ringBufferCapacityInBytes_ = requiredSize;
    }
    return SUCCESS;
}

void HpaeRendererStreamImpl::SetSendDataEnabled(bool enabled)
{
    sendDataEnabled_.store(enabled);
}

bool HpaeRendererStreamImpl::OnQueryUnderrun()
{
    if (isCallbackMode_) { // callback buffer
        auto writeCallback = writeCallback_.lock();
        CHECK_AND_RETURN_RET(writeCallback != nullptr, false);
        size_t requestDataLen = 0;
        writeCallback->GetAvailableSize(requestDataLen);
        return requestDataLen == 0;
    }
    return false;
}

static std::shared_ptr<IAudioRenderSink> GetRenderSinkInstance(std::string deviceClass, std::string deviceNetId)
{
    uint32_t renderId = HDI_INVALID_ID;
    renderId = HdiAdapterManager::GetInstance().GetRenderIdByDeviceClass(deviceClass,
        deviceNetId.empty() ? HDI_ID_INFO_DEFAULT : deviceNetId, false, false);
    return HdiAdapterManager::GetInstance().GetRenderSink(renderId, false);
}

static inline FadeType GetFadeType(uint64_t expectedPlaybackDurationMs)
{
    // duration <= 10 ms no fade
    if (expectedPlaybackDurationMs <= FRAME_LEN_10MS && expectedPlaybackDurationMs > 0) {
        return NONE_FADE;
    }

    // duration > 10ms && duration <= 40ms do 5ms fade
    if (expectedPlaybackDurationMs <= FRAME_LEN_40MS && expectedPlaybackDurationMs > FRAME_LEN_10MS) {
        return SHORT_FADE;
    }

    // 0 is default; duration > 40ms do default fade
    return DEFAULT_FADE;
}

int32_t HpaeRendererStreamImpl::FetchSinkLatency(uint32_t &sinkLatency)
{
    std::function<int32_t (uint32_t &)> fetcher;
    {
        std::lock_guard<std::mutex> lock(sinkLatencyFetcherMutex_);
        fetcher = sinkLatencyFetcher_;
    }
    CHECK_AND_RETURN_RET_LOG(fetcher, ERR_OPERATION_FAILED, "sinkLatencyFetcher is null");
    return fetcher(sinkLatency);
}

uint64_t HpaeRendererStreamImpl::GetOffloadLatency()
{
    float speed = speed_;
    if (deviceClass_ == DEVICE_CLASS_OFFLOAD && processConfig_.streamType != STREAM_MOVIE) {
        speed = 1.0f;
    }
    auto now = std::chrono::high_resolution_clock::now();
    uint64_t time = now > hdiPos_.second ?
        static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(now - hdiPos_.second).count()) : 0;
    uint64_t hdiPos = hdiPos_.first + static_cast<uint64_t>(time * speed);
    uint64_t cacheLenInHdi = writePos_ > hdiPos ? (writePos_ - hdiPos) : 0;
    AUDIO_DEBUG_LOG("offload latency: %{public}" PRIu64 " write pos: %{public}" PRIu64
                    " hdi pos: %{public}" PRIu64 " time: %{public}" PRIu64 " speed: %{public}f",
                    cacheLenInHdi, writePos_, hdiPos, time, speed);
    return cacheLenInHdi / MICROSECOND_PER_MILLISECOND;
}

void HpaeRendererStreamImpl::UpdateInnerCapWriteState(bool isWriteFirst)
{
    if (isWriteFirst_ == isWriteFirst) {
        return;
    }
    isWriteFirst_ = isWriteFirst;
    std::shared_ptr<IStatusCallback> statusCallback = statusCallback_.lock();
    if (statusCallback != nullptr) {
        statusCallback->OnStatusUpdate(isWriteFirst ? OPERATION_OFFLOAD_FLUSH_BEGIN : OPERATION_OFFLOAD_FLUSH_END);
    }
}

void HpaeRendererStreamImpl::OnNotifyHdiData(const std::pair<uint64_t, TimePoint> &hdiPos)
{
    std::unique_lock<std::shared_mutex> lock(latencyMutex_);
    hdiPos_ = hdiPos;
}

void HpaeRendererStreamImpl::TriggerAppsUidUpdate()
{
    AUDIO_INFO_LOG("%{public}u Enter", streamIndex_);
    IHpaeManager::GetHpaeManager().TriggerAppsUidUpdate(HPAE_STREAM_CLASS_TYPE_PLAY, processConfig_.originalSessionId);
}

void HpaeRendererStreamImpl::TriggerClientWake()
{
    auto writeCallback = writeCallback_.lock();
    if (writeCallback) {
        writeCallback->WakeClientFutex();
    }
}

uint32_t HpaeRendererStreamImpl::GetRouteFlag() const noexcept
{
    return routeFlag_.load();
}
} // namespace AudioStandard
} // namespace OHOS
