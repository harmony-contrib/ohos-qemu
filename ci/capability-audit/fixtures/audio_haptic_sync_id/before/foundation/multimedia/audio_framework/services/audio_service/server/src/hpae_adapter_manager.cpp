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
#define LOG_TAG "HpaeAdapterManager"
#endif

#include "hpae_adapter_manager.h"
#include <sstream>
#include <atomic>
#include "audio_errors.h"
#include "hpae_renderer_stream_impl.h"
#include "hpae_capturer_stream_impl.h"
#include "audio_utils.h"
#include "audio_info.h"
#include "core_service_handler.h"
#include "policy_handler.h"
#include "audio_engine_log.h"

namespace OHOS {
namespace AudioStandard {

const char* PRO_INNER_CAPTURER_SOURCE = "Speaker";
const char* PRO_DUAL_PLAYBACK_SINK = "Speaker";
static constexpr uint64_t DUAL_STREAM_PREBUF_TIME_MS = 60;

HpaeAdapterManager::HpaeAdapterManager(ManagerType type)
{
    AUDIO_INFO_LOG("Constructor with type:%{public}d", type);
    managerType_ = type;
}

int32_t HpaeAdapterManager::CreateRender(AudioProcessConfig processConfig, std::shared_ptr<IRendererStream> &stream,
    std::optional<std::string_view> originDeviceName)
{
    AUDIO_DEBUG_LOG("Create renderer start");
    uint32_t sessionId = 0;
    sessionId = processConfig.originalSessionId;
    if (managerType_ == DUP_PLAYBACK || managerType_ == DUAL_PLAYBACK ||
        processConfig.originalSessionId < MIN_STREAMID || processConfig.originalSessionId > MAX_STREAMID) {
        sessionId = CoreServiceHandler::GetInstance().GenerateSessionId();
    }
    processConfig.originalSessionId = sessionId;
    AUDIO_INFO_LOG("Create [%{public}d] type renderer:[%{public}u]", managerType_, sessionId);
    std::string deviceName = "";
    int32_t ret = GetDeviceNameForConnect(processConfig, processConfig.originalSessionId, deviceName);
    CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS, ERROR_INVALID_PARAM,
        HILOG_COMM_ERROR("[CreateRender]get devicename err: %{public}d", ret));
    if (managerType_ != DUP_PLAYBACK && managerType_ != DUAL_PLAYBACK) {
        deviceName = CoreServiceHandler::GetInstance().GetModuleNameBySessionId(sessionId);
    }
    if (deviceName == "") {
        AUDIO_INFO_LOG("sink name is null");
        deviceName = "Speaker";
    }
    deviceName = originDeviceName.has_value() ? std::string(originDeviceName.value()) : deviceName;
    // HpaeAdapterManager is solely responsible for creating paStream objects
    std::shared_ptr<IRendererStream> rendererStream = CreateRendererStream(processConfig, deviceName);
    CHECK_AND_RETURN_RET_LOG(rendererStream != nullptr, ERR_DEVICE_INIT, "Failed to init pa stream");
    SetHighResolution(processConfig, sessionId);
    rendererStream->SetStreamIndex(sessionId);
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    rendererStreamMap_[sessionId] = rendererStream;
    stream = rendererStream;

    if (managerType_ == DUP_PLAYBACK || managerType_ == DUAL_PLAYBACK) {
        AUDIO_INFO_LOG("renderer:%{public}u is DUP or DUAL, not need add to sink vecotr", sessionId);
        return SUCCESS;
    }

    std::lock_guard<std::mutex> mutex(sinkInputsMutex_);
    SinkInput sinkInput;
    sinkInput.streamId = static_cast<int32_t>(sessionId);
    sinkInput.streamType = processConfig.streamType;
    sinkInput.uid = processConfig.appInfo.appUid;
    sinkInput.pid = processConfig.appInfo.appPid;
    sinkInput.paStreamId = sessionId;
    sinkInputs_.push_back(sinkInput);
    return SUCCESS;
}

int32_t HpaeAdapterManager::ReleaseRender(uint32_t streamIndex)
{
    AUDIO_DEBUG_LOG("Release [%{public}d] type render:[%{public}u]", managerType_, streamIndex);
    std::unique_lock<std::mutex> lock(streamMapMutex_);
    auto currentRender = SafeGetMap(rendererStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentRender != nullptr, SUCCESS, "No matching stream");
    rendererStreamMap_[streamIndex] = nullptr;
    rendererStreamMap_.erase(streamIndex);
    AUDIO_INFO_LOG("rendererStreamMap_.size() : %{public}zu", rendererStreamMap_.size());
    if (rendererStreamMap_.size() == 0) {
        AUDIO_INFO_LOG("Release the last stream");
    }
    lock.unlock();

    if (currentRender->Release() < 0) {
        AUDIO_WARNING_LOG("Release stream %{public}d failed", streamIndex);
        return ERR_OPERATION_FAILED;
    }

    if (isHighResolutionExist_ && highResolutionIndex_ == streamIndex) {
        isHighResolutionExist_ = false;
    }

    if (managerType_ == DUP_PLAYBACK || managerType_ == DUAL_PLAYBACK) {
        AUDIO_INFO_LOG("renderer:%{public}u is DUP or DUAL, not need remove", streamIndex);
        return SUCCESS;
    }

    std::lock_guard<std::mutex> mutex(sinkInputsMutex_);
    sinkInputs_.erase(
        std::remove_if(sinkInputs_.begin(),
            sinkInputs_.end(),
            [&](const SinkInput &sinkInput) { return static_cast<uint32_t>(sinkInput.streamId) == streamIndex; }),
        sinkInputs_.end());
    return SUCCESS;
}

int32_t HpaeAdapterManager::StartRender(uint32_t streamIndex)
{
    AUDIO_DEBUG_LOG("Enter StartRender");
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    auto currentRender = SafeGetMap(rendererStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentRender != nullptr, SUCCESS, "No matching stream");
    return currentRender->Start();
}

int32_t HpaeAdapterManager::StartRenderWithSyncId(uint32_t streamIndex, const int32_t &syncId)
{
    AUDIO_DEBUG_LOG("Enter StartRender");
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    auto currentRender = SafeGetMap(rendererStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentRender != nullptr, SUCCESS, "No matching stream");
    return syncId > 0 ? currentRender->StartWithSyncId(syncId) :
        currentRender->Start();
}

int32_t HpaeAdapterManager::StopRender(uint32_t streamIndex)
{
    AUDIO_DEBUG_LOG("Enter StopRender");
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    auto currentRender = SafeGetMap(rendererStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentRender != nullptr, SUCCESS, "No matching stream");
    return currentRender->Stop();
}

int32_t HpaeAdapterManager::PauseRender(uint32_t streamIndex, bool isStandby)
{
    AUDIO_DEBUG_LOG("Enter PauseRender");
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    auto currentRender = SafeGetMap(rendererStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentRender != nullptr, SUCCESS, "No matching stream");
    currentRender->Pause();
    return SUCCESS;
}

int32_t HpaeAdapterManager::TriggerStartIfNecessary()
{
    return SUCCESS;
}

int32_t HpaeAdapterManager::GetStreamCount() const noexcept
{
    if (managerType_ == RECORDER) {
        return capturerStreamMap_.size();
    } else {
        return rendererStreamMap_.size();
    }
}

int32_t HpaeAdapterManager::GetDeviceNameForConnect(AudioProcessConfig processConfig, uint32_t sessionId,
    std::string &deviceName)
{
    deviceName = "";
    if (processConfig.audioMode == AUDIO_MODE_RECORD) {
        if (processConfig.isWakeupCapturer) {
            int32_t ret = CoreServiceHandler::GetInstance().SetWakeUpAudioCapturerFromAudioServer(processConfig);
            if (ret < 0) {
                AUDIO_ERR_LOG("ErrorCode: %{public}d", ret);
                return ERROR;
            }
            deviceName = PRIMARY_WAKEUP;
        }
        if (processConfig.isInnerCapturer) {
            deviceName = std::string(INNER_CAPTURER_SINK) + std::to_string(processConfig.innerCapId);
        } else if (processConfig.capturerInfo.sourceType == SOURCE_TYPE_REMOTE_CAST) {
            deviceName = std::string(REMOTE_CAST_INNER_CAPTURER_SINK_NAME);
        }
        return PolicyHandler::GetInstance().NotifyCapturerAdded(processConfig.capturerInfo,
            processConfig.streamInfo, sessionId);
    } else if (managerType_ == DUP_PLAYBACK) {
        deviceName = std::string(INNER_CAPTURER_SINK) + std::to_string(processConfig.innerCapId);
    } else if (managerType_ == DUAL_PLAYBACK) {
        deviceName = PRO_DUAL_PLAYBACK_SINK;
    }
    return SUCCESS;
}

int32_t HpaeAdapterManager::CreateCapturer(AudioProcessConfig processConfig, std::shared_ptr<ICapturerStream> &stream)
{
    AUDIO_DEBUG_LOG("Create capturer start");
    CHECK_AND_RETURN_RET_LOG(managerType_ == RECORDER, ERROR, "Invalid managerType:%{public}d", managerType_);
    uint32_t sessionId = processConfig.originalSessionId;
    if (processConfig.originalSessionId < MIN_STREAMID || processConfig.originalSessionId > MAX_STREAMID) {
        sessionId = CoreServiceHandler::GetInstance().GenerateSessionId();
        AUDIO_ERR_LOG("Create capturer originalSessionId is error %{public}d, get new sessionId:%{public}u",
            processConfig.originalSessionId, sessionId);
    }
    processConfig.originalSessionId = sessionId;

    std::string deviceName = "";
    int32_t ret = GetDeviceNameForConnect(processConfig, processConfig.originalSessionId, deviceName);
    CHECK_AND_CALL_FUNC_RETURN_RET(ret == SUCCESS, ERROR_INVALID_PARAM,
        HILOG_COMM_ERROR("[CreateRender]get devicename err: %{public}d", ret));
    SourceType &sourceType = processConfig.capturerInfo.sourceType;
    if (sourceType != SOURCE_TYPE_PLAYBACK_CAPTURE &&
        sourceType != SOURCE_TYPE_REMOTE_CAST &&
        sourceType != SOURCE_TYPE_WAKEUP) {
        deviceName = CoreServiceHandler::GetInstance().GetModuleNameBySessionId(sessionId);
    }
    if (deviceName == "") {
        AUDIO_INFO_LOG("source name is null");
        deviceName = "Built_in_mic";
    }
    // HpaeAdapterManager is solely responsible for creating paStream objects
    std::shared_ptr<ICapturerStream> capturerStream = CreateCapturerStream(processConfig, deviceName);
    CHECK_AND_CALL_FUNC_RETURN_RET(capturerStream != nullptr, ERR_DEVICE_INIT,
        HILOG_COMM_ERROR("[CreateCapturer]Failed to init pa stream"));
    capturerStream->SetStreamIndex(sessionId);
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    capturerStreamMap_[sessionId] = capturerStream;
    stream = capturerStream;
    return SUCCESS;
}

int32_t HpaeAdapterManager::AddUnprocessStream(int32_t appUid)
{
    std::lock_guard<std::mutex> lock(paElementsMutex_);
    AUDIO_INFO_LOG("unprocessAppUidSet_ add appUid:%{public}d", appUid);
    unprocessAppUidSet_.insert(appUid);
    return SUCCESS;
}

int32_t HpaeAdapterManager::ReleaseCapturer(uint32_t streamIndex)
{
    AUDIO_DEBUG_LOG("Enter ReleaseCapturer");
    std::lock_guard<std::mutex> lock(streamMapMutex_);
    auto currentCapture = SafeGetMap(capturerStreamMap_, static_cast<int32_t>(streamIndex));
    CHECK_AND_RETURN_RET_LOG(currentCapture != nullptr, SUCCESS, "No matching stream");

    CHECK_AND_RETURN_RET_LOG(currentCapture->Release() == SUCCESS, ERR_OPERATION_FAILED,
        "Release stream %{public}d failed", streamIndex);

    capturerStreamMap_[streamIndex] = nullptr;
    capturerStreamMap_.erase(streamIndex);
    if (capturerStreamMap_.size() == 0) {
        AUDIO_INFO_LOG("Release the last stream");
    }
    return SUCCESS;
}

std::shared_ptr<IRendererStream> HpaeAdapterManager::CreateRendererStream(AudioProcessConfig processConfig,
    const std::string &deviceName)
{
    std::lock_guard<std::mutex> lock(paElementsMutex_);
    bool isCallbackMode = true;
    bool isMoveAble = true;
    size_t preBufSizeInBytes = 0;
    if (managerType_ == DUP_PLAYBACK) {
        // todo check
        processConfig.isInnerCapturer = true;
        isMoveAble = false;
        AUDIO_INFO_LOG("Create dup playback renderer stream");
    } else if (managerType_ == DUAL_PLAYBACK) {
        isCallbackMode = false;
        isMoveAble = false;
        uint32_t sampleRate = processConfig.streamInfo.customSampleRate == 0 ?
            processConfig.streamInfo.samplingRate : processConfig.streamInfo.customSampleRate;
        size_t byteSizePerFrame = processConfig.streamInfo.channels *
            static_cast<size_t>(Util::GetSamplePerFrame(processConfig.streamInfo.format));
        preBufSizeInBytes = DUAL_STREAM_PREBUF_TIME_MS * sampleRate * byteSizePerFrame / AUDIO_MS_PER_S;
    }
    std::shared_ptr<HpaeRendererStreamImpl> rendererStream =
        std::make_shared<HpaeRendererStreamImpl>(processConfig, isMoveAble, deviceName, isCallbackMode,
        preBufSizeInBytes);
    if (rendererStream->InitParams(deviceName) != SUCCESS) {
        HILOG_COMM_ERROR("[CreateRendererStream]Create rendererStream Failed");
        return nullptr;
    }
    return rendererStream;
}

std::shared_ptr<ICapturerStream> HpaeAdapterManager::CreateCapturerStream(AudioProcessConfig processConfig,
    const std::string &deviceName)
{
    std::lock_guard<std::mutex> lock(paElementsMutex_);
    if (unprocessAppUidSet_.find(processConfig.appInfo.appUid) != unprocessAppUidSet_.end()) {
        processConfig.capturerInfo.sourceType = SOURCE_TYPE_UNPROCESSED;
        AUDIO_INFO_LOG("app uid:%{public}d sourcetype set to unprocessed", processConfig.appInfo.appUid);
    }
    std::shared_ptr<HpaeCapturerStreamImpl> capturerStream =
        std::make_shared<HpaeCapturerStreamImpl>(processConfig);
    if (capturerStream->InitParams(deviceName) != SUCCESS) {
        AUDIO_ERR_LOG("Create capturerStream Failed, error");
        return nullptr;
    }
    return capturerStream;
}

uint64_t HpaeAdapterManager::GetLatency() noexcept
{
    return 0;
}

void HpaeAdapterManager::GetAllSinkInputs(std::vector<SinkInput> &sinkInputs)
{
    std::lock_guard<std::mutex> lock(sinkInputsMutex_);
    sinkInputs = sinkInputs_;
    return;
}

int32_t HpaeAdapterManager::GetSessionIdAndRemove(uint32_t paIndex, uint32_t &sessionId)
{
    AUDIO_INFO_LOG("get sessionId: %{public}d for paIndex: %{public}d", sessionId, paIndex);
    return SUCCESS;
}

void HpaeAdapterManager::SetHighResolution(AudioProcessConfig &processConfig, uint32_t sessionId)
{
    if (processConfig.audioMode != AUDIO_MODE_PLAYBACK || managerType_ == DIRECT_PLAYBACK) {
        return;
    }
    bool spatializationEnabled = processConfig.rendererInfo.spatializationEnabled;
    AUDIO_DEBUG_LOG("spatializationEnabled : %{public}d, isHighResolutionExist_ : %{public}d",
        spatializationEnabled, isHighResolutionExist_);

    if (spatializationEnabled == false && isHighResolutionExist_ == false && CheckHighResolution(processConfig)) {
        AUDIO_INFO_LOG("current stream marked as high resolution");
        isHighResolutionExist_ = true;
        highResolutionIndex_ = sessionId;
    } else {
        AUDIO_INFO_LOG("current stream marked as non-high resolution");
    }
}

bool HpaeAdapterManager::CheckHighResolution(const AudioProcessConfig &processConfig) const
{
    DeviceType deviceType = processConfig.deviceType;
    AudioStreamType streamType = processConfig.streamType;
    AudioSamplingRate sampleRate = processConfig.streamInfo.samplingRate;
    AudioSampleFormat sampleFormat = processConfig.streamInfo.format;

    AUDIO_DEBUG_LOG("deviceType:%{public}d, streamType:%{public}d, sampleRate:%{public}d, sampleFormat:%{public}d",
        deviceType, streamType, sampleRate, sampleFormat);

    if (deviceType == DEVICE_TYPE_BLUETOOTH_A2DP && streamType == STREAM_MUSIC &&
        sampleRate >= SAMPLE_RATE_48000 && sampleFormat >= SAMPLE_S24LE) {
        return true;
    }
    return false;
}
} // namespace AudioStandard
} // namespace OHOS
