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
#ifndef LOG_TAG
#define LOG_TAG "RendererInClientInner"
#endif

#include "renderer_in_client.h"
#include "renderer_in_client_private.h"

#include <atomic>
#include <cinttypes>
#include <condition_variable>
#include <sstream>
#include <string>
#include <mutex>
#include <thread>

#include "iservice_registry.h"
#include "system_ability_definition.h"
#include "securec.h"
#include "hisysevent.h"

#include "audio_errors.h"
#include "audio_policy_manager.h"
#include "audio_renderer_log.h"
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
#include "audio_policy_manager.h"
#include "audio_spatialization_types.h"
#include "audio_utils_c.h"
#include "policy_handler.h"
#include "volume_tools.h"
#include "stream_dfx_manager.h"

#include "media_monitor_manager.h"
#include "istandard_audio_service.h"
#include "app_bundle_manager.h"
#include "audio_performance_monitor.h"

using namespace OHOS::HiviewDFX;
using namespace OHOS::AppExecFwk;

namespace OHOS {
namespace AudioStandard {
namespace {
const uint64_t OLD_BUF_DURATION_IN_USEC = 92880; // This value is used for compatibility purposes.
const uint64_t MAX_BUF_DURATION_IN_USEC = 2000000; // 2S
const int64_t MUTE_PLAY_MIN_DURAION = 3000000000; // 3S
const int64_t MUTE_PLAY_MAX_DURAION = 30000000000; // 30S
static const size_t MAX_WRITE_SIZE = 20 * 1024 * 1024; // 20M
static const int32_t OPERATION_TIMEOUT_IN_MS = 1000; // 1000ms
static const int32_t OFFLOAD_OPERATION_TIMEOUT_IN_MS = 8000; // 8000ms for offload
static const int32_t WRITE_CACHE_TIMEOUT_IN_MS = 1500; // 1500ms
static const int32_t FAST_WRITE_CACHE_TIMEOUT_IN_MS = 40; // 40ms, align with legacy AudioProcessInClient
static const int32_t WRITE_BUFFER_TIMEOUT_IN_MS = 20; // ms
static const uint32_t WAIT_FOR_NEXT_CB = 10000; // 10ms
static constexpr int32_t ONE_MINUTE = 60;
static const int32_t MAX_WRITE_INTERVAL_MS = 40;
constexpr int32_t RETRY_WAIT_TIME_MS = 500; // 500ms
constexpr int32_t MAX_RETRY_COUNT = 8;
static const int64_t STATIC_HEARTBEAT_INTERVAL_IN_MS = 1000; // 1s
static const int32_t VOIP_DIRECT_BUFFER_DURATION_IN_US = 120000;
static const int64_t ONWRITEDATA_TIMEOUT_NS = 40000000;
} // namespace

static AppExecFwk::BundleInfo gBundleInfo_;
std::mutex g_serverProxyMutex;
sptr<IStandardAudioService> gServerProxy_ = nullptr;

const sptr<IStandardAudioService> RendererInClientInner::GetAudioServerProxy()
{
    std::lock_guard<std::mutex> lock(g_serverProxyMutex);
    if (gServerProxy_ == nullptr) {
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
        gServerProxy_ = iface_cast<IStandardAudioService>(object);
        if (gServerProxy_ == nullptr) {
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
    sptr<IStandardAudioService> gasp = gServerProxy_;
    return gasp;
}

void RendererInClientInner::AudioServerDied(pid_t pid, pid_t uid)
{
    AUDIO_INFO_LOG("audio server died clear proxy, will restore proxy in next call");
    std::lock_guard<std::mutex> lock(g_serverProxyMutex);
    gServerProxy_ = nullptr;
}

void RendererInClientInner::RegisterTracker(const std::shared_ptr<AudioClientTracker> &proxyObj)
{
    if (audioStreamTracker_ && audioStreamTracker_.get() && !streamTrackerRegistered_) {
        // make sure sessionId_ is valid.
        AUDIO_INFO_LOG("Calling register tracker, sessionid is %{public}d", sessionId_);
        AudioRegisterTrackerInfo registerTrackerInfo;

        rendererInfo_.samplingRate = static_cast<AudioSamplingRate>(curStreamParams_.samplingRate);
        rendererInfo_.format = static_cast<AudioSampleFormat>(curStreamParams_.format);
        registerTrackerInfo.sessionId = sessionId_;
        registerTrackerInfo.clientPid = clientPid_;
        registerTrackerInfo.state = state_;
        registerTrackerInfo.rendererInfo = rendererInfo_;
        registerTrackerInfo.capturerInfo = capturerInfo_;
        registerTrackerInfo.channelCount = curStreamParams_.channels;
        registerTrackerInfo.backMute = backMute_;

        audioStreamTracker_->RegisterTracker(registerTrackerInfo, proxyObj);
        streamTrackerRegistered_ = true;
    }
}

void RendererInClientInner::UpdateTracker(const std::string &updateCase)
{
    if (audioStreamTracker_ && audioStreamTracker_.get()) {
        AUDIO_DEBUG_LOG("Renderer:Calling Update tracker for %{public}s", updateCase.c_str());
        audioStreamTracker_->UpdateTracker(sessionId_, state_, clientPid_, rendererInfo_, capturerInfo_);
    }
}

bool RendererInClientInner::IsHighResolution() const noexcept
{
    return eStreamType_ == STREAM_MUSIC && curStreamParams_.samplingRate >= SAMPLE_RATE_48000 &&
           curStreamParams_.format >= SAMPLE_S24LE;
}

void RendererInClientInner::InitDFXOperaiton()
{
    // eg: 100005_44100_2_1_client_out.pcm
    dumpOutFile_ = std::to_string(sessionId_) + "_" + std::to_string(curStreamParams_.customSampleRate == 0 ?
        curStreamParams_.samplingRate : curStreamParams_.customSampleRate) + "_" +
        std::to_string(curStreamParams_.channels) + "_" + std::to_string(curStreamParams_.format) + "_client_out." +
        (isHWDecodingType_ ? EncodingTypeStr(static_cast<AudioEncodingType>(curStreamParams_.encoding)) : "pcm");

    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_CLIENT_PARA, dumpOutFile_, &dumpOutFd_);
    logUtilsTag_ = "[" + std::to_string(sessionId_) + "]NormalRenderer";
}

void RendererInClientInner::InitDirectPipeType()
{
    if (rendererInfo_.rendererFlags == AUDIO_FLAG_VOIP_DIRECT || IsHighResolution()) {
        AudioPipeType originType = rendererInfo_.pipeType;
        int32_t type = ipcStream_->GetStreamManagerType();
        if (type == AUDIO_DIRECT_MANAGER_TYPE) {
            rendererInfo_.pipeType = (rendererInfo_.rendererFlags == AUDIO_FLAG_VOIP_DIRECT) ?
                PIPE_TYPE_OUT_VOIP : PIPE_TYPE_OUT_DIRECT_NORMAL;
        } else if (originType == PIPE_TYPE_OUT_DIRECT_NORMAL) {
            rendererInfo_.pipeType = PIPE_TYPE_OUT_NORMAL;
        }
    }
}

// call this without lock, we should be able to call deinit in any case.
int32_t RendererInClientInner::DeinitIpcStream()
{
    Trace trace("RendererInClientInner::DeinitIpcStream");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERROR,
        "ipcStream_ is nullptr");
    ipcStream_->Release(false);
    return SUCCESS;
}

const AudioProcessConfig RendererInClientInner::ConstructConfig()
{
    AudioProcessConfig config = {};

    config.appInfo.appPid = clientPid_;
    config.appInfo.appUid = clientUid_;
    config.appInfo.appTokenId = appTokenId_;
    config.appInfo.appFullTokenId = fullTokenId_;

    config.streamInfo.channels = static_cast<AudioChannel>(curStreamParams_.channels);
    config.streamInfo.encoding = static_cast<AudioEncodingType>(curStreamParams_.encoding);
    config.streamInfo.format = static_cast<AudioSampleFormat>(curStreamParams_.format);
    config.streamInfo.samplingRate = static_cast<AudioSamplingRate>(curStreamParams_.samplingRate);
    config.streamInfo.customSampleRate = curStreamParams_.customSampleRate;
    config.streamInfo.channelLayout = static_cast<AudioChannelLayout>(curStreamParams_.channelLayout);
    config.originalSessionId = curStreamParams_.originalSessionId;

    config.audioMode = AUDIO_MODE_PLAYBACK;

    if (rendererInfo_.rendererFlags != AUDIO_FLAG_NORMAL && rendererInfo_.rendererFlags != AUDIO_FLAG_MMAP &&
        rendererInfo_.rendererFlags != AUDIO_FLAG_VOIP_FAST &&
        rendererInfo_.rendererFlags != AUDIO_FLAG_VOIP_DIRECT &&
        rendererInfo_.rendererFlags != AUDIO_FLAG_DIRECT && rendererInfo_.rendererFlags != AUDIO_FLAG_3DA_DIRECT) {
        AUDIO_WARNING_LOG("ConstructConfig find renderer flag invalid:%{public}d", rendererInfo_.rendererFlags);
        rendererInfo_.rendererFlags = 0;
    }
    config.rendererInfo = rendererInfo_;

    config.capturerInfo = {};

    config.streamType = eStreamType_;

    config.deviceType = AudioPolicyManager::GetInstance().GetActiveOutputDevice();

    config.privacyType = privacyType_;

    config.staticBufferInfo = staticBufferInfo_;

    config.ultraFastFlag = curStreamParams_.ultraFastFlag;

    clientConfig_ = config;

    return config;
}

int32_t RendererInClientInner::CopyStaticBufferData()
{
    clientBuffer_->SetStaticMode(true);
    CHECK_AND_RETURN_RET_LOG(clientBuffer_->GetDataBase() != nullptr, ERR_OPERATION_FAILED,
        "clientBuffer_->GetDataBase() is nullptr");

    CHECK_AND_RETURN_RET_LOG(staticSharedMemory_ != nullptr &&
        staticSharedMemory_->GetSize() == clientBuffer_->GetDataSize(),
        ERR_OPERATION_FAILED, "staticSharedMemory_ %{public}d is inValid!", staticSharedMemory_ != nullptr);
    
    int32_t copyRet = memcpy_s(clientBuffer_->GetDataBase(), clientBuffer_->GetDataSize(),
        staticSharedMemory_->GetBase(), staticSharedMemory_->GetSize());
    CHECK_AND_RETURN_RET_LOG(copyRet == SUCCESS, ERR_OPERATION_FAILED,
        "memcpy static buffer data failed, ret: %{public}d", copyRet);
    
    AUDIO_INFO_LOG("Static mode: copied data from client to server buffer, size:%{public}zu",
        clientBuffer_->GetDataSize());
    return SUCCESS;
}

int32_t RendererInClientInner::InitSharedBuffer()
{
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED, "InitSharedBuffer failed, null ipcStream_.");
    uint64_t engineSize = 0;
    int32_t ret = ipcStream_->ResolveBufferBaseAndGetServerSpanSize(clientBuffer_, spanSizeInFrame_, engineSize);

    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS && clientBuffer_ != nullptr, ret, "ResolveBuffer failed:%{public}d", ret);
    cacheSizeInFrame_ = engineSize;

    uint32_t totalSizeInFrame = 0;
    uint32_t byteSizePerFrame = 0;
    ret = clientBuffer_->GetSizeParameter(totalSizeInFrame, byteSizePerFrame);

    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS && byteSizePerFrame == sizePerFrameInByte_, ret, "GetSizeParameter failed"
        ":%{public}d, byteSizePerFrame:%{public}u, sizePerFrameInByte_:%{public}zu", ret, byteSizePerFrame,
        sizePerFrameInByte_);

    clientSpanSizeInByte_ = spanSizeInFrame_ * byteSizePerFrame;

    AUDIO_INFO_LOG("totalSizeInFrame_[%{public}u] spanSizeInFrame[%{public}u] sizePerFrameInByte_[%{public}zu]"
        "clientSpanSizeInByte_[%{public}zu]", totalSizeInFrame, spanSizeInFrame_, sizePerFrameInByte_,
        clientSpanSizeInByte_);
    if (rendererInfo_.isStatic) {
        CHECK_AND_RETURN_RET_LOG(CopyStaticBufferData() == SUCCESS, ERR_OPERATION_FAILED,
            "CopyStaticBufferData failed");
    }
    return SUCCESS;
}

bool RendererInClientInner::IsLowLatencyRenderer() const
{
    return (rendererInfo_.audioFlag & AUDIO_OUTPUT_FLAG_FAST);
}

uint64_t RendererInClientInner::GetDefaultCallbackBufferDurationInUs() const
{
    if (!IsLowLatencyRenderer()) {
        return OLD_BUF_DURATION_IN_USEC;
    }
    uint32_t sampleRate = curStreamParams_.customSampleRate == 0 ? curStreamParams_.samplingRate :
        curStreamParams_.customSampleRate;
    if (sampleRate == 0) {
        return OLD_BUF_DURATION_IN_USEC;
    }
    // For low-latency callback mode, the callback quantum should follow one server span.
    // cacheSizeInFrame_ comes from server engine size, which is typically span * 2.
    uint32_t frameCount = spanSizeInFrame_ > 0 ? spanSizeInFrame_ : cacheSizeInFrame_.load();
    if (frameCount == 0) {
        return OLD_BUF_DURATION_IN_USEC;
    }
    uint64_t durationInUs = static_cast<uint64_t>(frameCount) * AUDIO_US_PER_S / sampleRate;
    AUDIO_INFO_LOG("GetDefaultCallbackBufferDurationInUs low latency, frameCount:%{public}u sampleRate:%{public}u "
        "durationInUs:%{public}" PRIu64, frameCount, sampleRate, durationInUs);
    return durationInUs;
}

int32_t RendererInClientInner::GetBufferWaitTimeoutInMs() const
{
    if (offloadEnable_) {
        return OFFLOAD_OPERATION_TIMEOUT_IN_MS;
    }
    return IsLowLatencyRenderer() ? FAST_WRITE_CACHE_TIMEOUT_IN_MS : WRITE_CACHE_TIMEOUT_IN_MS;
}

int32_t RendererInClientInner::InitIpcStream()
{
    Trace trace("RendererInClientInner::InitIpcStream");
    AudioProcessConfig config = ConstructConfig();
    bool resetSilentMode = (gServerProxy_ == nullptr) ? true : false;
    sptr<IStandardAudioService> gasp = RendererInClientInner::GetAudioServerProxy();
    CHECK_AND_CALL_FUNC_RETURN_RET_REPORT(gasp != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_SERVICE_UNAVAILABLE, "Can not get service", true),
        HILOG_COMM_ERROR("[InitIpcStream]Create failed, can not get service."));
    int32_t errorCode = 0;
    ipcProxy_ = nullptr;
    AudioPlaybackCaptureConfig playbackConfig = {};
    gasp->CreateAudioProcess(config, errorCode, playbackConfig, ipcProxy_);
    for (int32_t retrycount = 0; (errorCode == ERR_RETRY_IN_CLIENT) && (retrycount < MAX_RETRY_COUNT); retrycount++) {
        AUDIO_WARNING_LOG("retry in client");
        std::this_thread::sleep_for(std::chrono::milliseconds(RETRY_WAIT_TIME_MS));
        gasp->CreateAudioProcess(config, errorCode, playbackConfig, ipcProxy_);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcProxy_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_NULL_POINTER, "ipcProxy is null", true),
        "failed with null ipcProxy.");
    ipcStream_ = iface_cast<IIpcStream>(ipcProxy_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_NULL_POINTER, "iface_cast failed", true),
        "failed when iface_cast.");

    // in plan next: old listener_ is destoried here, will server receive dieth notify?
    listener_ = sptr<IpcStreamListenerImpl>::MakeSptr(shared_from_this());
    int32_t ret = ipcStream_->RegisterStreamListener(listener_->AsObject());
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_OPERATION_FAILED, "RegisterStreamListener failed", true),
        "RegisterStreamListener failed:%{public}d", ret);

    if (resetSilentMode && gServerProxy_ != nullptr && silentModeAndMixWithOthers_) {
        ipcStream_->SetSilentModeAndMixWithOthers(silentModeAndMixWithOthers_);
    }
    ret = InitSharedBuffer();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_OPERATION_FAILED, "InitSharedBuffer failed", true),
        "InitSharedBuffer failed:%{public}d", ret);

    ret = ipcStream_->GetAudioSessionID(sessionId_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(clientUid_),
            PLAY_CREATE_INVALID_INDEX, "GetAudioSessionID failed", true),
        "GetAudioSessionID failed:%{public}d", ret);
    traceTag_ = "[" + std::to_string(sessionId_) + "]RendererInClient"; // [100001]RendererInClient
    InitCallbackHandler();
    return SUCCESS;
}

int32_t RendererInClientInner::SetInnerVolume(float volume)
{
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, ERR_OPERATION_FAILED, "buffer is not inited");
    clientBuffer_->SetStreamVolume(volume);
    CHECK_AND_CALL_FUNC_RETURN_RET(ipcStream_ != nullptr, false,
        HILOG_COMM_ERROR("[SetInnerVolume]ipcStream is not inited!"));
    int32_t ret = ipcStream_->SetClientVolume();
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("Set Client Volume failed:%{public}u", ret);
        return ERROR;
    }
    AUDIO_PRERELEASE_LOGI("volume: %{public}f", volume);
    return SUCCESS;
}

void RendererInClientInner::SetCacheSize(uint32_t cacheSizeInFrame)
{
    if (spanSizeInFrame_ == 0) {
        AUDIO_ERR_LOG("failed: spanSizeInFrame is invalid");
        return;
    }
    if (ipcStream_ == nullptr) {
        AUDIO_ERR_LOG("failed: ipcStream_ is null");
        return;
    }
    // 20 -> 40, 93 -> 120
    uint32_t cacheCount = 0;
    int32_t ret = ipcStream_->CalculateCacheCount(cacheSizeInFrame, cacheCount);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("CalculateCacheCount failed: %{public}d", ret);
        cacheCount = (cacheSizeInFrame + spanSizeInFrame_ - 1) / spanSizeInFrame_ + 1;
    }
    cacheSizeInFrame_ = cacheCount * spanSizeInFrame_;
    AUDIO_INFO_LOG("cacheCount:%{public}d cacheSizeInFrame:%{public}d", cacheCount, cacheSizeInFrame_.load());
}

void RendererInClientInner::InitCallbackBuffer(uint64_t bufferDurationInUs)
{
    if (bufferDurationInUs > MAX_BUF_DURATION_IN_USEC) {
        AUDIO_ERR_LOG("InitCallbackBuffer with invalid duration %{public}" PRIu64", use default instead.",
            bufferDurationInUs);
        bufferDurationInUs = GetDefaultCallbackBufferDurationInUs();
    }
    // Calculate buffer size based on duration.

    size_t metaSize = 0;
    uint32_t sampleRate = curStreamParams_.customSampleRate == 0 ? curStreamParams_.samplingRate :
            curStreamParams_.customSampleRate;
    if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
        CHECK_AND_RETURN_LOG(converter_ != nullptr, "converter is not inited");
        metaSize = converter_->GetMetaSize();
        converter_->GetInputBufferSize(cbBufferSize_);
    } else {
        cbBufferSize_ = static_cast<size_t>(bufferDurationInUs * sampleRate / AUDIO_US_PER_S) *
            sizePerFrameInByte_;
    }
    if (rendererInfo_.rendererFlags == AUDIO_FLAG_VOIP_DIRECT && isMainUseArk_) {
        AUDIO_INFO_LOG("Change duration for voip direct, %{public}" PRIu64 " to %{public}d",
            bufferDurationInUs, VOIP_DIRECT_BUFFER_DURATION_IN_US);
        bufferDurationInUs = VOIP_DIRECT_BUFFER_DURATION_IN_US;
    }
    uint64_t durationInFrame = bufferDurationInUs * sampleRate / AUDIO_US_PER_S;
    SetCacheSize(durationInFrame);
    AUDIO_INFO_LOG("duration %{public}" PRIu64 ", ecodingType: %{public}d, size: %{public}zu, metaSize: %{public}zu",
        bufferDurationInUs, curStreamParams_.encoding, cbBufferSize_, metaSize);
    std::lock_guard<std::mutex> lock(cbBufferMutex_);
    cbBuffer_ = std::make_unique<uint8_t[]>(cbBufferSize_ + metaSize);
}

// Sleep or wait in WaitForRunning to avoid dead looping.
bool RendererInClientInner::WaitForRunning()
{
    Trace trace("RendererInClientInner::WaitForRunning");
    // check renderer state_: call client write only in running else wait on statusMutex_
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
            AUDIO_DEBUG_LOG("Wait timeout, current state_ is %{public}d", state_.load()); // wait 0.5s
            return false;
        }
    }
    return true;
}

void RendererInClientInner::RecordDropPosition(size_t bufLength)
{
    CHECK_AND_RETURN_LOG(isHdiSpeed_.load() && !isHWDecodingType_, "record drop position only when is hdi speed ");
    uint32_t channels = clientConfig_.streamInfo.channels;
    uint32_t samplePerFrame = Util::GetSamplePerFrame(clientConfig_.streamInfo.format);
    // calculate samples by dropped buffer size
    uint32_t dropPostion = bufLength / (channels * samplePerFrame);
    dropPosition_ += dropPostion;
    dropHdiPosition_ += dropPostion / GetSpeed();
    AUDIO_WARNING_LOG("RendererInClientInner::RecordDropPosition dropPosition_:%{public}" PRIu64
        ",dropHdiPosition_:%{public}" PRIu64, dropPosition_.load(), dropHdiPosition_.load());
}

int32_t RendererInClientInner::WriteRawBuffer(BufferDesc &bufferDesc)
{
    Trace trace("RendererInClient::WriteRawBuffer dataLength:" + std::to_string(bufferDesc.dataLength) + " bufLength:" +
        std::to_string(bufferDesc.bufLength));
    if (bufferDesc.dataLength == 0) {
        if (sleepCount_++ == LOG_COUNT_LIMIT) {
            sleepCount_ = 0;
            AUDIO_WARNING_LOG("1st or 200 times INVALID buffer");
        }
        Trace waitTrace("RendererInClient::WaitClientWrite");
        usleep(WAIT_FOR_NEXT_CB);
        return SUCCESS;
    }
    FirstFrameProcess();
    if (gServerProxy_ == nullptr) {
        cbThreadReleased_ = true;
        Trace waitTrace("RendererInClient::WaitServerRestart");
        usleep(WAIT_FOR_NEXT_CB);
        return ERR_WRITE_BUFFER;
    }
    sleepCount_ = LOG_COUNT_LIMIT;
    std::unique_lock<std::mutex> statusLock(statusMutex_);
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERR_WRITE_FAILED, "ipc stream is null");
    int32_t ret = ipcStream_->RequestHandleData(bufferDesc.syncFramePts, bufferDesc.dataLength);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "RequestHandleData failed:%{public}d", ret);
    return ret;
}

int32_t RendererInClientInner::Write3DADirectBuffer(BufferDesc &bufferDesc)
{
    Trace trace("RendererInClient::Write3DADirectBuffer PCM:" +
        std::to_string(bufferDesc.bufLength) + " Meta:" +
        std::to_string(bufferDesc.metaLength));

    CHECK_AND_RETURN_RET_LOG(bufferDesc.dataLength != 0 &&
        bufferDesc.metaBuffer != nullptr, ERR_INVALID_PARAM,
        "3DA: Invalid buffer, dataLength=%{public}zu", bufferDesc.dataLength);

    CHECK_AND_RETURN_RET(CallStartWhenInStandby() == SUCCESS, ERR_OPERATION_FAILED);
    FirstFrameProcess();

    uint64_t writePos = clientBuffer_->GetCurWriteFrame();

    if (gServerProxy_ == nullptr) {
        cbThreadReleased_ = true;
        Trace waitTrace("RendererInClient::WaitServerRestart");
        usleep(WAIT_FOR_NEXT_CB);
        return ERR_WRITE_BUFFER;
    }

    size_t blockSize = bufferDesc.bufLength + bufferDesc.metaLength;
    uint8_t *dataBase = clientBuffer_->GetDataBase();
    CHECK_AND_RETURN_RET_LOG(dataBase != nullptr, ERR_OPERATION_FAILED,
        "3DA: GetDataBase returned NULL! writePos=%{public}" PRIu64, writePos);

    // Calculate offset in circular buffer
    size_t pcmOffset = writePos % clientBuffer_->GetDataSize();
    size_t metaOffset = pcmOffset + bufferDesc.bufLength;
    CHECK_AND_RETURN_RET_LOG(pcmOffset + bufferDesc.bufLength <= clientBuffer_->GetDataSize(),
        ERR_OPERATION_FAILED, "3DA: PCM out of bounds! offset=%{public}zu, size=%{public}zu, total=%{public}zu",
        pcmOffset, bufferDesc.bufLength, clientBuffer_->GetDataSize());

    memcpy_s(dataBase + pcmOffset, bufferDesc.bufLength, bufferDesc.buffer, bufferDesc.bufLength);
    DumpFileUtil::WriteDumpFile(dumpOutFd_, static_cast<void *>(bufferDesc.buffer), bufferDesc.bufLength);

    CHECK_AND_RETURN_RET_LOG(metaOffset + bufferDesc.metaLength <= clientBuffer_->GetDataSize(),
        ERR_OPERATION_FAILED, "3DA: Metadata out of bounds! metaOffset=%{public}zu,"
        "size=%{public}zu, total=%{public}zu",
        metaOffset, bufferDesc.metaLength, clientBuffer_->GetDataSize());

    memcpy_s(dataBase + metaOffset, bufferDesc.metaLength, bufferDesc.metaBuffer, bufferDesc.metaLength);
    uint64_t newWriteFrame = writePos + blockSize;
    clientBuffer_->SetCurWriteFrame(newWriteFrame, false);

    return SUCCESS;
}

int32_t RendererInClientInner::ProcessWriteInner(BufferDesc &bufferDesc)
{
    int32_t result = 0; // Ensure result with default value.
    if (isHWDecodingType_) {
        result = WriteRawBuffer(bufferDesc);
        return result;
    }
    if ((rendererInfo_.rendererFlags == AUDIO_FLAG_3DA_DIRECT) &&
        (curStreamParams_.encoding == ENCODING_AUDIOVIVID)) {
        if (bufferDesc.dataLength != 0) {
            result = Write3DADirectBuffer(bufferDesc);
        } else {
            AUDIO_WARNING_LOG("INVALID 3DA buffer");
            usleep(WAIT_FOR_NEXT_CB);
        }
        return result;
    }
    if (curStreamParams_.encoding == ENCODING_AUDIOVIVID) {
        if (bufferDesc.dataLength != 0) {
            result = WriteInner(bufferDesc.buffer, bufferDesc.bufLength, bufferDesc.metaBuffer, bufferDesc.metaLength);
        } else {
            AUDIO_WARNING_LOG("INVALID AudioVivid buffer");
            usleep(WAIT_FOR_NEXT_CB);
        }
    }
    if (curStreamParams_.encoding == ENCODING_PCM) {
        if (bufferDesc.dataLength != 0) {
            result = WriteInner(bufferDesc.buffer, bufferDesc.bufLength);
            sleepCount_ = LOG_COUNT_LIMIT;
        } else {
            int32_t readableSizeInFrames = clientBuffer_->GetReadableDataFrames();
            bool flagTryPrintLog = ((readableSizeInFrames >= 0)
                && (static_cast<uint32_t>(readableSizeInFrames) < spanSizeInFrame_));
            if (flagTryPrintLog && (sleepCount_++ == LOG_COUNT_LIMIT)) {
                sleepCount_ = 0;
                AUDIO_WARNING_LOG("1st or 200 times INVALID buffer");
            }
            usleep(WAIT_FOR_NEXT_CB);
        }
    }
    if (result < 0) {
        AUDIO_WARNING_LOG("Call write fail, result:%{public}d, bufLength:%{public}zu", result, bufferDesc.bufLength);
        RecordDropPosition(bufferDesc.bufLength);
    }
    return result;
}

bool RendererInClientInner::CheckBufferNeedWrite()
{
    uint32_t totalSizeInFrame = clientBuffer_->GetTotalSizeInFrame();
    size_t totalSizeInByte = totalSizeInFrame * sizePerFrameInByte_;
    int32_t writableInFrame = clientBuffer_->GetWritableDataFrames();
    size_t writableSizeInByte = static_cast<size_t>(writableInFrame) * sizePerFrameInByte_;

    int32_t readableFrames = clientBuffer_->GetReadableDataFrames();
    AUTO_CTRACE("CheckBufferNeedWrite writeable:%d readable:%d cacheSize:%u", writableInFrame, readableFrames,
        cacheSizeInFrame_.load());
    if (writableInFrame <= 0) {
        return false;
    }

    if (cbBufferSize_ > totalSizeInByte) {
        return false;
    }

    // writableSizeInByte >= cbBufferSize_, call write() will not wait.
    if (writableSizeInByte < cbBufferSize_) {
        return false;
    }

    if (IsLowLatencyRenderer()) {
        RETURN_RET_IF(readableFrames < static_cast<int32_t>(cacheSizeInFrame_), true);
    } else {
        RETURN_RET_IF(readableFrames <= static_cast<int32_t>(cacheSizeInFrame_), true);
    }

    return false;
}

bool RendererInClientInner::IsRestoreNeeded()
{
    if (writeCb_ == nullptr) {
        return true;
    }
    CHECK_AND_RETURN_RET_LOG(clientBuffer_ != nullptr, false, "buffer null");

    RestoreStatus restoreStatus = clientBuffer_->GetRestoreStatus();
    if (restoreStatus == NEED_RESTORE) {
        return true;
    }

    if (restoreStatus == NEED_RESTORE_TO_NORMAL) {
        return true;
    }

    return false;
}

void RendererInClientInner::WaitForBufferNeedOperate()
{
    Trace trace("WaitForBufferNeedOperate");
    CheckFrozenStateInStaticMode();
    int32_t timeout = GetBufferWaitTimeoutInMs();
    FutexCode futexRes = clientBuffer_->WaitFor(
        (rendererInfo_.isStatic ? STATIC_HEARTBEAT_INTERVAL_IN_MS : static_cast<int64_t>(timeout)) *
        AUDIO_US_PER_SECOND,
        [this] () {
            if (state_ != RUNNING) {
                return true;
            }

            if (IsRestoreNeeded()) {
                return true;
            }

            return CheckStaticAndOperate();
        });
    if (futexRes == FUTEX_TIMEOUT && clientBuffer_ != nullptr) {
        uint32_t totalSizeInFrame = clientBuffer_->GetTotalSizeInFrame();
        int32_t writableInFrame = clientBuffer_->GetWritableDataFrames();
        int32_t readableFrames = clientBuffer_->GetReadableDataFrames();
        size_t totalSizeInByte = static_cast<size_t>(totalSizeInFrame) * sizePerFrameInByte_;
        size_t writableSizeInByte = writableInFrame > 0 ?
            static_cast<size_t>(writableInFrame) * sizePerFrameInByte_ : 0;
        bool condWritable = writableInFrame > 0;
        bool condCbFit = cbBufferSize_ <= totalSizeInByte;
        bool condWritableEnough = writableSizeInByte >= cbBufferSize_;
        bool condReadableLow = readableFrames <= static_cast<int32_t>(cacheSizeInFrame_.load());
        AUDIO_INFO_LOG("WaitForBufferNeedOperate timeout, sessionId:%{public}u state:%{public}d "
            "timeoutMs:%{public}d lowLatency:%{public}d writable:%{public}d readable:%{public}d cache:%{public}u "
            "cbBytes:%{public}zu totalFrames:%{public}u totalBytes:%{public}zu writableBytes:%{public}zu "
            "condWritable:%{public}d condCbFit:%{public}d condWritableEnough:%{public}d condReadableLow:%{public}d",
            sessionId_, state_.load(), timeout, IsLowLatencyRenderer(), writableInFrame, readableFrames,
            cacheSizeInFrame_.load(), cbBufferSize_,
            totalSizeInFrame, totalSizeInByte, writableSizeInByte, condWritable, condCbFit, condWritableEnough,
            condReadableLow);
    } else if (futexRes != SUCCESS) {
        AUDIO_ERR_LOG("futex err: %{public}d", futexRes);
    }
}

void RendererInClientInner::CallClientHandle()
{
    CHECK_AND_RETURN(!rendererInfo_.isStatic);
    // call client write
    std::shared_ptr<AudioRendererWriteCallback> cb = nullptr;
    {
        std::unique_lock<std::mutex> lockCb(writeCbMutex_);
        cb = writeCb_;
    }
    if (cb != nullptr) {
        Trace traceCb("RendererInClientInner::OnWriteData");
        WatchTimeout guard("write interval too long"); // default time out 40ms
        size_t length = isHWDecodingType_ ? clientBuffer_->GetDataSize() : cbBufferSize_;
        auto startRunning = ClockTime::GetCurNano();
        cb->OnWriteData(length);
        auto endRunning = ClockTime::GetCurNano();
        auto duration = endRunning - startRunning;
        if (duration >= ONWRITEDATA_TIMEOUT_NS) {
            ipcStream_->UpdateUnderrunInfo(UNDERRUN_TYPE_ISTIMEOUT, true);
        }
        guard.CheckCurrTimeout();
    }
}

bool RendererInClientInner::WriteCallbackFunc()
{
    CHECK_AND_RETURN_RET_LOG(!cbThreadReleased_, false, "Callback thread released");
    Trace traceLoop("RendererInClientInner::WriteCallbackFunc");
    if (!WaitForRunning()) {
        return true;
    }
    CheckAndProcessPendingSpanSize();
    if (cbBufferQueue_.Size() > 1) { // One callback, one enqueue, queue size should always be 1.
        HILOG_COMM_WARN("[WriteCallbackFunc]The queue is too long, reducing data through loops");
    }
    BufferDesc temp;
    while (cbBufferQueue_.PopNotWait(temp)) {
        Trace traceQueuePop("RendererInClientInner::QueueWaitPop");
        if (state_ != RUNNING) {
            cbBufferQueue_.Push(temp);
            AUDIO_INFO_LOG("Repush left buffer in queue");
            break;
        }
        traceQueuePop.End();
        // call write here.
        int32_t result = ProcessWriteInner(temp);
        // only run in pause scene, do not repush audiovivid buffer cause metadata error
        if (result > 0 && static_cast<size_t>(result) < temp.dataLength &&
            curStreamParams_.encoding == ENCODING_PCM) {
            BufferDesc tmp = {temp.buffer + static_cast<size_t>(result),
                temp.bufLength - static_cast<size_t>(result), temp.dataLength - static_cast<size_t>(result)};
            cbBufferQueue_.Push(tmp);
            AUDIO_INFO_LOG("Repush %{public}zu bytes in queue", temp.dataLength - static_cast<size_t>(result));
            break;
        }
    }

    WaitForBufferNeedOperate();

    CheckOperations();

    if (state_ != RUNNING) {
        return true;
    }
    CallClientHandle();

    Trace traceQueuePush("RendererInClientInner::QueueWaitPush");
    std::unique_lock<std::mutex> lockBuffer(cbBufferMutex_);
    cbBufferQueue_.WaitNotEmptyFor(std::chrono::milliseconds(WRITE_BUFFER_TIMEOUT_IN_MS));
    return true;
}

bool RendererInClientInner::ProcessSpeed(uint8_t *&buffer, size_t &bufferSize, bool &speedCached)
{
    speedCached = false;
#ifdef SONIC_ENABLE
    std::lock_guard lockSpeed(speedMutex_);
    if (speedEnable_.load()) {
        Trace trace(traceTag_ + " ProcessSpeed" + std::to_string(speed_));
        if (audioSpeed_ == nullptr) {
            AUDIO_ERR_LOG("audioSpeed_ is nullptr, use speed default 1.0");
            return true;
        }
        int32_t outBufferSize = 0;
        if (audioSpeed_->ChangeSpeedFunc(buffer, bufferSize, speedBuffer_, outBufferSize) == 0) {
            bufferSize = 0;
            HILOG_COMM_ERROR("[ProcessSpeed]process speed error");
            return false;
        }
        if (outBufferSize == 0) {
            HILOG_COMM_ERROR("[ProcessSpeed]speed buffer is not full");
            return false;
        }
        buffer = speedBuffer_.get();
        bufferSize = static_cast<size_t>(outBufferSize);
        speedCached = true;
    }
#endif
    return true;
}

bool RendererInClientInner::ProcessPitch(uint8_t *&buffer, size_t &bufferSize, bool &pitchCached)
{
    pitchCached = false;
    std::lock_guard lockPitch(pitchMutex_);
    
    if (isEqual(curPitch_, 1.0f) || pitchProcessor_ == nullptr) {
        return true;
    }
    Trace trace(traceTag_ + " ProcessPitch" + std::to_string(curPitch_));
    size_t outputSize = bufferSize * MAX_PITCH_BUFFER_FACTOR;
    int32_t ret = pitchProcessor_->ProcessBufferPitch(reinterpret_cast<int8_t*>(buffer), bufferSize,
        reinterpret_cast<int8_t*>(pitchBuffer_.get()), outputSize);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("ProcessBufferPitch failed");
        return false;
    }
    
    if (outputSize == 0) {
        AUDIO_ERR_LOG("Pitch buffer is empty");
        return false;
    }
    
    buffer = pitchBuffer_.get();
    bufferSize = outputSize;
    pitchCached = true;
    return true;
}

void RendererInClientInner::DfxWriteInterval()
{
    CHECK_AND_RETURN(renderMode_ == RENDER_MODE_NORMAL); // should only work in write mode.
    if (preWriteEndTime_ != 0 &&
        ((ClockTime::GetCurNano() / AUDIO_US_PER_SECOND) - preWriteEndTime_) > MAX_WRITE_INTERVAL_MS) {
        AUDIO_WARNING_LOG("[%{public}s] write interval too long cost %{public}" PRId64,
            logUtilsTag_.c_str(), (ClockTime::GetCurNano() / AUDIO_US_PER_SECOND) - preWriteEndTime_);
    }
}

int32_t RendererInClientInner::WriteInner(uint8_t *pcmBuffer, size_t pcmBufferSize, uint8_t *metaBuffer,
    size_t metaBufferSize)
{
    Trace trace("RendererInClient::Write with meta " + std::to_string(pcmBufferSize));
    CHECK_AND_RETURN_RET_LOG(curStreamParams_.encoding == ENCODING_AUDIOVIVID, ERR_NOT_SUPPORTED,
        "Write: Write not supported. encoding doesnot match.");
    BufferDesc bufDesc = {pcmBuffer, pcmBufferSize, pcmBufferSize, metaBuffer, metaBufferSize};
    CHECK_AND_RETURN_RET_LOG(converter_ != nullptr, ERR_WRITE_FAILED, "Write: converter isn't init.");
    CHECK_AND_RETURN_RET_LOG(converter_->CheckInputValid(bufDesc), ERR_INVALID_PARAM, "Write: Invalid input.");

    WriteMuteDataSysEvent(pcmBuffer, pcmBufferSize);

    converter_->Process(bufDesc);
    uint8_t *buffer;
    uint32_t bufferSize;
    converter_->GetOutputBufferStream(buffer, bufferSize);
    return WriteInner(buffer, bufferSize);
}

void RendererInClientInner::FirstFrameProcess()
{
    if (ipcStream_ == nullptr) {
        AUDIO_ERR_LOG("Error: ipcStream_ is not initialized!");
        return;
    }

    // if first call, call set thread priority. if thread tid change recall set thread priority
    if (needSetThreadPriority_.exchange(false)) {
        ipcStream_->RegisterThreadPriority(gettid(), bundleName, METHOD_WRITE_OR_READ, THREAD_PRIORITY_QOS_7);
    }

    if (!hasFirstFrameWrited_.exchange(true)) { OnFirstFrameWriting(); }
}

void RendererInClientInner::NotifyStreamSilentChange()
{
    CHECK_AND_RETURN(needNotifyStreamSilentChange_.load() && GetVolume() > 0.0f && volumeDataCount_ > 0);
    int64_t stamp = ClockTime::GetCurNano();
    Trace trace("RendererInClientInner::NotifyStreamSilentChange " + std::to_string(sessionId_));
    AudioPolicyManager::GetInstance().NotifyStreamSilentChange(clientPid_, sessionId_);
    needNotifyStreamSilentChange_.store(false);
    AUDIO_INFO_LOG("NotifyStreamSilentChange cost %{public}" PRId64 " ns", ClockTime::GetCurNano() - stamp);
}

int32_t RendererInClientInner::WriteCacheData(uint8_t *buffer, size_t bufferSize, bool bufferCached,
    size_t oriBufferSize)
{
    CHECK_AND_CALL_FUNC_RETURN_RET(sizePerFrameInByte_ > 0, ERROR,
        HILOG_COMM_ERROR("[WriteCacheData]sizePerFrameInByte :%{public}zu", sizePerFrameInByte_));
    size_t remainSize = (bufferSize / sizePerFrameInByte_) * sizePerFrameInByte_;

    RingBufferWrapper inBuffer = {
        .basicBufferDescs = {{
            {.buffer = buffer, .bufLength = remainSize},
            {.buffer = nullptr, .bufLength = 0}
        }},
        .dataLength = 0
    };

    while (remainSize >= sizePerFrameInByte_) {
        FutexCode futexRes = FUTEX_OPERATION_FAILED;
        int32_t timeout = GetBufferWaitTimeoutInMs();
        futexRes = clientBuffer_->WaitFor(static_cast<int64_t>(timeout) * AUDIO_US_PER_SECOND,
            [this] () { return (state_ != RUNNING) || CheckBufferNeedWrite(); });
        CHECK_AND_RETURN_RET_LOG(state_ == RUNNING, ERR_ILLEGAL_STATE, "failed with state:%{public}d", state_.load());
        CHECK_AND_CALL_FUNC_RETURN_RET(futexRes != FUTEX_TIMEOUT, ERROR, HILOG_COMM_ERROR("[WriteCacheData]write data "
            "time out, mode is %{public}s", (offloadEnable_ ? "offload" : "normal")));

        uint64_t writePos = clientBuffer_->GetCurWriteFrame();
        uint64_t readPos = clientBuffer_->GetCurReadFrame();
        CHECK_AND_CALL_FUNC_RETURN_RET(writePos >= readPos, ERROR, HILOG_COMM_ERROR("[WriteCacheData]writePos: "
            "%{public}" PRIu64 " readPos: %{public}" PRIu64 "", writePos, readPos));
        RingBufferWrapper ringBuffer;
        int32_t ret = clientBuffer_->GetAllWritableBufferFromPosFrame(writePos, ringBuffer);
        CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS && (ringBuffer.dataLength > 0), ERROR,
            HILOG_COMM_ERROR("[WriteCacheData]Write failed:%{public}d", ret));
        auto copySize = std::min(remainSize, ringBuffer.dataLength);
        inBuffer.dataLength = copySize;
        ret = ringBuffer.CopyInputBufferValueToCurBuffer(inBuffer);
        CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS, ret,
            HILOG_COMM_ERROR("[WriteCacheData]errcode: %{public}d", ret));
        clientBuffer_->SetCurWriteFrame((writePos + (copySize / sizePerFrameInByte_)), false);
        inBuffer.SeekFromStart(copySize);
        remainSize -= copySize;
    }
    size_t writtenSize = bufferSize - remainSize;

    preWriteEndTime_ = ClockTime::GetCurNano() / AUDIO_US_PER_SECOND;

    CHECK_AND_RETURN_RET(ProcessVolume(), ERR_OPERATION_FAILED);
    VolumeTools::DfxOperation({.buffer = buffer, .bufLength = writtenSize, .dataLength = writtenSize},
        clientConfig_.streamInfo, traceTag_, volumeDataCount_);
    NotifyStreamSilentChange();
    DumpFileUtil::WriteDumpFile(dumpOutFd_, static_cast<void *>(buffer), writtenSize);

    CHECK_AND_CALL_FUNC_RETURN_RET(ipcStream_ != nullptr, ERR_OPERATION_FAILED,
        HILOG_COMM_ERROR("[WriteCacheData]WriteCacheData failed, null ipcStream_."));
    ipcStream_->UpdatePosition(); // notiify server update position
    HandleRendererPositionChanges(writtenSize);

    return bufferCached ? oriBufferSize : writtenSize;
}

void RendererInClientInner::HandleRendererPositionChanges(size_t bytesWritten)
{
    totalBytesWritten_ += static_cast<int64_t>(bytesWritten);
    if (sizePerFrameInByte_ == 0) {
        AUDIO_ERR_LOG("HandleRendererPositionChanges: sizePerFrameInByte_ is 0");
        return;
    }
    int64_t writtenFrameNumber = totalBytesWritten_ / static_cast<int64_t>(sizePerFrameInByte_);
    AUDIO_DEBUG_LOG("frame size: %{public}zu", sizePerFrameInByte_);

    {
        std::lock_guard<std::mutex> lock(markReachMutex_);
        if (!rendererMarkReached_) {
            AUDIO_DEBUG_LOG("Frame mark position: %{public}" PRId64", Total frames written: %{public}" PRId64,
                static_cast<int64_t>(rendererMarkPosition_), static_cast<int64_t>(writtenFrameNumber));
            if (writtenFrameNumber >= rendererMarkPosition_) {
                AUDIO_DEBUG_LOG("OnMarkReached %{public}" PRId64".", rendererMarkPosition_);
                SendRenderMarkReachedEvent(rendererMarkPosition_);
                rendererMarkReached_ = true;
            }
        }
    }

    {
        std::lock_guard<std::mutex> lock(periodReachMutex_);
        rendererPeriodWritten_ += static_cast<int64_t>((bytesWritten / sizePerFrameInByte_));
        AUDIO_DEBUG_LOG("Frame period number: %{public}" PRId64", Total frames written: %{public}" PRId64,
            static_cast<int64_t>(rendererPeriodWritten_), static_cast<int64_t>(totalBytesWritten_));
        if (rendererPeriodWritten_ >= rendererPeriodSize_ && rendererPeriodSize_ > 0) {
            rendererPeriodWritten_ %= rendererPeriodSize_;
            AUDIO_DEBUG_LOG("OnPeriodReached, remaining frames: %{public}" PRId64,
                static_cast<int64_t>(rendererPeriodWritten_));
            SendRenderPeriodReachedEvent(rendererPeriodSize_);
        }
    }
}

int32_t RendererInClientInner::ProcessBufferAndWriteCache(uint8_t *buffer, size_t bufferSize, size_t oriBufferSize)
{
    bool speedCached = false;
    bool pitchCached = false;
    AudioWriteState currentState = audioWriteState_.load();
    currentState.perPeriodFrame_ += bufferSize / sizePerFrameInByte_;
    
    if (!ProcessSpeed(buffer, bufferSize, speedCached)) {
        audioWriteState_.store(currentState);
        return bufferSize;
    }
    
    if (!ProcessPitch(buffer, bufferSize, pitchCached)) {
        audioWriteState_.store(currentState);
        return bufferSize;
    }
    
    WriteMuteDataSysEvent(buffer, bufferSize);
    
    CHECK_AND_RETURN_RET_PRELOG(state_ == RUNNING, ERR_ILLEGAL_STATE,
        "Write: Illegal state:%{public}u sessionid: %{public}u", state_.load(), sessionId_);
    
    if (isBlendSet_) {
        audioBlend_.Process(buffer, bufferSize);
    }
    
    currentState.unprocessedFramesBytes_ += currentState.perPeriodFrame_;
    currentState.totalBytesWrittenAfterFlush_ += bufferSize / sizePerFrameInByte_;
    currentState.perPeriodFrame_ = 0;
    audioWriteState_.store(currentState);
    
    return WriteCacheData(buffer, bufferSize, speedCached || pitchCached, oriBufferSize);
}

int32_t RendererInClientInner::WriteInner(uint8_t *buffer, size_t bufferSize)
{
    CheckAndProcessPendingSpanSize();
    // eg: RendererInClient::sessionId:100001 WriteSize:3840
    DfxWriteInterval();
    Trace trace(traceTag_+ " WriteSize:" + std::to_string(bufferSize));
    CHECK_AND_RETURN_RET_LOG(buffer != nullptr && bufferSize < MAX_WRITE_SIZE && bufferSize > 0, ERR_INVALID_PARAM,
        "invalid size is %{public}zu", bufferSize);

    // Bugfix. Callback threadloop would go into infinite loop, consuming too much data from app
    // but fail to play them due to audio server's death. Block and exit callback threadloop when server died.
    if (gServerProxy_ == nullptr) {
        cbThreadReleased_ = true;
        uint32_t samplingRate = clientConfig_.streamInfo.samplingRate;
        uint32_t channels = clientConfig_.streamInfo.channels;
        uint32_t samplePerFrame = Util::GetSamplePerFrame(clientConfig_.streamInfo.format);
        // calculate wait time by buffer size, 10e6 is converting seconds to microseconds
        uint32_t waitTimeUs = bufferSize * 10e6 / (samplingRate * channels * samplePerFrame);
        HILOG_COMM_ERROR("[WriteInner]server is died! wait %{public}d us", waitTimeUs);
        usleep(waitTimeUs);
        return ERR_WRITE_BUFFER;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET(gServerProxy_ != nullptr, ERROR,
        HILOG_COMM_ERROR("[WriteInner]server is died"));
    if (clientBuffer_->GetStreamStatus() == nullptr) {
        HILOG_COMM_ERROR("[WriteInner]The stream status is null!");
        return ERR_INVALID_PARAM;
    }

    CHECK_AND_RETURN_RET(CallStartWhenInStandby() == SUCCESS, ERR_OPERATION_FAILED);

    FirstFrameProcess();

    std::lock_guard<std::mutex> lock(writeMutex_);

    size_t oriBufferSize = bufferSize;
    int32_t result = ProcessBufferAndWriteCache(buffer, bufferSize, oriBufferSize);
    MonitorMutePlay(false);
    return result;
}

void RendererInClientInner::ResetFramePosition()
{
    Trace trace("RendererInClientInner::ResetFramePosition");
    uint64_t timestampval = 0;
    uint64_t latency = 0;
    CHECK_AND_CALL_FUNC_RETURN(ipcStream_ != nullptr,
        HILOG_COMM_ERROR("[ResetFramePosition]ipcStream is not inited!"));
    int32_t ret = ipcStream_->GetAudioPosition(lastFlushReadIndex_, timestampval, latency,
        Timestamp::Timestampbase::MONOTONIC);
    CHECK_AND_RETURN_PRELOG(ret == SUCCESS, "Get position failed: %{public}d", ret);
    ret = ipcStream_->GetSpeedPosition(lastSpeedFlushReadIndex_, timestampval, latency,
        Timestamp::Timestampbase::MONOTONIC);
    CHECK_AND_RETURN_PRELOG(ret == SUCCESS, "Get speed position failed: %{public}d", ret);
    // no need to reset timestamp, only reset frameposition
    for (int32_t base = 0; base < Timestamp::Timestampbase::BASESIZE; base++) {
        lastFramePosAndTimePair_[base].first = 0;
        lastFramePosAndTimePairWithSpeed_[base].first = 0;
        lastSwitchPosition_[base] = 0;
    }
    dropPosition_ = 0;
    dropHdiPosition_ = 0;
    audioWriteState_.store(AudioWriteState{});
    writtenAtSpeedChange_.store(WrittenFramesWithSpeed{0, speed_});
}

bool RendererInClientInner::IsMutePlaying()
{
    // this is updated in DfxOperation
    if (volumeDataCount_ < 0) {
        return true;
    }

    return mutePlaying_;
}

void RendererInClientInner::MonitorMutePlay(bool isPlayEnd)
{
    int64_t cur = ClockTime::GetRealNano();
    // judge if write mute
    bool isMutePlay = isPlayEnd ? false : IsMutePlaying();
    // not write mute or play end
    if (!isMutePlay) {
        if (mutePlayStartTime_ == 0) {
            return;
        }
        if (cur - mutePlayStartTime_ > MUTE_PLAY_MIN_DURAION) {
            ReportWriteMuteEvent(cur - mutePlayStartTime_);
            return;
        }
        mutePlayStartTime_ = 0;
        return;
    }

    // write mute
    if (mutePlayStartTime_ == 0) {
        // record first mute play
        mutePlayStartTime_ = cur;
        return;
    }
    if (cur - mutePlayStartTime_ > MUTE_PLAY_MAX_DURAION) {
        ReportWriteMuteEvent(cur - mutePlayStartTime_);
    }
}

void RendererInClientInner::ReportWriteMuteEvent(int64_t mutePlayDuration)
{
    mutePlayDuration /= AUDIO_US_PER_SECOND; // ns -> ms
    bool isMute = GetMute();
    bool isClientMute = muteCmd_ == CMD_FROM_CLIENT;
    uint8_t muteState = (isClientMute ? 0x0 : 0x4) | (isMute ? 0x1 : 0x0);

    AUDIO_WARNING_LOG("[%{public}d]MutePlaying for %{public}" PRId64" ms, muteState:%{public}d", sessionId_,
        mutePlayDuration, muteState);
    std::shared_ptr<Media::MediaMonitor::EventBean> bean = std::make_shared<Media::MediaMonitor::EventBean>(
        Media::MediaMonitor::AUDIO, Media::MediaMonitor::APP_WRITE_MUTE, Media::MediaMonitor::EventType::FAULT_EVENT);
    bean->Add("UID", appUid_); // for APP_BUNDLE_NAME
    bean->Add("STREAM_TYPE", clientConfig_.rendererInfo.streamUsage);
    bean->Add("SESSION_ID", static_cast<int32_t>(sessionId_));
    bean->Add("STREAM_VOLUME", clientVolume_);
    bean->Add("MUTE_STATE", static_cast<int32_t>(muteState));
    bean->Add("APP_BACKGROUND_STATE", 0);
    bean->Add("MUTE_PLAY_START_TIME", static_cast<uint64_t>(mutePlayStartTime_ / AUDIO_US_PER_SECOND));
    bean->Add("MUTE_PLAY_DURATION", static_cast<int32_t>(mutePlayDuration));
    Media::MediaMonitor::MediaMonitorManager::GetInstance().WriteLogMsg(bean);
    mutePlayStartTime_ = 0; // reset it to 0 for next record
}

void RendererInClientInner::WriteMuteDataSysEvent(uint8_t *buffer, size_t bufferSize)
{
    if (silentModeAndMixWithOthers_) {
        return;
    }
    if (IsInvalidBuffer(buffer, bufferSize)) {
        if (startMuteTime_ == 0) {
            startMuteTime_ = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        }
        std::time_t currentTime = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        if ((currentTime - startMuteTime_ >= ONE_MINUTE) && !isUpEvent_) {
            HILOG_COMM_WARN("[WriteMuteDataSysEvent]write silent data for some time");
            isUpEvent_ = true;
            std::shared_ptr<Media::MediaMonitor::EventBean> bean = std::make_shared<Media::MediaMonitor::EventBean>(
                Media::MediaMonitor::AUDIO, Media::MediaMonitor::BACKGROUND_SILENT_PLAYBACK,
                Media::MediaMonitor::FREQUENCY_AGGREGATION_EVENT);
            bean->Add("CLIENT_UID", appUid_);
            Media::MediaMonitor::MediaMonitorManager::GetInstance().WriteLogMsg(bean);
        }
    } else if (buffer[0] != 0 && startMuteTime_ != 0) {
        startMuteTime_ = 0;
    }
}

bool RendererInClientInner::IsInvalidBuffer(uint8_t *buffer, size_t bufferSize)
{
    bool isInvalid = false;
    uint8_t ui8Data = 0;
    int16_t i16Data = 0;
    switch (clientConfig_.streamInfo.format) {
        case SAMPLE_U8:
            CHECK_AND_RETURN_RET_LOG(bufferSize > 0, false, "buffer size is too small");
            ui8Data = *buffer;
            isInvalid = ui8Data == 0;
            break;
        case SAMPLE_S16LE:
            CHECK_AND_RETURN_RET_LOG(bufferSize > 1, false, "buffer size is too small");
            i16Data = *(reinterpret_cast<const int16_t*>(buffer));
            isInvalid = i16Data == 0;
            break;
        default:
            break;
    }
    return isInvalid;
}

bool RendererInClientInner::ProcessVolume()
{
    // volume process in client
    if (volumeRamp_.IsActive()) {
        // do not call SetVolume here.
        clientVolume_ = volumeRamp_.GetRampVolume();
        AUDIO_INFO_LOG("clientVolume_:%{public}f", clientVolume_);
        Trace traceVolume("RendererInClientInner::WriteCacheData:Ramp:clientVolume_:" + std::to_string(clientVolume_));
        SetInnerVolume(clientVolume_);
    }
    return true;
}

int32_t RendererInClientInner::RegisterSpatializationStateEventListener()
{
    if (firstSpatializationRegistered_) {
        firstSpatializationRegistered_ = false;
    } else {
        UnregisterSpatializationStateEventListener(spatializationRegisteredSessionID_);
    }

    if (!spatializationStateChangeCallback_) {
        spatializationStateChangeCallback_ = std::make_shared<SpatializationStateChangeCallbackImpl>();
        CHECK_AND_RETURN_RET_LOG(spatializationStateChangeCallback_, ERROR, "Memory Allocation Failed !!");
    }
    spatializationStateChangeCallback_->SetRendererInClientPtr(shared_from_this());

    int32_t ret = AudioPolicyManager::GetInstance().RegisterSpatializationStateEventListener(
        sessionId_, rendererInfo_.streamUsage, spatializationStateChangeCallback_);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "RegisterSpatializationStateEventListener failed");
    spatializationRegisteredSessionID_ = sessionId_;

    return SUCCESS;
}

int32_t RendererInClientInner::UnregisterSpatializationStateEventListener(uint32_t sessionID)
{
    int32_t ret = AudioPolicyManager::GetInstance().UnregisterSpatializationStateEventListener(sessionID);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "UnregisterSpatializationStateEventListener failed");
    return SUCCESS;
}

bool RendererInClientInner::DrainAudioStreamInner(bool stopFlag)
{
    Trace trace("RendererInClientInner::DrainAudioStreamInner " + std::to_string(sessionId_));
    if (state_ != RUNNING) {
        AUDIO_ERR_LOG("Drain failed. Illegal state:%{public}u", state_.load());
        return false;
    }
    if (rendererInfo_.streamUsage == STREAM_USAGE_INTERPHONE) {
        return true;
    }

    CHECK_AND_CALL_FUNC_RETURN_RET(ipcStream_ != nullptr, false,
        HILOG_COMM_ERROR("[DrainAudioStreamInner]ipcStream is not inited!"));
    AUDIO_INFO_LOG("stopFlag:%{public}d", stopFlag);
    int32_t ret = ipcStream_->Drain(stopFlag);
    if (ret != SUCCESS) {
        AUDIO_ERR_LOG("Drain call server failed:%{public}u", ret);
        return false;
    }
    std::unique_lock<std::mutex> waitLock(callServerMutex_);
    bool stopWaiting = callServerCV_.wait_for(waitLock, std::chrono::milliseconds(OPERATION_TIMEOUT_IN_MS), [this] {
        return notifiedOperation_ == DRAIN_STREAM; // will be false when got notified.
    });

    // clear cbBufferQueue
    if (renderMode_ == RENDER_MODE_CALLBACK && stopFlag) {
        cbBufferQueue_.Clear();
        if (memset_s(cbBuffer_.get(), cbBufferSize_, 0, cbBufferSize_) != EOK) {
            AUDIO_ERR_LOG("memset_s buffer failed");
        };
    }

    if (notifiedOperation_ != DRAIN_STREAM || notifiedResult_ != SUCCESS) {
        AUDIO_ERR_LOG("Drain failed: %{public}s Operation:%{public}d result:%{public}" PRId64".",
            (!stopWaiting ? "timeout" : "no timeout"), notifiedOperation_, notifiedResult_);
        notifiedOperation_ = MAX_OPERATION_CODE;
        return false;
    }
    notifiedOperation_ = MAX_OPERATION_CODE;
    waitLock.unlock();
    AUDIO_INFO_LOG("Drain stream SUCCESS, sessionId: %{public}d", sessionId_);
    return true;
}

void RendererInClientInner::RegisterThreadPriorityOnStart(StateChangeCmdType cmdType)
{
    pid_t tid;
    switch (rendererInfo_.playerType) {
        case PLAYER_TYPE_ARKTS_AUDIO_RENDERER:
            // main thread
            tid = getpid();
            break;
        case PLAYER_TYPE_OH_AUDIO_RENDERER:
            tid = gettid();
            break;
        default:
            return;
    }

    if (cmdType == CMD_FROM_CLIENT) {
        std::lock_guard lock(lastCallStartByUserTidMutex_);
        lastCallStartByUserTid_ = tid;
    } else if (cmdType == CMD_FROM_SYSTEM) {
        std::lock_guard lock(lastCallStartByUserTidMutex_);
        CHECK_AND_RETURN_LOG(lastCallStartByUserTid_.has_value(), "has not value");
        tid = lastCallStartByUserTid_.value();
    } else {
        AUDIO_ERR_LOG("illegal param");
        return;
    }

    ipcStream_->RegisterThreadPriority(tid, bundleName, METHOD_START, THREAD_PRIORITY_QOS_7);
}

void RendererInClientInner::ResetCallbackLoopTid()
{
    AUDIO_INFO_LOG("to -1");
    callbackLoopTid_ = -1;
}

SpatializationStateChangeCallbackImpl::SpatializationStateChangeCallbackImpl()
{
    AUDIO_INFO_LOG("Instance create");
}

SpatializationStateChangeCallbackImpl::~SpatializationStateChangeCallbackImpl()
{
    AUDIO_INFO_LOG("Instance destory");
}

void SpatializationStateChangeCallbackImpl::SetRendererInClientPtr(
    std::shared_ptr<RendererInClientInner> rendererInClientPtr)
{
    rendererInClientPtr_ = rendererInClientPtr;
}

void SpatializationStateChangeCallbackImpl::OnSpatializationStateChange(
    const AudioSpatializationState &spatializationState)
{
    std::shared_ptr<RendererInClientInner> rendererInClient = rendererInClientPtr_.lock();
    if (rendererInClient != nullptr) {
        rendererInClient->OnSpatializationStateChange(spatializationState);
    }
}

void RendererInClientInner::FlushSpeedBuffer()
{
    std::lock_guard lock(speedMutex_);

    if (audioSpeed_ != nullptr) {
        audioSpeed_->Flush();
    }
}

int32_t RendererInClientInner::SetSpeedInner(float speed)
{
    // set the speed to 1.0 and the speed has never been turned on, no actual sonic stream is created.
    if (isEqual(speed, SPEED_NORMAL) && !speedEnable_) {
        speed_ = speed;
        return SUCCESS;
    }

    if (audioSpeed_ == nullptr) {
        audioSpeed_ = std::make_unique<AudioSpeed>(curStreamParams_.samplingRate, curStreamParams_.format,
            curStreamParams_.channels);
        GetBufferSize(bufferSize_);
        speedBuffer_ = std::make_unique<uint8_t[]>(MAX_SPEED_BUFFER_SIZE);
    }
    audioSpeed_->SetSpeed(speed);
    AudioWriteState state = audioWriteState_.load();
    uint64_t samplesWritten = state.totalBytesWrittenAfterFlush_;
    writtenAtSpeedChange_.store(WrittenFramesWithSpeed{samplesWritten, speed_});
    speed_ = speed;
    speedEnable_ = true;
    AUDIO_DEBUG_LOG("SetSpeed %{public}f, OffloadEnable %{public}d", speed_, offloadEnable_);
    return SUCCESS;
}

int32_t RendererInClientInner::SetStaticBufferEventCallback(std::shared_ptr<StaticBufferEventCallback> callback)
{
    CHECK_AND_RETURN_RET_LOG(rendererInfo_.isStatic, ERROR_UNSUPPORTED, "not support!");
    CHECK_AND_RETURN_RET_LOG(callback != nullptr, ERR_INVALID_PARAM, "Invalid null callback");
    CHECK_AND_RETURN_RET_LOG(renderMode_ == RENDER_MODE_STATIC, ERR_INCORRECT_MODE, "incorrect render mode");
    std::lock_guard<std::mutex> lock(staticBufferMutex_);
    audioStaticBufferEventCallback_ = callback;
    return SUCCESS;
}

int32_t RendererInClientInner::SetStaticTriggerRecreateCallback(std::function<void()> sendStaticRecreateFunc)
{
    CHECK_AND_RETURN_RET_LOG(rendererInfo_.isStatic, ERROR_UNSUPPORTED, "not support!");
    CHECK_AND_RETURN_RET_LOG(sendStaticRecreateFunc != nullptr, ERR_INVALID_PARAM, "Invalid null callback");
    CHECK_AND_RETURN_RET_LOG(renderMode_ == RENDER_MODE_STATIC, ERR_INCORRECT_MODE, "incorrect render mode");
    std::lock_guard<std::mutex> lock(staticBufferMutex_);
    sendStaticRecreateFunc_ = sendStaticRecreateFunc;
    return SUCCESS;
}

void RendererInClientInner::UpdateUnderrunInfo(UnderrunInfoType underrunInfoKey, int32_t underrunInfoVal)
{
    CHECK_AND_RETURN_LOG(ipcStream_ != nullptr, "ipcStream_ is nullptr");
    ipcStream_->UpdateUnderrunInfo(underrunInfoKey, underrunInfoVal);
    if (underrunInfoKey == UNDERRUN_TYPE_ISUSEARK) {
        isMainUseArk_ = !!underrunInfoVal;
    }
}

int32_t RendererInClientInner::SetLoopTimes(int64_t bufferLoopTimes)
{
    CHECK_AND_RETURN_RET_LOG(rendererInfo_.isStatic, ERROR_UNSUPPORTED, "not support!");
    CHECK_AND_RETURN_RET_LOG(renderMode_ == RENDER_MODE_STATIC, ERR_INCORRECT_MODE, "incorrect render mode");
    CHECK_AND_RETURN_RET_LOG(ipcStream_ != nullptr, ERROR, "ipcStream_ is nullptr");
    staticBufferInfo_.totalLoopTimes_ = bufferLoopTimes;
    ipcStream_->SetLoopTimes(bufferLoopTimes);
    return SUCCESS;
}

bool RendererInClientInner::CheckStaticAndOperate()
{
    if (rendererInfo_.isStatic) {
        return clientBuffer_->IsNeedSendLoopEndCallback() || clientBuffer_->IsNeedSendBufferEndCallback() ||
            clientBuffer_->IsFirstFrame();
    } else {
        return CheckBufferNeedWrite();
    }
}

void RendererInClientInner::CheckOperations()
{
    if (!rendererInfo_.isStatic) {
        return;
    }

    Trace trace("RendererInClientInner::ProcessStaticOperations");
    if (IsRestoreNeeded() && sendStaticRecreateFunc_ != nullptr) {
        sendStaticRecreateFunc_();
    }
    std::unique_lock<std::mutex> staticBufferLock(staticBufferMutex_);
    CHECK_AND_RETURN_LOG(audioStaticBufferEventCallback_ != nullptr, "audioStaticBufferEventCallback_ is nullptr");
    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "clientBuffer is nullptr");
    while (clientBuffer_->IsNeedSendBufferEndCallback()) {
        Trace traceLoop("RendererInClientInner send BUFFER_END_EVENT");
        audioStaticBufferEventCallback_->OnStaticBufferEvent(BUFFER_END_EVENT);
        clientBuffer_->DecreaseBufferEndCallbackSendTimes();
    }
    if (clientBuffer_->IsNeedSendLoopEndCallback()) {
        audioStaticBufferEventCallback_->OnStaticBufferEvent(LOOP_END_EVENT);
        clientBuffer_->SetIsNeedSendLoopEndCallback(false);
    }
    if (clientBuffer_->IsFirstFrame()) {
        clientBuffer_->SetIsFirstFrame(false);
        OnFirstFrameWriting();
    }
}

void RendererInClientInner::SetStaticBufferInfo(StaticBufferInfo staticBufferInfo,
    std::shared_ptr<AudioSharedMemory> sharedMemory)
{
    CHECK_AND_RETURN_LOG(rendererInfo_.isStatic, "SetStaticBufferInfo not support!");
    staticBufferInfo_ = staticBufferInfo;
    staticSharedMemory_ = sharedMemory;
}

void RendererInClientInner::CheckFrozenStateInStaticMode()
{
    if (rendererInfo_.isStatic && clientBuffer_->CheckFrozenAndSetLastProcessTime(BUFFER_IN_CLIENT)) {
        CHECK_AND_RETURN_LOG(CallStartWhenInStandby() == SUCCESS, "CallStartWhenInStandby failed");
    }
}

int32_t RendererInClientInner::CallStartWhenInStandby()
{
    CHECK_AND_RETURN_RET(clientBuffer_->GetStreamStatus()->load() == STREAM_STAND_BY, SUCCESS);
    Trace trace2(traceTag_+ " call start to exit stand-by");
    std::unique_lock<std::mutex> stateLock(statusMutex_);
    // The Client is still in RUNNING state when been frozen.
    CHECK_AND_RETURN_RET_LOG(state_ == RUNNING, SUCCESS, "Client is not RUNNING!");
    CHECK_AND_CALL_FUNC_RETURN_RET(ipcStream_ != nullptr, ERROR,
        HILOG_COMM_ERROR("[CallStartWhenInStandby]ipcStream is not inited!"));
    int32_t ret = ipcStream_->Start(writeCb_ == nullptr);
    AUDIO_INFO_LOG("%{public}u call start to exit stand-by ret %{public}u", sessionId_, ret);
    return SUCCESS;
}

void RendererInClientInner::CheckAndProcessPendingSpanSize()
{
    Trace trace("RendererInClientInner::CheckAndProcessPendingSpanSize");
    AUDIO_DEBUG_LOG("CheckAndProcessPendingSpanSize enter, sessionId:%{public}u", sessionId_);

    CHECK_AND_RETURN_LOG(clientBuffer_ != nullptr, "clientBuffer_ is nullptr");
    uint64_t spanSize = 0;
    uint64_t engineSize = 0;
    uint32_t routeFlag = 0;
    spanSize = clientBuffer_->GetAndClearPendingSpanSize(engineSize, routeFlag);
    if (spanSize == 0) {
        AUDIO_DEBUG_LOG("No pending span size");
        return;
    }
    const uint32_t MIN_SPAN_SIZE = 32;
    const uint32_t MAX_SPAN_SIZE = 8192;
    uint32_t spanSizeInFrame = static_cast<uint32_t>(spanSize);
    if (spanSizeInFrame < MIN_SPAN_SIZE || spanSizeInFrame > MAX_SPAN_SIZE) {
        AUDIO_ERR_LOG("Invalid pending span size %{public}u, ignore", spanSizeInFrame);
        return;
    }
    AUDIO_INFO_LOG("Process pending span size: %{public}u engineSize:%{public}" PRIu64 " routeFlag:0x%{public}x",
        spanSizeInFrame, engineSize, routeFlag);

    // Directly update the parameters without calling InitSharedBuffer (the buffer remains unchanged)
    spanSizeInFrame_ = spanSizeInFrame;
    clientSpanSizeInByte_ = spanSizeInFrame_ * sizePerFrameInByte_;
    cacheSizeInFrame_ = engineSize;

    // Update rendererFlags (based on routeFlag)
    if (routeFlag != 0) {
        rendererInfo_.audioFlag = routeFlag;
        if (routeFlag & AUDIO_OUTPUT_FLAG_FAST) {
            if (routeFlag & AUDIO_OUTPUT_FLAG_VOIP) {
                rendererInfo_.rendererFlags = AUDIO_FLAG_VOIP_FAST;
                AUDIO_INFO_LOG("Updated rendererFlags to VOIP_FAST (0x%{public}x)", rendererInfo_.rendererFlags);
            } else {
                rendererInfo_.rendererFlags = AUDIO_FLAG_MMAP;
                AUDIO_INFO_LOG("Updated rendererFlags to MMAP (0x%{public}x)", rendererInfo_.rendererFlags);
            }
        } else {
            rendererInfo_.rendererFlags = AUDIO_FLAG_NORMAL;
            AUDIO_INFO_LOG("Updated rendererFlags to NORMAL (0x%{public}x)", rendererInfo_.rendererFlags);
        }
    }
    AUDIO_INFO_LOG("Updated spanSize:%{public}u clientSpanByte:%{public}zu cacheSize:%{public}u "
        "rendererFlags:0x%{public}x",
        spanSizeInFrame_, clientSpanSizeInByte_, cacheSizeInFrame_.load(), rendererInfo_.rendererFlags);
}

void RendererInClientInner::UpdateStreamState(State state)
{
   // When updating the stream state, the focus state is updated synchronously.
    state_ = state;
    streamFocusState_ = static_cast<StreamFocusState>(state);
}

StreamFocusState RendererInClientInner::GetFocusState()
{
    std::lock_guard lock(focusStatusMutex_);
    return streamFocusState_;
}
 
void RendererInClientInner::SetFocusState(StreamFocusState state)
{
    std::lock_guard lock(focusStatusMutex_);
    streamFocusState_ = state;
}

void RendererInClientInner::SendAudioErrorEventAndProcessOther(int32_t uid, int32_t errorCode,
    const std::string &erroDesc, bool isClient, State state)
{
    StreamDfxManager::GetInstance().SendAudioErrorEvent(uid, errorCode, erroDesc, isClient);
    streamFocusState_ = static_cast<StreamFocusState>(state);
}

} // namespace AudioStandard
} // namespace OHOS
