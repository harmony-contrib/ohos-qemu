/*
 * Copyright (c) 2023-2025 Huawei Device Co., Ltd.
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
#ifndef FAST_AUDIO_STREAM_H
#define FAST_AUDIO_STREAM_H

#ifndef LOG_TAG
#define LOG_TAG "CapturerInClientInner"
#endif

#include "capturer_in_client.h"
#include "capturer_in_client_inner.h"

#include <unistd.h>
#include <atomic>
#include <cinttypes>
#include <condition_variable>
#include <sstream>
#include <string>
#include <mutex>
#include <thread>
#include <vector>

#include "iservice_registry.h"
#include "system_ability_definition.h"
#include "securec.h"

#include "iipc_stream.h"
#include "audio_capturer_log.h"
#include "audio_dump_pcm.h"
#include "audio_errors.h"
#include "stream_dfx_manager.h"
#include "volume_tools.h"
#include "audio_ring_cache.h"
#include "audio_utils.h"
#include "audio_policy_manager.h"
#include "audio_device_info.h"
#include "audio_stream_change_info.h"
#include "audio_server_death_recipient.h"
#include "audio_stream_tracker.h"
#include "audio_process_config.h"
#include "ipc_stream_listener_impl.h"
#include "ipc_stream_listener_stub.h"
#include "callback_handler.h"
#include "audio_safe_block_queue.h"
#include "istandard_audio_service.h"
#include "app_bundle_manager.h"
#include "media_monitor_manager.h"

namespace OHOS {
namespace AudioStandard {
namespace {
static const size_t MAX_CLIENT_READ_SIZE = 20 * 1024 * 1024; // 20M
static const int32_t CREATE_TIMEOUT_IN_SECOND = 9; // 9S
static const int32_t OPERATION_TIMEOUT_IN_MS = 1000; // 1000ms
#ifdef CONFIG_FACTORY_VERSION
static const int32_t OPERATION_TIMEOUT_FOR_STOP_IN_MS = 2000; // 2000ms
#else
static const int32_t OPERATION_TIMEOUT_FOR_STOP_IN_MS = 1000; // 1000ms
#endif
static const int32_t LOGLITMITTIMES = 20;
const uint64_t DEFAULT_BUF_DURATION_IN_USEC = 20000; // 20ms
const uint64_t MAX_BUF_DURATION_IN_USEC = 2000000; // 2S
const int64_t INVALID_FRAME_SIZE = -1;
static const int32_t SHORT_TIMEOUT_IN_MS = 20; // ms
static constexpr int CB_QUEUE_CAPACITY = 3;
constexpr int32_t RETRY_WAIT_TIME_MS = 500; // 500ms
constexpr int32_t MAX_RETRY_COUNT = 8;
const float ERROR_VOLUME = -0.1f;

inline bool IsVoiceRecognitionMicInEcRequest(const AudioCapturerInfo &capturerInfo, const AudioStreamParams &params)
{
    return capturerInfo.sourceType == SOURCE_TYPE_VOICE_RECOGNITION &&
        (params.micInChannels > CHANNEL_UNKNOW || params.ecChannels > CHANNEL_UNKNOW);
}

inline bool IsDegradeVoiceRecognitionMicInEcRequest(const AudioCapturerInfo &capturerInfo,
    const AudioStreamParams &params)
{
    return IsVoiceRecognitionMicInEcRequest(capturerInfo, params) && params.isVoiceRecognitionMicInEcDegrade;
}

inline bool IsCamcorderMicInRequest(const AudioCapturerInfo &capturerInfo,
    const AudioStreamParams &params)
{
    return capturerInfo.sourceType == SOURCE_TYPE_CAMCORDER &&
       params.micInChannels > CHANNEL_UNKNOW;
}
}

std::shared_ptr<CapturerInClient> CapturerInClient::GetInstance(AudioStreamType eStreamType, int32_t appUid)
{
    return std::make_shared<CapturerInClientInner>(eStreamType, appUid);
}

CapturerInClientInner::CapturerInClientInner(AudioStreamType eStreamType, int32_t appUid) : eStreamType_(eStreamType),
    appUid_(appUid), cbBufferQueue_(CB_QUEUE_CAPACITY)
{
    AUDIO_INFO_LOG("Create with StreamType:%{public}d appUid:%{public}d ", eStreamType_, appUid_);
    audioStreamTracker_ = std::make_unique<AudioStreamTracker>(AUDIO_MODE_RECORD, appUid);
    UpdateStreamState(NEW);
}

CapturerInClientInner::~CapturerInClientInner()
{
    AUDIO_INFO_LOG("~CapturerInClientInner()");
    DumpFileUtil::CloseDumpFile(&dumpInFd_);
    CapturerInClientInner::ReleaseAudioStream(true);
    AUDIO_INFO_LOG("[%{public}s] volume data counts: %{public}" PRId64, logUtilsTag_.c_str(), volumeDataCount_);
}

void CapturerInClientInner::UpdateStreamState(State state)
{
   // When updating the stream state, the focus state is updated synchronously.
    state_ = state;
    streamFocusState_ = static_cast<StreamFocusState>(state);
}

int32_t CapturerInClientInner::OnOperationHandled(Operation operation, int64_t result)
{
    // read/write operation may print many log, use debug.
    if (operation == UPDATE_STREAM) {
        AUDIO_DEBUG_LOG("OnOperationHandled() UPDATE_STREAM result:%{public}" PRId64".", result);
        // notify write if blocked
        return SUCCESS;
    }

    if (operation == BUFFER_OVERFLOW) {
        AUDIO_WARNING_LOG("recv overflow %{public}d", overflowCount_);
        // in plan next: do more to reduce overflow
        return SUCCESS;
    }

    if (operation == RESTORE_SESSION) {
        return SUCCESS;
    }

    if (operation == UPDATE_SPANSIZE) {
        NotifyFastStatusChange(static_cast<FastStatus>(result));
        return SUCCESS;
    }

    if (operation == SENSITIVE_RECORD_PERMIT) {
        std::lock_guard<std::mutex> lock(sensitiveRecordPermitCallbackMutex_);
        if (sensitiveRecordPermitCallback_ != nullptr) {
            sensitiveRecordPermitCallback_->OnSensitiveRecordPermit(result != 0);
        }
        return SUCCESS;
    }

    AUDIO_INFO_LOG("OnOperationHandled() recv operation:%{public}d result:%{public}" PRId64".", operation, result);
    std::unique_lock<std::mutex> lock(callServerMutex_);
    notifiedOperation_ = operation;
    notifiedResult_ = result;

    callServerCV_.notify_all();
    return SUCCESS;
}

int32_t CapturerInClientInner::OnMetaData(const std::vector<uint8_t> &metaData)
{
    CHECK_AND_RETURN_RET_LOG(!metaData.empty(), ERR_INVALID_PARAM, "metaData is empty");
    DumpMetadata(metaData);
    std::shared_ptr<AudioCapturerMetaDataCallback> metaCb;
    {
        std::lock_guard<std::mutex> lock(metaDataCbMutex_);
        metaCb = metaDataCb_;
    }
    CHECK_AND_RETURN_RET_LOG(metaCb != nullptr, ERR_ILLEGAL_STATE, "metaDataCb_ is nullptr");
    CaptureMetaDataType metaType = CaptureMetaDataType::CAMCORDER;
    metaCb->OnMetaData(metaType, metaData);
    return SUCCESS;
}

void CapturerInClientInner::DumpMetadata(const std::vector<uint8_t> &metaData)
{
    CHECK_AND_RETURN_LOG(!metaData.empty(), "metaData is empty");
    if (dumpMetaDataFileName_.empty()) {
        dumpMetaDataFileName_ = DumpFileUtil::GetMetadataClientDumpFileName(sessionId_);
    }
    DumpFileUtil::OpenDumpFile(
        DumpFileUtil::DUMP_CLIENT_PARA, dumpMetaDataFileName_, &dumpMetaDataFile_, OTHER_NATIVE_SERVICE);
    DumpFileUtil::WriteDumpFile(dumpMetaDataFile_, const_cast<uint8_t *>(metaData.data()), metaData.size());
}

void CapturerInClientInner::SetClientID(int32_t clientPid, int32_t clientUid, uint32_t appTokenId, uint64_t fullTokenId)
{
    AUDIO_INFO_LOG("PID:%{public}d UID:%{public}d.", clientPid, clientUid);
    clientPid_ = clientPid;
    clientUid_ = clientUid;
    appTokenId_ = appTokenId;
    fullTokenId_ = fullTokenId;
    return;
}

void CapturerInClientInner::SetClientDeviceId(const std::string &deviceId)
{
    deviceId_ = deviceId;
}

int32_t CapturerInClientInner::UpdatePlaybackCaptureConfig(const AudioPlaybackCaptureConfig &config)
{
#ifdef HAS_FEATURE_INNERCAPTURER
    AUDIO_INFO_LOG("client set %{public}s", ProcessConfig::DumpInnerCapConfig(config).c_str());
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "IpcStream is already nullptr", true), "IpcStream is already nullptr");
    int32_t ret = ipcStream_->UpdatePlaybackCaptureConfig(config);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_OPERATION_FAILED, "UpdatePlaybackCaptureConfig failed", true), "failed: %{public}d", ret);

    filterConfig_ = config;
#endif
    return SUCCESS;
}

void CapturerInClientInner::SetRendererInfo(const AudioRendererInfo &rendererInfo)
{
    AUDIO_WARNING_LOG("SetRendererInfo is not supported");
    return;
}

void CapturerInClientInner::GetRendererInfo(AudioRendererInfo &rendererInfo)
{
    AUDIO_WARNING_LOG("GetRendererInfo is not supported");
}

void CapturerInClientInner::SetCapturerInfo(const AudioCapturerInfo &capturerInfo)
{
    capturerInfo_ = capturerInfo;
    capturerInfo_.samplingRate = static_cast<AudioSamplingRate>(streamParams_.samplingRate);
    capturerInfo_.encodingType = streamParams_.encoding;
    capturerInfo_.channelLayout = streamParams_.channelLayout;
    AUDIO_INFO_LOG("SetCapturerInfo with SourceType %{public}d flag %{public}d", capturerInfo_.sourceType,
        capturerInfo_.capturerFlags);
    return;
}

void CapturerInClientInner::RegisterTracker(const std::shared_ptr<AudioClientTracker> &proxyObj)
{
    if (audioStreamTracker_ && audioStreamTracker_.get() && !streamTrackerRegistered_) {
        // make sure sessionId_ is set before.
        AUDIO_INFO_LOG("Calling register tracker, sessionid = %{public}d", sessionId_);
        AudioRegisterTrackerInfo registerTrackerInfo;

        capturerInfo_.samplingRate = static_cast<AudioSamplingRate>(streamParams_.samplingRate);
        registerTrackerInfo.sessionId = sessionId_;
        registerTrackerInfo.clientPid = clientPid_;
        registerTrackerInfo.state = state_;
        registerTrackerInfo.rendererInfo = rendererInfo_;
        registerTrackerInfo.capturerInfo = capturerInfo_;
        registerTrackerInfo.appTokenId = appTokenId_;

        audioStreamTracker_->RegisterTracker(registerTrackerInfo, proxyObj);
        streamTrackerRegistered_ = true;
    }
}

void CapturerInClientInner::UpdateTracker(const std::string &updateCase)
{
    if (audioStreamTracker_ && audioStreamTracker_.get()) {
        AUDIO_DEBUG_LOG("Capturer:Calling Update tracker for %{public}s", updateCase.c_str());
        audioStreamTracker_->UpdateTracker(sessionId_, state_, clientPid_, rendererInfo_, capturerInfo_);
    }
}

int32_t CapturerInClientInner::CheckForSetAudioStreamInfo(const AudioStreamParams info)
{
    if (capturerInfo_.sourceType == SOURCE_TYPE_UNPROCESSED_VOICE_ASSISTANT) {
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(
            IAudioStream::GetByteSizePerFrameWithEc(info, sizePerFrameInByte_) == SUCCESS, ERROR_INVALID_PARAM,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrameWithEc failed with invalid params"),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_OPERATION_FAILED,
                "[SetAudioStreamInfo]GetByteSizePerFrameWithEc failed with invalid params", true));
    } else if (IsDegradeVoiceRecognitionMicInEcRequest(capturerInfo_, info)) {
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(IAudioStream::GetByteSizePerFrame(info, sizePerFrameInByte_) == SUCCESS,
            ERROR_INVALID_PARAM,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrame failed with invalid params"),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_OPERATION_FAILED,
                "[SetAudioStreamInfo]GetByteSizePerFrame failed with invalid params", true));
    } else if (IsVoiceRecognitionMicInEcRequest(capturerInfo_, info)) {
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(IAudioStream::GetByteSizePerFrameWithMicInEc(info, sizePerFrameInByte_) ==
            SUCCESS, ERROR_INVALID_PARAM,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrameWithMicInEc failed with invalid params"),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_OPERATION_FAILED,
                "[SetAudioStreamInfo]GetByteSizePerFrameWithMicInEc failed with invalid params", true));
    } else if (IsCamcorderMicInRequest(capturerInfo_, info)) {
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(IAudioStream::GetByteSizePerFrameWithMicIn(info, sizePerFrameInByte_) ==
            SUCCESS, ERROR_INVALID_PARAM,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrameWithMicIn failed with invalid params"),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_OPERATION_FAILED,
                "[SetAudioStreamInfo]GetByteSizePerFrameWithMicIn failed with invalid params", true));
    } else {
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(IAudioStream::GetByteSizePerFrame(info, sizePerFrameInByte_) == SUCCESS,
            ERROR_INVALID_PARAM,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]GetByteSizePerFrame failed with invalid params"),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_OPERATION_FAILED,
                "[SetAudioStreamInfo]GetByteSizePerFrame failed with invalid params", true));
    }
    return SUCCESS;
}

int32_t CapturerInClientInner::SetAudioStreamInfo(const AudioStreamParams info,
    const std::shared_ptr<AudioClientTracker> &proxyObj,
    const AudioPlaybackCaptureConfig &config)
{
    HILOG_COMM_INFO("[SetAudioStreamInfo]AudioStreamInfo, Sampling rate: %{public}d, channels: %{public}d, "
        "format: %{public}d, stream type: %{public}d, encoding type: %{public}d", info.samplingRate, info.channels,
        info.format, eStreamType_, info.encoding);
    AudioXCollie guard("CapturerInClientInner::SetAudioStreamInfo", CREATE_TIMEOUT_IN_SECOND,
         nullptr, nullptr, AUDIO_XCOLLIE_FLAG_LOG);
    int32_t initRet = CheckForSetAudioStreamInfo(info);
    CHECK_AND_CALL_FUNC_RETURN_RET(initRet == SUCCESS, initRet,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_ILLEGAL_STATE, "CheckForSetAudioStreamInfo failed", true));
    if (state_ != NEW) {
        AUDIO_INFO_LOG("State is %{public}d, not new, release existing stream and recreate.", state_.load());
        int32_t ret = DeinitIpcStream();
        CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(ret == SUCCESS, ret,
            HILOG_COMM_ERROR("[SetAudioStreamInfo]release existing stream failed."),
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_CONFIG_ILLEGAL_STATE, "[SetAudioStreamInfo]release existing stream failed.", true));
    }

    streamParams_ = info; // keep it for later use
    paramsIsSet_ = true;
    initRet = InitIpcStream(config);
    CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(initRet == SUCCESS, initRet,
        HILOG_COMM_ERROR("[SetAudioStreamInfo]Init stream failed: %{public}d", initRet),
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "[SetAudioStreamInfo]Init stream failed", true));
    UpdateStreamState(PREPARED);
    logUtilsTag_ = "[" + std::to_string(sessionId_) + "]NormalCapturer";

    proxyObj_ = proxyObj;
    RegisterTracker(proxyObj);
    return SUCCESS;
}

std::mutex g_serverMutex;
sptr<IStandardAudioService> g_ServerProxy = nullptr;
const sptr<IStandardAudioService> CapturerInClientInner::GetAudioServerProxy()
{
    std::lock_guard<std::mutex> lock(g_serverMutex);
    if (g_ServerProxy == nullptr) {
        auto samgr = SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
        if (samgr == nullptr) {
            AUDIO_ERR_LOG("GetAudioServerProxy: get sa manager failed");
            return nullptr;
        }
        sptr<IRemoteObject> object = samgr->GetSystemAbility(AUDIO_DISTRIBUTED_SERVICE_ID);
        if (object == nullptr) {
            AUDIO_ERR_LOG("GetAudioServerProxy: get audio service remote object failed");
            return nullptr;
        }
        g_ServerProxy = iface_cast<IStandardAudioService>(object);
        if (g_ServerProxy == nullptr) {
            AUDIO_ERR_LOG("GetAudioServerProxy: get audio service proxy failed");
            return nullptr;
        }

        // register death recipent to restore proxy
        sptr<AudioServerDeathRecipient> asDeathRecipient =
            new(std::nothrow) AudioServerDeathRecipient(getpid(), getuid());
        if (asDeathRecipient != nullptr) {
            asDeathRecipient->SetNotifyCb([] (pid_t pid, pid_t uid) { AudioServerDied(pid, uid); });
            bool result = object->AddDeathRecipient(asDeathRecipient);
            if (!result) {
                AUDIO_ERR_LOG("GetAudioServerProxy: failed to add deathRecipient");
            }
        }
    }
    sptr<IStandardAudioService> gasp = g_ServerProxy;
    return gasp;
}

void CapturerInClientInner::AudioServerDied(pid_t pid, pid_t uid)
{
    AUDIO_INFO_LOG("audio server died clear proxy, will restore proxy in next call");
    std::lock_guard<std::mutex> lock(g_serverMutex);
    g_ServerProxy = nullptr;
}

void CapturerInClientInner::OnHandle(uint32_t code, int64_t data)
{
    AUDIO_DEBUG_LOG("On handle event, event code: %{public}d, data: %{public}" PRIu64 "", code, data);
    switch (code) {
        case STATE_CHANGE_EVENT:
            HandleStateChangeEvent(data);
            break;
        case RENDERER_MARK_REACHED_EVENT:
            HandleCapturerMarkReachedEvent(data);
            break;
        case RENDERER_PERIOD_REACHED_EVENT:
            HandleCapturerPeriodReachedEvent(data);
            break;
        default:
            break;
    }
}

void CapturerInClientInner::HandleStateChangeEvent(int64_t data)
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

void CapturerInClientInner::HandleCapturerMarkReachedEvent(int64_t capturerMarkPosition)
{
    AUDIO_DEBUG_LOG("Start HandleCapturerMarkReachedEvent");
    std::unique_lock<std::mutex> lock(markReachMutex_);
    if (capturerPositionCallback_) {
        capturerPositionCallback_->OnMarkReached(capturerMarkPosition);
    }
}

void CapturerInClientInner::HandleCapturerPeriodReachedEvent(int64_t capturerPeriodNumber)
{
    AUDIO_DEBUG_LOG("Start HandleCapturerPeriodReachedEvent");
    std::unique_lock<std::mutex> lock(periodReachMutex_);
    if (capturerPeriodPositionCallback_) {
        capturerPeriodPositionCallback_->OnPeriodReached(capturerPeriodNumber);
    }
}

// OnCapturerMarkReach by eventHandler
void CapturerInClientInner::SendCapturerMarkReachedEvent(int64_t capturerMarkPosition)
{
    SafeSendCallbackEvent(RENDERER_MARK_REACHED_EVENT, capturerMarkPosition);
}

// OnCapturerPeriodReach by eventHandler
void CapturerInClientInner::SendCapturerPeriodReachedEvent(int64_t capturerPeriodSize)
{
    SafeSendCallbackEvent(RENDERER_PERIOD_REACHED_EVENT, capturerPeriodSize);
}

int32_t CapturerInClientInner::ParamsToStateCmdType(int64_t params, State &state, StateChangeCmdType &cmdType)
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

int32_t CapturerInClientInner::StateCmdTypeToParams(int64_t &params, State state, StateChangeCmdType cmdType)
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

void CapturerInClientInner::SafeSendCallbackEvent(uint32_t eventCode, int64_t data)
{
    std::lock_guard<std::mutex> lock(runnerMutex_);
    AUDIO_INFO_LOG("Send callback event, code: %{public}u, data: %{public}" PRId64 "", eventCode, data);
    CHECK_AND_CALL_FUNC_RETURN_LOG(callbackHandler_ != nullptr && runnerReleased_ == false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_ILLEGAL_STATE, "Runner is Released", true), "Runner is Released");
    callbackHandler_->SendCallbackEvent(eventCode, data);
}

void CapturerInClientInner::InitCallbackHandler()
{
    if (callbackHandler_ == nullptr) {
        callbackHandler_ = CallbackHandler::GetInstance(shared_from_this(), "OS_AudioStateCB");
    }
}

// call this without lock, we should be able to call deinit in any case.
int32_t CapturerInClientInner::DeinitIpcStream()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, SUCCESS,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_RELEASE_ILLEGAL_STATE, "IpcStream is already nullptr", true), "IpcStream is already nullptr");
    ipcStream_->Release(false);
    // in plan:
    ipcStream_ = nullptr;
    ringCache_->ResetBuffer();
    return SUCCESS;
}

const AudioProcessConfig CapturerInClientInner::ConstructConfig()
{
    AudioProcessConfig config = {};
    // in plan: get token id
    config.appInfo.appPid = clientPid_;
    config.appInfo.appUid = clientUid_;
    config.appInfo.appTokenId = appTokenId_;
    config.appInfo.appFullTokenId = fullTokenId_;
    config.appInfo.deviceId = deviceId_;

    if (capturerInfo_.sourceType == SOURCE_TYPE_UNPROCESSED_VOICE_ASSISTANT) {
        config.streamInfo.channels = static_cast<AudioChannel>(streamParams_.channels + streamParams_.ecChannels);
    } else if (IsDegradeVoiceRecognitionMicInEcRequest(capturerInfo_, streamParams_)) {
        config.streamInfo.channels = static_cast<AudioChannel>(streamParams_.channels);
        AUDIO_INFO_LOG("voice recognition use process channels only for degrade input, channels:%{public}d",
            config.streamInfo.channels);
    } else if (IsVoiceRecognitionMicInEcRequest(capturerInfo_, streamParams_)) {
        config.streamInfo.channels = static_cast<AudioChannel>(streamParams_.channels + streamParams_.micInChannels +
            streamParams_.ecChannels);
    } else if (IsCamcorderMicInRequest(capturerInfo_, streamParams_)) {
        config.streamInfo.channels = static_cast<AudioChannel>(streamParams_.channels + streamParams_.micInChannels);
    } else {
        config.streamInfo.channels = static_cast<AudioChannel>(streamParams_.channels);
    }
    config.streamInfo.encoding = static_cast<AudioEncodingType>(streamParams_.encoding);
    config.streamInfo.format = static_cast<AudioSampleFormat>(streamParams_.format);
    config.streamInfo.samplingRate = static_cast<AudioSamplingRate>(streamParams_.samplingRate);
    config.streamInfo.channelLayout = static_cast<AudioChannelLayout>(streamParams_.channelLayout);
    config.originalSessionId = streamParams_.originalSessionId;

    config.audioMode = AUDIO_MODE_RECORD;

    if (capturerInfo_.capturerFlags != AUDIO_FLAG_NORMAL &&
        capturerInfo_.capturerFlags != AUDIO_FLAG_MMAP &&
        capturerInfo_.capturerFlags != AUDIO_FLAG_VOIP_FAST) {
        AUDIO_WARNING_LOG("ConstructConfig find Capturer flag invalid:%{public}d", capturerInfo_.capturerFlags);
        capturerInfo_.capturerFlags = AUDIO_FLAG_NORMAL;
    }
    config.capturerInfo = capturerInfo_;

    config.rendererInfo = {};

    config.streamType = eStreamType_;

    config.isInnerCapturer = isInnerCapturer_;
    config.isWakeupCapturer = isWakeupCapturer_;
    config.innerCapId = innerCapId_;

    clientConfig_ = config;
    return config;
}

int32_t CapturerInClientInner::InitSharedBuffer()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()), RECORD_CREATE_ILLEGAL_STATE,
        "InitSharedBuffer failed, null ipcStream_", true), "InitSharedBuffer failed, null ipcStream_.");
    int32_t ret = ipcStream_->ResolveBuffer(clientBuffer_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS && clientBuffer_ != nullptr, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "ResolveBuffer failed", true), "ResolveBuffer failed:%{public}d", ret);

    uint32_t totalSizeInFrame = 0;
    uint32_t byteSizePerFrame = 0;
    ret = clientBuffer_->GetSizeParameter(totalSizeInFrame, spanSizeInFrame_, byteSizePerFrame);

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS && byteSizePerFrame == sizePerFrameInByte_, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_INVALID_PARAM, "ResolveBuffer size mismatch", true), "ResolveBuffer failed:%{public}d", ret);

    clientSpanSizeInByte_ = spanSizeInFrame_ * byteSizePerFrame;

    AUDIO_INFO_LOG("totalSizeInFrame_[%{public}u] spanSizeInFrame_[%{public}u] sizePerFrameInByte_["
        "%{public}zu] clientSpanSizeInByte_[%{public}zu]", totalSizeInFrame, spanSizeInFrame_, sizePerFrameInByte_,
        clientSpanSizeInByte_);

    return SUCCESS;
}

// InitCacheBuffer should be able to modify the cache size between clientSpanSizeInByte_ and 4 * clientSpanSizeInByte_
int32_t CapturerInClientInner::InitCacheBuffer(size_t targetSize)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientSpanSizeInByte_ != 0, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_ILLEGAL_STATE, "clientSpanSizeInByte_ invalid", true), "clientSpanSizeInByte_ invalid");

    AUDIO_INFO_LOG("old size:%{public}zu, new size:%{public}zu", cacheSizeInByte_, targetSize);
    cacheSizeInByte_ = targetSize;

    if (ringCache_ == nullptr) {
        ringCache_ = AudioRingCache::Create(cacheSizeInByte_);
    } else {
        OptResult result = ringCache_->ReConfig(cacheSizeInByte_, false); // false --> clear buffer
        if (result.ret != OPERATION_SUCCESS) {
            AUDIO_ERR_LOG("ReConfig AudioRingCache to size %{public}u failed:ret%{public}zu", result.ret, targetSize);
            return ERR_OPERATION_FAILED;
        }
    }

    return SUCCESS;
}

void CapturerInClientInner::InitDfxOperation()
{
    DumpFileUtil::CloseDumpFile(&dumpInFd_);
    dumpInFile_ = std::to_string(sessionId_) + "_" + std::to_string(clientConfig_.streamInfo.customSampleRate == 0 ?
        clientConfig_.streamInfo.samplingRate : clientConfig_.streamInfo.customSampleRate) + "_" +
        std::to_string(clientConfig_.streamInfo.channels) + "_" + std::to_string(clientConfig_.streamInfo.format) +
        "_capturer_client_in.pcm";
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_CLIENT_PARA, dumpInFile_, &dumpInFd_);
}

int32_t CapturerInClientInner::InitIpcStream(const AudioPlaybackCaptureConfig &filterConfig)
{
    AUDIO_INFO_LOG("Init Ipc stream");
    AudioProcessConfig config = ConstructConfig();

    sptr<IStandardAudioService> gasp = CapturerInClientInner::GetAudioServerProxy();
    CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(gasp != nullptr, ERR_OPERATION_FAILED,
        HILOG_COMM_ERROR("[InitIpcStream]Create failed, can not get service."),
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "[InitIpcStream]Create failed, can not get service.", true));
    int32_t errorCode = 0;
    ipcProxy_ = nullptr;
    gasp->CreateAudioProcess(config, errorCode, filterConfig, ipcProxy_);
    for (int32_t retrycount = 0; (errorCode == ERR_RETRY_IN_CLIENT) && (retrycount < MAX_RETRY_COUNT); retrycount++) {
        AUDIO_WARNING_LOG("retry in client");
        std::this_thread::sleep_for(std::chrono::milliseconds(RETRY_WAIT_TIME_MS));
        gasp->CreateAudioProcess(config, errorCode, filterConfig, ipcProxy_);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(errorCode == SUCCESS, errorCode,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "create audio stream fail", true), "failed with create audio stream fail.");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcProxy_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_NULL_POINTER, "ipcProxy is null", true),
        "failed with null ipcProxy.");
    ipcStream_ = iface_cast<IIpcStream>(ipcProxy_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_NULL_POINTER, "iface_cast IIpcStream failed", true), "failed when iface_cast.");

    // in plan: old listener_ is destoried here, will server receive dieth notify?
    listener_ = sptr<IpcStreamListenerImpl>::MakeSptr(shared_from_this());
    int32_t ret = ipcStream_->RegisterStreamListener(listener_->AsObject());
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "RegisterStreamListener failed", true),
        "RegisterStreamListener failed:%{public}d", ret);

    ret = InitSharedBuffer();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "InitSharedBuffer fail", true), "InitSharedBuffer failed:%{public}d", ret);

    ret = InitCacheBuffer(clientSpanSizeInByte_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "InitCacheBuffer failed", true), "InitCacheBuffer failed:%{public}d", ret);

    ret = ipcStream_->GetAudioSessionID(sessionId_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_OPERATION_FAILED, "GetAudioSessionID fail", true), "GetAudioSessionID fail:%{public}d", ret);

    InitDfxOperation();
    InitCallbackHandler();
    return SUCCESS;
}

int32_t CapturerInClientInner::GetAudioStreamInfo(AudioStreamParams &info)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(paramsIsSet_ == true, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Params is not set", true), "Params is not set");
    info = streamParams_;
    return SUCCESS;
}

int32_t CapturerInClientInner::GetAudioSessionID(uint32_t &sessionID)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG((state_ != RELEASED) && (state_ != NEW), ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "State error", true), "State error %{public}d", state_.load());
    sessionID = sessionId_;
    return SUCCESS;
}

void CapturerInClientInner::GetAudioPipeType(AudioPipeType &pipeType)
{
    pipeType = capturerInfo_.pipeType;
}

State CapturerInClientInner::GetState()
{
    return state_;
}

StreamFocusState CapturerInClientInner::GetFocusState()
{
    std::lock_guard lock(focusStatusMutex_);
    return streamFocusState_;
}
 
void CapturerInClientInner::SetFocusState(StreamFocusState state)
{
    std::lock_guard lock(focusStatusMutex_);
    streamFocusState_ = state;
}

bool CapturerInClientInner::GetAudioTimeInner(
    Timestamp &timestamp, Timestamp::Timestampbase base, int64_t latency)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(paramsIsSet_ == true, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Params is not set", true), "Params is not set");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ != STOPPED, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Invalid status", true), "Invalid status:%{public}d", state_.load());
    uint64_t currentReadPos = totalBytesRead_ / sizePerFrameInByte_;
    timestamp.framePosition = currentReadPos > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(currentReadPos);

    uint64_t writePos = 0;
    int64_t handleTime = 0;
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "invalid buffer status", true), "invalid buffer status");
    clientBuffer_->GetHandleInfo(writePos, handleTime);
    if (writePos == 0 || handleTime == 0) {
        AUDIO_WARNING_LOG("GetHandleInfo may failed");
    }

    int64_t deltaPos = writePos >= currentReadPos ? static_cast<int64_t>(writePos - currentReadPos) : 0;
    int64_t deltaTime = deltaPos * AUDIO_MS_PER_SECOND /
        static_cast<int64_t>(streamParams_.samplingRate) * AUDIO_US_PER_S;
    handleTime = handleTime + deltaTime + latency;

    timestamp.time.tv_sec = static_cast<time_t>(handleTime / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(handleTime % AUDIO_NS_PER_SECOND);

    return true;
}

bool CapturerInClientInner::GetAudioTime(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    int64_t tempLatency = 25000000; // 25000000 -> 25 ms
    return GetAudioTimeInner(timestamp, base, tempLatency);
}

bool CapturerInClientInner::GetTimeStampInfo(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(paramsIsSet_ == true, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Params is not set", true), "Params is not set");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ != STOPPED, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Invalid status", true), "Invalid status:%{public}d", state_.load());
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "invalid buffer status", true), "invalid buffer status");

    if (capturerInfo_.sourceType == SOURCE_TYPE_PLAYBACK_CAPTURE) {
        return GetAudioTimeInner(timestamp, base, 0);
    }

    uint64_t writePos = 0;
    uint64_t writeTimeStamp = 0;
    clientBuffer_->GetTimeStampInfo(writePos, writeTimeStamp);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(writeTimeStamp != 0, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "writeTimeStamp is zero", true), "writeTimeStamp is zero");
    AUDIO_DEBUG_LOG("pos:%{public}" PRIu64 " ts:%{public}" PRIu64, writePos, writeTimeStamp);

    timestamp.framePosition = writePos > static_cast<uint64_t>(INT64_MAX) ?
        INT64_MAX : static_cast<int64_t>(writePos);
    timestamp.time.tv_sec = static_cast<time_t>(writeTimeStamp / AUDIO_NS_PER_SECOND);
    timestamp.time.tv_nsec = static_cast<time_t>(writeTimeStamp % AUDIO_NS_PER_SECOND);

    return true;
}

bool CapturerInClientInner::GetAudioPosition(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    return GetAudioTime(timestamp, base);
}

void CapturerInClientInner::SetSwitchInfoTimestamp(
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePair,
    std::vector<std::pair<uint64_t, uint64_t>> lastFramePosAndTimePairWithSpeed)
{
    (void)lastFramePosAndTimePair;
    (void)lastFramePosAndTimePairWithSpeed;
    AUDIO_INFO_LOG("capturer stream not support timestamp re-set when stream switching");
}

int32_t CapturerInClientInner::GetBufferSize(size_t &bufferSize)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ != RELEASED, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Capturer stream is released", true), "Capturer stream is released");
    bufferSize = clientSpanSizeInByte_;
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        bufferSize = cbBufferSize_;
    }
    AUDIO_DEBUG_LOG("Buffer size is %{public}zu, mode is %{public}s", bufferSize, capturerMode_ == CAPTURE_MODE_NORMAL ?
        "CAPTURE_MODE_NORMAL" : "CAPTURE_MODE_CALLBACK");
    return SUCCESS;
}

int32_t CapturerInClientInner::GetFrameCount(uint32_t &frameCount)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ != RELEASED, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Capturer stream is released", true), "Capturer stream is released");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(sizePerFrameInByte_ != 0, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "sizePerFrameInByte_ is 0", true), "sizePerFrameInByte_ is 0!");
    frameCount = spanSizeInFrame_;
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        frameCount = cbBufferSize_ / sizePerFrameInByte_;
    }
    AUDIO_INFO_LOG("Frame count is %{public}u, mode is %{public}s", frameCount, capturerMode_ == CAPTURE_MODE_NORMAL ?
        "CAPTURE_MODE_NORMAL" : "CAPTURE_MODE_CALLBACK");
    return SUCCESS;
}

int32_t CapturerInClientInner::GetLatency(uint64_t &latency)
{
    // GetLatency is never called in audio_capturer.cpp
    latency = 150000; // unit is us, 150000 is 150ms
    return ERROR;
}

int32_t CapturerInClientInner::SetAudioStreamType(AudioStreamType audioStreamType)
{
    AUDIO_ERR_LOG("Change stream type %{public}d to %{public}d is not supported", eStreamType_, audioStreamType);
    return ERROR;
}

int32_t CapturerInClientInner::SetVolume(float volume)
{
    AUDIO_WARNING_LOG("SetVolume is only for renderer");
    return ERROR;
}

float CapturerInClientInner::GetVolume()
{
    AUDIO_WARNING_LOG("GetVolume is only for renderer");
    return 0.0;
}

int32_t CapturerInClientInner::SetLoudnessGain(float loudnessGain)
{
    AUDIO_WARNING_LOG("SetLoudnessGain is only for renderer");
    return ERROR;
}

float CapturerInClientInner::GetLoudnessGain()
{
    AUDIO_WARNING_LOG("GetLoudnessGain is only for renderer");
    return 0.0;
}

int32_t CapturerInClientInner::SetMute(bool mute, StateChangeCmdType cmdType)
{
    AUDIO_WARNING_LOG("only for renderer");
    return ERROR;
}

int32_t CapturerInClientInner::SetBackMute(bool backMute)
{
    AUDIO_WARNING_LOG("only for renderer");
    return ERROR;
}

bool CapturerInClientInner::GetMute()
{
    AUDIO_WARNING_LOG("only for renderer");
    return false;
}

int32_t CapturerInClientInner::SetMuteHint(bool mute)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "ipcStream is null", true), "ipcStream is null");
    return ipcStream_->SetMuteHint(mute);
}

int32_t CapturerInClientInner::SetDuckVolume(float volume)
{
    AUDIO_WARNING_LOG("only for renderer");
    return ERROR;
}

float CapturerInClientInner::GetDuckVolume()
{
    AUDIO_WARNING_LOG("only for renderer");
    return ERROR_VOLUME;
}

int32_t CapturerInClientInner::SetSpeed(float speed)
{
    AUDIO_ERR_LOG("SetSpeed is not supported");
    return ERROR;
}

int32_t CapturerInClientInner::SetPitch(float pitch)
{
    AUDIO_ERR_LOG("SetPitch is not supported");
    return ERROR;
}

int32_t CapturerInClientInner::SetSonicPitch(float pitch)
{
    AUDIO_ERR_LOG("SetSonicPitch is not supported");
    return ERROR;
}

float CapturerInClientInner::GetSpeed()
{
    AUDIO_ERR_LOG("GetSpeed is not supported");
    return 1.0;
}

void CapturerInClientInner::FillCapturerClientOnlyInfo(AudioDebugInfo &debugInfo)
{
    Timestamp timestamp;
    if (GetAudioTime(timestamp, Timestamp::Timestampbase::MONOTONIC)) {
        debugInfo.captureTimestamp = timestamp;
    }

    size_t bufferSize = 0;
    if (GetBufferSize(bufferSize) == SUCCESS) {
        debugInfo.captureBufferSize = bufferSize;
    }

    debugInfo.captureOverflowCount = GetOverflowCount();
}

void CapturerInClientInner::FillCapturerDeviceInfo(AudioDebugInfo &debugInfo, uint32_t sessionId)
{
    std::vector<std::shared_ptr<AudioCapturerChangeInfo>> changeInfos;
    auto &policyMgr = AudioPolicyManager::GetInstance();
    int32_t ret = policyMgr.GetCurrentCapturerChangeInfos(changeInfos);
    if (ret != SUCCESS) {
        AUDIO_WARNING_LOG("GetCurrentCapturerChangeInfos failed:%{public}d", ret);
        return;
    }
    for (const auto &info : changeInfos) {
        if (info == nullptr) {
            continue;
        }
        if (info->sessionId == static_cast<int32_t>(sessionId)) {
            debugInfo.inputDeviceInfo = info->inputDeviceInfo;
            break;
        }
    }
}

int32_t CapturerInClientInner::GetAudioDebugInfo(AudioDebugInfo &debugInfo)
{
    AUDIO_DEBUG_LOG("GetAudioDebugInfo enter");
    uint32_t sessionId = UINT32_MAX;
    if (GetAudioSessionID(sessionId) != SUCCESS) {
        AUDIO_WARNING_LOG("GetAudioSessionID failed");
    }

    if (sessionId != UINT32_MAX) {
        int32_t ret = AudioPolicyManager::GetInstance().GetAudioDebugInfo(sessionId, debugInfo);
        if (ret == SUCCESS) {
            FillCapturerClientOnlyInfo(debugInfo);
            FillCapturerDeviceInfo(debugInfo, sessionId);
            StreamDfxManager::GetErrorInfosFromMedia(debugInfo.errorInfos);
            return SUCCESS;
        }
        AUDIO_WARNING_LOG("GetAudioDebugInfo failed, sessionId:%{public}u, ret:%{public}d", sessionId, ret);
    }

    debugInfo.sessionId = sessionId;
    GetAudioStreamInfo(debugInfo.streamParams);
    *debugInfo.capturerInfo = capturerInfo_;
    debugInfo.capturerInfo->samplingRate = static_cast<AudioSamplingRate>(debugInfo.streamParams.samplingRate);
    debugInfo.capturerInfo->encodingType = static_cast<uint8_t>(debugInfo.streamParams.encoding);
    debugInfo.capturerInfo->channelLayout = debugInfo.streamParams.channelLayout;

    FillCapturerClientOnlyInfo(debugInfo);
    FillCapturerDeviceInfo(debugInfo, sessionId);
    StreamDfxManager::GetErrorInfosFromMedia(debugInfo.errorInfos);
    return SUCCESS;
}


int32_t CapturerInClientInner::SetRenderRate(AudioRendererRate renderRate)
{
    AUDIO_WARNING_LOG("SetRenderRate is only for renderer");
    return ERROR;
}

AudioRendererRate CapturerInClientInner::GetRenderRate()
{
    AUDIO_WARNING_LOG("GetRenderRate is only for renderer");
    return RENDER_RATE_NORMAL; // not supported
}

int32_t CapturerInClientInner::SetStreamCallback(const std::shared_ptr<AudioStreamCallback> &callback)
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

int32_t CapturerInClientInner::SetRenderMode(AudioRenderMode renderMode)
{
    AUDIO_WARNING_LOG("SetRenderMode is only for renderer");
    return ERROR;
}

AudioRenderMode CapturerInClientInner::GetRenderMode()
{
    AUDIO_WARNING_LOG("GetRenderMode is only for renderer");
    return RENDER_MODE_NORMAL; // not supported
}

int32_t CapturerInClientInner::SetRendererWriteCallback(const std::shared_ptr<AudioRendererWriteCallback> &callback)
{
    AUDIO_WARNING_LOG("SetRendererWriteCallback is only for renderer");
    return ERROR;
}

void CapturerInClientInner::InitCallbackBuffer(uint64_t bufferDurationInUs)
{
    if (bufferDurationInUs > MAX_BUF_DURATION_IN_USEC) {
        AUDIO_ERR_LOG("InitCallbackBuffer with invalid duration %{public}" PRIu64", use default instead.",
            bufferDurationInUs);
        bufferDurationInUs = DEFAULT_BUF_DURATION_IN_USEC;
    }
    // Calculate buffer size based on duration.
    cbBufferSize_ = static_cast<size_t>(bufferDurationInUs * streamParams_.samplingRate / AUDIO_US_PER_S) *
        sizePerFrameInByte_;
    AUDIO_INFO_LOG("InitCallbackBuffer with duration %{public}" PRIu64", size: %{public}zu", bufferDurationInUs,
        cbBufferSize_);
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    cbBuffer_ = std::make_unique<uint8_t[]>(cbBufferSize_);
    BufferDesc temp = {cbBuffer_.get(), cbBufferSize_, cbBufferSize_};
    cbBufferQueue_.Clear();
    cbBufferQueue_.Push(temp);
}

void CapturerInClientInner::InitCallbackLoop()
{
    cbThreadReleased_ = false;
    auto weakRef = weak_from_this();

    // OS_AudioWriteCB
    ResetCallbackLoopTid();
    callbackLoop_ = std::thread([weakRef] {
        bool keepRunning = true;
        std::shared_ptr<CapturerInClientInner> strongRef = weakRef.lock();
        strongRef->SetCallbackLoopTid(gettid());
        if (strongRef != nullptr) {
            strongRef->cbThreadCv_.notify_one();
            AUDIO_INFO_LOG("Thread start, sessionID :%{public}d", strongRef->sessionId_);
        } else {
            AUDIO_WARNING_LOG("Strong ref is nullptr, could cause error");
        }
        strongRef = nullptr;
        // start loop
        while (keepRunning) {
            strongRef = weakRef.lock();
            if (strongRef == nullptr) {
                AUDIO_INFO_LOG("CapturerInClientInner destroyed");
                break;
            }
            keepRunning = strongRef->ReadCallbackFunc(); // Main operation in callback loop
        }
        if (strongRef != nullptr) {
            AUDIO_INFO_LOG("CBThread end sessionID :%{public}d", strongRef->sessionId_);
        }
    });
    pthread_setname_np(callbackLoop_.native_handle(), "OS_AudioReadCb");
}

int32_t CapturerInClientInner::SetCaptureMode(AudioCaptureMode captureMode)
{
    AUDIO_INFO_LOG("Set mode to %{public}s", captureMode == CAPTURE_MODE_NORMAL ? "CAPTURE_MODE_NORMAL" :
        "CAPTURE_MODE_CALLBACK");
    if (capturerMode_ == captureMode) {
        return SUCCESS;
    }

    // capturerMode_ is inited as CAPTURE_MODE_NORMAL, can only be set to CAPTURE_MODE_CALLBACK.
    if (capturerMode_ == CAPTURE_MODE_CALLBACK && captureMode == CAPTURE_MODE_NORMAL) {
        AUDIO_ERR_LOG("Set capturer mode from callback to normal is not supported.");
        return ERR_INCORRECT_MODE;
    }

    // state check
    if (state_ != PREPARED && state_ != NEW) {
        AUDIO_ERR_LOG("Set capturer mode failed. invalid state:%{public}d", state_.load());
        return ERR_ILLEGAL_STATE;
    }
    capturerMode_ = captureMode;
    CHECK_AND_RETURN_RET_LOG(capturerInfo_.isLoopback == false, SUCCESS, "loopback no need InitCallbackLoop");
    // init callbackLoop_
    InitCallbackLoop();

    std::unique_lock<std::mutex> threadStartlock(statusMutex_);
    bool stopWaiting = cbThreadCv_.wait_for(threadStartlock, std::chrono::milliseconds(SHORT_TIMEOUT_IN_MS), [this] {
        return cbThreadReleased_ == false; // When thread is started, cbThreadReleased_ will be false. So stop waiting.
    });
    if (!stopWaiting) {
        AUDIO_WARNING_LOG("Init OS_AudioReadCB thread time out");
    }

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(streamParams_.samplingRate != 0, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "invalid sample rate", true), "invalid sample rate");

    uint64_t bufferDurationInUs = spanSizeInFrame_ * AUDIO_US_PER_S / streamParams_.samplingRate;
    InitCallbackBuffer(bufferDurationInUs);
    return SUCCESS;
}

AudioCaptureMode CapturerInClientInner::GetCaptureMode()
{
    AUDIO_INFO_LOG("capturer mode is %{public}s", capturerMode_ == CAPTURE_MODE_NORMAL ? "CAPTURE_MODE_NORMAL" :
        "CAPTURE_MODE_CALLBACK");
    return capturerMode_;
}

int32_t CapturerInClientInner::SetCapturerReadCallback(const std::shared_ptr<AudioCapturerReadCallback> &callback)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(callback != nullptr, ERR_INVALID_PARAM,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_INVALID_PARAM, "Invalid null callback", true), "Invalid null callback");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(capturerMode_ == CAPTURE_MODE_CALLBACK, ERR_INCORRECT_MODE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_INVALID_OPERATION, "incorrect capturer mode", true), "incorrect capturer mode");
    std::lock_guard<std::mutex> lock(readCbMutex_);
    readCb_ = callback;
    return SUCCESS;
}

int32_t CapturerInClientInner::SetCapturerMetaDataCallback(
    const std::shared_ptr<AudioCapturerMetaDataCallback> &callback)
{
    CHECK_AND_RETURN_RET_LOG(callback != nullptr, ERR_INVALID_PARAM, "Invalid null callback");
    std::lock_guard<std::mutex> lock(metaDataCbMutex_);
    metaDataCb_ = callback;
    return SUCCESS;
}

bool CapturerInClientInner::WaitForRunning()
{
    Trace trace("CapturerInClientInner::WaitForRunning");
    // check capturer state_: call client write only in running else wait on statusMutex_
    std::unique_lock<std::mutex> stateLock(statusMutex_);
    if (state_ != RUNNING) {
        bool stopWaiting = cbThreadCv_.wait_for(stateLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
            return state_ == RUNNING || cbThreadReleased_;
        });
        if (cbThreadReleased_) {
            AUDIO_INFO_LOG("CBThread end in non-running status, sessionID :%{public}d", sessionId_);
            return false;
        }
        if (!stopWaiting) {
            AUDIO_INFO_LOG("Wait timeout, current state_ is %{public}d", state_.load()); // wait 0.5s
            return false;
        }
    }
    return true;
}

bool CapturerInClientInner::ReadCallbackFunc()
{
    if (cbThreadReleased_) {
        return false;
    }
    Trace traceLoop("CapturerInClientInner::WriteCallbackFunc");
    if (!WaitForRunning()) {
        return true;
    }

    // If client didn't call GetBufferDesc/Enqueue in OnReadData, pop will block here.
    BufferDesc temp = cbBufferQueue_.Pop();
    if (temp.buffer == nullptr) {
        AUDIO_WARNING_LOG("Queue pop error: get nullptr.");
        return false;
    }

    // call read here.
    int32_t result = Read(*temp.buffer, temp.bufLength, true); // blocking read
    std::unique_lock<std::mutex> lockBuffer(cbBufferMutex_);
    if (result < 0 || result != static_cast<int32_t>(cbBufferSize_)) {
        AUDIO_WARNING_LOG("Call read error, ret:%{public}d, cbBufferSize_:%{public}zu", result, cbBufferSize_);
    }
    if (state_ != RUNNING) {
        return true;
    }
    lockBuffer.unlock();

    // call client read
    Trace traceCb("CapturerInClientInner::OnReadData");
    std::unique_lock<std::mutex> lockCb(readCbMutex_);
    if (readCb_ != nullptr) {
        readCb_->OnReadData(cbBufferSize_);
    }
    lockCb.unlock();
    traceCb.End();
    return true;
}


int32_t CapturerInClientInner::GetBufferDesc(BufferDesc &bufDesc)
{
    Trace trace("CapturerInClientInner::GetBufferDesc");
    if (capturerMode_ != CAPTURE_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Not supported. mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    bufDesc.buffer = cbBuffer_.get();
    bufDesc.bufLength = cbBufferSize_;
    bufDesc.dataLength = cbBufferSize_;
    return SUCCESS;
}

int32_t CapturerInClientInner::GetBufQueueState(BufferQueueState &bufState)
{
    Trace trace("CapturerInClientInner::GetBufQueueState");
    if (capturerMode_ != CAPTURE_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Not supported, mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    // only one buffer in queue.
    bufState.numBuffers = 1;
    bufState.currentIndex = 0;
    return SUCCESS;
}

int32_t CapturerInClientInner::Enqueue(const BufferDesc &bufDesc)
{
    Trace trace("CapturerInClientInner::Enqueue");
    if (capturerMode_ != CAPTURE_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Not supported, mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    CHECK_AND_RETURN_RET_LOG(state_ != RELEASED, ERR_ILLEGAL_STATE, "Invalid state: %{public}d", state_.load());
    std::lock_guard<std::mutex> lock(cbBufferMutex_);

    if (bufDesc.bufLength != cbBufferSize_ || bufDesc.dataLength != cbBufferSize_) {
        AUDIO_ERR_LOG("Enqueue invalid bufLength:%{public}zu or dataLength:%{public}zu, should be %{public}zu",
            bufDesc.bufLength, bufDesc.dataLength, cbBufferSize_);
        return ERR_INVALID_INDEX;
    }
    if (bufDesc.buffer != cbBuffer_.get()) {
        AUDIO_WARNING_LOG("Enqueue buffer is not from us.");
    }

    // if Enqueue is not called in OnReadData, loop thread will block on pop, wait for the Push call here.
    BufferDesc temp = {cbBuffer_.get(), cbBufferSize_, cbBufferSize_};
    cbBufferQueue_.Push(temp);
    // Call read may block, so put it in loop callbackLoop_
    return SUCCESS;
}

int32_t CapturerInClientInner::Clear()
{
    Trace trace("CapturerInClientInner::Clear");
    if (capturerMode_ != CAPTURE_MODE_CALLBACK) {
        AUDIO_ERR_LOG("Not supported, mode is not callback.");
        return ERR_INCORRECT_MODE;
    }
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    int32_t ret = memset_s(cbBuffer_.get(), cbBufferSize_, 0, cbBufferSize_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == EOK, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_SEND_DATA_OPERATION_FAILED, "Clear buffer fail", true), "Clear buffer fail, ret %{public}d.", ret);
    return SUCCESS;
}

int32_t CapturerInClientInner::SetLowPowerVolume(float volume)
{
    AUDIO_WARNING_LOG("SetLowPowerVolume is only for renderer");
    return ERROR;
}

float CapturerInClientInner::GetLowPowerVolume()
{
    AUDIO_WARNING_LOG("GetLowPowerVolume is only for renderer");
    return 0.0;
}

int32_t CapturerInClientInner::SetOffloadMode(int32_t state, bool isAppBack)
{
    AUDIO_WARNING_LOG("SetOffloadMode is only for renderer");
    return ERROR;
}

int32_t CapturerInClientInner::UnsetOffloadMode()
{
    AUDIO_WARNING_LOG("UnsetOffloadMode is only for renderer");
    return ERROR;
}

float CapturerInClientInner::GetSingleStreamVolume()
{
    AUDIO_WARNING_LOG("GetSingleStreamVolume is only for renderer");
    return 0.0;
}

AudioEffectMode CapturerInClientInner::GetAudioEffectMode()
{
    AUDIO_WARNING_LOG("GetAudioEffectMode is only for renderer");
    return EFFECT_NONE;
}

int32_t CapturerInClientInner::SetAudioEffectMode(AudioEffectMode effectMode)
{
    AUDIO_WARNING_LOG("SetAudioEffectMode is only for renderer");
    return ERROR;
}

int64_t CapturerInClientInner::GetFramesWritten()
{
    AUDIO_WARNING_LOG("GetFramesWritten is only for renderer");
    return -1;
}

int64_t CapturerInClientInner::GetFramesRead()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(sizePerFrameInByte_ != 0, INVALID_FRAME_SIZE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "sizePerFrameInByte_ is 0", true), "sizePerFrameInByte_ is 0!");
    uint64_t readFrameNumber = totalBytesRead_ / sizePerFrameInByte_;
    return readFrameNumber;
}

// Will only take effect before SetAudioStreaminfo
void CapturerInClientInner::SetInnerCapturerState(bool isInnerCapturer)
{
    isInnerCapturer_ = isInnerCapturer;
    AUDIO_INFO_LOG("SetInnerCapturerState %{public}s", (isInnerCapturer_ ? "true" : "false"));
    return;
}

// Will only take effect before SetAudioStreaminfo
void CapturerInClientInner::SetWakeupCapturerState(bool isWakeupCapturer)
{
    isWakeupCapturer_ = isWakeupCapturer;
    AUDIO_INFO_LOG("SetWakeupCapturerState %{public}s", (isWakeupCapturer_ ? "true" : "false"));
    return;
}

void CapturerInClientInner::SetCapturerSource(int capturerSource)
{
    // capturerSource is kept in capturerInfo_, no need to be set again.
    (void)capturerSource;
    return;
}

void CapturerInClientInner::SetPrivacyType(AudioPrivacyType privacyType)
{
    AUDIO_WARNING_LOG("SetPrivacyType is only for renderer");
    return;
}

void CapturerInClientInner::SendAudioErrorEventAndProcessOther(int32_t uid, int32_t errorCode,
    const std::string &erroDesc, bool isClient, State state)
{
    StreamDfxManager::GetInstance().SendAudioErrorEvent(uid, errorCode, erroDesc, isClient);
    streamFocusState_ = static_cast<StreamFocusState>(state);
}

bool CapturerInClientInner::StartAudioStream(StateChangeCmdType cmdType, AudioStreamDeviceChangeReasonExt reason)
{
    Trace trace("CapturerInClientInner::StartAudioStream " + std::to_string(sessionId_));
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ != PREPARED && state_ != STOPPED && state_ != PAUSED) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_START_ILLEGAL_STATE, "Start failed Illegal state", true, state_);
        AUDIO_ERR_LOG("Start failed Illegal state: %{public}d", state_.load());
        return false;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_START_ILLEGAL_STATE, "ipcStream is not inited", true), "ipcStream is not inited!");
    int32_t ret = ipcStream_->Start(readCb_ == nullptr);
    if (ret != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_START_OPERATION_FAILED, "Start call server failed", true, state_);
        AUDIO_ERR_LOG("Start call server failed: %{public}u", ret);
        return false;
    }

    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return notifiedOperation_ == START_STREAM; // will be false when got notified.
    });

    if (notifiedOperation_ != START_STREAM || notifiedResult_ != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_START_OPERATION_FAILED, "Start failed", true, state_);
        AUDIO_ERR_LOG("Start failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        return false;
    }
    waitLock.unlock();

    if (capturerMode_ == CAPTURE_MODE_NORMAL) {
        normalReadGeneration_.fetch_add(1);
    }
    UpdateStreamState(RUNNING); // change state_ to RUNNING, then notify cbThread
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        if (cbBufferQueue_.IsEmpty()) {
            cbBufferQueue_.Push({cbBuffer_.get(), cbBufferSize_, cbBufferSize_});
        }
        // start the callback-write thread
        cbThreadCv_.notify_all();
    }
    statusLock.unlock();
    // in plan: call HiSysEventWrite
    int64_t param = -1;
    StateCmdTypeToParams(param, state_, cmdType);
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, param);

    AUDIO_INFO_LOG("Start SUCCESS, sessionId: %{public}d, uid: %{public}d", sessionId_, clientUid_);
    UpdateTracker("RUNNING");
    return true;
}

void CapturerInClientInner::SetPlaybackCaptureStartStateCallback(
    const std::shared_ptr<AudioCapturerOnPlaybackCaptureStartCallback> &callback)
{
    std::lock_guard<std::mutex> lock(playbackCaptureStartCallbackMutex_);
    playbackCaptureStartCallback_ = callback;
}
 
int32_t CapturerInClientInner::RequestUserPrivacyAuthority(uint32_t sessionId)
{
    sptr<IStandardAudioService> gasp = CapturerInClientInner::GetAudioServerProxy();
    if (gasp == nullptr) {
        AUDIO_ERR_LOG("LatencyMeas failed to get AudioServerProxy");
        return ERROR;
    }
    gasp->RequestUserPrivacyAuthority(sessionId);
 
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS * 5), [this] {
        return notifiedOperation_ == USER_PRIVACY_AUTHORITY; // will be false when got notified.
    });
    Operation operation = notifiedOperation_;
    int64_t result = notifiedResult_;
    waitLock.unlock();
 
    std::unique_lock<std::mutex> lock(playbackCaptureStartCallbackMutex_);
    CHECK_AND_CALL_FUNC_RETURN_RET(playbackCaptureStartCallback_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_ILLEGAL_STATE, "playbackCaptureStartCallback_ is nullptr", true));
    if (operation != USER_PRIVACY_AUTHORITY) {
        AUDIO_ERR_LOG("authorization failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), operation, result);
        playbackCaptureStartCallback_->OnPlaybackCaptureStartResult(START_STATE_FAILED);
        return ERROR;
    }
    playbackCaptureStartCallback_->OnPlaybackCaptureStartResult(
        static_cast<PlaybackCaptureStartState>(notifiedResult_));
    lock.unlock();
 
    return SUCCESS;
}

bool CapturerInClientInner::PauseAudioStream(StateChangeCmdType cmdType)
{
    Trace trace("CapturerInClientInner::PauseAudioStream " + std::to_string(sessionId_));
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ != RUNNING) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_PAUSE_ILLEGAL_STATE, "Pause State is not RUNNING", true, state_);
        AUDIO_ERR_LOG("Pause State is not RUNNING. Illegal state:%{public}u", state_.load());
        return false;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_PAUSE_ILLEGAL_STATE, "ipcStream is not inited", true), "ipcStream is not inited!");
    int32_t ret = ipcStream_->Pause();
    if (ret != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_PAUSE_OPERATION_FAILED, "Pause call server failed", true, state_);
        AUDIO_ERR_LOG("Pause call server failed:%{public}u", ret);
        return false;
    }
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return notifiedOperation_ == PAUSE_STREAM; // will be false when got notified.
    });

    if (notifiedOperation_ != PAUSE_STREAM || notifiedResult_ != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_PAUSE_OPERATION_FAILED, "Pause failed", true, state_);
        AUDIO_ERR_LOG("Pause failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        return false;
    }
    waitLock.unlock();

    UpdateStreamState(PAUSED);
    RetireNormalReadsLocked();
    statusLock.unlock();

    // waiting for review: use send event to clent with cmdType | call OnStateChange | call HiSysEventWrite
    int64_t param = -1;
    StateCmdTypeToParams(param, state_, cmdType);
    SafeSendCallbackEvent(STATE_CHANGE_EVENT, param);

    AUDIO_INFO_LOG("Pause SUCCESS, sessionId: %{public}d, uid: %{public}d, mode %{public}s", sessionId_, clientUid_,
        capturerMode_ == CAPTURE_MODE_NORMAL ? "CAPTURE_MODE_NORMAL" : "CAPTURE_MODE_CALLBACK");
    UpdateTracker("PAUSED");
    return true;
}

bool CapturerInClientInner::StopAudioStream()
{
    Trace trace("CapturerInClientInner::StopAudioStream " + std::to_string(sessionId_));
    AUDIO_INFO_LOG("Stop begin for sessionId %{public}d uid: %{public}d", sessionId_, clientUid_);
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ == STOPPED) {
        streamFocusState_ = static_cast<StreamFocusState>(STOPPED);
        return true;
    }
    if ((state_ != RUNNING) && (state_ != PAUSED)) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_STOP_ILLEGAL_STATE, "Stop failed. Illegal state", true, state_);
        AUDIO_ERR_LOG("Stop failed. Illegal state:%{public}u", state_.load());
        return false;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_STOP_ILLEGAL_STATE, "ipcStream is not inited", true), "ipcStream is not inited!");
    int32_t ret = ipcStream_->Stop();
    if (ret != SUCCESS) {
        SendAudioErrorEventAndProcessOther(static_cast<int32_t>(getuid()),
            RECORD_STOP_OPERATION_FAILED, "Stop call server failed", true, state_);
        AUDIO_ERR_LOG("Stop call server failed:%{public}u", ret);
        return false;
    }

    // An accepted Stop retires normal reads before waiting for its acknowledgement.
    // Do not expose a new normal-mode state or wait for a reader under statusMutex_.
    RetireNormalReadsLocked();
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        UpdateStreamState(STOPPING);
        clientBuffer_->WakeFutex();
        AUDIO_INFO_LOG("Stop begin in callback mode sessionId %{public}d uid: %{public}d", sessionId_, clientUid_);
    }

    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock,
        std::chrono::milliseconds(OPERATION_TIMEOUT_FOR_STOP_IN_MS), [this] {
            return notifiedOperation_ == STOP_STREAM; // will be false when got notified.
        });

    if (notifiedOperation_ != STOP_STREAM || notifiedResult_ != SUCCESS) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_STOP_OPERATION_FAILED, "Stop failed", true);
        AUDIO_ERR_LOG("Stop failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        UpdateStreamState(INVALID);
        RetireNormalReadsLocked();
        return false;
    }
    waitLock.unlock();

    UpdateStreamState(STOPPED);
    statusLock.unlock();

    SafeSendCallbackEvent(STATE_CHANGE_EVENT, state_);

    AUDIO_INFO_LOG("Stop SUCCESS, sessionId: %{public}d, uid: %{public}d", sessionId_, clientUid_);
    UpdateTracker("STOPPED");
    return true;
}

bool CapturerInClientInner::ReleaseAudioStream(bool releaseRunner, bool isSwitchStream)
{
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if (state_ == RELEASED) {
        DumpFileUtil::CloseDumpFile(&dumpMetaDataFile_);
        dumpMetaDataFileName_.clear();
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_RELEASE_ILLEGAL_STATE, "Already release, do nothing", true);
        AUDIO_WARNING_LOG("Already release, do nothing");
        return true;
    }
    UpdateStreamState(RELEASED);
    RetireNormalReadsLocked(); // Wake before remote Release or callback-thread teardown.
    statusLock.unlock();

    Trace trace("CapturerInClientInner::ReleaseAudioStream " + std::to_string(sessionId_));
    if (ipcStream_ != nullptr) {
        ipcStream_->Release(isSwitchStream);
    } else {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_RELEASE_ILLEGAL_STATE, "Release while ipcStream is null", true);
        AUDIO_WARNING_LOG("Release while ipcStream is null");
    }

    ReleaseCallbackResources(releaseRunner);
    FinalizeRelease();
    return true;
}

void CapturerInClientInner::ReleaseCallbackResources(bool releaseRunner)
{
    // no lock, call release in any case, include blocked case.
    {
        std::lock_guard<std::mutex> runnerlock(runnerMutex_);
        if (releaseRunner && callbackHandler_ != nullptr) {
            AUDIO_INFO_LOG("runner remove");
            callbackHandler_->ReleaseEventRunner();
            runnerReleased_ = true;
            callbackHandler_ = nullptr;
        }
    }

    // clear write callback
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        cbThreadReleased_ = true; // stop loop
        if (cbBufferQueue_.IsEmpty()) {
            cbBufferQueue_.PushNoWait({nullptr, 0, 0});
        }
        cbThreadCv_.notify_all();
        clientBuffer_->WakeFutex();
        if (callbackLoop_.joinable()) {
            callbackLoop_.join();
        }
    }
    paramsIsSet_ = false;
}

void CapturerInClientInner::FinalizeRelease()
{
    {
        std::unique_lock<std::mutex> lock(streamCbMutex_);
        std::shared_ptr<AudioStreamCallback> streamCb = streamCallback_.lock();
        if (streamCb != nullptr) {
            AUDIO_INFO_LOG("Notify client the state is released");
            streamCb->OnStateChange(RELEASED, CMD_FROM_CLIENT);
        }
    }

    UpdateTracker("RELEASED");
    DumpFileUtil::CloseDumpFile(&dumpMetaDataFile_);
    dumpMetaDataFileName_.clear();
    AUDIO_INFO_LOG("Release end, sessionId: %{public}d, uid: %{public}d", sessionId_, clientUid_);
}

bool CapturerInClientInner::FlushAudioStream()
{
    Trace trace("CapturerInClientInner::FlushAudioStream " + std::to_string(sessionId_));
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    if ((state_ != RUNNING) && (state_ != PAUSED) && (state_ != STOPPED)) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "Flush failed. Illegal state", true);
        AUDIO_ERR_LOG("Flush failed. Illegal state:%{public}u", state_.load());
        return false;
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(FlushRingCache() == SUCCESS, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "Flush ringCache failed", true), "Flush ringCache failed");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(FlushCbBuffer() == SUCCESS, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "Flush cbBuffer failed", true), "Flush cbBuffer failed");

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "ipcStream is not inited", true), "ipcStream is not inited!");
    int32_t ret = ipcStream_->Flush();
    if (ret != SUCCESS) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "Flush call server failed", true);
        AUDIO_ERR_LOG("Flush call server failed:%{public}u", ret);
        return false;
    }
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return notifiedOperation_ == FLUSH_STREAM; // will be false when got notified.
    });

    if (notifiedOperation_ != FLUSH_STREAM || notifiedResult_ != SUCCESS) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_FLUSH_ILLEGAL_STATE, "Flush failed", true);
        AUDIO_ERR_LOG("Flush failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        notifiedOperation_ = MAX_OPERATION_CODE;
        return false;
    }
    notifiedOperation_ = MAX_OPERATION_CODE;
    waitLock.unlock();
    AUDIO_INFO_LOG("Flush stream SUCCESS, sessionId: %{public}d", sessionId_);
    return true;
}

int32_t CapturerInClientInner::FlushRingCache()
{
    ringCache_->ResetBuffer();
    return SUCCESS;
}

int32_t CapturerInClientInner::FlushCbBuffer()
{
    Trace trace("CapturerInClientInner::FlushCbBuffer");
    if (cbBuffer_ != nullptr && capturerMode_ == CAPTURE_MODE_CALLBACK) {
        std::lock_guard<std::mutex> lock(cbBufferMutex_);
        int32_t ret = memset_s(cbBuffer_.get(), cbBufferSize_, 0, cbBufferSize_);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == EOK, ERR_OPERATION_FAILED,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_FLUSH_ILLEGAL_STATE, "Clear buffer fail", true), "Clear buffer fail, ret %{public}d.", ret);
        AUDIO_INFO_LOG("Flush cbBuffer_ for sessionId:%{public}d uid:%{public}d, ret:%{public}d",
            sessionId_, clientUid_, ret);
    }
    return SUCCESS;
}

bool CapturerInClientInner::DrainAudioStream(bool stopFlag)
{
    AUDIO_ERR_LOG("Drain is not supported");
    return false;
}

void CapturerInClientInner::SetPreferredFrameSize(int32_t frameSize, bool isRecreate)
{
    AUDIO_INFO_LOG("NSetPreferredFrameSize to %{public}d", frameSize);
    int32_t sampleRate = clientConfig_.streamInfo.samplingRate;
    CHECK_AND_CALL_FUNC_RETURN(sampleRate != 0,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "sampleRate is 0", true));
    int32_t duration = frameSize * AUDIO_US_PER_SECOND / sampleRate * AUDIO_MS_PER_SECOND;
    InitCallbackBuffer(duration);
}

void CapturerInClientInner::UpdateLatencyTimestamp(std::string &timestamp, bool isRenderer)
{
    sptr<IStandardAudioService> gasp = CapturerInClientInner::GetAudioServerProxy();
    if (gasp == nullptr) {
        AUDIO_ERR_LOG("LatencyMeas failed to get AudioServerProxy");
        return;
    }
    gasp->UpdateLatencyTimestamp(timestamp, isRenderer);
}

int32_t CapturerInClientInner::SetRendererFirstFrameWritingCallback(
    const std::shared_ptr<AudioRendererFirstFrameWritingCallback> &callback)
{
    AUDIO_ERR_LOG("SetRendererFirstFrameWritingCallback is not supported for capturer");
    return ERR_INVALID_OPERATION;
}

void CapturerInClientInner::OnFirstFrameWriting()
{
    AUDIO_ERR_LOG("OnFirstFrameWriting is not supported for capturer");
}

int32_t CapturerInClientInner::Write(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer,
    size_t metaBufferSize)
{
    AUDIO_ERR_LOG("Write is not supported");
    return ERR_INVALID_OPERATION;
}

int32_t CapturerInClientInner::Write(uint8_t *buffer, size_t bufferSize)
{
    AUDIO_ERR_LOG("Write is not supported");
    return ERR_INVALID_OPERATION;
}

int32_t CapturerInClientInner::HandleCapturerRead(size_t &readSize, size_t &userSize, uint8_t &buffer,
    bool isBlockingRead)
{
    Trace trace("CapturerInClientInner::HandleCapturerRead " + std::to_string(userSize));
    while (readSize < userSize) {
        AUDIO_DEBUG_LOG("readSize %{public}zu < userSize %{public}zu", readSize, userSize);
        OptResult result = ringCache_->GetReadableSize();
        CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "GetReadableSize err %{public}d", result.ret);
        size_t readableSize = std::min(result.size, userSize - readSize);
        if (readSize + result.size >= userSize) { // If ringCache is sufficient
            result = ringCache_->Dequeue({&buffer + (readSize), readableSize});
            CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "DequeueCache err %{public}d", result.ret);
            readSize += readableSize;
            return readSize; // data size
        }
        if (result.size != 0) {
            result = ringCache_->Dequeue({&buffer + readSize, result.size});
            CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "Dequeue failed %{public}d", result.ret);
            readSize += result.size;
        }
        uint64_t availableSizeInFrame = clientBuffer_->GetCurWriteFrame() - clientBuffer_->GetCurReadFrame();
        AUDIO_DEBUG_LOG("availableSizeInFrame %{public}" PRId64 "", availableSizeInFrame);
        if (availableSizeInFrame > 0) { // If OHAudioBuffer has data
            BufferDesc currentOHBuffer_ = {};
            clientBuffer_->GetTimeStampInfo(currentOHBuffer_.position, currentOHBuffer_.timeStampInNs);
            clientBuffer_->GetReadbuffer(clientBuffer_->GetCurReadFrame(), currentOHBuffer_);
            BufferWrap bufferWrap = {currentOHBuffer_.buffer, clientSpanSizeInByte_};
            ringCache_->Enqueue(bufferWrap);
            memset_s(static_cast<void *>(bufferWrap.dataPtr), bufferWrap.dataSize, 0, bufferWrap.dataSize);
            clientBuffer_->SetCurReadFrame((clientBuffer_->GetCurReadFrame() + spanSizeInFrame_), false);
        } else {
            if (!isBlockingRead) {
                return readSize; // Return buffer immediately
            }
            // wait for server read some data
            constexpr auto timeoutInNano = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS * 100)).count();
            FutexCode futexRet = clientBuffer_->WaitFor(timeoutInNano, [this] {
                return clientBuffer_->GetCurWriteFrame() > clientBuffer_->GetCurReadFrame() || state_ != RUNNING;
            });
            CHECK_AND_RETURN_RET_LOG(state_ == RUNNING, ERR_ILLEGAL_STATE, "State is not running");
            CHECK_AND_RETURN_RET_LOG(futexRet == FUTEX_SUCCESS, ERROR, "Wait timeout or breaked:%{public}d", futexRet);
        }
    }
    return readSize;
}

void CapturerInClientInner::RetireNormalReadsLocked()
{
    if (capturerMode_ != CAPTURE_MODE_NORMAL) {
        return; // Preserve the existing callback-mode queue and wake path.
    }
    normalReadGeneration_.fetch_add(1);
    if (clientBuffer_ != nullptr) {
        clientBuffer_->WakeFutex();
    }
}

bool CapturerInClientInner::NormalReadIsCurrent(uint64_t generation) const
{
    return state_ == RUNNING && normalReadGeneration_.load() == generation;
}

int32_t CapturerInClientInner::HandleNormalCapturerRead(size_t &readSize, size_t userSize, uint8_t &buffer,
    bool isBlockingRead, uint64_t generation)
{
    std::shared_ptr<OHAudioBuffer> audioBuffer;
    {
        std::lock_guard<std::mutex> statusLock(statusMutex_);
        CHECK_AND_RETURN_RET_LOG(NormalReadIsCurrent(generation), ERR_ILLEGAL_STATE, "Normal read retired");
        audioBuffer = clientBuffer_;
        CHECK_AND_RETURN_RET_LOG(audioBuffer != nullptr && ringCache_ != nullptr, ERROR, "Read buffer is null");
    }
    while (readSize < userSize) {
        // All bounded buffer mutations are serialized with retirement. In particular,
        // an old Read queued on readMutex_ cannot consume frames from a later Start.
        std::unique_lock<std::mutex> statusLock(statusMutex_);
        CHECK_AND_RETURN_RET_LOG(NormalReadIsCurrent(generation), ERR_ILLEGAL_STATE, "Normal read retired");
        OptResult result = ringCache_->GetReadableSize();
        CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "GetReadableSize failed");
        size_t readableSize = std::min(result.size, userSize - readSize);
        if (readSize + result.size >= userSize) {
            result = ringCache_->Dequeue({&buffer + readSize, readableSize});
            CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "DequeueCache failed");
            readSize += readableSize;
            return static_cast<int32_t>(readSize);
        }
        if (result.size != 0) {
            result = ringCache_->Dequeue({&buffer + readSize, result.size});
            CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "Dequeue failed");
            readSize += result.size;
        }
        if (audioBuffer->GetCurWriteFrame() > audioBuffer->GetCurReadFrame()) {
            BufferDesc currentBuffer = {};
            audioBuffer->GetTimeStampInfo(currentBuffer.position, currentBuffer.timeStampInNs);
            audioBuffer->GetReadbuffer(audioBuffer->GetCurReadFrame(), currentBuffer);
            BufferWrap bufferWrap = {currentBuffer.buffer, clientSpanSizeInByte_};
            result = ringCache_->Enqueue(bufferWrap);
            CHECK_AND_RETURN_RET_LOG(result.ret == OPERATION_SUCCESS, ERROR, "Enqueue failed");
            memset_s(static_cast<void *>(bufferWrap.dataPtr), bufferWrap.dataSize, 0, bufferWrap.dataSize);
            audioBuffer->SetCurReadFrame(audioBuffer->GetCurReadFrame() + spanSizeInFrame_, false);
            continue;
        }
        if (!isBlockingRead) {
            return static_cast<int32_t>(readSize);
        }
        statusLock.unlock(); // Never hold statusMutex_ while sleeping, calling IPC, or waiting for a reader.
        constexpr auto timeoutInNano = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS * 100)).count();
        FutexCode futexRet = audioBuffer->WaitFor(timeoutInNano, [this, audioBuffer, generation] {
            return !NormalReadIsCurrent(generation) ||
                audioBuffer->GetCurWriteFrame() > audioBuffer->GetCurReadFrame();
        });
        CHECK_AND_RETURN_RET_LOG(NormalReadIsCurrent(generation), ERR_ILLEGAL_STATE, "Normal read retired");
        CHECK_AND_RETURN_RET_LOG(futexRet == FUTEX_SUCCESS, ERROR, "Wait timeout or interrupted");
    }
    return static_cast<int32_t>(readSize);
}

int32_t CapturerInClientInner::Read(uint8_t &buffer, size_t userSize, bool isBlockingRead)
{
    Trace trace("CapturerInClientInner::Read " + std::to_string(userSize));

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(userSize < MAX_CLIENT_READ_SIZE && userSize > 0,
        ERR_INVALID_PARAM,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_SEND_DATA_INVALID_PARAM, "invalid size", true), "invalid size %{public}zu", userSize);

    std::unique_lock<std::mutex> statusLock(statusMutex_); // status check
    if (state_ != RUNNING) {
        if (readLogTimes_ < LOGLITMITTIMES) {
            readLogTimes_.fetch_add(1);
            AUDIO_ERR_LOG("Illegal state:%{public}u", state_.load());
        } else {
            AUDIO_DEBUG_LOG("Illegal state:%{public}u", state_.load());
        }
        return ERR_ILLEGAL_STATE;
    } else {
        readLogTimes_ = 0;
    }

    const bool normalRead = capturerMode_ == CAPTURE_MODE_NORMAL;
    const uint64_t generation = normalReadGeneration_.load();
    statusLock.unlock();

    std::lock_guard<std::mutex> lock(readMutex_);
    if (normalRead) {
        std::lock_guard<std::mutex> readStatusLock(statusMutex_);
        CHECK_AND_RETURN_RET_LOG(NormalReadIsCurrent(generation), ERROR, "Queued normal read retired");
    }
    // if first call, call set thread priority. if thread tid change recall set thread priority
    if (needSetThreadPriority_) {
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERROR,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                RECORD_SEND_DATA_ILLEGAL_STATE, "ipcStream_ is null", true), "ipcStream_ is null");
        ipcStream_->RegisterThreadPriority(gettid(),
            AppBundleManager::GetSelfBundleName(clientConfig_.appInfo.appUid),
            METHOD_WRITE_OR_READ, THREAD_PRIORITY_QOS_7);
        needSetThreadPriority_ = false;
    }

    size_t readSize = 0;
    int32_t res = normalRead ? HandleNormalCapturerRead(readSize, userSize, buffer, isBlockingRead, generation) :
        HandleCapturerRead(readSize, userSize, buffer, isBlockingRead);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(res >= 0, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_SEND_DATA_OPERATION_FAILED, "HandleCapturerRead err", true),
        "HandleCapturerRead err : %{public}d", res);
    int64_t markPosition = -1;
    int64_t periodSize = -1;
    if (normalRead) {
        CHECK_AND_RETURN_RET_LOG(CommitNormalReadPositionChanges(readSize, generation, markPosition, periodSize),
            ERROR, "Completed normal read retired");
    }
    BufferDesc tmpBuffer = {reinterpret_cast<uint8_t *>(&buffer), userSize, userSize};
    VolumeTools::DfxOperation(tmpBuffer, clientConfig_.streamInfo, logUtilsTag_, volumeDataCount_);
    DumpFileUtil::WriteDumpFile(dumpInFd_, static_cast<void *>(&buffer), readSize);
    if (normalRead) {
        if (markPosition >= 0) {
            SendCapturerMarkReachedEvent(markPosition);
        }
        if (periodSize >= 0) {
            SendCapturerPeriodReachedEvent(periodSize);
        }
    } else {
        HandleCapturerPositionChanges(readSize);
    }
    return readSize;
}

bool CapturerInClientInner::CommitNormalReadPositionChanges(size_t bytesRead, uint64_t generation,
    int64_t &markPosition, int64_t &periodSize)
{
    uint64_t readFrameNumber = 0;
    {
        // Existing position callbacks hold period/mark locks while invoking user
        // code, which may re-enter Stop. Never acquire either lock under status.
        std::lock_guard<std::mutex> periodLock(periodReachMutex_);
        std::lock_guard<std::mutex> statusLock(statusMutex_);
        CHECK_AND_RETURN_RET_LOG(NormalReadIsCurrent(generation), false, "Completed normal read retired");
        // Successful Read linearizes here. A later Stop cannot reattribute this
        // committed stream-wide count to a newer read operation.
        totalBytesRead_ += bytesRead;
        if (sizePerFrameInByte_ == 0) {
            return true;
        }
        readFrameNumber = totalBytesRead_ / sizePerFrameInByte_;
        capturerPeriodRead_ += static_cast<int64_t>(bytesRead / sizePerFrameInByte_);
        if (capturerPeriodRead_ >= capturerPeriodSize_ && capturerPeriodSize_ > 0) {
            capturerPeriodRead_ %= capturerPeriodSize_;
            periodSize = capturerPeriodSize_;
        }
    }
    {
        // No status/period lock is held while waiting for a mark callback.
        std::lock_guard<std::mutex> markLock(markReachMutex_);
        if (!capturerMarkReached_ && readFrameNumber >= static_cast<uint64_t>(capturerMarkPosition_)) {
            markPosition = capturerMarkPosition_;
            capturerMarkReached_ = true;
        }
    }
    return true;
}

void CapturerInClientInner::HandleCapturerPositionChanges(size_t bytesRead)
{
    totalBytesRead_ += bytesRead;
    if (sizePerFrameInByte_ == 0) {
        AUDIO_ERR_LOG("HandleCapturerPositionChanges: sizePerFrameInByte_ is 0");
        return;
    }
    uint64_t readFrameNumber = totalBytesRead_ / sizePerFrameInByte_;
    AUDIO_DEBUG_LOG("totalBytesRead_ %{public}" PRId64 ", frame size: %{public}zu", totalBytesRead_,
        sizePerFrameInByte_);
    {
        std::lock_guard<std::mutex> lock(markReachMutex_);
        if (!capturerMarkReached_) {
            AUDIO_DEBUG_LOG("Frame mark position: %{public}" PRId64 ", Total frames read: %{public}" PRId64,
                capturerMarkPosition_, static_cast<int64_t>(readFrameNumber));
            if (readFrameNumber >= static_cast<uint64_t>(capturerMarkPosition_)) {
                AUDIO_DEBUG_LOG("capturerInClient OnMarkReached");
                SendCapturerMarkReachedEvent(capturerMarkPosition_);
                capturerMarkReached_ = true;
            }
        }
    }

    {
        std::lock_guard<std::mutex> lock(periodReachMutex_);
        capturerPeriodRead_ += static_cast<int64_t>(bytesRead / sizePerFrameInByte_);
        AUDIO_DEBUG_LOG("Frame period number: %{public}" PRId64 ", Total frames written: %{public}" PRId64,
            static_cast<int64_t>(capturerPeriodRead_), static_cast<int64_t>(totalBytesRead_));
        if (capturerPeriodRead_ >= capturerPeriodSize_ && capturerPeriodSize_ > 0) {
            capturerPeriodRead_ %= capturerPeriodSize_;
            AUDIO_DEBUG_LOG("OnPeriodReached, remaining frames: %{public}" PRId64,
                static_cast<int64_t>(capturerPeriodRead_));
            SendCapturerPeriodReachedEvent(capturerPeriodSize_);
        }
    }
}

uint32_t CapturerInClientInner::GetUnderflowCount()
{
    // not supported for capturer
    AUDIO_WARNING_LOG("No Underflow in Capturer");
    return 0;
}

uint32_t CapturerInClientInner::GetOverflowCount()
{
    return overflowCount_;
}

void CapturerInClientInner::SetUnderflowCount(uint32_t underflowCount)
{
    // not supported for capturer
    AUDIO_WARNING_LOG("No Underflow in Capturer");
    return;
}

void CapturerInClientInner::SetOverflowCount(uint32_t overflowCount)
{
    overflowCount_ = overflowCount;
}

int32_t CapturerInClientInner::RegisterRemoteDiedCallback(const std::shared_ptr<RemoteDiedCallback> &callback)
{
    std::lock_guard<std::mutex> lock(deathRecipientLock_);
    if (deathRecipient_ == nullptr) {
        deathRecipient_ = sptr<RemoteDeathRecipient>::MakeSptr(callback);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcProxy_ != nullptr, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_ILLEGAL_STATE, "ipcProxy_ is null", true), "ipcProxy_ is null!");
    bool result = ipcProxy_->AddDeathRecipient(deathRecipient_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(result, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_OPERATION_FAILED, "AddDeathRecipient failed", true), "AddDeathRecipient failed.");
    return SUCCESS;
}

int32_t CapturerInClientInner::UnregisterRemoteDiedCallback()
{
    std::lock_guard<std::mutex> lock(deathRecipientLock_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(deathRecipient_ != nullptr && ipcProxy_ != nullptr, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_ILLEGAL_STATE, "deathRecipient or ipcProxy_ is null", true),
        "deathRecipient or ipcProxy_ is null!");
    bool result = ipcProxy_->RemoveDeathRecipient(deathRecipient_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(result, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CALLBACK_OPERATION_FAILED, "RemoveDeathRecipient failed", true),
        "RemoveDeathRecipient failed.");
    deathRecipient_ = nullptr;
    return SUCCESS;
}

void CapturerInClientInner::SetCapturerPositionCallback(int64_t markPosition, const
    std::shared_ptr<CapturerPositionCallback> &callback)
{
    std::lock_guard<std::mutex> lock(markReachMutex_);
    CHECK_AND_CALL_FUNC_RETURN_LOG(callback != nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_INVALID_PARAM, "CapturerPositionCallback is nullptr", true),
        "CapturerPositionCallback is nullptr");
    capturerPositionCallback_ = callback;
    capturerMarkPosition_ = markPosition;
    capturerMarkReached_ = false;
}

void CapturerInClientInner::UnsetCapturerPositionCallback()
{
    std::lock_guard<std::mutex> lock(markReachMutex_);
    capturerPositionCallback_ = nullptr;
    capturerMarkPosition_ = 0;
    capturerMarkReached_ = false;
}

void CapturerInClientInner::SetCapturerPeriodPositionCallback(int64_t periodPosition,
    const std::shared_ptr<CapturerPeriodPositionCallback> &callback)
{
    std::lock_guard<std::mutex> lock(periodReachMutex_);
    CHECK_AND_CALL_FUNC_RETURN_LOG(callback != nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_INVALID_PARAM, "CapturerPeriodPositionCallback is nullptr", true),
        "CapturerPeriodPositionCallback is nullptr");
    capturerPeriodPositionCallback_ = callback;
    capturerPeriodSize_ = periodPosition;
    totalBytesRead_ = 0;
    capturerPeriodRead_ = 0;
}

void CapturerInClientInner::UnsetCapturerPeriodPositionCallback()
{
    std::lock_guard<std::mutex> lock(periodReachMutex_);
    capturerPeriodPositionCallback_ = nullptr;
    capturerPeriodSize_ = 0;
    totalBytesRead_ = 0;
    capturerPeriodRead_ = 0;
}

void CapturerInClientInner::SetRendererPositionCallback(int64_t markPosition,
    const std::shared_ptr<RendererPositionCallback> &callback)
{
    AUDIO_ERR_LOG("SetRendererPositionCallback is not supported");
    return;
}

void CapturerInClientInner::UnsetRendererPositionCallback()
{
    AUDIO_ERR_LOG("UnsetRendererPositionCallback is not supported");
    return;
}

void CapturerInClientInner::SetRendererPeriodPositionCallback(int64_t periodPosition,
    const std::shared_ptr<RendererPeriodPositionCallback> &callback)
{
    AUDIO_ERR_LOG("SetRendererPeriodPositionCallback is not supported");
    return;
}

void CapturerInClientInner::UnsetRendererPeriodPositionCallback()
{
    AUDIO_ERR_LOG("UnsetRendererPeriodPositionCallback is not supported");
    return;
}

int32_t CapturerInClientInner::SetRendererSamplingRate(uint32_t sampleRate)
{
    // in plan
    return ERROR;
}

uint32_t CapturerInClientInner::GetRendererSamplingRate()
{
    // in plan
    return 0; // not supported
}

int32_t CapturerInClientInner::SetBufferSizeInMsec(int32_t bufferSizeInMsec)
{
    // bufferSizeInMsec is checked between 5ms and 20ms.
    bufferSizeInMsec_ = bufferSizeInMsec;
    AUDIO_INFO_LOG("SetBufferSizeInMsec to %{public}d", bufferSizeInMsec_);
    if (capturerMode_ == CAPTURE_MODE_CALLBACK) {
        uint64_t bufferDurationInUs = static_cast<uint64_t>(bufferSizeInMsec_ * AUDIO_US_PER_MS);
        InitCallbackBuffer(bufferDurationInUs);
    }
    return SUCCESS;
}

int32_t CapturerInClientInner::SetChannelBlendMode(ChannelBlendMode blendMode)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERROR;
}

int32_t CapturerInClientInner::SetVolumeWithRamp(float volume, int32_t duration)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERROR;
}

void CapturerInClientInner::SetStreamTrackerState(bool trackerRegisteredState)
{
    streamTrackerRegistered_ = trackerRegisteredState;
}

void CapturerInClientInner::GetSwitchInfo(IAudioStream::SwitchInfo& info)
{
    info.params = streamParams_;

    info.rendererInfo = rendererInfo_;
    info.capturerInfo = capturerInfo_;
    info.eStreamType = eStreamType_;
    info.state = state_;
    info.sessionId = sessionId_;
    info.streamTrackerRegistered = streamTrackerRegistered_;
    GetStreamSwitchInfo(info);
}

void CapturerInClientInner::GetStreamSwitchInfo(IAudioStream::SwitchInfo& info)
{
    info.overFlowCount = overflowCount_;
    info.clientPid = clientPid_;
    info.clientUid = clientUid_;

    info.frameMarkPosition = static_cast<uint64_t>(capturerMarkPosition_);
    info.capturePositionCb = capturerPositionCallback_;

    info.framePeriodNumber = static_cast<uint64_t>(capturerPeriodSize_);
    info.capturePeriodPositionCb = capturerPeriodPositionCallback_;

    info.capturerReadCallback = readCb_;
}

bool CapturerInClientInner::GetOffloadEnable()
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return false;
}

bool CapturerInClientInner::GetSpatializationEnabled()
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return false;
}

bool CapturerInClientInner::GetHighResolutionEnabled()
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return false;
}

IAudioStream::StreamClass CapturerInClientInner::GetStreamClass()
{
    if (capturerInfo_.capturerFlags == AUDIO_FLAG_MMAP || capturerInfo_.capturerFlags == AUDIO_FLAG_VOIP_FAST) {
        return IAudioStream::StreamClass::FAST_STREAM;
    }
    return PA_STREAM;
}

void CapturerInClientInner::SetSilentModeAndMixWithOthers(bool on)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return;
}

bool CapturerInClientInner::GetSilentModeAndMixWithOthers()
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return false;
}

bool CapturerInClientInner::RestoreAudioStream(bool needStoreState)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(proxyObj_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_ILLEGAL_STATE, "proxyObj_ is null", true), "proxyObj_ is null");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(state_ != NEW && state_ != INVALID && state_ != RELEASED, true,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CREATE_ILLEGAL_STATE, "state_ no need for restore", true),
        "state_ is %{public}d, no need for restore", state_.load());
    bool result = false;
    State oldState = state_;
    UpdateStreamState(NEW);
    SetStreamTrackerState(false);

    int32_t ret = SetAudioStreamInfo(streamParams_, proxyObj_);
    if (ret != SUCCESS) {
        goto error;
    }
#ifdef HAS_FEATURE_INNERCAPTURER
    // for inner-capturer
    if (capturerInfo_.sourceType == SOURCE_TYPE_PLAYBACK_CAPTURE) {
        ret = UpdatePlaybackCaptureConfig(filterConfig_);
        if (ret != SUCCESS) {
            goto error;
        }
    }
#endif
    switch (oldState) {
        case RUNNING:
            result = StartAudioStream();
            break;
        case PAUSED:
            result = StartAudioStream() && PauseAudioStream();
            break;
        case STOPPED:
        case STOPPING:
            result = StartAudioStream() && StopAudioStream();
            break;
        default:
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

void CapturerInClientInner::JoinCallbackLoop()
{
    AUDIO_INFO_LOG("Not Support");
}

int32_t CapturerInClientInner::SetDefaultOutputDevice(const DeviceType defaultOutputDevice, bool skipForce)
{
    (void)defaultOutputDevice;
    (void)skipForce;
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERROR;
}

FastStatus CapturerInClientInner::GetFastStatus()
{
    if (capturerInfo_.capturerFlags == AUDIO_FLAG_MMAP || capturerInfo_.capturerFlags == AUDIO_FLAG_VOIP_FAST) {
        return FASTSTATUS_FAST;
    }
    return FASTSTATUS_NORMAL;
}

void CapturerInClientInner::SetFastStatusChangeCallback(const std::function<void(FastStatus)> &callback)
{
    std::lock_guard lock(fastStatusChangeCallbackMutex_);
    fastStatusChangeCallback_ = callback;
}

void CapturerInClientInner::NotifyFastStatusChange(FastStatus status)
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

DeviceType CapturerInClientInner::GetDefaultOutputDevice()
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return DEVICE_TYPE_NONE;
}

// diffrence from GetAudioPosition only when set speed
int32_t CapturerInClientInner::GetAudioTimestampInfo(Timestamp &timestamp, Timestamp::Timestampbase base)
{
    return GetAudioTime(timestamp, base) ? SUCCESS : ERROR;
}

void CapturerInClientInner::SetSwitchingStatus(bool isSwitching)
{
    AUDIO_WARNING_LOG("not supported in capturer");
}

void CapturerInClientInner::GetRestoreInfo(RestoreInfo &restoreInfo)
{
    CHECK_AND_CALL_FUNC_RETURN_LOG(clientBuffer_ != nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Client OHAudioBuffer is nullptr", true), "Client OHAudioBuffer is nullptr");
    clientBuffer_->GetRestoreInfo(restoreInfo);
    return;
}

void CapturerInClientInner::SetRestoreInfo(RestoreInfo &restoreInfo)
{
    CHECK_AND_CALL_FUNC_RETURN_LOG(clientBuffer_ != nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "Client OHAudioBuffer is nullptr", true), "Client OHAudioBuffer is nullptr");
    clientBuffer_->SetRestoreInfo(restoreInfo);
    return;
}

RestoreStatus CapturerInClientInner::CheckRestoreStatus()
{
    bool restoreFlag = (GetFastStatus() == FASTSTATUS_FAST) && (readCb_ == nullptr);
    if (restoreFlag) {
        AUDIO_INFO_LOG("Fast stream without callback, restore to normal");
        capturerMode_ = CAPTURE_MODE_NORMAL;
        return NEED_RESTORE_TO_NORMAL;
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, RESTORE_ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Client OHAudioBuffer is nullptr", true), "Client OHAudioBuffer is nullptr");
    return clientBuffer_->CheckRestoreStatus();
}

RestoreStatus CapturerInClientInner::SetRestoreStatus(RestoreStatus restoreStatus)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, RESTORE_ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "Client OHAudioBuffer is nullptr", true), "Client OHAudioBuffer is nullptr");
    return clientBuffer_->SetRestoreStatus(restoreStatus);
}

void CapturerInClientInner::FetchDeviceForSplitStream()
{
    AUDIO_INFO_LOG("Fetch input device for split stream %{public}u", sessionId_);
    SetRestoreStatus(NO_NEED_FOR_RESTORE);
}

void CapturerInClientInner::SetCallStartByUserTid(pid_t tid)
{
    AUDIO_WARNING_LOG("not supported in capturer");
}

void CapturerInClientInner::SetCallbackLoopTid(int32_t tid)
{
    std::unique_lock<std::mutex> waitLock(callbackLoopTidMutex_);
    AUDIO_INFO_LOG("Callback loop tid: %{public}d", tid);
    callbackLoopTid_ = tid;
    callbackLoopTidCv_.notify_all();
}

int32_t CapturerInClientInner::GetCallbackLoopTid()
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

void CapturerInClientInner::ResetCallbackLoopTid()
{
    AUDIO_INFO_LOG("to -1");
    callbackLoopTid_ = -1;
}

bool CapturerInClientInner::GetStopFlag() const
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "Client OHAudioBuffer is nullptr", true), "Client OHAudioBuffer is nullptr");
    return clientBuffer_->GetStopFlag();
}

int32_t CapturerInClientInner::SetRebuildFlag()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "ipcStream is not inited", true), "ipcStream is not inited!");
    return ipcStream_->SetRebuildFlag();
}

int32_t CapturerInClientInner::GetLatencyWithFlag(uint64_t &latency, LatencyFlag flag)
{
    (void)latency;
    (void)flag;
    return ERR_NOT_SUPPORTED;
}

bool CapturerInClientInner::IsRestoreNeeded()
{
    if (readCb_ == nullptr) {
        return true;
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(clientBuffer_ != nullptr, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_QUERY_ILLEGAL_STATE, "buffer null", true), "buffer null");

    RestoreStatus restoreStatus = clientBuffer_->GetRestoreStatus();
    if (restoreStatus == NEED_RESTORE) {
        return true;
    }

    if (restoreStatus == NEED_RESTORE_TO_NORMAL) {
        return true;
    }

    return false;
}

int32_t CapturerInClientInner::SetLoopTimes(int64_t bufferLoopTimes)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERR_INCORRECT_MODE;
}

void CapturerInClientInner::SetStaticBufferInfo(StaticBufferInfo staticBufferInfo,
    std::shared_ptr<AudioSharedMemory> sharedMemory)
{
    AUDIO_WARNING_LOG("not supported in capturer");
}

int32_t CapturerInClientInner::SetStaticBufferEventCallback(std::shared_ptr<StaticBufferEventCallback> callback)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERR_INCORRECT_MODE;
}

int32_t CapturerInClientInner::SetStaticTriggerRecreateCallback(std::function<void()> sendStaticRecreateFunc)
{
    AUDIO_WARNING_LOG("not supported in capturer");
    return ERR_INCORRECT_MODE;
}

const std::string CapturerInClientInner::GetBundleName()
{
    return bundleName;
}

void CapturerInClientInner::SetBundleName(std::string &name)
{
    bundleName = name;
}

bool CapturerInClientInner::ResetStaticPlayPosition()
{
    AUDIO_ERR_LOG("Not Support!");
    return false;
}

int32_t CapturerInClientInner::ResetNotifyStreamSilentChangeFlag()
{
    AUDIO_WARNING_LOG("Not support");
    return ERR_NOT_SUPPORTED;
}

int32_t CapturerInClientInner::SetInMainThreadState(bool isInMainThread)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            RECORD_CONFIG_ILLEGAL_STATE, "IpcStream is nullptr", true), "IpcStream is nullptr");
    return ipcStream_->SetInMainThreadState(isInMainThread);
}

void CapturerInClientInner::SetSensitiveRecordPermitCallback(
    const std::shared_ptr<AudioCapturerSensitiveRecordPermitCallback> &callback)
{
    CHECK_AND_RETURN_LOG(callback != nullptr, "Invalid null callback");
    std::lock_guard<std::mutex> lock(sensitiveRecordPermitCallbackMutex_);
    sensitiveRecordPermitCallback_ = callback;
}
} // namespace AudioStandard
} // namespace OHOS
#endif // FAST_AUDIO_STREAM_H
