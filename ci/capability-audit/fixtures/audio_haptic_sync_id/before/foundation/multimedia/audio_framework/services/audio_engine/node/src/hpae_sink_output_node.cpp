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
#define LOG_TAG "HpaeSinkOutputNode"
#endif

#include <hpae_sink_output_node.h>
#include "hpae_remote_device_class.h"
#include "audio_errors.h"
#include <iostream>
#include "hpae_format_convert.h"
#include "audio_utils.h"
#include "hpae_node_common.h"
#include "audio_engine_log.h"
#include "audio_stream_enum.h"
#include "stream_dfx_manager.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
namespace {
constexpr uint32_t SLEEP_TIME_IN_US = 20000;
static constexpr int64_t WAIT_CLOSE_PA_TIME = 4; // 4s
static constexpr int64_t MONITOR_CLOSE_PA_TIME = 5 * 60; // 5m
static constexpr int64_t TIME_IN_US = 1000000;
static const std::string BT_SINK_NAME = "a2dp";
static const std::string USB_SINK_NAME = "usb";
constexpr size_t DEFAULT_COLL_RENDER_FAILED_FRAME = 3;

static inline const std::unordered_set<std::string> AUXILIARY_SPEAKER_LIST = {
    BT_SINK_NAME,
    USB_SINK_NAME
};

static inline const std::unordered_set<StreamUsage> VALID_STREAMUSAGE_AUXILIARY_FILTER = {
    STREAM_USAGE_MUSIC,
    STREAM_USAGE_MOVIE,
    STREAM_USAGE_GAME,
    STREAM_USAGE_AUDIOBOOK
};

static inline const std::unordered_set<StreamUsage> INVALID_STREAMUSAGE_AUXILIARY_FILTER = {
    STREAM_USAGE_VOICE_COMMUNICATION,
    STREAM_USAGE_VIDEO_COMMUNICATION
};
}

HpaeSinkOutputNode::HpaeSinkOutputNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo),
      renderFrameData_(nodeInfo.frameLen * nodeInfo.channels * GetSizeFromFormat(nodeInfo.format)),
      interleveData_(nodeInfo.frameLen * nodeInfo.channels)
{
    renderSize_ = renderFrameData_.size();
    outputSize_ = renderSize_;
    AUDIO_INFO_LOG("name is %{public}s renderSize = %{public}zu", sinkOutAttr_.adapterName.c_str(),
        renderSize_);
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeSinkOutputNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeSinkOutputNode::~HpaeSinkOutputNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

void HpaeSinkOutputNode::HandleRemoteTiming()
{
    CHECK_AND_RETURN(IsRemoteDeviceClass(GetDeviceClass()));
    auto now = std::chrono::high_resolution_clock::now();
    remoteTimePoint_ += std::chrono::milliseconds(20);  // 20ms frameLen, need optimize
    if (remoteTimePoint_ > now) {
        remoteSleepTime_ = std::chrono::duration_cast<std::chrono::milliseconds>(remoteTimePoint_ - now);
    } else {
        remoteSleepTime_ = std::chrono::milliseconds(0);
    }
    std::this_thread::sleep_for(remoteSleepTime_);
    AUDIO_DEBUG_LOG("remoteSleepTime_ %{public}lld", remoteSleepTime_.count());
}

void HpaeSinkOutputNode::DoProcess()
{
    Trace trace("HpaeSinkOutputNode::DoProcess " + GetTraceInfo());
    if (audioRendererSink_ == nullptr) {
        AUDIO_WARNING_LOG("audioRendererSink_ is nullptr sessionId: %{public}u", GetSessionId());
        return;
    }
    if (GetNodeInfo().routeFlag == AUDIO_OUTPUT_FLAG_INTERPHONE) {
        return;
    }

    CHECK_AND_RETURN(ReadDataAndConvertFormat());
    uint64_t writeLen = 0;
    char *renderFrameData = (char *)renderFrameData_.data();

#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer timer;
    timer.Start();
    intervalTimer_.Stop();
#endif
    HandleHapticParam(renderFrameTimes_);
    renderFrameTimes_ += FRAME_LEN_20MS;
    auto ret = audioRendererSink_->RenderFrame(*renderFrameData, renderSize_, writeLen);
    if (ret != SUCCESS || writeLen != renderSize_) {
        AUDIO_ERR_LOG("RenderFrame failed");
        if (!IsRemoteDeviceClass(GetDeviceClass())) {
            periodTimer_.Stop();
            uint64_t usedTimeUs = static_cast<uint64_t>(periodTimer_.Elapsed<std::chrono::microseconds>());
            usleep(SLEEP_TIME_IN_US > usedTimeUs ? SLEEP_TIME_IN_US - usedTimeUs : 0);
        }
        collRenderFrameFailedCount_.fetch_add(1);
    } else {
        collRenderFrameFailedCount_.store(0);
    }

    CheckAndSetCollDelayForRenderFrameFailed();
    RenderFrameForAuxiliarySink();
    periodTimer_.Start();
    HandleRemoteTiming(); // used to control remote RenderFrame tempo.
    std::move(renderFrameData_.begin() + renderSize_, renderFrameData_.begin() + currentSize_,
        renderFrameData_.begin());
    currentSize_ -= renderSize_;
#ifdef ENABLE_HOOK_PCM
    timer.Stop();
    int64_t elapsed = timer.Elapsed();
    AUDIO_DEBUG_LOG("name %{public}s, RenderFrame elapsed time: %{public}" PRId64 " ms",
        sinkOutAttr_.adapterName.c_str(),
        elapsed);
    intervalTimer_.Start();
#endif
    return;
}

void HpaeSinkOutputNode::RenderFrameForAuxiliarySink()
{
    AUDIO_DEBUG_LOG("spkName:%{public}s, auxSinkEnable_:%{public}s auxSinkState:%{public}d ",
        sinkOutAttr_.sinkName.c_str(), auxSinkEnable_ ? "true" : "false", auxSinkState_);
    CHECK_AND_RETURN(auxSinkEnable_ && auxSinkState_ == STREAM_MANAGER_RUNNING &&
        AUXILIARY_SPEAKER_LIST.count(sinkOutAttr_.sinkName) > 0);
    Trace trace("HpaeSinkOutputNode::RenderFrameForAuxiliarySink spkName:" + sinkOutAttr_.sinkName +
       " isEnabled:" + std::to_string(auxSinkEnable_) + " state:" + std::to_string(auxSinkState_));

    CHECK_AND_RETURN_LOG(auxiliarySink_ != nullptr, "auxiliarySink_ is null");
    uint64_t writeLen = 0;
    char *renderFrameData = (char *)renderFrameData_.data();
    auxiliarySink_->RenderFrame(*renderFrameData, renderSize_, writeLen);
}

const char *HpaeSinkOutputNode::GetRenderFrameData(void)
{
    return renderFrameData_.data();
}

void HpaeSinkOutputNode::RegisterCurrentDeviceCallback(const std::function<void(bool)> &callback)
{
    CHECK_AND_RETURN_LOG(audioRendererSink_ != nullptr, "audioRendererSink_ is nullptr");
    CHECK_AND_RETURN_LOG(callback != nullptr, "callback is nullptr");
    audioRendererSink_->RegisterCurrentDeviceCallback(callback);
}

bool HpaeSinkOutputNode::Reset()
{
    const auto preOutputMap = inputStream_.GetPreOutputMap();
    for (const auto &preOutput : preOutputMap) {
        OutputPort<HpaePcmBuffer *> *output = preOutput.first;
        inputStream_.DisConnect(output);
    }
    return true;
}

bool HpaeSinkOutputNode::ResetAll()
{
    const auto preOutputMap = inputStream_.GetPreOutputMap();
    for (const auto &preOutput : preOutputMap) {
        OutputPort<HpaePcmBuffer *> *output = preOutput.first;
        std::shared_ptr<HpaeNode> hpaeNode = preOutput.second;
        if (hpaeNode->ResetAll()) {
            inputStream_.DisConnect(output);
        }
    }
    return true;
}

void HpaeSinkOutputNode::Connect(const std::shared_ptr<OutputNode<HpaePcmBuffer *>> &preNode)
{
    inputStream_.Connect(preNode->GetSharedInstance(), preNode->GetOutputPort());
#ifdef ENABLE_HIDUMP_DFX
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeInfo(true, GetNodeId(), preNode->GetSharedInstance()->GetNodeId());
    }
#endif
}

void HpaeSinkOutputNode::DisConnect(const std::shared_ptr<OutputNode<HpaePcmBuffer *>> &preNode)
{
    inputStream_.DisConnect(preNode->GetOutputPort());
#ifdef ENABLE_HIDUMP_DFX
    if (auto callback = GetNodeStatusCallback().lock()) {
        auto preNodeReal = preNode->GetSharedInstance();
        callback->OnNotifyDfxNodeInfo(false, GetNodeId(), preNodeReal->GetNodeId());
    }
#endif
}

int32_t HpaeSinkOutputNode::GetRenderSinkInstance(const std::string &deviceClass, const std::string &deviceNetId,
    const std::string &macAddress)
{
    // macAddress has highest priority for device selection, then deviceNetId, then default
    const std::string &info = !macAddress.empty() ? macAddress
        : (!deviceNetId.empty() ? deviceNetId : HDI_ID_INFO_DEFAULT);
    renderId_ = HdiAdapterManager::GetInstance().GetRenderIdByDeviceClass(deviceClass, info, true,
        true, GetNodeInfo().routeFlag);

    audioRendererSink_ = HdiAdapterManager::GetInstance().GetRenderSink(renderId_, true);
    if (audioRendererSink_ == nullptr) {
        // Do not print macAddress (sensitive); indicate the actual selection source instead.
        AUDIO_ERR_LOG("get sink fail, deviceClass: %{public}s, selectByMac: %{public}d, netIdLen: %{public}zu, "
            "renderId_: %{public}u", deviceClass.c_str(), !macAddress.empty(), deviceNetId.size(), renderId_);
        HdiAdapterManager::GetInstance().ReleaseId(renderId_);
        return ERROR;
    }
    GetAuxiliarySink(deviceClass);
    return SUCCESS;
}

DeviceType HpaeSinkOutputNode::GetCurrentActiveDevice() const
{
    if (audioRendererSink_ == nullptr) {
        return DEVICE_TYPE_NONE;
    }
    return audioRendererSink_->GetCurrentOutputDevice();
}

int32_t HpaeSinkOutputNode::GetAuxiliarySink(const std::string &sinkName)
{
    AUDIO_INFO_LOG("spkName:%{public}s auxSinkEnable_:%{public}s", sinkName.c_str(),
        auxSinkEnable_ ? "true" : "false");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(AUXILIARY_SPEAKER_LIST.count(sinkName) > 0, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_INVALID_PARAM),
            "invalid sink name", false),
        "spkName:%{public}s invalid", sinkName.c_str());
    auxiliarySink_ = HdiAdapterManager::GetInstance().GetAuxiliarySink();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(auxiliarySink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "get auxiliary sink fail", false),
        "get auxiliary sink fail");
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkInit(IAudioSinkAttr &attr)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioRendererSink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "audioRendererSink_ is nullptr", false),
        "audioRendererSink_ is nullptr sessionId: %{public}u", GetSessionId());

    sinkOutAttr_ = attr;
    auxSinkEnable_ = attr.auxSinkEnable;
    if (audioRendererSink_->IsInited()) {
        AUDIO_WARNING_LOG("audioRenderSink already inited");
        SetSinkState(STREAM_MANAGER_IDLE);
        AuxiliarySinkInit();
        return SUCCESS;
    }
#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer timer;
    timer.Start();
#endif
    int32_t ret = audioRendererSink_->Init(attr);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ret,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_OPERATION_FAILED),
            "audioRendererSink_ init failed", false),
        "audioRendererSink_ init failed, errCode is %{public}d", ret);
    SetSinkState(STREAM_MANAGER_IDLE);
#ifdef ENABLE_HOOK_PCM
    timer.Stop();
    int64_t interval = timer.Elapsed();
    AUDIO_INFO_LOG("name %{public}s, RenderSinkInit Elapsed: %{public}" PRId64 " ms ret: %{public}d",
        sinkOutAttr_.adapterName.c_str(), interval, ret);
    std::string adapterName = sinkOutAttr_.adapterName;
#endif
    AuxiliarySinkInit();
    return ret;
}

int32_t HpaeSinkOutputNode::AuxiliarySinkInit()
{
    AUDIO_INFO_LOG("spkName:%{public}s, isEnabled:%{public}s", sinkOutAttr_.sinkName.c_str(),
        auxSinkEnable_ ? "true" : "false");
    Trace trace("HpaeSinkOutputNode::AuxiliarySinkInit spkName:" + std::string(sinkOutAttr_.sinkName) +
        "isEnabled:" + std::to_string(auxSinkEnable_));
    CHECK_AND_RETURN_RET(AUXILIARY_SPEAKER_LIST.count(sinkOutAttr_.sinkName) > 0 && auxSinkEnable_, ERROR);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(auxiliarySink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "auxiliarySink is null", false),
        "auxiliarySink is null");
    if (auxiliarySink_->IsInited()) {
        AUDIO_WARNING_LOG("auxiliarySink is already inited");
        return SUCCESS;
    }

    auto ret = auxiliarySink_->Init(sinkOutAttr_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_OPERATION_FAILED),
            "auxiliarySink_ init fail", false),
        "auxiliarySink_ init fail");
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkDeInit(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    SetSinkState(STREAM_MANAGER_RELEASED);
#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer timer;
    timer.Start();
#endif
    audioRendererSink_->DeInit();
    audioRendererSink_ = nullptr;
    HdiAdapterManager::GetInstance().ReleaseId(renderId_);
#ifdef ENABLE_HOOK_PCM
    timer.Stop();
    int64_t interval = timer.Elapsed();
    AUDIO_INFO_LOG("name %{public}s, RenderSinkDeInit Elapsed: %{public}" PRId64 " ms",
        sinkOutAttr_.adapterName.c_str(),
        interval);
#endif
    AuxiliarySinkDeInit();
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::AuxiliarySinkDeInit(void)
{
    AUDIO_INFO_LOG("spkName:%{public}s, isEnabled:%{public}s", sinkOutAttr_.sinkName.c_str(),
        auxSinkEnable_ ? "true" : "false");
    Trace trace("HpaeSinkOutputNode::AuxiliarySinkDeInit spkName:" + sinkOutAttr_.sinkName + "isEnabled:" +
        std::to_string(auxSinkEnable_));
    CHECK_AND_RETURN_RET(AUXILIARY_SPEAKER_LIST.count(sinkOutAttr_.sinkName) > 0, ERROR);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(auxiliarySink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::RELEASE, ERR_NULL_POINTER),
            "auxiliarySink is null", false),
        "auxiliarySink is null");
    if (!auxiliarySink_->IsInited()) {
        AUDIO_WARNING_LOG("auxiliarySink is already DeInited");
        auxiliarySink_ = nullptr;
        return SUCCESS;
    }

    auxiliarySink_->DeInit();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(!auxiliarySink_->IsInited(), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::RELEASE, ERR_OPERATION_FAILED),
            "auxiliarySink_ deinit fail", false),
        "auxiliarySink_ deinit fail");
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkFlush(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    return audioRendererSink_->Flush();
}

int32_t HpaeSinkOutputNode::RenderSinkPause(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    audioRendererSink_->Pause();
    SetSinkState(STREAM_MANAGER_SUSPENDED);
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkReset(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    return audioRendererSink_->Reset();
}

int32_t HpaeSinkOutputNode::RenderSinkResume(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    int32_t ret = audioRendererSink_->Resume();
    CHECK_AND_RETURN_RET(ret == SUCCESS, ret);
    SetSinkState(STREAM_MANAGER_RUNNING);
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkStart(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    CHECK_AND_RETURN_RET_LOG(audioRendererSink_->IsInited(), ERROR, "audioRendererSink_ not init");
    renderFrameTimes_ = 0;
    int32_t ret;
#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer timer;
    timer.Start();
#endif
    ret = audioRendererSink_->Start();
    CHECK_AND_RETURN_RET(ret == SUCCESS, ret);
#ifdef ENABLE_HOOK_PCM
    timer.Stop();
    int64_t interval = timer.Elapsed();
    AUDIO_INFO_LOG("name %{public}s, RenderSinkStart Elapsed: %{public}" PRId64 " ms",
        sinkOutAttr_.adapterName.c_str(),
        interval);
#endif
    SetSinkState(STREAM_MANAGER_RUNNING);
    if (IsRemoteDeviceClass(GetDeviceClass())) {
        remoteTimePoint_ = std::chrono::high_resolution_clock::now();
    }
    if (GetDeviceClass() == "primary") {
        ret = audioRendererSink_->SetPaPower(true);
        isOpenPaPower_ = true;
        isDisplayPaPowerState_ = false;
        silenceDataUs_ = 0;
        AUDIO_INFO_LOG("Speaker sink started, open pa:[%{public}s] -- [%{public}s], ret:%{public}d",
            GetDeviceClass().c_str(), (ret == 0 ? "success" : "failed"), ret);
    }
    periodTimer_.Start();
    return SUCCESS;
}

int32_t HpaeSinkOutputNode::RenderSinkStop(void)
{
    CHECK_AND_RETURN_RET(audioRendererSink_ != nullptr, ERROR);
    SetSinkState(STREAM_MANAGER_SUSPENDED);
    int32_t ret;
#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer timer;
    timer.Start();
#endif
    ret = audioRendererSink_->Stop();
    CHECK_AND_RETURN_RET(ret == SUCCESS, ret);
#ifdef ENABLE_HOOK_PCM
    timer.Stop();
    int64_t interval = timer.Elapsed();
    AUDIO_INFO_LOG("name %{public}s, RenderSinkStop Elapsed: %{public}" PRId64 " ms",
        sinkOutAttr_.adapterName.c_str(), interval);
#endif

    return SUCCESS;
}

StreamManagerState HpaeSinkOutputNode::GetSinkState(void)
{
    return state_;
}

int32_t HpaeSinkOutputNode::SetSinkState(StreamManagerState sinkState)
{
    HILOG_COMM_INFO("[SetSinkState]Sink[%{public}s] state change:[%{public}s]-->[%{public}s]",
        GetDeviceClass().c_str(), ConvertStreamManagerState2Str(state_).c_str(),
        ConvertStreamManagerState2Str(sinkState).c_str());
    state_ = sinkState;
    return SUCCESS;
}

size_t HpaeSinkOutputNode::GetPreOutNum()
{
    return inputStream_.GetPreOutputNum();
}

int32_t HpaeSinkOutputNode::UpdateAppsUid(const std::vector<int32_t> &appsUid)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioRendererSink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_NULL_POINTER),
            "audioRendererSink_ is nullptr", false),
        "audioRendererSink_ is nullptr sessionId: %{public}u", GetSessionId());
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioRendererSink_->IsInited(), ERR_ILLEGAL_STATE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::START, ERR_ILLEGAL_STATE),
            "audioRendererSink_ not init", false),
        "audioRendererSink_ not init");
    streamRunningNum_ = appsUid.size();
    return audioRendererSink_->UpdateAppsUid(appsUid);
}

void HpaeSinkOutputNode::NotifyStreamChangeToSink(StreamChangeType change,
    uint32_t sessionId, StreamUsage usage, RendererState state, uint32_t appUid)
{
    CHECK_AND_RETURN_LOG(audioRendererSink_ != nullptr, "audioRendererSink_ is nullptr");
    CHECK_AND_RETURN_LOG(audioRendererSink_->IsInited(), "audioRendererSink_ not init");
    audioRendererSink_->NotifyStreamChangeToSink(change, sessionId, usage, state, appUid);
    UpdateAuxiliarySinkState(change, sessionId, usage, state);
}

void HpaeSinkOutputNode::UpdateAuxiliarySinkState(StreamChangeType change,
    uint32_t sessionId, StreamUsage usage, RendererState state)
{
    CHECK_AND_RETURN(AUXILIARY_SPEAKER_LIST.count(sinkOutAttr_.sinkName) > 0);
    CHECK_AND_RETURN_LOG(VALID_STREAMUSAGE_AUXILIARY_FILTER.count(usage) > 0 ||
        INVALID_STREAMUSAGE_AUXILIARY_FILTER.count(usage) > 0,
        "sessionId:%{public}u usage:%{public}d", sessionId, usage);

    if (VALID_STREAMUSAGE_AUXILIARY_FILTER.count(usage) > 0) {
        if ((change == STREAM_CHANGE_TYPE_ADD || change == STREAM_CHANGE_TYPE_STATE_CHANGE) &&
            state == RENDERER_RUNNING) {
            AUDIO_INFO_LOG("add valid sessionId:%{public}d", sessionId);
            sessionsWithAuxSinkValidFilter_[sessionId] = usage;
        } else {
            CHECK_AND_RETURN_LOG(sessionsWithAuxSinkValidFilter_.find(sessionId) !=
                sessionsWithAuxSinkValidFilter_.end(), "sessionId:%{public}u is not in filter_, "
                "change:%{public}d state:%{public}d usage:%{public}d", sessionId, change, state, usage);
            AUDIO_INFO_LOG("remove valid sessionId:%{public}d", sessionId);
            sessionsWithAuxSinkValidFilter_.erase(sessionId);
        }
    }

    if (INVALID_STREAMUSAGE_AUXILIARY_FILTER.count(usage) > 0) {
        if ((change == STREAM_CHANGE_TYPE_ADD || change == STREAM_CHANGE_TYPE_STATE_CHANGE) &&
            state == RENDERER_RUNNING) {
            AUDIO_INFO_LOG("add invalid sessionId:%{public}d", sessionId);
            sessionsWithAuxSinkInvalidFilter_[sessionId] = usage;
        } else {
            CHECK_AND_RETURN_LOG(sessionsWithAuxSinkInvalidFilter_.find(sessionId) !=
                sessionsWithAuxSinkInvalidFilter_.end(), "sessionId:%{public}u is not in filter_, "
                "change:%{public}d state:%{public}d usage:%{public}d", sessionId, change, state, usage);
            AUDIO_INFO_LOG("remove invalid sessionId:%{public}d", sessionId);
            sessionsWithAuxSinkInvalidFilter_.erase(sessionId);
        }
    }
    bool isRunning = sessionsWithAuxSinkInvalidFilter_.empty() && !sessionsWithAuxSinkValidFilter_.empty();
    auto auxState = isRunning ? STREAM_MANAGER_RUNNING : STREAM_MANAGER_IDLE;
    AUDIO_INFO_LOG("auxSinkState_ change:[%{public}s]-->[%{public}s] with sessionId:%{public}u change:%{public}d"
        " state:%{public}d usage:%{public}d", ConvertStreamManagerState2Str(auxSinkState_).c_str(),
        ConvertStreamManagerState2Str(auxState).c_str(), sessionId, change, state, usage);
    auxSinkState_ = auxState;
}

void HpaeSinkOutputNode::HandlePaPower(HpaePcmBuffer *pcmBuffer)
{
    if (GetDeviceClass() != "primary") {
        return;
    }
    CHECK_AND_RETURN(collaborationState_ == COLLABORATION_CLOSE);
    if (pcmBuffer->IsSilence() && streamRunningNum_ > 0) {
        if (!isDisplayPaPowerState_) {
            AUDIO_INFO_LOG("Timing begins, will close speaker after [%{public}" PRId64 "]s", WAIT_CLOSE_PA_TIME);
            isDisplayPaPowerState_ = true;
        }
        silenceDataUs_ += static_cast<int64_t>(pcmBuffer->GetFrameLen()) * TIME_IN_US /
            static_cast<int64_t>(pcmBuffer->GetSampleRate());
        if (isOpenPaPower_ && silenceDataUs_ >= WAIT_CLOSE_PA_TIME * TIME_IN_US &&
            (audioRendererSink_->GetAudioScene() == 0 || audioRendererSink_->GetAudioScene() == -1)) {
            int32_t ret = audioRendererSink_->SetPaPower(false);
            isOpenPaPower_ = false;
            silenceDataUs_ = 0;
            AUDIO_INFO_LOG("Speaker pa volume change to zero over [%{public}" PRId64
                "]s, close %{public}s pa [%{public}s], ret:%{public}d",
                WAIT_CLOSE_PA_TIME, GetDeviceClass().c_str(), (ret == 0 ? "success" : "failed"), ret);
        } else if (!isOpenPaPower_ && silenceDataUs_ >= MONITOR_CLOSE_PA_TIME * TIME_IN_US) {
            silenceDataUs_ = 0;
            AUDIO_INFO_LOG("Speaker pa have closed [%{public}" PRId64 "]s.", MONITOR_CLOSE_PA_TIME);
        }
    } else {
        if (isDisplayPaPowerState_) {
            isDisplayPaPowerState_ = false;
            AUDIO_INFO_LOG("Volume change to non zero, break the speaker closing.");
        }
        silenceDataUs_ = 0;
        if (!isOpenPaPower_) {
            int32_t ret = audioRendererSink_->SetPaPower(true);
            isOpenPaPower_ = true;
            AUDIO_INFO_LOG("Volume change to non zero or no stream running, \
                open closed pa:[%{public}s] -- [%{public}s], ret:%{public}d",
                GetDeviceClass().c_str(), (ret == 0 ? "success" : "failed"), ret);
        }
    }
}

int32_t HpaeSinkOutputNode::RenderSinkSetPriPaPower()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioRendererSink_ != nullptr, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_NULL_POINTER),
            "audioRendererSink_ is nullptr", false),
        "audioRendererSink_ is nullptr sessionId: %{public}u", GetSessionId());
    int32_t ret = audioRendererSink_->SetPriPaPower();
    AUDIO_INFO_LOG("Open pri pa:[%{public}s] -- [%{public}s], ret:%{public}d",
        GetDeviceClass().c_str(), (ret == 0 ? "success" : "failed"), ret);
    return ret;
}

uint32_t HpaeSinkOutputNode::GetLatency()
{
    if (audioRendererSink_ == nullptr) {
        return ERROR;
    }
    audioRendererSink_->GetLatency(latency_);
    return latency_;
}

int32_t HpaeSinkOutputNode::RenderSinkSetSyncId(int32_t syncId)
{
    isSyncIdSet_ = true;
    syncId_ = syncId;
    return SUCCESS;
}

void HpaeSinkOutputNode::HandleHapticParam(uint64_t syncTime)
{
    if (isSyncIdSet_) {
        isSyncIdSet_ = false;
        AudioParamKey key = NONE;
        std::string condition = "haptic";
        std::string param = "haptic_sessionid=" + std::to_string(syncId_) +
            ";haptic_offset=" + std::to_string(syncTime);
        audioRendererSink_->SetAudioParameter(key, condition, param);
    }
}

bool HpaeSinkOutputNode::ReadDataAndConvertFormat()
{
    while (currentSize_ < renderSize_) {
        std::vector<HpaePcmBuffer *> &outputVec = inputStream_.ReadPreOutputData();
        CHECK_AND_RETURN_RET(!outputVec.empty(), false);
        HpaePcmBuffer *outputData = outputVec.front();
        if (outputData == nullptr) {
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                    BusinessScenario::SEND_DATA, ERR_NULL_POINTER),
                "outputData is nullptr", false);
            return false;
        }
        HandlePaPower(outputData);
        uint32_t frameLen = outputData->GetFrameLen();
        uint32_t channels = outputData->GetChannelCount();
        uint32_t inDurationMs = frameLen * AUDIO_MS_PER_S / outputData->GetSampleRate();
        uint32_t outDurationMs = GetFrameLen() * AUDIO_MS_PER_S / GetSampleRate();
        if (renderFrameData_.size() == renderSize_ && inDurationMs != outDurationMs) {
            outputSize_ = frameLen * channels * static_cast<size_t>(GetSizeFromFormat(GetBitWidth()));
            AUDIO_INFO_LOG("Update outputSize to %{public}zu", outputSize_);
            renderFrameData_.resize(outputSize_ + renderSize_);
        }
        ConvertFromFloat(
            GetBitWidth(), channels * frameLen, outputData->GetPcmDataBuffer(), renderFrameData_.data() + currentSize_);
        currentSize_ += outputSize_;
    }
    return true;
}

int32_t HpaeSinkOutputNode::SetAuxiliarySinkEnable(bool isEnabled)
{
    AUDIO_INFO_LOG("set to isEnabled:%{public}s for spkName:%{public}s",
        isEnabled ? "true" : "false", sinkOutAttr_.sinkName.c_str());
    auxSinkEnable_ = isEnabled;
    if (auxSinkEnable_) {
        if (auxiliarySink_ == nullptr) {
            AUDIO_ERR_LOG("auxiliarySink_ is null, need get auxiliarySink");
            GetAuxiliarySink(sinkOutAttr_.sinkName);
        }
        AuxiliarySinkInit();
    } else {
        AuxiliarySinkDeInit();
    }

    return SUCCESS;
}

void HpaeSinkOutputNode::CheckAndSetCollDelayForRenderFrameFailed()
{
    if (collRenderFrameFailedCount_.load() == DEFAULT_COLL_RENDER_FAILED_FRAME) {
        collRenderFrameFailedCount_.store(0);
        auto statusCallback = GetNodeStatusCallback().lock();
        CHECK_AND_RETURN_LOG(statusCallback != nullptr, "statusCallback is nullptr");
        statusCallback->SetCollDelayCount();
    }
}

void HpaeSinkOutputNode::SetCollaborationState(CollaborationState isCollaborationEnabled)
{
    collaborationState_ = isCollaborationEnabled;
    AUDIO_INFO_LOG("isCollaborationEnabled: %{public}d", isCollaborationEnabled);
}

uint32_t HpaeSinkOutputNode::GetRenderId() const
{
    return renderId_;
}
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
