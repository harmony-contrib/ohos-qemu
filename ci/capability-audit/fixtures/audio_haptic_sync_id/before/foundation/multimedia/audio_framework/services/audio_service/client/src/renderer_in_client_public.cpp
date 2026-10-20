/*
 * Copyright (c) 2024-2025 Huawei Device Co., Ltd.
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
#define LOG_TAG "RendererInClientInnerPublic"
#endif

#include "renderer_in_client.h"
#include "renderer_in_client_private.h"

#include <atomic>
#include <cinttypes>
#include <condition_variable>
#include <sstream>

#include "securec.h"
#include "hisysevent.h"

#include "audio_errors.h"
#include "audio_policy_manager.h"
#include "audio_renderer_log.h"
#include "audio_ring_cache.h"
#include "audio_channel_blend.h"
#include "audio_server_death_recipient.h"
#include "audio_stream_tracker.h"
#include "futex_tool.h"
#include "ipc_stream_listener_impl.h"
#include "ipc_stream_listener_stub.h"
#include "volume_ramp.h"
#include "callback_handler.h"
#include "audio_speed.h"
#include "audio_spatial_channel_converter.h"
#include "audio_spatialization_types.h"
#include "policy_handler.h"
#include "volume_tools.h"
#include "audio_manager_util.h"
#include "audio_effect_map.h"
#include "audio_common_utils.h"
#include "stream_dfx_manager.h"

#include "media_monitor_manager.h"
#include "parameters.h"
#include "app_bundle_manager.h"

using namespace OHOS::HiviewDFX;
using namespace OHOS::AppExecFwk;

namespace OHOS {
namespace AudioStandard {
namespace {
static constexpr int CB_QUEUE_CAPACITY = 3;
constexpr uint32_t TONE_PLAYER_CACHE_SIZE = 4;
const uint64_t AUDIO_FIRST_FRAME_LATENCY = 120; //ms
static const int32_t CREATE_TIMEOUT_IN_SECOND = 9; // 9S
static const int32_t OPERATION_TIMEOUT_IN_MS = 1000; // 1000ms
static const int32_t SHORT_TIMEOUT_IN_MS = 20; // ms
static constexpr uint64_t PRINT_TIMESTAMP_INTERVAL_NS = 1000000000;
static constexpr float MIN_LOUDNESS_GAIN = -90.0;
static constexpr float MAX_LOUDNESS_GAIN = 24.0;
constexpr uint32_t SONIC_LATENCY_IN_MS = 20; // cache in sonic
const std::vector<int32_t> STOP_FLUSH_UIDS = {1013}; // MEDIA_SERVICE_UID
static const int64_t DUCK_UNDUCK_DURATION_MS = 500; // 500ms
static const int64_t MIN_INTERVAL_IN_NS = 150000000;
} // namespace
std::shared_ptr<RendererInClient> RendererInClient::GetInstance(AudioStreamType eStreamType, int32_t appUid)
{
    return std::make_shared<RendererInClientInner>(eStreamType, appUid);
}

RendererInClientInner::RendererInClientInner(AudioStreamType eStreamType, int32_t appUid)
    : eStreamType_(eStreamType), appUid_(appUid), cbBufferQueue_(CB_QUEUE_CAPACITY)
{
    AUDIO_INFO_LOG("Create with StreamType:%{public}d appUid:%{public}d ", eStreamType_, appUid_);
    audioStreamTracker_ = std::make_unique<AudioStreamTracker>(AUDIO_MODE_PLAYBACK, appUid);
    loudVolumeSupportMode_ = OHOS::system::GetIntParameter("const.audio.loudvolume", 0);
    UpdateStreamState(NEW);
}

RendererInClientInner::~RendererInClientInner()
{
    DumpFileUtil::CloseDumpFile(&dumpOutFd_);
    RendererInClientInner::ReleaseAudioStream(true);
    std::lock_guard<std::mutex> runnerlock(runnerMutex_);
    if (!runnerReleased_ && callbackHandler_ != nullptr) {
        AUDIO_INFO_LOG("runner remove");
        callbackHandler_->ReleaseEventRunner();
        runnerReleased_ = true;
        callbackHandler_ = nullptr;
    }
    UnregisterSpatializationStateEventListener(spatializationRegisteredSessionID_);
    
    if (pitchProcessor_ != nullptr) {
        pitchProcessor_->PitchAlgoRelease();
        pitchProcessor_ = nullptr;
    }
    pitchBuffer_ = nullptr;
    
    AUDIO_INFO_LOG("[%{public}s] volume data counts: %{public}" PRId64, logUtilsTag_.c_str(), volumeDataCount_);
}

int32_t RendererInClientInner::OnOperationHandled(Operation operation, int64_t result)
{
    Trace trace(traceTag_ + " OnOperationHandled:" + std::to_string(static_cast<int>(operation)));
    HILOG_COMM_INFO("[OnOperationHandled]sessionId %{public}d recv operation:%{public}d result:%{public}" PRId64".",
        sessionId_, static_cast<int>(operation), result);
    if (operation == SET_OFFLOAD_ENABLE) {
        AUDIO_INFO_LOG("SET_OFFLOAD_ENABLE result:%{public}" PRId64".", result);
        if (!offloadEnable_ && static_cast<bool>(result)) {
            offloadStartReadPos_ = 0;
        }
        offloadEnable_ = static_cast<bool>(result);
        rendererInfo_.pipeType = offloadEnable_ ? PIPE_TYPE_OUT_OFFLOAD : PIPE_TYPE_OUT_NORMAL;
        return SUCCESS;
    }

    if (operation == RESTORE_SESSION) {
        // fix it when restoreAudioStream work right
        return SUCCESS;
    }
    if (operation == UPDATE_SPANSIZE) {
        int32_t ret = InitSharedBuffer();
        CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "InitSharedBuffer for UPDATE_SPANSIZE failed:%{public}d", ret);
        AUDIO_INFO_LOG("UPDATE_SPANSIZE sessionId:%{public}u spanSizeInFrame:%{public}u cacheSizeInFrame:%{public}u",
            sessionId_, spanSizeInFrame_, cacheSizeInFrame_.load());
        NotifyFastStatusChange(static_cast<FastStatus>(result));
        return SUCCESS;
    }

    std::unique_lock<std::mutex> lock(callServerMutex_);
    notifiedOperation_ = operation;
    notifiedResult_ = result;

    if (notifiedResult_ == SUCCESS) {
        HandleStatusChangeOperation(operation);
    } else {
        streamFocusState_ = static_cast<StreamFocusState>(state_.load());
        AUDIO_ERR_LOG("operation %{public}d failed, result: %{public}" PRId64 "", operation, result);
    }

    callServerCV_.notify_all();
    return SUCCESS;
}

void RendererInClientInner::HandleStatusChangeOperation(Operation operation)
{
    switch (operation) {
        case START_STREAM :
            UpdateStreamState(RUNNING);
            break;
        case PAUSE_STREAM :
            UpdateStreamState(PAUSED);
            break;
        case STOP_STREAM :
            UpdateStreamState(STOPPED);
            break;
        default :
            break;
    }
}

void RendererInClientInner::SetClientID(int32_t clientPid, int32_t clientUid, uint32_t appTokenId, uint64_t fullTokenId)
{
    AUDIO_INFO_LOG("PID:%{public}d UID:%{public}d.", clientPid, clientUid);
    clientPid_ = clientPid;
    clientUid_ = clientUid;
    appTokenId_ = appTokenId;
    fullTokenId_ = fullTokenId;
}

void RendererInClientInner::SetClientDeviceId(const std::string &deviceId)
{
    // not support
}

int32_t RendererInClientInner::UpdatePlaybackCaptureConfig(const AudioPlaybackCaptureConfig &config)
{
    AUDIO_ERR_LOG("Unsupported operation!");
    return ERR_NOT_SUPPORTED;
}

void RendererInClientInner::SetPlaybackCaptureStartStateCallback(
    const std::shared_ptr<AudioCapturerOnPlaybackCaptureStartCallback> &callback)
{
    return;
}
 
int32_t RendererInClientInner::RequestUserPrivacyAuthority(uint32_t sessionId)
{
    AUDIO_ERR_LOG("Unsupported operation!");
    return ERR_NOT_SUPPORTED;
}

int32_t RendererInClientInner::SetInMainThreadState(bool isInMainThread)
{
    AUDIO_ERR_LOG("Unsupported operation!");
    return ERR_NOT_SUPPORTED;
}

void RendererInClientInner::SetRendererInfo(const AudioRendererInfo &rendererInfo)
{
    rendererInfo_ = rendererInfo;

    rendererInfo_.sceneType = AudioManagerUtil::GetEffectSceneName(rendererInfo_.streamUsage);

    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();

    if (rendererInfo_.sceneType == audioSupportedSceneTypes.find(SCENE_OTHERS)->second) {
        effectMode_ = EFFECT_NONE;
        rendererInfo_.effectMode = EFFECT_NONE;
    }

    AUDIO_PRERELEASE_LOGI("flag %{public}d, sceneType %{public}s", rendererInfo_.rendererFlags,
        rendererInfo_.sceneType.c_str());
    AudioSpatializationState spatializationState =
        AudioPolicyManager::GetInstance().GetSpatializationState(rendererInfo_.streamUsage);
    rendererInfo_.spatializationEnabled = spatializationState.spatializationEnabled;
    rendererInfo_.headTrackingEnabled = spatializationState.headTrackingEnabled;
    rendererInfo_.encodingType = curStreamParams_.encoding;
    rendererInfo_.channelLayout = curStreamParams_.channelLayout;
    UpdateTracker("UPDATE");
}

void RendererInClientInner::GetRendererInfo(AudioRendererInfo &rendererInfo)
{
    rendererInfo = rendererInfo_;
}

void RendererInClientInner::SetCapturerInfo(const AudioCapturerInfo &capturerInfo)
{
    AUDIO_WARNING_LOG("SetCapturerInfo is not supported");
    return;
}

int32_t RendererInClientInner::SetAudioStreamInfo(const AudioStreamParams info,
    const std::shared_ptr<AudioClientTracker> &proxyObj,
    const AudioPlaybackCaptureConfig &config)
{
    // In plan: If paramsIsSet_ is true, and new info is same as old info, return
    AUDIO_INFO_LOG("AudioStreamInfo, Sampling rate: %{public}u, channels: %{public}d, "
        "format: %{public}d, stream type: %{public}d, encoding type: %{public}d, "
        "remoteLayout: %{public}llx, isRemoteSpatialChannel: %{public}d",
        info.customSampleRate == 0 ? info.samplingRate : info.customSampleRate,
        info.channels, info.format, eStreamType_, info.encoding,
        static_cast<unsigned long long>(info.remoteChannelLayout), info.isRemoteSpatialChannel);

    AudioXCollie guard("RendererInClientInner::SetAudioStreamInfo", CREATE_TIMEOUT_IN_SECOND,
         nullptr, nullptr, AUDIO_XCOLLIE_FLAG_LOG);

    streamParams_ = curStreamParams_ = info; // keep it for later use
    isHWDecodingType_ = IsHWDecodingType(static_cast<AudioEncodingType>(streamParams_.encoding));
    if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
        ConverterConfig cfg = AudioPolicyManager::GetInstance().GetConverterConfig();
        if (info.isRemoteSpatialChannel) {
            cfg.outChannelLayout = info.remoteChannelLayout;
            AUDIO_INFO_LOG("replace cfg outChannelLayout as %{public}llx",
                static_cast<unsigned long long>(cfg.outChannelLayout));
        }
        converter_ = std::make_unique<AudioSpatialChannelConverter>();
        if (converter_ == nullptr || !converter_->Init(curStreamParams_, cfg) || !converter_->AllocateMem()) {
            AUDIO_ERR_LOG("AudioStream: converter construct error");
            return ERR_NOT_SUPPORTED;
        }

        AUDIO_INFO_LOG("rendererInfo rendererFlags: %{public}u", rendererInfo_.rendererFlags);
        if (rendererInfo_.rendererFlags == AUDIO_FLAG_3DA_DIRECT) {
            curStreamParams_.channelLayout = (std::find(cfg.supportOutChannelLayout.begin(),
            cfg.supportOutChannelLayout.end(), cfg.outChannelLayout) != cfg.supportOutChannelLayout.end()) ?\
            cfg.outChannelLayout : CH_LAYOUT_5POINT1POINT2;
        } else {
            converter_->ConverterChannels(curStreamParams_.channels, curStreamParams_.channelLayout);
        }
    }

    CHECK_AND_CALL_FUNC_RETURN_RET(IAudioStream::GetByteSizePerFrame(curStreamParams_, sizePerFrameInByte_) == SUCCESS,
        ERROR_INVALID_PARAM,
        HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrame failed with invalid params"));

    if (state_ != NEW) {
        HILOG_COMM_ERROR("[SetAudioStreamInfo]State is not new, release existing stream and recreate, state %{public}d",
            state_.load());
        int32_t ret = DeinitIpcStream();
        CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS, ret,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]release existing stream failed."));
    }
    paramsIsSet_ = true;
    int32_t initRet = InitIpcStream();
    CHECK_AND_CALL_FUNC_RETURN_RET(initRet == SUCCESS, initRet,
        HILOG_COMM_ERROR("[SetAudioStreamInfo]Init stream failed: %{public}d", initRet));
    UpdateStreamState(PREPARED);

    InitDFXOperaiton();
    InitDirectPipeType();

    proxyObj_ = proxyObj;
    RegisterTracker(proxyObj);
    RegisterSpatializationStateEventListener();
    return SUCCESS;
}

int32_t RendererInClientInner::GetAudioStreamInfo(AudioStreamParams &info)
{
    CHECK_AND_RETURN_RET_LOG(paramsIsSet_ == true, ERR_OPERATION_FAILED, "Params is not set");
    info = streamParams_;
    return SUCCESS;
}

int32_t RendererInClientInner::GetAudioSessionID(uint32_t &sessionID)
{
    CHECK_AND_RETURN_RET_LOG((state_ != RELEASED) && (state_ != NEW), ERR_ILLEGAL_STATE,
        "State error %{public}d", state_.load());
    sessionID = sessionId_;
    return SUCCESS;
}

void RendererInClientInner::GetAudioPipeType(AudioPipeType &pipeType)
{
    pipeType = rendererInfo_.pipeType;
}

State RendererInClientInner::GetState()
{
    std::lock_guard lock(switchingMutex_);
    if (switchingInfo_.isSwitching_) {
        AUDIO_INFO_LOG("switching, return state in switchingInfo");
        return switchingInfo_.state_;
    }
    return state_;
}

bool RendererInClientInner::GetAudioTime(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    CheckAndReportTimestamp();
    CHECK_AND_RETURN_RET_LOG(paramsIsSet_ == true, false, "Params is not set");
    CHECK_AND_RETURN_RET_LOG(state_ != STOPPED, false, "Invalid status:%{public}d", state_.load());
    CHECK_AND_RETURN_RET_LOG(renderTarget_ == NORMAL_PLAYBACK, false, "Now in injection mode.​​");
    uint64_t readPos = 0;
    int64_t handleTime = 0;
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, false, "invalid buffer status");
    clientBuffer_->GetHandleInfo(readPos, handleTime);
    if (readPos == 0 || handleTime == 0) {
        AUDIO_WARNING_LOG("GetHandleInfo may failed");
    }

    timestamp.framePosition = readPos > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(readPos);
    int64_t audioTimeResult = handleTime;

    if (offloadEnable_) {
        uint64_t timestampHdi = 0;
        uint64_t paWriteIndex = 0;
        uint64_t cacheTimeDsp = 0;
        uint64_t cacheTimePa = 0;
        ipcStream_->GetOffloadApproximatelyCacheTime(timestampHdi, paWriteIndex, cacheTimeDsp, cacheTimePa);
        int64_t cacheTime = static_cast<int64_t>(cacheTimeDsp + cacheTimePa) * AUDIO_NS_PER_US;
        int64_t timeNow = static_cast<int64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
        int64_t deltaTimeStamp = (static_cast<int64_t>(timeNow) - static_cast<int64_t>(timestampHdi)) * AUDIO_NS_PER_US;
        uint64_t paWriteIndexNs = paWriteIndex * AUDIO_NS_PER_US;
        uint64_t readPosNs = readPos * AUDIO_MS_PER_SECOND / curStreamParams_.samplingRate * AUDIO_US_PER_S;

        int64_t deltaPaWriteIndexNs = static_cast<int64_t>(readPosNs) - static_cast<int64_t>(paWriteIndexNs);
        int64_t cacheTimeNow = cacheTime - deltaTimeStamp + deltaPaWriteIndexNs;
        if (offloadStartReadPos_ == 0) {
            offloadStartReadPos_ = readPosNs;
            offloadStartHandleTime_ = handleTime;
        }
        int64_t offloadDelta = 0;
        if (offloadStartReadPos_ != 0) {
            offloadDelta = (static_cast<int64_t>(readPosNs) - static_cast<int64_t>(offloadStartReadPos_)) -
                           (handleTime - offloadStartHandleTime_) - cacheTimeNow;
        }
        audioTimeResult += offloadDelta;
    }

    timestamp.time.tv_sec = static_cast<time_t>(audioTimeResult / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(audioTimeResult % AUDIO_NS_PER_SECOND);
    AUDIO_DEBUG_LOG("audioTimeResult: %{public}" PRIi64, audioTimeResult);
    return true;
}

void RendererInClientInner::SetSwitchInfoTimestamp(
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePair,
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePairWithSpeed)
{
    CHECK_AND_RETURN_LOG(!IsFastStream(),
        "SetSwitchInfoTimestamp: switching, not support reset timestamp");
    AUDIO_INFO_LOG("RendererInClientInner::SetSwitchInfoTimestamp");

    lastFramePosAndTimePair_ = lastFramePosAndTimePair;
    lastFramePosAndTimePairWithSpeed_ = lastFramePosAndTimePairWithSpeed;
    for (int32_t base = 0; base < Timestamp::Timestampbase::BASESIZE; base++) {
        lastSwitchPosition_[base] = lastFramePosAndTimePair[base].first;
        lastSwitchPositionWithSpeed_[base] = lastFramePosAndTimePairWithSpeed[base].first;
    }
}

// time base is not used by hdi
bool RendererInClientInner::GetHWDecodingTime(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    uint64_t readIdx = 0;
    uint64_t timestampVal = 0;
    uint64_t latency = 0;
    int32_t ret = ipcStream_->GetAudioPosition(readIdx, timestampVal, latency, base);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, false, "failed to get time:%{public}d", ret);

    timestamp.framePosition = readIdx > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(readIdx);
    timestamp.time.tv_sec = static_cast<time_t>(timestampVal / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(timestampVal % AUDIO_NS_PER_SECOND);
    Trace trace("GetHWDecodingTime::ReadIndex:" + std::to_string(readIdx) + ",time:" + std::to_string(timestampVal));
    return true;
}

bool RendererInClientInner::GetAudioPosition(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    CheckAndReportTimestamp();
    CHECK_AND_RETURN_RET_LOG(state_ == RUNNING, false, "Renderer stream state is not RUNNING");
    CHECK_AND_RETURN_RET_LOG(base >= 0 && base < Timestamp::Timestampbase::BASESIZE,
        ERR_INVALID_PARAM, "Timestampbase is not allowed");
    RETURN_RET_IF(isHWDecodingType_, GetHWDecodingTime(timestamp, base));
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    uint64_t readIdx = 0;
    uint64_t timestampVal = 0;
    uint64_t latency = 0;
    int32_t ret = ipcStream_->GetSpeedPosition(readIdx, timestampVal, latency, base);
    std::vector<uint64_t> timestampCurrent = {0};
    ClockTime::GetAllTimeStamp(timestampCurrent);

    uint64_t framePosition = readIdx > lastSpeedFlushReadIndex_ ? readIdx - lastSpeedFlushReadIndex_ : 0;
    framePosition = framePosition > latency ? framePosition - latency : 0;
    framePosition += dropHdiPosition_.load();
    framePosition += lastSwitchPosition_[base];

    // reset the timestamp
    if (lastFramePosAndTimePair_[base].first < framePosition || lastFramePosAndTimePair_[base].second == 0) {
        lastFramePosAndTimePair_[base] = {framePosition, timestampVal};
    } else {
        AUDIO_DEBUG_LOG("The frame position should be continuously increasing");
        framePosition = lastFramePosAndTimePair_[base].first;
        timestampVal = lastFramePosAndTimePair_[base].second;
    }
    if (lastPrintTimestamp_.load() + PRINT_TIMESTAMP_INTERVAL_NS < timestampCurrent[0]) {
        AUDIO_INFO_LOG("[CLIENT]Latency info: framePosition: %{public}" PRIu64
            ", lastSpeedFlushReadIndex_ %{public}" PRIu64
            ", timestamp %{public}" PRIu64 ", Sinklatency %{public}" PRIu64 ", lastSwitchPosition_ %{public}" PRIu64,
            framePosition, lastSpeedFlushReadIndex_, timestampVal, latency, lastSwitchPosition_[base]);
            lastPrintTimestamp_.store(timestampCurrent[0]);
    } else {
        AUDIO_DEBUG_LOG("[CLIENT]Latency info: framePosition: %{public}" PRIu64
            ", lastSpeedFlushReadIndex_ %{public}" PRIu64
            ", timestamp %{public}" PRIu64 ", Sinklatency %{public}" PRIu64 ", lastSwitchPosition_ %{public}" PRIu64,
            framePosition, lastSpeedFlushReadIndex_, timestampVal, latency, lastSwitchPosition_[base]);
    }

    timestamp.framePosition = framePosition > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(framePosition);
    timestamp.time.tv_sec = static_cast<time_t>(timestampVal / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(timestampVal % AUDIO_NS_PER_SECOND);
    return ret == SUCCESS;
}

int32_t RendererInClientInner::GetBufferSize(size_t &bufferSize)
{
    CHECK_AND_RETURN_RET_LOG(state_ != RELEASED, ERR_ILLEGAL_STATE, "Renderer stream is released");
    bufferSize = clientSpanSizeInByte_;
    if (renderMode_ == RENDER_MODE_CALLBACK) {
        bufferSize = cbBufferSize_;
    }

    if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
        CHECK_AND_RETURN_RET(converter_ != nullptr && converter_->GetInputBufferSize(bufferSize), ERR_OPERATION_FAILED);
    }

    AUDIO_INFO_LOG("Buffer size is %{public}zu, mode is %{public}s", bufferSize, renderMode_ == RENDER_MODE_NORMAL ?
        "RENDER_MODE_NORMAL" : "RENDER_MODE_CALLBACK");
    return SUCCESS;
}

int32_t RendererInClientInner::GetFrameCount(uint32_t &frameCount)
{
    CHECK_AND_RETURN_RET_LOG(state_ != RELEASED, ERR_ILLEGAL_STATE, "Renderer stream is released");
    CHECK_AND_RETURN_RET_LOG(sizePerFrameInByte_ != 0, ERR_ILLEGAL_STATE, "sizePerFrameInByte_ is 0!");
    frameCount = spanSizeInFrame_;
    if (renderMode_ == RENDER_MODE_CALLBACK) {
        frameCount = cbBufferSize_ / sizePerFrameInByte_;
        if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
            frameCount = frameCount * curStreamParams_.channels / streamParams_.channels;
        }
    }
    AUDIO_INFO_LOG("Frame count is %{public}u, mode is %{public}s", frameCount, renderMode_ == RENDER_MODE_NORMAL ?
        "RENDER_MODE_NORMAL" : "RENDER_MODE_CALLBACK");
    return SUCCESS;
}

int32_t RendererInClientInner::GetFastLatency(uint64_t &latency)
{
    latency = 20; // 20ms for debug; Consistent with the historical version (FastAudioStream)
    return SUCCESS;
}

int32_t RendererInClientInner::GetFastLatencyWithFlag(uint64_t &latency, LatencyFlag flag)
{
    latency = 0;
    bool needHardware = (flag & LATENCY_FLAG_HARDWARE) != 0;
    bool needEngine = (flag & LATENCY_FLAG_ENGINE) != 0;
    if (needEngine) {
        latency += 5ULL * AUDIO_US_PER_MS;
    }
    if (needHardware) {
        latency += 20ULL * AUDIO_US_PER_MS;
    }
    return SUCCESS;
}

int32_t RendererInClientInner::GetLatency(uint64_t &latency)
{
    if (IsLowLatencyRenderer()) {
        return GetFastLatency(latency);
    }
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    return ipcStream_->GetLatency(latency);
}

int32_t RendererInClientInner::GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag)
{
    if (IsLowLatencyRenderer()) {
        return GetFastLatencyWithFlag(latency, flag);
    }
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED, "ipcStream is not inited!");
    return ipcStream_->GetLatencyWithFlag(latency, flag);
}

int32_t RendererInClientInner::SetAudioStreamType(AudioStreamType audioStreamType)
{
    AUDIO_ERR_LOG("Change stream type %{public}d to %{public}d is not supported", eStreamType_, audioStreamType);
    return SUCCESS;
}

int32_t RendererInClientInner::SetVolume(float volume)
{
    Trace trace("RendererInClientInner::SetVolume:" + std::to_string(volume));
    AUDIO_INFO_LOG("[%{public}s]sessionId:%{public}d volume:%{public}f", (offloadEnable_ ? "offload" : "normal"),
        sessionId_, volume);
#ifdef MULTI_ALARM_LEVEL
    if (eStreamType_ == STREAM_ANNOUNCEMENT || eStreamType_ == STREAM_EMERGENCY) {
        AUDIO_INFO_LOG("streamType:%{public}d not support to set volume", eStreamType_);
        return SUCCESS;
    }
#endif
    if (volume < 0.0 || volume > 1.0) {
        AUDIO_ERR_LOG("SetVolume with invalid volume %{public}f", volume);
        return ERR_INVALID_PARAM;
    }
    if (volumeRamp_.IsActive()) {
        volumeRamp_.Terminate();
    }
    if (std::abs(volume - 0.0f) <= std::numeric_limits<float>::epsilon()) {
        mutePlaying_ = true;
    } else {
        MonitorMutePlay(true); // if report mute play event, will use mutePlaying_ state inside
        mutePlaying_ = false;
    }
    clientVolume_ = volume;

    return SetInnerVolume(volume);
}

float RendererInClientInner::GetVolume()
{
    Trace trace("RendererInClientInner::GetVolume:" + std::to_string(clientVolume_));
    return clientVolume_;
}

int32_t RendererInClientInner::SetLoudnessGain(float loudnessGain)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERROR, "SetLoudnessGain: only for renderer");
    AUDIO_INFO_LOG("[%{public}s]sessionId:%{public}d loudnessGain:%{public}f", (offloadEnable_ ? "offload" : "normal"),
        sessionId_, loudnessGain);
    CHECK_AND_RETURN_RET_LOG(loudnessGain <= MAX_LOUDNESS_GAIN && loudnessGain >= MIN_LOUDNESS_GAIN, ERR_INVALID_PARAM,
        "SetLoudnessGain with invalid volume %{public}f", loudnessGain);
    loudnessGain_ = loudnessGain;

    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetLoudnessGain(loudnessGain);
    
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "Set loudnessGain failed:%{public}u", ret);
    return SUCCESS;
}

float RendererInClientInner::GetLoudnessGain()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), 0.0, "GetLoudnessGain: only for renderer");
    AUDIO_INFO_LOG("loudnessGain: %{public}f", loudnessGain_);
    return loudnessGain_;
}

int32_t RendererInClientInner::SetDuckVolume(float volume)
{
    Trace trace("RendererInClientInner::SetDuckVolume:" + std::to_string(volume));
    AUDIO_INFO_LOG("sessionId:%{public}d SetDuck:%{public}f", sessionId_, volume);
    if (volume < 0.0 || volume > 1.0) {
        AUDIO_ERR_LOG("SetDuckVolume with invalid volume %{public}f", volume);
        return ERR_INVALID_PARAM;
    }
    duckVolume_ = volume;
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, ERR_OPERATION_FAILED, "buffer is not inited");
    clientBuffer_->SetDuckFactor(volume, DUCK_UNDUCK_DURATION_MS);
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetDuckFactor(volume, DUCK_UNDUCK_DURATION_MS);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("Set Duck failed:%{public}u", ret);
        return ERROR;
    }
    return SUCCESS;
}

float RendererInClientInner::GetDuckVolume()
{
    return duckVolume_;
}

int32_t RendererInClientInner::SetMute(bool mute, StateChangeCmdType cmdType)
{
    Trace trace("RendererInClientInner::SetMute:" + std::to_string(mute));
    AUDIO_INFO_LOG("sessionId:%{public}d SetMute:%{public}d", sessionId_, mute);
    if (mute) {
        mutePlaying_ = true;
    } else {
        MonitorMutePlay(true); // if report mute play event, will use mutePlaying_ state inside
        mutePlaying_ = false;
    }
    muteCmd_ = cmdType;
    muteVolume_ = mute ? 0.0f : 1.0f;
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, ERR_OPERATION_FAILED, "buffer is not inited");
    clientBuffer_->SetMuteFactor(muteVolume_);
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetMute(mute);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("Set Mute failed:%{public}u", ret);
        return ERROR;
    }
    return SUCCESS;
}

int32_t RendererInClientInner::SetBackMute(bool backMute)
{
    backMute_ = backMute;
    return SUCCESS;
}

bool RendererInClientInner::GetMute()
{
    return std::abs(muteVolume_ - 0.0f) <= std::numeric_limits<float>::epsilon();
}

int32_t RendererInClientInner::SetMuteHint(bool mute)
{
    AUDIO_WARNING_LOG("SetMuteHint is only supported for capturer, sessionId:%{public}d mute:%{public}d",
        sessionId_, mute);
    return ERR_NOT_SUPPORTED;
}

int32_t RendererInClientInner::SetRenderRate(AudioRendererRate renderRate)
{
    if (IsFastStream()) {
        CHECK_AND_RETURN_RET(RENDER_RATE_NORMAL != renderRate, SUCCESS);
        return ERR_INVALID_OPERATION;
    }
    if (rendererRate_ == renderRate) {
        AUDIO_INFO_LOG("Set same rate");
        return SUCCESS;
    }
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is not inited!");
    rendererRate_ = renderRate;
    return ipcStream_->SetRate(renderRate);
}

AudioRendererRate RendererInClientInner::GetRenderRate()
{
    AUDIO_INFO_LOG("Get RenderRate %{public}d", rendererRate_);
    return rendererRate_;
}

int32_t RendererInClientInner::SetRenderTarget(RenderTarget renderTarget)
{
    CHECK_AND_RETURN_RET_LOG(renderTarget_ != renderTarget, SUCCESS, "Set same renderTarget");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERROR, "ipcStream is not inited!");
    int32_t ret = ERROR;
    int32_t ipcRet = ipcStream_->SetTarget(renderTarget, INVALID_UID, INVALID_STREAM_ID, ret);
    CHECK_AND_RETURN_RET_LOG(ipcRet == SUCCESS, ret, "ipcStream error: %{public}d", ipcRet);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "Set render target error: %{public}d", ret);
    renderTarget_ = renderTarget;
    return ret;
}

int32_t RendererInClientInner::SetRenderTarget(RenderTarget renderTarget, int32_t targetUid,
    uint32_t targetStreamId)
{
    bool noTargetParams = (targetUid == INVALID_UID && targetStreamId == INVALID_STREAM_ID);
    bool hasTargetParams = (targetUid != INVALID_UID && targetStreamId != INVALID_STREAM_ID);
    CHECK_AND_RETURN_RET_LOG(noTargetParams || hasTargetParams, ERR_INVALID_PARAM,
        "targetUid and targetStreamId must be set together");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERROR, "ipcStream is not inited!");
    int32_t ret = ERROR;
    int32_t ipcRet = ipcStream_->SetTarget(renderTarget, targetUid, targetStreamId, ret);
    CHECK_AND_RETURN_RET_LOG(ipcRet == SUCCESS, ret, "ipcStream error: %{public}d", ipcRet);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "Set render target error: %{public}d", ret);
    renderTarget_ = renderTarget;
    return ret;
}

RenderTarget RendererInClientInner::GetRenderTarget()
{
    AUDIO_INFO_LOG("Get RenderRate %{public}d", renderTarget_);
    return renderTarget_;
}

int32_t RendererInClientInner::SetStreamCallback(const std::shared_ptr<AudioStreamCallback> &callback)
{
    if (callback == nullptr) {
        AUDIO_ERR_LOG("SetStreamCallback failed. callback == nullptr");
        return ERR_INVALID_PARAM;
    }

    std::unique_lock<std::mutex> lock(streamCbMutex_);
    streamCallback_ = callback;
    lock.unlock();

    if (state_ != PREPARED) {
        return SUCCESS;
    }
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, PREPARED);
    return SUCCESS;
}

int32_t RendererInClientInner::SetRendererFirstFrameWritingCallback(
    const std::shared_ptr<AudioRendererFirstFrameWritingCallback> &callback)
{
    AUDIO_INFO_LOG("in");
    CHECK_AND_RETURN_RET_LOG(callback, ERR_INVALID_PARAM, "callback is nullptr");
    std::lock_guard<std::mutex> lock(firstFrameWritingMutex_);
    firstFrameWritingCb_ = callback;
    return SUCCESS;
}

void RendererInClientInner::OnFirstFrameWriting()
{
    Trace trace("RendererInClientInner::OnFirstFrameWriting");
    AUDIO_DEBUG_LOG("In");
    uint64_t latency = AUDIO_FIRST_FRAME_LATENCY;
    if (IsLowLatencyRenderer()) {
        GetFastLatency(latency);
    }

    std::shared_ptr<AudioRendererFirstFrameWritingCallback> cb = nullptr;
    {
        std::lock_guard<std::mutex> lock(firstFrameWritingMutex_);
        CHECK_AND_RETURN(firstFrameWritingCb_!= nullptr);
        cb = firstFrameWritingCb_;
    }
    AUDIO_INFO_LOG("OnFirstFrameWriting: latency %{public}" PRIu64 "", latency);
    cb->OnFirstFrameWriting(latency);
}

bool RendererInClientInner::DoHdiSetSpeed(float speed, bool force)
{
    AUDIO_INFO_LOG("set speed to hdi, sessionId: %{public}d, speed: %{public}f", sessionId_, speed);
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, true, "ipcStream is not inited!");
    CHECK_AND_RETURN_RET_LOG(force || !isEqual(speed, hdiSpeed_), true, "forbid duplicate set speed");
    ipcStream_->SetSpeed(speed);
    hdiSpeed_ = speed;
    return true;
}

void RendererInClientInner::NotifyRouteUpdate(uint32_t routeFlag, const std::string &networkId)
{
    AUDIO_DEBUG_LOG("NotifyRouteUpdate: routeFlag=0x%{public}x networkId=%{public}s",
        routeFlag, networkId.c_str());
    
    // rendererFlags 更新已通过共享内存 pendingRouteFlag 传递
    // CheckAndProcessPendingSpanSize 中处理，延迟通知不唤醒暂停客户端
    
    // offload speed 处理
    std::lock_guard lock(speedMutex_);
    bool isOffload = routeFlag & (AUDIO_OUTPUT_FLAG_COMPRESS_OFFLOAD | AUDIO_OUTPUT_FLAG_LOWPOWER);
    bool curIsHdiSpeed = isOffload && (networkId != LOCAL_NETWORK_ID || (eStreamType_ == STREAM_MOVIE &&
        rendererInfo_.originalFlag == AUDIO_FLAG_PCM_OFFLOAD));
    CHECK_AND_RETURN(curIsHdiSpeed != isHdiSpeed_.load());
    AUDIO_INFO_LOG("need set speed to hdi: %{public}s", curIsHdiSpeed ? "true" : "false");
    isHdiSpeed_.store(curIsHdiSpeed);
    if (curIsHdiSpeed) {
        if (realSpeed_.has_value()) {
            DoHdiSetSpeed(realSpeed_.value(), true);
            SetSpeedInner(1.0);
        }
    } else {
        if (realSpeed_.has_value()) {
            SetSpeedInner(realSpeed_.value());
            DoHdiSetSpeed(1.0, false);
        }
    }
}

int32_t RendererInClientInner::SetSpeed(float speed)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_OPERATION_FAILED,
        "SetSpeed: not supported");
    if (isHWDecodingType_) {
        CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_INVALID_HANDLE, "ipcStream is not inited!");
        std::lock_guard lock(speedMutex_);
        realSpeed_ = speed;
        ipcStream_->SetSpeed(speed);
        return SUCCESS;
    }
    std::lock_guard lock(speedMutex_);
    realSpeed_ = speed;
    if (isHdiSpeed_.load()) {
        DoHdiSetSpeed(speed, false);
        SetSpeedInner(1.0);
    } else {
        SetSpeedInner(speed);
    }
    return SUCCESS;
}

int32_t RendererInClientInner::SetPitch(float pitch)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_OPERATION_FAILED, "SetPitch: not supported");
    RETURN_RET_IF(isHWDecodingType_, SUCCESS);
    if (rendererInfo_.isStatic) {
        CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is not inited!");
        return ipcStream_->SetPitch(pitch);
    }
    
    std::lock_guard lock(pitchMutex_);
    if (pitchProcessor_ == nullptr) {
        AudioStreamInfo streamInfo(
            static_cast<AudioSamplingRate>(curStreamParams_.samplingRate),
            static_cast<AudioEncodingType>(curStreamParams_.encoding),
            static_cast<AudioSampleFormat>(curStreamParams_.format),
            static_cast<AudioChannel>(curStreamParams_.channels),
            static_cast<AudioChannelLayout>(curStreamParams_.channelLayout));
        pitchProcessor_ = AudioPitchProcessor::CreateInstance(streamInfo);
        CHECK_AND_RETURN_RET_LOG(pitchProcessor_ != nullptr, ERR_OPERATION_FAILED,
            "Create pitch processor failed");
        
        int32_t ret = pitchProcessor_->PitchAlgoInit();
        if (ret != SUCCESS) {
            AUDIO_INFO_LOG("PitchAlgoInit failed");
            pitchProcessor_ = nullptr;
            return ERR_OPERATION_FAILED;
        }
        
        GetBufferSize(bufferSize_);
        pitchBuffer_ = std::make_unique<uint8_t[]>(bufferSize_ * MAX_PITCH_BUFFER_FACTOR);
    }
    
    pitchProcessor_->SetPitch(pitch);
    curPitch_ = pitch;
    AUDIO_DEBUG_LOG("SetPitch %{public}f", pitch);
    return SUCCESS;
}

int32_t RendererInClientInner::SetSonicPitch(float pitch)
{
    RETURN_RET_IF(isHWDecodingType_, SUCCESS);
    std::lock_guard lock(speedMutex_);
    if (audioSpeed_ == nullptr) {
        audioSpeed_ = std::make_unique<AudioSpeed>(curStreamParams_.samplingRate, curStreamParams_.format,
            curStreamParams_.channels);
        GetBufferSize(bufferSize_);
        speedBuffer_ = std::make_unique<uint8_t[]>(MAX_SPEED_BUFFER_SIZE);
    }
    audioSpeed_->SetPitch(pitch);
    AUDIO_DEBUG_LOG("SetSonicPitch %{public}f", pitch);
    return SUCCESS;
}

float RendererInClientInner::GetSpeed()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), static_cast<float>(ERROR), "GetSpeed: not supported");
    std::lock_guard lock(speedMutex_);
    return realSpeed_.has_value() ? realSpeed_.value() : 1.0f;
}

int32_t RendererInClientInner::GetAudioDebugInfo(AudioDebugInfo &debugInfo)
{
    AUDIO_DEBUG_LOG("GetAudioDebugInfo enter");
    uint32_t sessionId = UINT32_MAX;
    if (GetAudioSessionID(sessionId) != SUCCESS) {
        AUDIO_WARNING_LOG("GetAudioSessionID failed");
    }
    AUDIO_INFO_LOG("GetAudioDebugInfo sessionId:%{public}u", sessionId);

    auto FillClientOnlyInfo = [&debugInfo, this]() {
        debugInfo.speed = GetSpeed();
        debugInfo.pitch = 1.0f; // Audio pitch debug is not implemented currently, keep default value.
        debugInfo.effectMode = GetAudioEffectMode();
    };

    if (sessionId != UINT32_MAX) {
        int32_t ret = AudioPolicyManager::GetInstance().GetAudioDebugInfo(sessionId, debugInfo);
        if (ret != SUCCESS) {
            AUDIO_WARNING_LOG("GetAudioDebugInfo failed, sessionId:%{public}u, ret:%{public}d", sessionId, ret);
        }
    }

    debugInfo.sessionId = sessionId;
    GetAudioStreamInfo(debugInfo.streamParams);
    GetRendererInfo(debugInfo.rendererInfo);

    FillClientOnlyInfo();
    StreamDfxManager::GetErrorInfosFromMedia(debugInfo.errorInfos);
    return SUCCESS;
}

void RendererInClientInner::InitCallbackLoop()
{
    cbThreadReleased_ = false;
    auto weakRef = weak_from_this();
    ResetCallbackLoopTid();
    // OS_AudioWriteCB
    std::unique_lock<std::mutex> statusLock(loopMutex_);
    callbackLoop_ = std::thread([weakRef] {
        bool keepRunning = true;
        std::shared_ptr<RendererInClientInner> strongRef = weakRef.lock();

        if (strongRef != nullptr) {
            strongRef->SetCallbackLoopTid(gettid());
            
            if (strongRef->IsFastStream()) {
                strongRef->SetupFastStreamThreadPriority();
            }
            
            strongRef->cbThreadCv_.notify_one();
            AUDIO_INFO_LOG("WriteCallbackFunc start, sessionID :%{public}d, IsFastStream:%{public}d, "
                "IsUltraFastStream:%{public}d", strongRef->sessionId_, strongRef->IsFastStream(),
                strongRef->IsUltraFastStream());
        } else {
            HILOG_COMM_WARN("[InitCallbackLoop]Strong ref is nullptr, could cause error");
        }
        strongRef = nullptr;
        // start loop
        while (keepRunning) {
            strongRef = weakRef.lock();
            if (strongRef == nullptr) {
                HILOG_COMM_INFO("[InitCallbackLoop]RendererInClientInner destroyed");
                break;
            }
            keepRunning = strongRef->WriteCallbackFunc(); // Main operation in callback loop
        }
        if (strongRef != nullptr) {
            AUDIO_INFO_LOG("CBThread end sessionID :%{public}d", strongRef->sessionId_);
        }
    });
    pthread_setname_np(callbackLoop_.native_handle(), "OS_AudioWriteCB");
}

void RendererInClientInner::SetupFastStreamThreadPriority()
{
    ThreadPriorityConfig threadPriority = THREAD_PRIORITY_QOS_7;

    if (IsUltraFastStream()) {
        BindBigAndMidCore();
        threadPriority = THREAD_PRIORITY_4;
    }

    if (ipcStream_ != nullptr) {
        ipcStream_->RegisterThreadPriority(gettid(),
            AppBundleManager::GetSelfBundleName(appUid_),
            METHOD_WRITE_OR_READ, threadPriority);
    }

    AUDIO_INFO_LOG("SetupFastStreamThreadPriority: IsUltraFastStream=%{public}d, priority=%{public}d",
        IsUltraFastStream(), threadPriority);
}

int32_t RendererInClientInner::SetRenderMode(AudioRenderMode renderMode)
{
    AUDIO_INFO_LOG("to %{public}d", renderMode);
    if (renderMode_ == renderMode) {
        return SUCCESS;
    }

    // renderMode_ is inited as RENDER_MODE_NORMAL, can only be set to RENDER_MODE_CALLBACK or RENDER_MODE_STATIC.
    if (renderMode_ == RENDER_MODE_CALLBACK && renderMode == RENDER_MODE_NORMAL) {
        AUDIO_ERR_LOG("SetRenderMode from callback to normal is not supported.");
        return ERR_INCORRECT_MODE;
    }

    // state check
    if (state_ != PREPARED && state_ != NEW) {
        AUDIO_ERR_LOG("SetRenderMode failed. invalid state:%{public}d", state_.load());
        return ERR_ILLEGAL_STATE;
    }
    renderMode_ = renderMode;

    // init callbackLoop_
    InitCallbackLoop();

    std::unique_lock<std::mutex> threadStartlock(statusMutex_);
    bool stopWaiting = cbThreadCv_.wait_for(threadStartlock, std::chrono::milliseconds(SHORT_TIMEOUT_IN_MS), [this] {
        return cbThreadReleased_ == false; // When thread is started, cbThreadReleased_ will be false. So stop waiting.
    });
    if (!stopWaiting) {
        AUDIO_WARNING_LOG("Init OS_AudioWriteCB thread time out");
    }

    InitCallbackBuffer(GetDefaultCallbackBufferDurationInUs());
    return SUCCESS;
}

AudioRenderMode RendererInClientInner::GetRenderMode()
{
    AUDIO_INFO_LOG("Render mode is %{public}s", renderMode_ == RENDER_MODE_NORMAL ? "RENDER_MODE_NORMAL" :
        "RENDER_MODE_CALLBACK");
    return renderMode_;
}

int32_t RendererInClientInner::SetRendererWriteCallback(const std::shared_ptr<AudioRendererWriteCallback> &callback)
{
    CHECK_AND_RETURN_RET_LOG(callback != nullptr, ERR_INVALID_PARAM, "Invalid null callback");
    CHECK_AND_RETURN_RET_LOG(renderMode_ == RENDER_MODE_CALLBACK, ERR_INCORRECT_MODE, "incorrect render mode");
    std::lock_guard<std::mutex> lock(writeCbMutex_);
    writeCb_ = callback;
    return SUCCESS;
}

int32_t RendererInClientInner::SetCaptureMode(AudioCaptureMode captureMode)
{
    AUDIO_ERR_LOG("SetCaptureMode is not supported");
    return ERROR;
}

AudioCaptureMode RendererInClientInner::GetCaptureMode()
{
    AUDIO_ERR_LOG("GetCaptureMode is not supported");
    return CAPTURE_MODE_NORMAL; // not supported
}

int32_t RendererInClientInner::SetCapturerReadCallback(const std::shared_ptr<AudioCapturerReadCallback> &callback)
{
    AUDIO_ERR_LOG("SetCapturerReadCallback is not supported");
    return ERROR;
}

int32_t RendererInClientInner::SetCapturerMetaDataCallback(
    const std::shared_ptr<AudioCapturerMetaDataCallback> &callback)
{
    AUDIO_ERR_LOG("SetCapturerMetaDataCallback is not supported");
    return ERROR;
}

int32_t RendererInClientInner::GetRawBuffer(BufferDesc &bufDesc)
{
    Trace trace("RendererInClientInner::GetRawBuffer");
    if (clientBuffer_ == nullptr) {
        AUDIO_ERR_LOG("buffer is not inited");
        return ERR_OPERATION_FAILED;
    }
    size_t bufferSize = clientBuffer_->GetDataSize();
    int32_t ret = clientBuffer_->GetRawBuffer(bufferSize, bufDesc);
    return ret;
}

int32_t RendererInClientInner::GetBufferDesc(BufferDesc &bufDesc)
{
    Trace trace("RendererInClientInner::GetBufferDesc");
    if (renderMode_ != RENDER_MODE_CALLBACK) {
        AUDIO_ERR_LOG("GetBufferDesc is not supported. Render mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    if (isHWDecodingType_) {
        return GetRawBuffer(bufDesc);
    }
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    if (IsLowLatencyRenderer()) {
        memset_s(cbBuffer_.get(), cbBufferSize_, 0, cbBufferSize_);
    }
    bufDesc.buffer = cbBuffer_.get();
    bufDesc.bufLength = cbBufferSize_;
    bufDesc.dataLength = cbBufferSize_;
    if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
        CHECK_AND_RETURN_RET_LOG(converter_ != nullptr, ERR_INVALID_OPERATION, "converter is not inited");
        bufDesc.metaBuffer = bufDesc.buffer + cbBufferSize_;
        bufDesc.metaLength = converter_->GetMetaSize();
    }
    return SUCCESS;
}

int32_t RendererInClientInner::GetBufQueueState(BufferQueueState &bufState)
{
    Trace trace("RendererInClientInner::GetBufQueueState");
    if (renderMode_ != RENDER_MODE_CALLBACK) {
        AUDIO_ERR_LOG("GetBufQueueState is not supported. Render mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    // only one buffer in queue.
    bufState.numBuffers = 1;
    bufState.currentIndex = 0;
    return SUCCESS;
}

bool RendererInClientInner::CheckBufferValid(const BufferDesc &bufDesc)
{
    if (bufDesc.bufLength > cbBufferSize_) {
        return false;
    }

    if (bufDesc.dataLength > cbBufferSize_) {
        return false;
    }

    return true;
}

int32_t RendererInClientInner::Enqueue(const BufferDesc &bufDesc)
{
    Trace trace("RendererInClientInner::Enqueue " + std::to_string(bufDesc.bufLength));
    if (renderMode_ != RENDER_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Enqueue is not supported. Render mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    CHECK_AND_RETURN_RET_LOG(bufDesc.buffer != nullptr && bufDesc.bufLength != 0, ERR_INVALID_PARAM, "Invalid buffer");
    CHECK_AND_RETURN_RET_LOG(curStreamParams_.encoding != ENCODING_AUDIOVIVID ||
            converter_ != nullptr && converter_->CheckInputValid(bufDesc),
        ERR_INVALID_PARAM, "Invalid buffer desc");

    BufferDesc temp = bufDesc;

    if (state_ == RELEASED) {
        AUDIO_WARNING_LOG("Invalid state: %{public}d", state_.load());
        return ERR_ILLEGAL_STATE;
    }
    // Call write here may block, so put it in loop callbackLoop_
    cbBufferQueue_.Push(temp);
    return SUCCESS;
}

int32_t RendererInClientInner::Clear()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), SUCCESS, "Clear: not supported");
    Trace trace("RendererInClientInner::Clear");
    if (renderMode_ != RENDER_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Clear is not supported. Render mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    std::unique_lock<std::mutex> lock(cbBufferMutex_);
    int32_t ret = memset_s(cbBuffer_.get(), cbBufferSize_, 0, cbBufferSize_);
    CHECK_AND_RETURN_RET_LOG(ret == EOK, ERR_OPERATION_FAILED, "Clear buffer fail, ret %{public}d.", ret);
    lock.unlock();
    FlushAudioStream();
    return SUCCESS;
}

int32_t RendererInClientInner::SetLowPowerVolume(float volume)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), SUCCESS, "SetLowPowerVolume: in.");
    AUDIO_INFO_LOG("Volume number: %{public}f", volume);
    if (volume < 0.0 || volume > 1.0) {
        AUDIO_ERR_LOG("Invalid param: %{public}f", volume);
        return ERR_INVALID_PARAM;
    }
    lowPowerVolume_ = volume;

    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is null!");
    return ipcStream_->SetLowPowerVolume(lowPowerVolume_);
}

float RendererInClientInner::GetLowPowerVolume()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), 1.0f, "GetLowPowerVolume: in.");
    return lowPowerVolume_;
}

int32_t RendererInClientInner::SetOffloadMode(int32_t state, bool isAppBack)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_NOT_SUPPORTED, "SetOffloadMode: in.");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is null!");
    return ipcStream_->SetOffloadMode(state, isAppBack);
}

int32_t RendererInClientInner::UnsetOffloadMode()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_NOT_SUPPORTED, "UnsetOffloadMode: in.");
    rendererInfo_.pipeType = PIPE_TYPE_OUT_NORMAL;
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is null!");
    return ipcStream_->UnsetOffloadMode();
}

float RendererInClientInner::GetSingleStreamVolume()
{
    // in plan. For now, keep it consistent with fast_audio_stream
    return 1.0f;
}

AudioEffectMode RendererInClientInner::GetAudioEffectMode()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), EFFECT_NONE, "GetAudioEffectMode: not supported");
    AUDIO_DEBUG_LOG("Current audio effect mode is %{public}d", effectMode_);
    return effectMode_;
}

int32_t RendererInClientInner::SetAudioEffectMode(AudioEffectMode effectMode)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_NOT_SUPPORTED, "SetAudioEffectMode: not supported");
    if (effectMode_ == effectMode) {
        AUDIO_INFO_LOG("Set same effect mode");
        return SUCCESS;
    }

    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetAudioEffectMode(effectMode);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ERR_OPERATION_FAILED, "Set audio effect mode failed");
    effectMode_ = effectMode;
    return SUCCESS;
}

int64_t RendererInClientInner::GetFramesWritten()
{
    return totalBytesWritten_ / static_cast<int64_t>(sizePerFrameInByte_);
}

int64_t RendererInClientInner::GetFramesRead()
{
    AUDIO_ERR_LOG("not supported");
    return -1;
}

void RendererInClientInner::SetInnerCapturerState(bool isInnerCapturer)
{
    AUDIO_ERR_LOG("SetInnerCapturerState is not supported");
    return;
}

void RendererInClientInner::SetWakeupCapturerState(bool isWakeupCapturer)
{
    AUDIO_ERR_LOG("SetWakeupCapturerState is not supported");
    return;
}

void RendererInClientInner::SetCapturerSource(int capturerSource)
{
    AUDIO_ERR_LOG("SetCapturerSource is not supported");
    return;
}

void RendererInClientInner::SetPrivacyType(AudioPrivacyType privacyType)
{
    CHECK_AND_RETURN_LOG(!IsFastStream(), "SetPrivacyType: not supported");
    if (privacyType_ == privacyType) {
        AUDIO_INFO_LOG("same type");
        return;
    }
    privacyType_ = privacyType;
    CHECK_AND_RETURN_LOG(ipcStream_ != nullptr, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetPrivacyType(privacyType);
    CHECK_AND_RETURN_LOG(ret == SUCCESS, "Set privacy type failed");
}

int32_t RendererInClientInner::ResetNotifyStreamSilentChangeFlag()
{
    needNotifyStreamSilentChange_.store(true);
    volumeDataCount_ = 0;
    return SUCCESS;
}

bool RendererInClientInner::StartAudioStream(StateChangeCmdType cmdType,
    AudioStreamDeviceChangeReasonExt reason)
{
    CheckAndProcessPendingSpanSize();
    mutePlayStartTime_ = 0;
    Trace trace("RendererInClientInner::StartAudioStream " + std::to_string(sessionId_));
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ == PREPARED || state_ == STOPPED || state_ == PAUSED, false,
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_), PLAY_START_ILLEGAL_STATE,
            "Illegal state", true, state_), "Start failed");
    ResetNotifyStreamSilentChangeFlag();
    hasFirstFrameWrited_ = false;
    CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(ipcStream_ != nullptr, false,
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_START_NULL_POINTER, "ipcStream is not inited", true, state_),
        HILOG_COMM_ERROR("[StartAudioStream]ipcStream is not inited!"));
    int32_t ret = ipcStream_->Start(writeCb_ == nullptr);
    CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(ret == SUCCESS, false,
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_START_OPERATION_FAILED, "Start call server failed", true, state_),
        HILOG_COMM_ERROR("[StartAudioStream]Start call server failed:%{public}u", ret));
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return state_ == RUNNING; // will be false when got notified.
    });
    if (!stopWaiting) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_START_TIMEOUT, "Start timeout", true, state_);
        AUDIO_ERR_LOG("Start failed: timeout");
        ipcStream_->Stop();
        return false;
    }
    waitLock.unlock();
    if (loudVolumeSupportMode_ != LOUD_VOLUME_NOT_SUPPORT) {
        AudioPolicyManager::GetInstance().ReloadLoudVolumeMode(eStreamType_, LOUD_VOLUME_SWITCH_AUTO);
    }

    HILOG_COMM_INFO("[StartAudioStream]Start SUCCESS, sessionId: %{public}d, uid: %{public}d",
        sessionId_, clientUid_);
    UpdateTracker("RUNNING");
    FlushBeforeStart();
    offloadStartReadPos_ = 0;

    NotifyStopWaiting();

    RegisterThreadPriorityOnStart(cmdType);

    statusLock.unlock();
    // in plan: call HiSysEventWrite
    int64_t param = -1;
    StateCmdTypeToParams(param, state_, cmdType);
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, param);
    preWriteEndTime_ = 0;
    return true;
}

void RendererInClientInner::FlushBeforeStart()
{
    if (flushAfterStop_) {
        ResetFramePosition();
        AUDIO_INFO_LOG("flush before start");
        flushAfterStop_ = false;
    }
}

bool RendererInClientInner::PauseAudioStream(StateChangeCmdType cmdType)
{
    Trace trace("RendererInClientInner::PauseAudioStream " + std::to_string(sessionId_));
    MonitorMutePlay(true);
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ != RUNNING) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_PAUSE_ILLEGAL_STATE, "Illegal state", true, state_);
        AUDIO_ERR_LOG("State is not RUNNING. Illegal state:%{public}u", state_.load());
        return false;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_PAUSE_NULL_POINTER, "ipcStream is not inited", true, state_),
        "ipcStream is not inited!");
    int32_t ret = ipcStream_->Pause();
    if (ret != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_PAUSE_OPERATION_FAILED, "Pause call server failed", true, state_);
        AUDIO_ERR_LOG("call server failed:%{public}u", ret);
        return false;
    }
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return state_ == PAUSED; // will be false when got notified.
    });
    if (!stopWaiting) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_PAUSE_TIMEOUT, "Pause timeout", true, state_);
        AUDIO_ERR_LOG("Pause failed: timeout");
        return false;
    }

    waitLock.unlock();

    FutexTool::FutexWake(clientBuffer_->GetFutex());
    statusLock.unlock();

    // in plan: call HiSysEventWrite
    int64_t param = -1;
    StateCmdTypeToParams(param, state_, cmdType);
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, param);

    HILOG_COMM_INFO("[PauseAudioStream]Pause SUCCESS, sessionId %{public}d, uid %{public}d, mode %{public}s",
        sessionId_, clientUid_, renderMode_ == RENDER_MODE_NORMAL ? "RENDER_MODE_NORMAL" : "RENDER_MODE_CALLBACK");
    UpdateTracker("PAUSED");
    return true;
}

void RendererInClientInner::ReportExceptionForInterval()
{
    std::string appName = AppBundleManager::GetSelfBundleName();
    std::shared_ptr<Media::MediaMonitor::EventBean> bean = std::make_shared<Media::MediaMonitor::EventBean>(
        Media::MediaMonitor::AUDIO, Media::MediaMonitor::AUDIO_PLAYBACK_ERROR,
        Media::MediaMonitor::FAULT_EVENT);
    bean->Add("APP_NAME", appName);
    bean->Add("STREAM_TYPE", eStreamType_);
    bean->Add("TYPE", TYPE_GET_TIMESTAMP_TOO_FREQUENTLY);
    AUDIO_ERR_LOG("ReportExceptionForInterval: APP_NAME:%{public}s, STREAM_TYPE:%{public}d, TYPE:%{public}d",
        appName.c_str(), eStreamType_, TYPE_GET_TIMESTAMP_TOO_FREQUENTLY);
    Media::MediaMonitor::MediaMonitorManager::GetInstance().WriteLogMsg(bean);
}

void RendererInClientInner::HandleStopSuccess()
{
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, state_);
    HILOG_COMM_INFO("[StopAudioStream]Stop SUCCESS, sessionId: %{public}d, uid: %{public}d, "
        "volume data counts: %{public}" PRId64, sessionId_, clientUid_, volumeDataCount_);
    UpdateTracker("STOPPED");
    if (logStopCallCount_) {
        ReportExceptionForInterval();
        logStopCallCount_ = false;
    }
}

bool RendererInClientInner::StopAudioStream()
{
    Trace trace("RendererInClientInner::StopAudioStream " + std::to_string(sessionId_));
    MonitorMutePlay(true);
    AUDIO_INFO_LOG("Stop begin for sessionId %{public}d uid: %{public}d", sessionId_, clientUid_);
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    std::unique_lock<std::mutex> lock(writeMutex_, std::defer_lock);
    if (!offloadEnable_ && !rendererInfo_.isStatic) {
        lock.lock();
        DrainAudioStreamInner(true);
    }

    if (state_ == STOPPED) {
        AUDIO_INFO_LOG("Renderer in client is already stopped");
        streamFocusState_ = static_cast<StreamFocusState>(STOPPED);
        return true;
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ == RUNNING || state_ == PAUSED, false,
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(clientUid_),
            PLAY_STOP_ILLEGAL_STATE, "Illegal state", true, state_),
        "Stop failed. Illegal state:%{public}u", state_.load());

    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    UpdateStopState();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_STOP_NULL_POINTER, "ipcStream is not inited", true),
        "ipcStream is not inited!");
    int32_t ret = ipcStream_->Stop();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_STOP_OPERATION_FAILED, "Stop call server failed", true),
        "Stop call server failed:%{public}u", ret);
    
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return state_ == STOPPED; // will be false when got notified.
    });
    if (!stopWaiting) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_STOP_TIMEOUT, "Stop timeout", true);
        AUDIO_ERR_LOG("Stop failed: timeout");
        UpdateStreamState(INVALID);
        return false;
    }

    waitLock.unlock();
    FutexTool::FutexWake(clientBuffer_->GetFutex());
    statusLock.unlock();
    HandleStopSuccess();
    return true;
}

void RendererInClientInner::JoinCallbackLoop()
{
    std::unique_lock<std::mutex> statusLock(loopMutex_);
    CHECK_AND_RETURN(renderMode_ == RENDER_MODE_CALLBACK || renderMode_ == RENDER_MODE_STATIC);
    cbThreadReleased_ = true; // stop loop
    cbThreadCv_.notify_all();
    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "clientBuffer_ is nullptr!");
    FutexTool::FutexWake(clientBuffer_->GetFutex(), IS_PRE_EXIT);
    if (callbackLoop_.joinable()) {
        callbackLoop_.join();
    }
}

bool RendererInClientInner::ReleaseAudioStream(bool releaseRunner, bool isSwitchStream)
{
    (void)isSwitchStream;
    AUDIO_PRERELEASE_LOGI("Enter");
    MonitorMutePlay(true);
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ == RELEASED) {
        AUDIO_WARNING_LOG("Already released");
        return true;
    }
    UpdateStreamState(RELEASED);
    statusLock.unlock();

    Trace trace("RendererInClientInner::ReleaseAudioStream " + std::to_string(sessionId_));
    if (ipcStream_ != nullptr) {
        ipcStream_->Release(isSwitchStream);
    } else {
        AUDIO_WARNING_LOG("release while ipcStream is null");
    }

    // no lock, call release in any case, include blocked case.
    std::unique_lock<std::mutex> runnerlock(runnerMutex_);
    if (releaseRunner && callbackHandler_ != nullptr) {
        callbackHandler_->ReleaseEventRunner();
        runnerReleased_ = true;
        callbackHandler_ = nullptr;
    }
    runnerlock.unlock();

    //clear write callback
    JoinCallbackLoop();
    paramsIsSet_ = false;

    std::unique_lock<std::mutex> lock(streamCbMutex_);
    std::shared_ptr<AudioStreamCallback> streamCb = streamCallback_.lock();
    if (streamCb != nullptr) {
        AUDIO_INFO_LOG("Notify client");
        streamCb->OnStateChange(RELEASED, CMD_FROM_CLIENT);
    }
    lock.unlock();

    UpdateTracker("RELEASED");
    HILOG_COMM_INFO("[ReleaseAudioStream]Release end, sessionId: %{public}d, uid: %{public}d, "
        "volume data counts: %{public}" PRId64, sessionId_, clientUid_, volumeDataCount_);

    std::lock_guard lockSpeed(speedMutex_);
    audioSpeed_.reset();
    audioSpeed_ = nullptr;
    return true;
}

void RendererInClientInner::ClearCbBufferQueue()
{
    if (renderMode_ == RENDER_MODE_CALLBACK) {
        cbBufferQueue_.Clear();
        int chToFill = (clientConfig_.streamInfo.format == SAMPLE_U8) ? 0x7f : 0;
        if (memset_s(cbBuffer_.get(), cbBufferSize_, chToFill, cbBufferSize_) != EOK) {
            AUDIO_ERR_LOG("memset_s buffer failed");
        }
    }
}

bool RendererInClientInner::FlushAudioStream()
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), true, "FlushAudioStream: in");
    Trace trace("RendererInClientInner::FlushAudioStream " + std::to_string(sessionId_));
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    std::lock_guard<std::mutex>lock(writeMutex_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ == RUNNING || state_ == PAUSED || state_ == STOPPED, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_FLUSH_ILLEGAL_STATE, "Illegal state", true),
        "Flush failed. Illegal state:%{public}u", state_.load());

    ClearCbBufferQueue();
    FlushSpeedBuffer();

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_FLUSH_NULL_POINTER, "ipcStream is not inited", true),
        "ipcStream is not inited!");
    int32_t ret = ipcStream_->Flush();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_FLUSH_OPERATION_FAILED, "Flush call server failed", true),
        "Flush call server failed:%{public}u", ret);

    if (converter_) {
        ret = converter_->Flush();
        if (ret != SUCCESS) {
            AUDIO_ERR_LOG("Flush mcr buffer failed.");
        }
    }
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return notifiedOperation_ == FLUSH_STREAM;
    });

    if (notifiedOperation_ != FLUSH_STREAM || notifiedResult_ != SUCCESS) {
        AUDIO_ERR_LOG("Flush failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        notifiedOperation_ = MAX_OPERATION_CODE;
        return false;
    }
    notifiedOperation_ = MAX_OPERATION_CODE;
    waitLock.unlock();
    ResetFramePosition();

    if (NeedStopFlush() && state_ == STOPPED) {
        flushAfterStop_ = true;
    }
    
    AUDIO_INFO_LOG("Flush stream SUCCESS, sessionId: %{public}d", sessionId_);
    return true;
}

bool RendererInClientInner::DrainAudioStream(bool stopFlag)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), true, "RendererInClientInner::DrainAudioStream SUCCESS");
    std::lock_guard<std::mutex> statusLock(statusMutex_);
    std::lock_guard<std::mutex> lock(writeMutex_);
    bool ret = DrainAudioStreamInner(stopFlag);
    return ret;
}

int32_t RendererInClientInner::Write(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer,
    size_t metaBufferSize)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_INVALID_OPERATION, "Write with meta: not supported");
    CHECK_AND_RETURN_RET_LOG(renderMode_ != RENDER_MODE_CALLBACK, ERR_INCORRECT_MODE,
        "Write with callback is not supported");
    int32_t ret = WriteInner(pcmBuffer, pcmBufferSize, metaBuffer, metaBufferSize);
    return ret <= 0 ? ret : static_cast<int32_t>(pcmBufferSize);
}

int32_t RendererInClientInner::Write(uint8_t *buffer, size_t bufferSize)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_INVALID_OPERATION, "Write: not supported");
    CHECK_AND_RETURN_RET_LOG(renderMode_ != RENDER_MODE_CALLBACK, ERR_INCORRECT_MODE,
        "Write with callback is not supported");
    return WriteInner(buffer, bufferSize);
}

void RendererInClientInner::SetPreferredFrameSize(int32_t frameSize, bool isRecreate)
{
    CHECK_AND_RETURN_LOG(isHWDecodingType_ == false, "not support HWDecoding");
    std::lock_guard<std::mutex> lockSetPreferredFrameSize(setPreferredFrameSizeMutex_);
    userSettedPreferredFrameSize_ = frameSize;
    CHECK_AND_RETURN_LOG(curStreamParams_.encoding != ENCODING_AUDIOVIVID,
        "playing audiovivid, frameSize is always 1024.");
    size_t maxCbBufferSize =
        static_cast<size_t>(MAX_CBBUF_IN_USEC * curStreamParams_.samplingRate / AUDIO_US_PER_S) * sizePerFrameInByte_;
    size_t minSize = static_cast<size_t>(IsFastStream() ? DEFAULT_FAST_CBBUF_IN_USEC : MIN_CBBUF_IN_USEC);
    size_t minCbBufferSize =
        static_cast<size_t>(minSize * curStreamParams_.samplingRate / AUDIO_US_PER_S) * sizePerFrameInByte_;
    size_t preferredCbBufferSize = static_cast<size_t>(frameSize) * sizePerFrameInByte_;
    SetCacheSize(frameSize);
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    cbBufferSize_ = (preferredCbBufferSize > maxCbBufferSize || preferredCbBufferSize < minCbBufferSize) ?
        (preferredCbBufferSize > maxCbBufferSize ? maxCbBufferSize : minCbBufferSize) : preferredCbBufferSize;
    AUDIO_INFO_LOG("Set CallbackBuffer with byte size: %{public}zu", cbBufferSize_);
    cbBuffer_ = std::make_unique<uint8_t[]>(cbBufferSize_);
    return;
}

int32_t RendererInClientInner::Read(uint8_t &buffer, size_t userSize, bool isBlockingRead)
{
    AUDIO_ERR_LOG("Read is not supported");
    return ERROR;
}

uint32_t RendererInClientInner::GetUnderflowCount()
{
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, 0, "buffer is not inited");

    return clientBuffer_->GetUnderrunCount();
}

uint32_t RendererInClientInner::GetOverflowCount()
{
    AUDIO_WARNING_LOG("No Overflow in renderer");
    return 0;
}

void RendererInClientInner::SetUnderflowCount(uint32_t underflowCount)
{
    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "buffer is not inited");
    clientBuffer_->SetUnderrunCount(underflowCount);
}

void RendererInClientInner::SetOverflowCount(uint32_t overflowCount)
{
    // not support for renderer
    AUDIO_WARNING_LOG("No Overflow in renderer");
    return;
}

int32_t RendererInClientInner::RegisterRemoteDiedCallback(const std::shared_ptr<RemoteDiedCallback> &callback)
{
    std::lock_guard<std::mutex> lock(deathRecipientLock_);
    if (deathRecipient_ == nullptr) {
        deathRecipient_ = sptr<RemoteDeathRecipient>::MakeSptr(callback);
    }
    CHECK_AND_RETURN_RET_LOG(ipcProxy_ != nullptr, ERR_ILLEGAL_STATE, "ipcProxy_ is null!");
    bool result = ipcProxy_->AddDeathRecipient(deathRecipient_);
    CHECK_AND_RETURN_RET_LOG(result, ERR_OPERATION_FAILED, "AddDeathRecipient failed.");
    return SUCCESS;
}

int32_t RendererInClientInner::UnregisterRemoteDiedCallback()
{
    std::lock_guard<std::mutex> lock(deathRecipientLock_);
    CHECK_AND_RETURN_RET_LOG(deathRecipient_ != nullptr && ipcProxy_ != nullptr, ERR_ILLEGAL_STATE,
        "deathRecipient or ipcProxy_ is null!");
    bool result = ipcProxy_->RemoveDeathRecipient(deathRecipient_);
    CHECK_AND_RETURN_RET_LOG(result, ERR_OPERATION_FAILED, "RemoveDeathRecipient failed.");
    deathRecipient_ = nullptr;
    return SUCCESS;
}

void RendererInClientInner::SetRendererPositionCallback(int64_t markPosition,
    const std::shared_ptr<RendererPositionCallback> &callback)
{
    CHECK_AND_RETURN_LOG(!IsFastStream(),
        "Registering render frame position callback mark position");
    // waiting for review
    std::lock_guard<std::mutex> lock(markReachMutex_);
    CHECK_AND_RETURN_LOG(callback != nullptr, "RendererPositionCallback is nullptr");
    rendererPositionCallback_ = callback;
    rendererMarkPosition_ = markPosition;
    rendererMarkReached_ = false;
}

void RendererInClientInner::UnsetRendererPositionCallback()
{
    CHECK_AND_RETURN_LOG(!IsFastStream(), "Unregistering render frame position callback");
    // waiting for review
    std::lock_guard<std::mutex> lock(markReachMutex_);
    rendererPositionCallback_ = nullptr;
    rendererMarkPosition_ = 0;
    rendererMarkReached_ = false;
}

void RendererInClientInner::SetRendererPeriodPositionCallback(int64_t periodPosition,
    const std::shared_ptr<RendererPeriodPositionCallback> &callback)
{
    CHECK_AND_RETURN_LOG(!IsFastStream(), "Registering render period position callback");
    // waiting for review
    std::lock_guard<std::mutex> lock(periodReachMutex_);
    CHECK_AND_RETURN_LOG(callback != nullptr, "RendererPeriodPositionCallback is nullptr");
    rendererPeriodPositionCallback_ = callback;
    rendererPeriodSize_ = periodPosition;
    totalBytesWritten_ = 0;
    rendererPeriodWritten_ = 0;
}

void RendererInClientInner::UnsetRendererPeriodPositionCallback()
{
    CHECK_AND_RETURN_LOG(!IsFastStream(), "Unregistering render period position callback");
    // waiting for review
    std::lock_guard<std::mutex> lock(periodReachMutex_);
    rendererPeriodPositionCallback_ = nullptr;
    rendererPeriodSize_ = 0;
    totalBytesWritten_ = 0;
    rendererPeriodWritten_ = 0;
}

void RendererInClientInner::SetCapturerPositionCallback(int64_t markPosition,
    const std::shared_ptr<CapturerPositionCallback> &callback)
{
    AUDIO_ERR_LOG("SetCapturerPositionCallback is not supported");
    return;
}

void RendererInClientInner::UnsetCapturerPositionCallback()
{
    AUDIO_ERR_LOG("SetCapturerPositionCallback is not supported");
    return;
}

void RendererInClientInner::SetCapturerPeriodPositionCallback(int64_t periodPosition,
    const std::shared_ptr<CapturerPeriodPositionCallback> &callback)
{
    AUDIO_ERR_LOG("SetCapturerPositionCallback is not supported");
    return;
}

void RendererInClientInner::UnsetCapturerPeriodPositionCallback()
{
    AUDIO_ERR_LOG("SetCapturerPositionCallback is not supported");
    return;
}

int32_t RendererInClientInner::SetRendererSamplingRate(uint32_t sampleRate)
{
    AUDIO_ERR_LOG("SetRendererSamplingRate to %{public}d is not supported", sampleRate);
    return ERROR;
}

uint32_t RendererInClientInner::GetRendererSamplingRate()
{
    return curStreamParams_.samplingRate;
}

int32_t RendererInClientInner::SetBufferSizeInMsec(int32_t bufferSizeInMsec)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), ERR_NOT_SUPPORTED, "SetBufferSizeInMsec: not supported");
    // bufferSizeInMsec is checked between 5ms and 20ms.
    bufferSizeInMsec_ = static_cast<uint32_t>(bufferSizeInMsec);
    isBufferSizeInMsecSet_ = true;
    AUDIO_INFO_LOG("to %{public}d", bufferSizeInMsec_);
    if (renderMode_ == RENDER_MODE_CALLBACK) {
        uint64_t bufferDurationInUs = bufferSizeInMsec_ * AUDIO_US_PER_MS;
        InitCallbackBuffer(bufferDurationInUs);
    }
    if (rendererInfo_.playerType == PLAYER_TYPE_TONE_PLAYER) {
        SetCacheSize(TONE_PLAYER_CACHE_SIZE * spanSizeInFrame_);
    }
    return SUCCESS;
}

int32_t RendererInClientInner::SetChannelBlendMode(ChannelBlendMode blendMode)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), SUCCESS, "SetChannelBlendMode: not supported");
    if ((state_ != PREPARED) && (state_ != NEW)) {
        AUDIO_ERR_LOG("SetChannelBlendMode in invalid status:%{public}d", state_.load());
        return ERR_ILLEGAL_STATE;
    }
    isBlendSet_ = true;
    audioBlend_.SetParams(blendMode, curStreamParams_.format, curStreamParams_.channels);
    return SUCCESS;
}

int32_t RendererInClientInner::SetVolumeWithRamp(float volume, int32_t duration)
{
    CHECK_AND_RETURN_RET_LOG(!IsFastStream(), SUCCESS, "SetVolumeWithRamp: not supported");
    CHECK_AND_RETURN_RET_LOG((state_ != RELEASED) && (state_ != INVALID) && (state_ != STOPPED),
        ERR_ILLEGAL_STATE, "Illegal state %{public}d", state_.load());

    if (FLOAT_COMPARE_EQ(clientVolume_, volume)) {
        AUDIO_INFO_LOG("set same volume %{public}f", volume);
        return SUCCESS;
    }

    volumeRamp_.SetVolumeRampConfig(volume, clientVolume_, duration);
    return SUCCESS;
}

void RendererInClientInner::SetStreamTrackerState(bool trackerRegisteredState)
{
    streamTrackerRegistered_ = trackerRegisteredState;
}

void RendererInClientInner::GetRendererFirstFrameWritingCallback(IAudioStream::SwitchInfo& info)
{
    std::lock_guard<std::mutex> lock(firstFrameWritingMutex_);
    if (firstFrameWritingCb_) {
        info.rendererFirstFrameWritingCallback = firstFrameWritingCb_;
    }
}

void RendererInClientInner::GetSwitchInfo(IAudioStream::SwitchInfo& info)
{
    info.params = streamParams_;

    info.rendererInfo = rendererInfo_;
    info.capturerInfo = capturerInfo_;
    info.eStreamType = eStreamType_;
    info.renderMode = renderMode_;
    info.state = state_;
    info.sessionId = sessionId_;
    info.streamTrackerRegistered = streamTrackerRegistered_;
    info.defaultOutputDevice = defaultOutputDevice_;
    info.lastFramePosAndTimePair = lastFramePosAndTimePair_;
    info.lastFramePosAndTimePairWithSpeed = lastFramePosAndTimePairWithSpeed_;
    info.target = renderTarget_;

    GetStreamSwitchInfo(info);

    {
        std::lock_guard<std::mutex> lock(setPreferredFrameSizeMutex_);
        info.userSettedPreferredFrameSize = userSettedPreferredFrameSize_;
    }

    {
        std::lock_guard<std::mutex> lock(lastCallStartByUserTidMutex_);
        info.lastCallStartByUserTid = lastCallStartByUserTid_;
    }

    GetRendererFirstFrameWritingCallback(info);
}

void RendererInClientInner::GetStreamSwitchInfo(IAudioStream::SwitchInfo& info)
{
    info.underFlowCount = GetUnderflowCount();
    info.effectMode = effectMode_;
    info.renderRate = rendererRate_;
    info.clientPid = clientPid_;
    info.clientUid = clientUid_;
    info.volume = clientVolume_;
    info.duckVolume = duckVolume_;
    info.silentModeAndMixWithOthers = silentModeAndMixWithOthers_;

    info.frameMarkPosition = static_cast<uint64_t>(rendererMarkPosition_);
    info.renderPositionCb = rendererPositionCallback_;

    info.framePeriodNumber = static_cast<uint64_t>(rendererPeriodSize_);
    info.renderPeriodPositionCb = rendererPeriodPositionCallback_;

    info.rendererWriteCallback = writeCb_;
    info.unprocessSamples = audioWriteState_.load().unprocessedFramesBytes_ +
        audioWriteState_.load().perPeriodFrame_ +
        lastSwitchPositionWithSpeed_[Timestamp::Timestampbase::MONOTONIC];

    if (rendererInfo_.isStatic) {
        CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "Client OHAudioBuffer is nullptr");
        clientBuffer_->GetStaticPlayPosition(
            info.staticBufferInfo.currentLoopTimes_, info.staticBufferInfo.curStaticDataPos_);
        info.staticBufferInfo.bufferSize_ = staticBufferInfo_.bufferSize_;
        info.staticBufferInfo.totalLoopTimes_ = staticBufferInfo_.totalLoopTimes_;
        info.staticSharedMemory = staticSharedMemory_;
        info.staticBufferEventCallback = audioStaticBufferEventCallback_;
    }
}

IAudioStream::StreamClass RendererInClientInner::GetStreamClass()
{
    if (IsFastStream()) {
        return IAudioStream::StreamClass::FAST_STREAM;
    }
    return PA_STREAM;
}

void RendererInClientInner::OnHandle(uint32_t code, int64_t data)
{
    AUDIO_DEBUG_LOG("On handle event, event code: %{public}d, data: %{public}" PRIu64 "", code, data);
    switch (code) {
        case STATE_CHANGE_EVENT:
            HandleStateChangeEvent(data);
            break;
        case RENDERER_MARK_REACHED_EVENT:
            HandleRenderMarkReachedEvent(data);
            break;
        case RENDERER_PERIOD_REACHED_EVENT:
            HandleRenderPeriodReachedEvent(data);
            break;
        default:
            break;
    }
}

void RendererInClientInner::InitCallbackHandler()
{
    std::lock_guard<std::mutex> lock(runnerMutex_);
    if (callbackHandler_ == nullptr) {
        callbackHandler_ = CallbackHandler::GetInstance(shared_from_this(), "OS_AudioStateCB");
    }
}

void RendererInClientInner::SafeSendCallbackEvent(uint32_t eventCode, int64_t data)
{
    std::lock_guard<std::mutex> lock(runnerMutex_);
    AUDIO_INFO_LOG("code: %{public}u, data: %{public}" PRId64 "", eventCode, data);
    CHECK_AND_RETURN_LOG(callbackHandler_ != nullptr && runnerReleased_ == false, "Runner is Released");
    callbackHandler_->SendCallbackEvent(eventCode, data);
}

int32_t RendererInClientInner::StateCmdTypeToParams(int64_t &params, State state, StateChangeCmdType cmdType)
{
    if (cmdType == CMD_FROM_CLIENT) {
        params = static_cast<int64_t>(state);
        return SUCCESS;
    }
    switch (state) {
        case RUNNING:
            params = HANDLER_PARAM_RUNNING_FROM_SYSTEM;
            break;
        case PAUSED:
            params = HANDLER_PARAM_PAUSED_FROM_SYSTEM;
            break;
        default:
            params = HANDLER_PARAM_INVALID;
            break;
    }
    return SUCCESS;
}

int32_t RendererInClientInner::ParamsToStateCmdType(int64_t params, State &state, StateChangeCmdType &cmdType)
{
    cmdType = CMD_FROM_CLIENT;
    switch (params) {
        case HANDLER_PARAM_NEW:
            state = NEW;
            break;
        case HANDLER_PARAM_PREPARED:
            state = PREPARED;
            break;
        case HANDLER_PARAM_RUNNING:
            state = RUNNING;
            break;
        case HANDLER_PARAM_STOPPED:
            state = STOPPED;
            break;
        case HANDLER_PARAM_RELEASED:
            state = RELEASED;
            break;
        case HANDLER_PARAM_PAUSED:
            state = PAUSED;
            break;
        case HANDLER_PARAM_STOPPING:
            state = STOPPING;
            break;
        case HANDLER_PARAM_RUNNING_FROM_SYSTEM:
            state = RUNNING;
            cmdType = CMD_FROM_SYSTEM;
            break;
        case HANDLER_PARAM_PAUSED_FROM_SYSTEM:
            state = PAUSED;
            cmdType = CMD_FROM_SYSTEM;
            break;
        default:
            state = INVALID;
            break;
    }
    return SUCCESS;
}

// OnRenderMarkReach by eventHandler
void RendererInClientInner::SendRenderMarkReachedEvent(int64_t rendererMarkPosition)
{
    SafeSendCallbackEvent(RENDERER_MARK_REACHED_EVENT, rendererMarkPosition);
}

// OnRenderPeriodReach by eventHandler
void RendererInClientInner::SendRenderPeriodReachedEvent(int64_t rendererPeriodSize)
{
    SafeSendCallbackEvent(RENDERER_PERIOD_REACHED_EVENT, rendererPeriodSize);
}

void RendererInClientInner::HandleStateChangeEvent(int64_t data)
{
    State state = INVALID;
    StateChangeCmdType cmdType = CMD_FROM_CLIENT;
    ParamsToStateCmdType(data, state, cmdType);
    std::unique_lock<std::mutex> lock(streamCbMutex_);
    std::shared_ptr<AudioStreamCallback> streamCb = streamCallback_.lock();
    if (streamCb != nullptr) {
        state = state != STOPPING ? state : STOPPED; // client only need STOPPED
        streamCb->OnStateChange(state, cmdType);
    }
}

void RendererInClientInner::HandleRenderMarkReachedEvent(int64_t rendererMarkPosition)
{
    AUDIO_DEBUG_LOG("Start HandleRenderMarkReachedEvent");
    std::unique_lock<std::mutex> lock(markReachMutex_);
    if (rendererPositionCallback_) {
        rendererPositionCallback_->OnMarkReached(rendererMarkPosition);
    }
}

void RendererInClientInner::HandleRenderPeriodReachedEvent(int64_t rendererPeriodNumber)
{
    AUDIO_DEBUG_LOG("Start HandleRenderPeriodReachedEvent");
    std::unique_lock<std::mutex> lock(periodReachMutex_);
    if (rendererPeriodPositionCallback_) {
        rendererPeriodPositionCallback_->OnPeriodReached(rendererPeriodNumber);
    }
}

void RendererInClientInner::OnSpatializationStateChange(const AudioSpatializationState &spatializationState)
{
    CHECK_AND_RETURN_LOG(ipcStream_ != nullptr, "Object ipcStream is nullptr");
    CHECK_AND_RETURN_LOG(ipcStream_->UpdateSpatializationState(spatializationState.spatializationEnabled,
        spatializationState.headTrackingEnabled) == SUCCESS, "Update spatialization state failed");
}

void RendererInClientInner::UpdateLatencyTimestamp(std::string &timestamp, bool isRenderer)
{
    sptr<IStandardAudioService> gasp = RendererInClientInner::GetAudioServerProxy();
    if (gasp == nullptr) {
        AUDIO_ERR_LOG("LatencyMeas failed to get AudioServerProxy");
        return;
    }
    gasp->UpdateLatencyTimestamp(timestamp, isRenderer);
}

int32_t RendererInClientInner::SetSourceDuration(int64_t duration)
{
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetSourceDuration(duration);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("Set Source Duration failed:%{public}d", ret);
        return ERROR;
    }
    return SUCCESS;
}

bool RendererInClientInner::GetOffloadEnable()
{
    return offloadEnable_;
}

bool RendererInClientInner::GetSpatializationEnabled()
{
    return rendererInfo_.spatializationEnabled;
}

bool RendererInClientInner::GetHighResolutionEnabled()
{
    return AudioPolicyManager::GetInstance().IsHighResolutionExist();
}

void RendererInClientInner::SetSilentModeAndMixWithOthers(bool on)
{
    AUDIO_PRERELEASE_LOGI("%{public}d", on);
    silentModeAndMixWithOthers_ = on;
    CHECK_AND_RETURN_LOG(ipcStream_ != nullptr, "Object ipcStream is nullptr");
    ipcStream_->SetSilentModeAndMixWithOthers(on);
    return;
}

bool RendererInClientInner::GetSilentModeAndMixWithOthers()
{
    return silentModeAndMixWithOthers_;
}

bool RendererInClientInner::RestoreAudioStream(bool needStoreState)
{
    CHECK_AND_RETURN_RET_LOG(proxyObj_ != nullptr, false, "proxyObj_ is null");
    CHECK_AND_RETURN_RET_LOG(state_ != NEW && state_ != INVALID && state_ != RELEASED, true,
        "state_ is %{public}d, no need for restore", state_.load());
    bool result = true;
    State oldState = state_;
    UpdateStreamState(NEW);
    SetStreamTrackerState(false);
    // If pipe type is offload, need reset to normal.
    // Otherwise, unable to enter offload mode.
    if (rendererInfo_.pipeType == PIPE_TYPE_OUT_OFFLOAD) {
        rendererInfo_.pipeType = PIPE_TYPE_OUT_NORMAL;
    }
    int32_t ret = SetAudioStreamInfo(streamParams_, proxyObj_);
    if (ret != SUCCESS) {
        goto error;
    }
    if (!needStoreState) {
        AUDIO_INFO_LOG("telephony scene, return directly");
        return ret == SUCCESS;
    }

    SetDefaultOutputDevice(defaultOutputDevice_);

    switch (oldState) {
        case RUNNING:
            result = StartAudioStream(CMD_FROM_SYSTEM);
            break;
        case PAUSED:
            result = StartAudioStream(CMD_FROM_SYSTEM) && PauseAudioStream();
            break;
        case STOPPED:
        case STOPPING:
            result = StartAudioStream(CMD_FROM_SYSTEM) && StopAudioStream();
            break;
        default:
            UpdateStreamState(oldState);
            break;
    }
    if (!result) {
        goto error;
    }
    return result;

error:
    AUDIO_ERR_LOG("RestoreAudioStream failed");
    UpdateStreamState(oldState);
    return false;
}

int32_t RendererInClientInner::SetDefaultOutputDevice(const DeviceType defaultOutputDevice, bool skipForce)
{
    CHECK_AND_RETURN_RET_LOG(renderTarget_ == NORMAL_PLAYBACK, ERR_ILLEGAL_STATE, "Now in injection mode.​​");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetDefaultOutputDevice(defaultOutputDevice, skipForce);
    if (ret == SUCCESS) {
        defaultOutputDevice_ = defaultOutputDevice;
    }
    return ret;
}

FastStatus RendererInClientInner::GetFastStatus()
{
    if (IsFastStream()) {
        return FASTSTATUS_FAST;
    }
    return FASTSTATUS_NORMAL;
}

void RendererInClientInner::SetFastStatusChangeCallback(const std::function<void(FastStatus)> &callback)
{
    std::lock_guard lock(fastStatusChangeCallbackMutex_);
    fastStatusChangeCallback_ = callback;
}

void RendererInClientInner::NotifyFastStatusChange(FastStatus status)
{
    if (status != FASTSTATUS_FAST && status != FASTSTATUS_NORMAL) {
        AUDIO_WARNING_LOG("Invalid fast status:%{public}d", status);
        return;
    }
    fastStatus_.store(status);

    std::function<void(FastStatus)> callback;
    {
        std::lock_guard lock(fastStatusChangeCallbackMutex_);
        callback = fastStatusChangeCallback_;
    }
    CHECK_AND_RETURN_LOG(static_cast<bool>(callback), "fast status change callback is null");
    callback(status);
}

DeviceType RendererInClientInner::GetDefaultOutputDevice()
{
    return defaultOutputDevice_;
}

void RendererInClientInner::CheckAndReportTimestamp()
{
    auto currentTime = ClockTime::GetCurNano();
    auto duration = currentTime - lastTriggerTime_;
    if (duration <= MIN_INTERVAL_IN_NS) {
        logStopCallCount_ = true;
    }
    lastTriggerTime_ = currentTime;
}

int32_t RendererInClientInner::GetAudioTimestampInfo(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    CheckAndReportTimestamp();
    CHECK_AND_RETURN_RET_LOG(renderTarget_ == NORMAL_PLAYBACK, ERR_ILLEGAL_STATE, "Now in injection mode.​​");
    CHECK_AND_RETURN_RET_LOG(state_ == RUNNING, ERR_ILLEGAL_STATE, "Renderer stream state is not RUNNING");
    CHECK_AND_RETURN_RET_LOG(base >= 0 && base < Timestamp::Timestampbase::BASESIZE,
        ERR_INVALID_PARAM, "Timestampbase is not allowed");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE, "ipcStream is not inited!");
    uint64_t readIdx = 0;
    uint64_t timestampVal = 0;
    uint64_t latency = 0;
    int32_t ret = ipcStream_->GetAudioPosition(readIdx, timestampVal, latency, base);
    // cal readIdx from last flush
    readIdx = readIdx > lastFlushReadIndex_ ? readIdx - lastFlushReadIndex_ : 0;
    
    // cal latency between readIdx and framesWritten
    AudioWriteState state = audioWriteState_.load();
    uint64_t unprocessSamples = state.unprocessedFramesBytes_;
    uint64_t samplesWritten = state.totalBytesWrittenAfterFlush_;
    uint64_t deepLatency = samplesWritten > readIdx ? samplesWritten - readIdx : 0;
    // get position and speed since last change
    WrittenFramesWithSpeed fsPair = writtenAtSpeedChange_.load();
    uint64_t lastSpeedPosition = fsPair.writtenFrames;
    float lastSpeed = fsPair.speed;

    uint64_t frameLatency = 0;
    if (readIdx < latency + lastSpeedPosition) {
        // cache before speed change
        frameLatency = lastSpeed * (latency - readIdx + lastSpeedPosition);
        frameLatency += (samplesWritten > lastSpeedPosition ? (samplesWritten - lastSpeedPosition) * speed_ : 0);
    } else {
        frameLatency = (deepLatency + latency) * speed_;
    }
    // between unprocessSamples and framesWritten there is sonic
    frameLatency += SONIC_LATENCY_IN_MS * curStreamParams_.samplingRate / AUDIO_MS_PER_SECOND;
    
    // real frameposition
    uint64_t framePosition = unprocessSamples > frameLatency ? unprocessSamples - frameLatency : 0;
    framePosition += dropPosition_.load();
    framePosition += lastSwitchPositionWithSpeed_[base];

    // reset the timestamp
    if (lastFramePosAndTimePairWithSpeed_[base].first < framePosition ||
        lastFramePosAndTimePairWithSpeed_[base].second == 0) {
        lastFramePosAndTimePairWithSpeed_[base] = {framePosition, timestampVal};
    } else {
        AUDIO_DEBUG_LOG("The frame position should be continuously increasing");
        framePosition = lastFramePosAndTimePairWithSpeed_[base].first;
        timestampVal = lastFramePosAndTimePairWithSpeed_[base].second;
    }
    AUDIO_DEBUG_LOG("[CLIENT]Latency info: unprocessSamples %{public}" PRIu64 ", samplesWritten %{public}" PRIu64
        ", lastSpeedPosition %{public}" PRIu64, unprocessSamples, samplesWritten, lastSpeedPosition);
    AUDIO_DEBUG_LOG("[CLIENT]Latency info: framePosition: %{public}" PRIu64 ", lastFlushReadIndex_ %{public}" PRIu64
        ", timestamp %{public}" PRIu64 ", totlatency %{public}" PRIu64,
        framePosition, lastFlushReadIndex_, timestampVal, frameLatency);

    timestamp.framePosition = framePosition > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(framePosition);
    timestamp.time.tv_sec = static_cast<time_t>(timestampVal / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(timestampVal % AUDIO_NS_PER_SECOND);
    return ret;
}

void RendererInClientInner::SetSwitchingStatus(bool isSwitching)
{
    std::lock_guard lock(switchingMutex_);
    if (isSwitching) {
        switchingInfo_ = {true, state_};
    } else {
        switchingInfo_ = {false, INVALID};
    }
}

void RendererInClientInner::GetRestoreInfo(RestoreInfo &restoreInfo)
{
    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "Client OHAudioBuffer is nullptr");
    clientBuffer_->GetRestoreInfo(restoreInfo);
    return;
}

void RendererInClientInner::SetRestoreInfo(RestoreInfo &restoreInfo)
{
    if (restoreInfo.restoreReason == SERVER_DIED) {
        cbThreadReleased_ = true;
    }
    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "Client OHAudioBuffer is nullptr");
    clientBuffer_->SetRestoreInfo(restoreInfo);
    return;
}

RestoreStatus RendererInClientInner::CheckRestoreStatus()
{
    bool restoreFlag = IsFastStream() && (writeCb_ == nullptr) && !rendererInfo_.isStatic;
    if (restoreFlag) {
        AUDIO_INFO_LOG("Fast stream without callback, restore to normal");
        renderMode_ = RENDER_MODE_NORMAL;
        return NEED_RESTORE_TO_NORMAL;
    }
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, RESTORE_ERROR, "Client OHAudioBuffer is nullptr");
    return clientBuffer_->CheckRestoreStatus();
}

RestoreStatus RendererInClientInner::SetRestoreStatus(RestoreStatus restoreStatus)
{
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, RESTORE_ERROR, "Client OHAudioBuffer is nullptr");
    return clientBuffer_->SetRestoreStatus(restoreStatus);
}

void RendererInClientInner::FetchDeviceForSplitStream()
{
    AUDIO_INFO_LOG("Fetch output device for split stream %{public}u", sessionId_);
    SetRestoreStatus(NO_NEED_FOR_RESTORE);
}

void RendererInClientInner::SetCallStartByUserTid(pid_t tid)
{
    std::lock_guard lock(lastCallStartByUserTidMutex_);
    lastCallStartByUserTid_ = tid;
}

void RendererInClientInner::SetCallbackLoopTid(int32_t tid)
{
    std::unique_lock<std::mutex> waitLock(callbackLoopTidMutex_);
    AUDIO_INFO_LOG("Callback loop tid: %{public}d", tid);
    callbackLoopTid_ = tid;
    callbackLoopTidCv_.notify_all();
}

int32_t RendererInClientInner::GetCallbackLoopTid()
{
    std::unique_lock<std::mutex> waitLock(callbackLoopTidMutex_);
    bool stopWaiting = callbackLoopTidCv_.wait_for(waitLock, std::chrono::seconds(1), [this] {
        return callbackLoopTid_ != -1; // callbackLoopTid_ will change when got notified.
    });

    if (!stopWaiting) {
        AUDIO_WARNING_LOG("Wait timeout");
        callbackLoopTid_ = 0; // set tid to prevent get operation from getting stuck
    }
    return callbackLoopTid_;
}

int32_t RendererInClientInner::SetOffloadDataCallbackState(int cbState)
{
    Trace trace("RendererInClientInner::SetOffloadDataCallbackState: " + std::to_string(cbState));
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED, "ipcStream is not inited!");
    return ipcStream_->SetOffloadDataCallbackState(cbState);
}

bool RendererInClientInner::GetStopFlag() const
{
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, false, "Client OHAudioBuffer is nullptr");
    return clientBuffer_->GetStopFlag();
}

void RendererInClientInner::SetAudioHapticsSyncId(const int32_t &audioHapticsSyncId)
{
    CHECK_AND_RETURN_LOG(ipcStream_ != nullptr, "ipcStream is not inited!");
    int32_t ret = ipcStream_->SetAudioHapticsSyncId(audioHapticsSyncId);
    CHECK_AND_RETURN_LOG(ret == SUCCESS, "Set sync id failed");
}

bool RendererInClientInner::NeedStopFlush()
{
    return std::find(STOP_FLUSH_UIDS.begin(), STOP_FLUSH_UIDS.end(), uidGetter_()) != STOP_FLUSH_UIDS.end();
}

const std::string RendererInClientInner::GetBundleName()
{
    return bundleName;
}

void RendererInClientInner::SetBundleName(std::string &name)
{
    bundleName = name;
}

void RendererInClientInner::NotifyStopWaiting()
{
    CHECK_AND_RETURN(renderMode_ == RENDER_MODE_CALLBACK || renderMode_ == RENDER_MODE_STATIC);
    // start the callback-write thread
    cbThreadCv_.notify_all();
}

void RendererInClientInner::UpdateStopState()
{
    CHECK_AND_RETURN(renderMode_ == RENDER_MODE_CALLBACK || renderMode_ == RENDER_MODE_STATIC);
    UpdateStreamState(STOPPING);
    AUDIO_INFO_LOG("Stop begin in callback mode sessionId %{public}d uid: %{public}d", sessionId_, clientUid_);
}

bool RendererInClientInner::ResetStaticPlayPosition()
{
    CHECK_AND_RETURN_RET_LOG(rendererInfo_.isStatic, false, "Not in Static Mode");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, false, "ipcStream is not inited!");
    CHECK_AND_RETURN_RET(CallStartWhenInStandby() == SUCCESS, ERR_OPERATION_FAILED);

    int32_t ret = ipcStream_->ResetStaticPlayPosition();
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, false, "ResetStaticPlayPosition fail!");
    return true;
}

} // namespace AudioStandard
} // namespace OHOS
