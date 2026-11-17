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
#define LOG_TAG "HpaeRenderEffectNode"
#endif

#include <cinttypes>
#include "audio_errors.h"
#include "hpae_render_effect_node.h"
#include "hpae_node_common.h"
#include "hpae_pcm_buffer.h"
#include "audio_effect_chain_manager.h"
#include "audio_effect_map.h"
#include "audio_utils.h"
#include "audio_effect_log.h"
#include "stream_dfx_manager.h"
#include "audio_collaboration_manager.h"
#include "manager/hdi_adapter_manager.h"

static constexpr uint32_t DEFUALT_EFFECT_RATE = 48000;
static constexpr uint32_t DEFAULT_EFFECT_FRAMELEN = 960;
static constexpr int32_t COLLABORATIVE_OUTPUT_CHANNELS = 4;
static constexpr int32_t DIRECT_CHANNELS = 2;
static constexpr int32_t COLLABORATIVE_CHANNELS = 2;
static constexpr int32_t COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX = 2;
static constexpr int32_t COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX = 3;
static constexpr int64_t WAIT_CLOSE_EFFECT_TIME = 4; // 4s
static constexpr int64_t MONITOR_CLOSE_EFFECT_TIME = 5 * 60; // 5m
static constexpr int64_t TIME_IN_US = 1000000;
static constexpr float SMALL_SIGNAL_NUM = 1e-6;
static constexpr int32_t EFFECT_TEMP_BUFFER_MAX_CACHE_SIZE = 800;
static constexpr int32_t EFFECT_TEMP_BUFFER_MS_PER_SECOND = 1000;
static constexpr int32_t EFFECT_TEMP_BUFFER_DEFAULT_WAIT_COUNT = 10;
static constexpr int32_t EFFECT_TEMP_BUFFER_DEFAULT_CO_LATENCY = 260;
static constexpr int32_t UPDATE_NEARLINK_COLLAB_STATE_TO_HDI_WAIT_COUNT = 2; // 2 frames
namespace OHOS {
namespace AudioStandard {
namespace HPAE {
HpaeRenderEffectNode::HpaeRenderEffectNode(HpaeNodeInfo &nodeInfo, CollaborationState isCollaborationEnabled)
    : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
    // DEFAUT effect out format
    pcmBufferInfo_(nodeInfo.channels, DEFAULT_EFFECT_FRAMELEN, DEFUALT_EFFECT_RATE, nodeInfo.channelLayout),
    effectOutput_(pcmBufferInfo_)
{
    isCollaborationEnabled_ = isCollaborationEnabled;
    if (nodeInfo.sceneType == HPAE_SCENE_DEFAULT) {
        sceneType_ = "SCENE_DEFAULT";
    } else {
        const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
        if (audioSupportedSceneTypes.find(nodeInfo.effectInfo.effectScene) !=
            audioSupportedSceneTypes.end()) {
            sceneType_ = audioSupportedSceneTypes.at(nodeInfo.effectInfo.effectScene);
        }
        if (sceneType_ == "SCENE_COLLABORATIVE") {
            PcmBufferInfo pcmBufferInfo(STEREO, DEFAULT_EFFECT_FRAMELEN, DEFUALT_EFFECT_RATE, CH_LAYOUT_STEREO);
            if (isCollaborationEnabled_ == COLLABORATION_NEARLINK_OPEN) {
                tempEffectBuffer_ = std::make_shared<HpaeTempEffectBuffer>(pcmBufferInfo, isCollaborationEnabled);
            } else {
                directOutput_ = std::make_unique<HpaePcmBuffer>(pcmBufferInfo); // bt speaker
                collaborativeOutput_ = std::make_unique<HpaePcmBuffer>(pcmBufferInfo); // default speaker
            }
        }
    }
    if (Util::IsEnhancedRoutingSupported()) {
        deviceType_ = static_cast<DeviceType>(nodeInfo.deviceType);
        renderId_ = nodeInfo.renderId;
    }
    AUDIO_INFO_LOG("created, scene type: %{public}s, CollaborationEnabled: %{public}d",
        sceneType_.c_str(), isCollaborationEnabled_);
#ifdef ENABLE_HOOK_PCM
    if (sceneType_ == "SCENE_COLLABORATIVE" && isCollaborationEnabled_ == COLLABORATION_BLUETOOTH_OPEN) {
        directPcmDumper_ = std::make_unique<HpaePcmDumper>(
            "HpaeRenderEffectNodeDirect_id_" + std::to_string(GetNodeId()) + "_scene_" + sceneType_ + ".pcm");
        collaborativePcmDumper_ = std::make_unique<HpaePcmDumper>(
            "HpaeRenderEffectNodeCollaborative_id_" + std::to_string(GetNodeId()) + "_scene_" + sceneType_ + ".pcm");
    }
#endif
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeRenderEffectNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeRenderEffectNode::~HpaeRenderEffectNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

void HpaeRenderEffectNode::DoProcess()
{
    if (sceneType_ != "SCENE_COLLABORATIVE") {
        HpaePluginNode::DoProcess();
        return;
    }

    std::vector<HpaePcmBuffer *>& preOutputs = inputStream_.ReadPreOutputData();

    if (isCollaborationEnabled_ == COLLABORATION_NEARLINK_OPEN) {
        if (enableProcess_ && !preOutputs.empty() && tempEffectBuffer_) {
            SignalProcess(preOutputs);
            CHECK_AND_RETURN_LOG(effectOutput_.GetChannelCount() == static_cast<uint32_t>(CHANNEL_4),
                "collaborative channel count is invalid, count: %{public}d", CHANNEL_4);
            tempEffectBuffer_->ChangeEffectDataForLatency(&effectOutput_);
            outputStream_.WriteDataToOutput(&effectOutput_);
        }
        return;
    }
    if (enableProcess_ && !preOutputs.empty() && directOutput_ && collaborativeOutput_) {
        SignalProcess(preOutputs);
        int32_t ret = SplitCollaborativeData();
        if (ret != SUCCESS) {
            outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
            outputStream_.WriteDataToOutput(&silenceData_, HPAE_BUFFER_TYPE_COBUFFER);
        } else {
            outputStream_.WriteDataToOutput(directOutput_.get());
            outputStream_.WriteDataToOutput(collaborativeOutput_.get(), HPAE_BUFFER_TYPE_COBUFFER);
        }
    } else if (!preOutputs.empty()) {
        outputStream_.WriteDataToOutput(preOutputs[0]);
        outputStream_.WriteDataToOutput(preOutputs[0], HPAE_BUFFER_TYPE_COBUFFER);
    } else {
        outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
        outputStream_.WriteDataToOutput(&silenceData_, HPAE_BUFFER_TYPE_COBUFFER);
    }
#ifdef ENABLE_HOOK_PCM
    if (directPcmDumper_ && directOutput_) {
        directPcmDumper_->Dump((int8_t *)directOutput_->GetPcmDataBuffer(),
            directOutput_->GetFrameLen() * sizeof(float) * directOutput_->GetChannelCount());
    }
    if (collaborativePcmDumper_ && collaborativeOutput_) {
        collaborativePcmDumper_->Dump((int8_t *)collaborativeOutput_->GetPcmDataBuffer(),
            collaborativeOutput_->GetFrameLen() * sizeof(float) * collaborativeOutput_->GetChannelCount());
    }
#endif
}

HpaePcmBuffer *HpaeRenderEffectNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    if (inputs.empty()) {
        AUDIO_WARNING_LOG("inputs size is empty");
        return nullptr;
    }
    auto rate = "rate[" + std::to_string(inputs[0]->GetSampleRate()) + "]_";
    auto ch = "ch[" + std::to_string(inputs[0]->GetChannelCount()) + "]_";
    auto len = "len[" + std::to_string(inputs[0]->GetFrameLen()) + "]";
    auto render = "render[" + std::to_string(renderId_) + "]";
    Trace trace("[" + sceneType_ + "]HpaeRenderEffectNode::SignalProcess " + rate + ch + len + render);

    if (AudioEffectChainManager::GetInstance()->GetOffloadEnabled()) {
        return inputs[0];
    }
    if (IsByPassEffectZeroVolume(inputs[0])) {
        return inputs[0];
    }

    ReconfigOutputBuffer();
    effectOutput_.Origins579().Unknown();

    auto eBufferAttr = std::make_unique<EffectBufferAttr>(
        inputs[0]->GetPcmDataBuffer(),
        effectOutput_.GetPcmDataBuffer(),
        static_cast<int32_t>(inputs[0]->GetChannelCount()),
        static_cast<int32_t>(inputs[0]->GetFrameLen()),
        0,
        0
    );

    int32_t ret;
    if (Util::IsEnhancedRoutingSupported()) {
        ret = AudioEffectChainManager::GetInstance()->ApplyAudioEffectChain(sceneType_, deviceType_, renderId_,
            eBufferAttr);
    } else {
        ret = AudioEffectChainManager::GetInstance()->ApplyAudioEffectChain(sceneType_, eBufferAttr);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, inputs[0],
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_OPERATION_FAILED),
            "apply audio effect chain fail", false),
        "apply audio effect chain fail, ret: %{public}d", ret);

    if (eBufferAttr->identityCopy579 && effectOutput_.GetFrameLen() == inputs[0]->GetFrameLen() &&
        effectOutput_.GetSampleRate() == inputs[0]->GetSampleRate()) {
        effectOutput_.Origins579() = inputs[0]->Origins579();
    }
    effectOutput_.SetBufferState(inputs[0]->GetBufferState());
    effectOutput_.SetBufferValid(true);
    return &effectOutput_;
}

int32_t HpaeRenderEffectNode::SplitCollaborativeData()
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(effectOutput_.GetChannelCount() == static_cast<uint32_t>(CHANNEL_4), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_INVALID_PARAM),
            "collaborative channel count is invalid", false),
        "collaborative channel count is invalid, count: %{public}d", CHANNEL_4);
    // need to check whether the sample rate or frame length changes
    // currently, sample rate and frame length will not change
    float *tempOutput = effectOutput_.GetPcmDataBuffer();
    float *directOutput = directOutput_->GetPcmDataBuffer();
    float *collaborativeOutput = collaborativeOutput_->GetPcmDataBuffer();
    for (uint32_t i = 0; i < effectOutput_.GetFrameLen(); ++i) {
        directOutput[DIRECT_CHANNELS * i] = tempOutput[COLLABORATIVE_OUTPUT_CHANNELS * i] + SMALL_SIGNAL_NUM;
        directOutput[DIRECT_CHANNELS * i + 1] = tempOutput[COLLABORATIVE_OUTPUT_CHANNELS * i + 1] + SMALL_SIGNAL_NUM;
        collaborativeOutput[COLLABORATIVE_CHANNELS * i] =
            tempOutput[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] + SMALL_SIGNAL_NUM;
        collaborativeOutput[COLLABORATIVE_CHANNELS * i + 1] =
            tempOutput[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] + SMALL_SIGNAL_NUM;
    }
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioRendererCreate(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("in");
    int32_t ret = CreateAudioEffectChain(nodeInfo);
    if (ret != 0) {
        AUDIO_WARNING_LOG("failed, ret: %{public}d", ret);
    }
    AUDIO_INFO_LOG("out");
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioRendererStart(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("in");
    ModifyAudioEffectChainInfo(nodeInfo, ADD_AUDIO_EFFECT_CHAIN_INFO);
    if (isCollaborationEnabled_ == COLLABORATION_NEARLINK_OPEN && tempEffectBuffer_ != nullptr) {
        tempEffectBuffer_->SetStopRunningState(false);
        tempEffectBuffer_->SetCollabDoFade(false);
    }
    AUDIO_INFO_LOG("out");
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioRendererStop(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("in");
    ModifyAudioEffectChainInfo(nodeInfo, REMOVE_AUDIO_EFFECT_CHAIN_INFO);
    AUDIO_INFO_LOG("out");
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioRendererRelease(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("in");
    int32_t ret = ReleaseAudioEffectChain(nodeInfo);
    if (ret != 0) {
        AUDIO_WARNING_LOG("failed, ret: %{public}d", ret);
    }
    ModifyAudioEffectChainInfo(nodeInfo, REMOVE_AUDIO_EFFECT_CHAIN_INFO);
    AUDIO_INFO_LOG("out");
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioOffloadRendererCreate(HpaeNodeInfo &nodeInfo, const HpaeSinkInfo &sinkInfo)
{
    CHECK_AND_RETURN_RET_LOG(OffloadRendererCheckNotifyEffect(sinkInfo) == true,
        ERR_INVALID_HANDLE, "no need to create");

    int32_t ret = CreateAudioEffectChain(nodeInfo);
    AUDIO_WARNING_LOG("out, ret: %{public}d", ret);
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioOffloadRendererStart(HpaeNodeInfo &nodeInfo, const HpaeSinkInfo &sinkInfo)
{
    CHECK_AND_RETURN_RET_LOG(OffloadRendererCheckNotifyEffect(sinkInfo) == true,
        ERR_INVALID_HANDLE, "no need to start");

    ModifyAudioEffectChainInfo(nodeInfo, ADD_AUDIO_EFFECT_CHAIN_INFO);
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioOffloadRendererStop(HpaeNodeInfo &nodeInfo, const HpaeSinkInfo &sinkInfo)
{
    CHECK_AND_RETURN_RET_LOG(OffloadRendererCheckNotifyEffect(sinkInfo) == true,
        ERR_INVALID_HANDLE, "no need to stop");

    ModifyAudioEffectChainInfo(nodeInfo, REMOVE_AUDIO_EFFECT_CHAIN_INFO);
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::AudioOffloadRendererRelease(HpaeNodeInfo &nodeInfo, const HpaeSinkInfo &sinkInfo)
{
    CHECK_AND_RETURN_RET_LOG(OffloadRendererCheckNotifyEffect(sinkInfo) == true,
        ERR_INVALID_HANDLE, "no need to release");

    int32_t ret = ReleaseAudioEffectChain(nodeInfo);
    AUDIO_WARNING_LOG("out, ret: %{public}d", ret);
    ModifyAudioEffectChainInfo(nodeInfo, REMOVE_AUDIO_EFFECT_CHAIN_INFO);
    return SUCCESS;
}

bool HpaeRenderEffectNode::OffloadRendererCheckNotifyEffect(const HpaeSinkInfo &sinkInfo)
{
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_RETURN_RET_LOG(audioEffectChainManager != nullptr, false, "null audioEffectChainManager");
    CHECK_AND_RETURN_RET_LOG(audioEffectChainManager->GetOffloadEnabled() == true, false,
        "no effect offload scene");
    CHECK_AND_RETURN_RET_LOG(sinkInfo.deviceClass != "remote_offload", false, "no need notify effectChainManager");

    return true;
}

int32_t HpaeRenderEffectNode::CreateAudioEffectChain(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("sessionID is %{public}u, sceneType is %{public}d",
        nodeInfo.sessionId, nodeInfo.effectInfo.effectScene);
    // todo: if boot music, do not create audio effect
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioEffectChainManager != nullptr, ERR_INVALID_HANDLE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "null audioEffectChainManager", false),
        "null audioEffectChainManager");
    std::string sceneType = "EFFECT_NONE";
    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
    if (audioSupportedSceneTypes.find(nodeInfo.effectInfo.effectScene) !=
        audioSupportedSceneTypes.end()) {
        sceneType = audioSupportedSceneTypes.at(nodeInfo.effectInfo.effectScene);
    }
    if (!audioEffectChainManager->CheckAndAddSessionID(std::to_string(nodeInfo.sessionId))) {
        return SUCCESS;
    }
    audioEffectChainManager->UpdateSceneTypeList(sceneType, ADD_SCENE_TYPE);
    if (audioEffectChainManager->GetOffloadEnabled()) {
        return SUCCESS;
    }
    int32_t ret;
    if (Util::IsEnhancedRoutingSupported()) {
        ret = audioEffectChainManager->CreateAudioEffectChainDynamic(sceneType, deviceType_, renderId_);
    } else {
        ret = audioEffectChainManager->CreateAudioEffectChainDynamic(sceneType);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_OPERATION_FAILED),
            "create effect chain fail", false),
        "create effect chain fail, ret: %{public}d", ret);
    AUDIO_INFO_LOG("Success, sessionID is %{public}u, sceneType is %{public}d",
        nodeInfo.sessionId, nodeInfo.effectInfo.effectScene);
    return SUCCESS;
}

int32_t HpaeRenderEffectNode::ReleaseAudioEffectChain(HpaeNodeInfo &nodeInfo)
{
    AUDIO_INFO_LOG("sessionID is %{public}u, sceneType is %{public}d",
        nodeInfo.sessionId, nodeInfo.effectInfo.effectScene);
    // todo: if boot music, do not release audio effect
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioEffectChainManager != nullptr, ERR_INVALID_HANDLE,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::RELEASE, ERR_NULL_POINTER),
            "null audioEffectChainManager", false),
        "null audioEffectChainManager");
    std::string sceneType = "EFFECT_NONE";
    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
    if (audioSupportedSceneTypes.find(nodeInfo.effectInfo.effectScene) !=
        audioSupportedSceneTypes.end()) {
        sceneType = audioSupportedSceneTypes.at(nodeInfo.effectInfo.effectScene);
    }
    if (!audioEffectChainManager->CheckAndRemoveSessionID(std::to_string(nodeInfo.sessionId))) {
        return SUCCESS;
    }
    audioEffectChainManager->UpdateSceneTypeList(sceneType, REMOVE_SCENE_TYPE);
    if (audioEffectChainManager->GetOffloadEnabled()) {
        return SUCCESS;
    }
    int32_t ret;
    if (Util::IsEnhancedRoutingSupported()) {
        ret = audioEffectChainManager->ReleaseAudioEffectChainDynamic(sceneType, deviceType_, renderId_);
    } else {
        ret = audioEffectChainManager->ReleaseAudioEffectChainDynamic(sceneType);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::RELEASE, ERR_OPERATION_FAILED),
            "release effect chain fail", false),
        "release effect chain fail, ret: %{public}d", ret);
    AUDIO_INFO_LOG("Success, sessionID is %{public}u, sceneType is %{public}d",
        nodeInfo.sessionId, nodeInfo.effectInfo.effectScene);
    return SUCCESS;
}

void HpaeRenderEffectNode::ModifyAudioEffectChainInfo(HpaeNodeInfo &nodeInfo,
    ModifyAudioEffectChainInfoReason reason)
{
    std::string sessionID = std::to_string(nodeInfo.sessionId);
    std::string sceneType = "EFFECT_NONE";
    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
    if (audioSupportedSceneTypes.find(nodeInfo.effectInfo.effectScene) !=
        audioSupportedSceneTypes.end()) {
        sceneType = audioSupportedSceneTypes.at(nodeInfo.effectInfo.effectScene);
    }
    int32_t ret = 0;
    switch (reason) {
        case ADD_AUDIO_EFFECT_CHAIN_INFO: {
            const std::unordered_map<AudioEffectMode, std::string> &audioSupportedSceneModes =
                GetAudioSupportedSceneModes();
            SessionEffectInfo info;
            auto sceneMode = audioSupportedSceneModes.find(nodeInfo.effectInfo.effectMode);
            if (sceneMode != audioSupportedSceneModes.end()) {
                info.sceneMode = sceneMode->second;
            } else {
                AUDIO_WARNING_LOG("sceneMode: %{public}d is not supported", nodeInfo.effectInfo.effectMode);
                info.sceneMode = "EFFECT_NONE";
            }
            info.sceneType = sceneType;
            info.channels = static_cast<uint32_t>(nodeInfo.channels);
            info.channelLayout = nodeInfo.channelLayout;
            info.streamUsage = nodeInfo.effectInfo.streamUsage;
            info.systemVolumeType = static_cast<int32_t>(nodeInfo.effectInfo.systemVolumeType);
            if (Util::IsEnhancedRoutingSupported()) {
                info.renderId = renderId_;
                info.deviceType = deviceType_;
            }
            ret = AudioEffectChainManager::GetInstance()->SessionInfoMapAdd(sessionID, info);
            break;
        }
        case REMOVE_AUDIO_EFFECT_CHAIN_INFO:
            ret = AudioEffectChainManager::GetInstance()->SessionInfoMapDelete(sceneType, sessionID);
            break;
        default:
            break;
    }
    CHECK_AND_RETURN_LOG(ret == SUCCESS, "modify session info failed");
    UpdateAudioEffectChainInfo(nodeInfo);
}

void HpaeRenderEffectNode::UpdateAudioEffectChainInfo(HpaeNodeInfo &nodeInfo)
{
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_RETURN_LOG(audioEffectChainManager != nullptr, "null audioEffectChainManager");
    std::string sceneType = "EFFECT_NONE";
    const std::unordered_map<AudioEffectScene, std::string> &audioSupportedSceneTypes = GetSupportedSceneType();
    if (audioSupportedSceneTypes.find(nodeInfo.effectInfo.effectScene) !=
        audioSupportedSceneTypes.end()) {
        sceneType = audioSupportedSceneTypes.at(nodeInfo.effectInfo.effectScene);
    }
    if (Util::IsEnhancedRoutingSupported()) {
        audioEffectChainManager->UpdateMultichannelConfig(sceneType, deviceType_, renderId_);
    } else {
        audioEffectChainManager->UpdateMultichannelConfig(sceneType);
    }
    audioEffectChainManager->EffectVolumeUpdate();
    audioEffectChainManager->UpdateDefaultAudioEffect();
    audioEffectChainManager->UpdateStreamUsage();
}

void HpaeRenderEffectNode::ReconfigOutputBuffer()
{
    HpaeNodeInfo &effectNodeInfo = GetNodeInfo();
    uint32_t channels = static_cast<uint32_t>(effectNodeInfo.channels);
    uint64_t channelLayout = effectNodeInfo.channelLayout;
    int32_t ret;
    if (Util::IsEnhancedRoutingSupported()) {
        ret = AudioEffectChainManager::GetInstance()->GetOutputChannelInfo(
            sceneType_, deviceType_, renderId_, channels, channelLayout);
    } else {
        ret = AudioEffectChainManager::GetInstance()->GetOutputChannelInfo(sceneType_, channels, channelLayout);
    }
    if (ret != SUCCESS || channels == 0 || channelLayout == 0) {
        AUDIO_WARNING_LOG("output channel info incorrect, scene type: %{public}s, "
            "channels: %{public}u, channelLayout: %{public}" PRIu64, sceneType_.c_str(), channels, channelLayout);
    } else if (static_cast<uint32_t>(effectNodeInfo.channels) != channels ||
        static_cast<uint64_t>(effectNodeInfo.channelLayout) != channelLayout) {
        AUDIO_INFO_LOG("output channel info changed, scene type: %{public}s, "
            "channels change from %{public}u to %{public}u, "
            "channelLayout change from %{public}" PRIu64 " to %{public}" PRIu64,
            sceneType_.c_str(), effectNodeInfo.channels, channels, effectNodeInfo.channelLayout, channelLayout);
        PcmBufferInfo pcmBufferInfo = PcmBufferInfo(channels, DEFAULT_EFFECT_FRAMELEN,
            DEFUALT_EFFECT_RATE, channelLayout, effectOutput_.GetFrames());
        pcmBufferInfo.isMultiFrames = effectOutput_.IsMultiFrames();
        effectOutput_.ReConfig(pcmBufferInfo);
        effectNodeInfo.channels = static_cast<AudioChannel>(channels);
        effectNodeInfo.channelLayout = static_cast<AudioChannelLayout>(channelLayout);
        effectNodeInfo.samplingRate = static_cast<AudioSamplingRate>(DEFUALT_EFFECT_RATE);
        effectNodeInfo.frameLen = static_cast<uint32_t>(DEFAULT_EFFECT_FRAMELEN);
        SetNodeInfo(effectNodeInfo);
#ifdef ENABLE_HIDUMP_DFX
        if (auto callBack = GetNodeStatusCallback().lock()) {
            callBack->OnNotifyDfxNodeInfoChanged(GetNodeId(), GetNodeInfo());
        }
#endif
    }
}

int32_t HpaeRenderEffectNode::GetExpectedInputChannelInfo(AudioBasicFormat &basicFormat)
{
    basicFormat.rate = static_cast<AudioSamplingRate>(DEFUALT_EFFECT_RATE);
    uint64_t channelLayout = 0;
    int32_t ret;
    if (Util::IsEnhancedRoutingSupported()) {
        ret = AudioEffectChainManager::GetInstance()->QueryEffectChannelInfo(
            sceneType_, deviceType_, renderId_, basicFormat.audioChannelInfo.numChannels, channelLayout);
    } else {
        ret = AudioEffectChainManager::GetInstance()->QueryEffectChannelInfo(
            sceneType_, basicFormat.audioChannelInfo.numChannels, channelLayout);
    }
    basicFormat.audioChannelInfo.channelLayout = static_cast<AudioChannelLayout>(channelLayout);
    return ret;
}

bool HpaeRenderEffectNode::IsByPassEffectZeroVolume(HpaePcmBuffer *pcmBuffer)
{
    if (!pcmBuffer->IsValid()) {
        return false;
    }
    if (pcmBuffer->IsSilence()) {
        if (!isDisplayEffectZeroVolume_) {
            AUDIO_INFO_LOG("Timing begins, will close [%{public}s] effect after [%{public}" PRId64 "]s",
                sceneType_.c_str(), WAIT_CLOSE_EFFECT_TIME);
            isDisplayEffectZeroVolume_ = true;
        }
        silenceDataUs_ += static_cast<int64_t>(pcmBuffer->GetFrameLen() * TIME_IN_US / pcmBuffer->GetSampleRate());
        if (!isByPassEffect_ && silenceDataUs_ >= WAIT_CLOSE_EFFECT_TIME * TIME_IN_US) {
            AUDIO_INFO_LOG("Volume change to zero over %{public}" PRId64 "s, close effect:%{public}s success.",
                WAIT_CLOSE_EFFECT_TIME, sceneType_.c_str());
            isByPassEffect_ = true;
            silenceDataUs_ = 0;
        } else if (isByPassEffect_ && silenceDataUs_ >= MONITOR_CLOSE_EFFECT_TIME * TIME_IN_US) {
            silenceDataUs_ = 0;
            AUDIO_INFO_LOG("Effect [%{public}s] have closed [%{public}" PRId64 "]s.",
                sceneType_.c_str(), MONITOR_CLOSE_EFFECT_TIME);
        }
    } else {
        if (isDisplayEffectZeroVolume_) {
            AUDIO_INFO_LOG("Volume change to non zero, open effect:%{public}s success.", sceneType_.c_str());
            isDisplayEffectZeroVolume_ = false;
        }
        silenceDataUs_ = 0;
        isByPassEffect_ = false;
    }
    return isByPassEffect_;
}

void HpaeRenderEffectNode::InitEffectBuffer(const uint32_t sessionId)
{
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_RETURN_LOG(audioEffectChainManager != nullptr, "null audioEffectChainManager");
    CHECK_AND_RETURN_LOG(sceneType_ != "SCENE_COLLABORATIVE", "COLLABORATIVE, no need InitEffectBuffer");
    audioEffectChainManager->InitEffectBuffer(std::to_string(sessionId));
}

void HpaeRenderEffectNode::InitEffectBufferFromDisConnect()
{
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_RETURN_LOG(audioEffectChainManager != nullptr, "null audioEffectChainManager");
    if (Util::IsEnhancedRoutingSupported()) {
        audioEffectChainManager->InitAudioEffectChainDynamic(sceneType_, deviceType_, renderId_);
    } else {
        audioEffectChainManager->InitAudioEffectChainDynamic(sceneType_);
    }
    AUDIO_INFO_LOG("sceneType:%{public}s", sceneType_.c_str());
}

uint64_t HpaeRenderEffectNode::GetLatency(uint32_t sessionId)
{
    AudioEffectChainManager *audioEffectChainManager = AudioEffectChainManager::GetInstance();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioEffectChainManager != nullptr, 0,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "null audioEffectChainManager", false),
        "null audioEffectChainManager");
    return audioEffectChainManager->GetLatency(std::to_string(sessionId)) * AUDIO_US_PER_MS;
}

void HpaeRenderEffectNode::SetDelayCountToEffectNode(int32_t delayCount)
{
    if (tempEffectBuffer_ != nullptr) {
        tempEffectBuffer_->SetDelayCountToEffectNode(delayCount);
    }
}

void HpaeRenderEffectNode::SetCollabDoFade(bool fadeOutState)
{
    if (tempEffectBuffer_ != nullptr) {
        tempEffectBuffer_->SetCollabDoFade(fadeOutState);
    }
}

void HpaeRenderEffectNode::SetStopRunningState(bool stopRunning)
{
    if (tempEffectBuffer_ != nullptr) {
        tempEffectBuffer_->SetStopRunningState(stopRunning);
    }
}

HpaeTempEffectBuffer::HpaeTempEffectBuffer(PcmBufferInfo pcmBufferInfo, CollaborationState isCollaborationEnabled)
{
    const size_t size = static_cast<size_t>(SAMPLE_RATE_48000) *
                        static_cast<size_t>(STEREO) *
                        sizeof(float) *
                        static_cast<size_t>(EFFECT_TEMP_BUFFER_MAX_CACHE_SIZE) /
                        static_cast<size_t>(EFFECT_TEMP_BUFFER_MS_PER_SECOND);
    AUDIO_INFO_LOG("Create ring cached, size: %{public}zu", size);
    ringCache_ = AudioRingCache::Create(size);
    CHECK_AND_RETURN_LOG(ringCache_ != nullptr, "Create ring cache failed");
    waitCountThreshold_ = EFFECT_TEMP_BUFFER_DEFAULT_WAIT_COUNT;
    tempOutput_ = std::make_unique<HpaePcmBuffer>(pcmBufferInfo);
    isCollaborationEnabled_ = isCollaborationEnabled;
}

void HpaeTempEffectBuffer::ChangeEffectDataForLatency(HpaePcmBuffer* buffer)
{
    if (!DelayAlignmentForEffectNode(buffer)) {
        AUDIO_INFO_LOG("delay alignment for collabortive data is not ready");
        SetSilenceData(buffer);
        return;
    }

    if (stopRunning_ == true) {
        SetSilenceDataInAllChannel(buffer);
        return;
    }
    WriteDataEnqueueRingCache(buffer);
    ReadDataDequeueRingCache(buffer);

    if (effectCollabDoFadeOutState_ == true) {
        DoFadeOut(buffer);
        effectCollabDoFadeOutState_ = false;
        stopRunning_ = true;
        AUDIO_INFO_LOG("CollabDoFadeOut finish");
    }
}

void HpaeTempEffectBuffer::WriteDataEnqueueRingCache(HpaePcmBuffer* buffer)
{
    float *collOutPut = buffer->GetPcmDataBuffer();
    CHECK_AND_RETURN_LOG(tempOutput_ != nullptr, "tempOutput_ is null");
    float *tempOutput = tempOutput_->GetPcmDataBuffer();
    for (uint32_t i = 0; i < buffer->GetFrameLen(); ++i) {
        tempOutput[COLLABORATIVE_CHANNELS * i] =
            collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX];
        tempOutput[COLLABORATIVE_CHANNELS * i + 1] =
            collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX];
    }

    CHECK_AND_RETURN_LOG(ringCache_ != nullptr && buffer != nullptr, "Ring cache or buffer is nullptr");
    const size_t writeLen = static_cast<size_t>(SAMPLE_RATE_48000) *
                        static_cast<size_t>(STEREO) *
                        sizeof(float) *
                        static_cast<size_t>(FRAME_LEN_20MS) /
                        static_cast<size_t>(EFFECT_TEMP_BUFFER_MS_PER_SECOND);
    // check writable size
    OptResult result = ringCache_->GetWritableSize();
    CHECK_AND_RETURN_LOG(result.ret == OPERATION_SUCCESS, "get writable size failed");
    CHECK_AND_RETURN_LOG(result.size >= writeLen,
        "Insufficient cache space: %{public}zu < %{public}zu", result.size, writeLen);
    
    // enqueue buffer
    BufferWrap bufferWrap = {reinterpret_cast<uint8_t*>(tempOutput), writeLen};
    result = ringCache_->Enqueue(bufferWrap);
    CHECK_AND_RETURN_LOG(result.ret == OPERATION_SUCCESS, "Enqueue data failed");
}

void HpaeTempEffectBuffer::ReadDataDequeueRingCache(HpaePcmBuffer* buffer)
{
    CHECK_AND_RETURN_LOG(ringCache_ != nullptr, "Ring cache is null");
    const size_t requestDataLen = static_cast<size_t>(SAMPLE_RATE_48000) *
                                  static_cast<size_t>(STEREO) *
                                  sizeof(float) *
                                  static_cast<size_t>(FRAME_LEN_20MS) /
                                  static_cast<size_t>(EFFECT_TEMP_BUFFER_MS_PER_SECOND);
    // check readable size
    OptResult result = ringCache_->GetReadableSize();
    CHECK_AND_RETURN_LOG(result.ret == OPERATION_SUCCESS, "get readable size failed");

    if (result.size < requestDataLen) {
        AUDIO_WARNING_LOG("Insufficient data: %{public}zu < %{public}zu, outputting silence",
            result.size, requestDataLen);
        SetSilenceData(buffer);
    } else {
        CHECK_AND_RETURN_LOG(tempOutput_ != nullptr, "tempOutput_ is null");
        float *tempOutput = tempOutput_->GetPcmDataBuffer();
        // read buffer
        BufferWrap bufferWrap = {reinterpret_cast<uint8_t *>(tempOutput), requestDataLen};
        result = ringCache_->Dequeue(bufferWrap);
        if (result.ret != OPERATION_SUCCESS) {
            AUDIO_INFO_LOG("Dequeue data failed");
            SetSilenceData(buffer);
        } else {
            SetTempBufferData(buffer, tempOutput);
        }
    }
}

void HpaeTempEffectBuffer::SetSilenceData(HpaePcmBuffer* buffer)
{
    float *collOutPut = buffer->GetPcmDataBuffer();
    for (uint32_t i = 0; i < buffer->GetFrameLen(); ++i) {
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] = SMALL_SIGNAL_NUM;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] = SMALL_SIGNAL_NUM;
    }
}

void HpaeTempEffectBuffer::SetTempBufferData(HpaePcmBuffer* buffer, float *tempOutput)
{
    float *collOutPut = buffer->GetPcmDataBuffer();
    for (uint32_t i = 0; i < buffer->GetFrameLen(); ++i) {
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] =
            tempOutput[COLLABORATIVE_CHANNELS * i];
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] =
            tempOutput[COLLABORATIVE_CHANNELS * i + 1];
    }
}

 void HpaeTempEffectBuffer::SetSilenceDataInAllChannel(HpaePcmBuffer* buffer)
{
    float *collOutPut = buffer->GetPcmDataBuffer();
    for (uint32_t i = 0; i < buffer->GetFrameLen(); ++i) {
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i] = SMALL_SIGNAL_NUM;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + 1] = SMALL_SIGNAL_NUM;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] = SMALL_SIGNAL_NUM;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] = SMALL_SIGNAL_NUM;
    }
}
 	 
void HpaeTempEffectBuffer::DoFadeOut(HpaePcmBuffer* buffer)
{
    float *collOutPut = buffer->GetPcmDataBuffer();
    float gain = 1.0f;
    float deltaGain = 1.0f / buffer->GetFrameLen();
    for (uint32_t i = 0; i< buffer->GetFrameLen(); ++i) {
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i] *= gain;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + 1] *= gain;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] *= gain;
        collOutPut[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] *= gain;
        gain -= deltaGain;
    }
}

bool HpaeTempEffectBuffer::DelayAlignmentForEffectNode(HpaePcmBuffer* buffer)
{
    if (enqueueCount_ < waitCountThreshold_) {
        enqueueCount_++;
        SetSilenceData(buffer);
        if (enqueueCount_ <= UPDATE_NEARLINK_COLLAB_STATE_TO_HDI_WAIT_COUNT) {
            UpdateNearLinkCollaborationStateToHdi(isCollaborationEnabled_);
        }
        return false;
    }

    if (enqueueCount_ == waitCountThreshold_) {
        enqueueCount_++;
        //file silence frame for latency adjustment
        ringCache_->ResetBuffer();

        int32_t latency = EFFECT_TEMP_BUFFER_DEFAULT_CO_LATENCY;
        ChangeLatencyByCollManagerForEffectNode(latency);
        AUDIO_INFO_LOG("Filling silence frames for latency adjustment, use latency: %{public}d", latency);
        FillSilenceFramesForEffectNode(latency);
        // smoothen collaborative data
        float gain = 0;
        float deltaGain = 1.0f / DEFAULT_EFFECT_FRAMELEN;
        for (uint32_t i = 0; i< DEFAULT_EFFECT_FRAMELEN; ++i) {
            buffer->GetPcmDataBuffer()[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_1_INDEX] *=
                gain;
            buffer->GetPcmDataBuffer()[COLLABORATIVE_OUTPUT_CHANNELS * i + COLLABORATIVE_OUTPUT_CHANNEL_2_INDEX] *=
                gain;
            gain += deltaGain;
        }
    }

    return true;
}

void HpaeTempEffectBuffer::FillSilenceFramesForEffectNode(int32_t latencyMs)
{
    CHECK_AND_RETURN_LOG(ringCache_ != nullptr, "Ring cache is null");
    if (latencyMs < 0) {
        latencyMs = EFFECT_TEMP_BUFFER_DEFAULT_CO_LATENCY;
    }
    const size_t frameSize = ((static_cast<size_t>(SAMPLE_RATE_48000) * static_cast<size_t>(STEREO) *
        sizeof(float)) / static_cast<size_t>(EFFECT_TEMP_BUFFER_MS_PER_SECOND)) * latencyMs;
    
    // check writeable size;
    OptResult result = ringCache_->GetWritableSize();
    CHECK_AND_RETURN_LOG(result.ret == OPERATION_SUCCESS, "get writable size failed");
    CHECK_AND_RETURN_LOG(result.size >= frameSize,
        "Insufficient cache space: %{public}zu < %{public}zu", result.size, frameSize);
    
    std::vector<uint8_t> silenceData(frameSize, 0);
    // create silence frame
    BufferWrap bufferWrap = {silenceData.data(), frameSize};
    result = ringCache_->Enqueue(bufferWrap);
    CHECK_AND_RETURN_LOG(result.ret == OPERATION_SUCCESS, "Enqueue silence frame failed");
    AUDIO_INFO_LOG("filled %{public}u ms of silence frames", latencyMs);
}

void HpaeTempEffectBuffer::ChangeLatencyByCollManagerForEffectNode(int32_t &latency)
{
    AudioCollaborationManager *audioCollaborationManager = AudioCollaborationManager::GetInstance();
    CHECK_AND_RETURN_LOG(audioCollaborationManager != nullptr, "null audioCollaborationManager");
    latency = audioCollaborationManager->GetCollaborationLatency();
}

void HpaeTempEffectBuffer::SetDelayCountToEffectNode(int32_t delayCount)
{
    AUDIO_INFO_LOG("setDelayCount: %{public}d", delayCount);
    // reset status flag
    enqueueCount_ = 0;
    waitCountThreshold_ = delayCount;
}

HpaeTempEffectBuffer::HpaeTempEffectBuffer()
{
    AUDIO_INFO_LOG("HpaeTempEffectBuffer create");
}
HpaeTempEffectBuffer::~HpaeTempEffectBuffer()
{
    AUDIO_INFO_LOG("HpaeTempEffectBuffer release");
}

 void HpaeTempEffectBuffer::UpdateNearLinkCollaborationStateToHdi(CollaborationState isCollaborationEnabled)
{
    CHECK_AND_RETURN_LOG(isCollaborationEnabled == COLLABORATION_NEARLINK_OPEN,
        "isCollaborationEnabled not COLLABORATION_NEARLINK_OPEN");
    HdiAdapterManager &manager = HdiAdapterManager::GetInstance();
    std::shared_ptr<IDeviceManager> deviceManager = manager.GetDeviceManager(HDI_DEVICE_MANAGER_TYPE_LOCAL);
    CHECK_AND_RETURN_LOG(deviceManager != nullptr, "local device manager is nullptr");
    std::string keyValue = std::string("nearLink_collaborative_state=") + "1";
    deviceManager->SetAudioParameter("primary", AudioParamKey::NONE, "", keyValue);
    AUDIO_INFO_LOG("effectNode: UpdateNearLinkCollaborationStateToHdi, value: %{public}s", keyValue.c_str());
}
 	 
void HpaeTempEffectBuffer::SetCollabDoFade(bool fadeOutState)
{
    AUDIO_INFO_LOG("SetCollabDoFade: %{public}d", fadeOutState);
    effectCollabDoFadeOutState_ = fadeOutState;
}
 	 
void HpaeTempEffectBuffer::SetStopRunningState(bool stopRunning)
{
    AUDIO_INFO_LOG("SetStopRunningState: %{public}d", stopRunning);
    stopRunning_ = stopRunning;
}
} // namespace HPAE
} // namespace AudioStandard
} // namespace OHOS
