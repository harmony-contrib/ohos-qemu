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
#define LOG_TAG "HpaeMixerNode"
#endif

#include <iostream>
#include "hpae_mixer_node.h"
#include "hpae_pcm_buffer.h"
#include "audio_utils.h"
#include "cinttypes"
#include "audio_errors.h"
#include "audio_effect_log.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {

static constexpr uint32_t WAIT_FRAMES_NUM = 5; // wait 5 * 20ms before disconnect
static constexpr uint32_t DEFAULT_CHANNEL_COUNT = 2;
static constexpr uint32_t DEFAULT_FRAME_LEN = 960;
static constexpr uint32_t DEFAULT_SAMPLE_RATE = 48000;
    
HpaeMixerNode::HpaeMixerNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
    pcmBufferInfo_(nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate, nodeInfo.channelLayout),
    mixedOutput_(pcmBufferInfo_), tmpOutput_(pcmBufferInfo_)
{
    mixedOutput_.SetSplitStreamType(nodeInfo.GetSplitStreamType());
    mixedOutput_.SetAudioStreamType(nodeInfo.streamType);
    mixedOutput_.SetAudioStreamUsage(nodeInfo.effectInfo.streamUsage);
    dumpMixName_ = "hpae_mixer_out_" + std::to_string(nodeInfo.sessionId) + "_" +
        std::to_string(nodeInfo.samplingRate) + "_" + std::to_string(nodeInfo.channels) + "_" +
        std::to_string(nodeInfo.format) + ".pcm";
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpMixName_, &dumpMix_);
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeMixerNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeMixerNode::~HpaeMixerNode()
{
    DumpFileUtil::CloseDumpFile(&dumpMix_);
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

bool HpaeMixerNode::Reset()
{
    return HpaePluginNode::Reset();
}

void HpaeMixerNode::SetNodeInfo(HpaeNodeInfo& nodeInfo)
{
    mixedOutput_.SetAudioStreamType(nodeInfo.streamType);
    mixedOutput_.SetAudioStreamUsage(nodeInfo.effectInfo.streamUsage);
    tmpOutput_.SetAudioStreamType(nodeInfo.streamType);
    tmpOutput_.SetAudioStreamUsage(nodeInfo.effectInfo.streamUsage);
    silenceData_.SetAudioStreamType(nodeInfo.streamType);
    silenceData_.SetAudioStreamUsage(nodeInfo.effectInfo.streamUsage);
    HpaeNode::SetNodeInfo(nodeInfo);
}

void HpaeMixerNode::ConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>> &preNode,
    HpaeNodeInfo &nodeInfo)
{
    std::shared_ptr<HpaeNode> realPreNode = preNode->GetSharedInstance(nodeInfo);
    CHECK_AND_RETURN_LOG(realPreNode != nullptr, "realPreNode is nullptr");
    inputStream_.Connect(realPreNode, preNode->GetOutputPort(nodeInfo));
#ifdef ENABLE_HIDUMP_DFX
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeInfo(true, realPreNode->GetNodeId(), GetNodeId());
    }
#endif
}

void HpaeMixerNode::DisConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>>& preNode,
    HpaeNodeInfo &nodeInfo)
{
    CHECK_AND_RETURN_LOG(!inputStream_.CheckIfDisConnected(preNode->GetOutputPort(nodeInfo)),
        "HpaeMixerNode[%{public}u] has disconnected with preNode", GetNodeId());
    const auto port = preNode->GetOutputPort(nodeInfo, true);
    inputStream_.DisConnect(port);
#ifdef ENABLE_HIDUMP_DFX
    CHECK_AND_RETURN_LOG(port != nullptr, "port is nullptr");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeInfo(false, port->GetNodeId(), GetNodeId());
    }
#endif
}

int32_t HpaeMixerNode::SetupAudioLimiter()
{
    if (limiter_ != nullptr) {
        AUDIO_INFO_LOG("NodeId: %{public}d, limiter has already been setup!", GetNodeId());
        return ERROR;
    }
    return InitAudioLimiter();
}

int32_t HpaeMixerNode::InitAudioLimiter()
{
    limiter_ = std::make_unique<AudioLimiter>(GetNodeId());
    // limiter only supports float format
    int32_t ret = limiter_->SetConfig(GetFrameLen() * GetChannelCount() * sizeof(float), sizeof(float), GetSampleRate(),
        GetChannelCount());
    if (ret == SUCCESS) {
        AUDIO_INFO_LOG("NodeId: %{public}d, limiter init sucess!", GetNodeId());
    } else {
        limiter_ = nullptr;
        AUDIO_INFO_LOG("NodeId: %{public}d, limiter init fail!!", GetNodeId());
    }
    return ret;
}

HpaePcmBuffer *HpaeMixerNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    Trace trace("[sceneType:" + std::to_string(GetSceneType()) + "]" + "HpaeMixerNode::SignalProcess");
    mixedOutput_.Reset();

    if (GetSceneType() != HPAE_SCENE_EFFECT_OUT) {
        DrainProcess();
    }

    uint32_t bufferState = PCM_BUFFER_STATE_INVALID | PCM_BUFFER_STATE_SILENCE;
    if (limiter_ == nullptr) {
        bool ret = inputs.empty() ? CheckUpdateInfoForDisConnect() : CheckUpdateInfo(inputs[0]);
        if (ret) {
            mixedOutput_.ReConfig(pcmBufferInfo_);
        }
        for (auto input: inputs) {
            mixedOutput_ += *input;
            bufferState &= input->GetBufferState();
        }
    } else { // limiter does not support reconfigging frameLen at runtime
        tmpOutput_.Reset();
        for (auto input: inputs) {
            tmpOutput_ += *input;
            bufferState &= input->GetBufferState();
        }
        limiter_->Process(GetFrameLen() * GetChannelCount(),
            tmpOutput_.GetPcmDataBuffer(), mixedOutput_.GetPcmDataBuffer());
    }
    DumpFileUtil::WriteDumpFile(dumpMix_, static_cast<void *>(mixedOutput_.GetPcmDataBuffer()),
        mixedOutput_.DataSize());
    mixedOutput_.SetBufferState(bufferState);
    return &mixedOutput_;
}

bool HpaeMixerNode::CheckUpdateInfo(HpaePcmBuffer* input)
{
    struct UpdateCheck {
        std::string name;
        uint32_t &currentVal;
        uint32_t newVal;
    } checks[] = {
        {"channel count", pcmBufferInfo_.ch, input->GetChannelCount()},
        {"frame len", pcmBufferInfo_.frameLen, input->GetFrameLen()},
        {"sample rate", pcmBufferInfo_.rate, input->GetSampleRate()}
    };

    bool isPCMBufferInfoUpdated = false;
    
    for (auto& check : checks) {
        if (check.currentVal != check.newVal) {
            AUDIO_INFO_LOG("Update %{public}s: %{public}d -> %{public}d",
                check.name.c_str(), check.currentVal, check.newVal);
            check.currentVal = check.newVal;
            isPCMBufferInfoUpdated = true;
        }
    }

    if (pcmBufferInfo_.channelLayout != input->GetChannelLayout()) {
        AUDIO_INFO_LOG("Update channel layout %{public}" PRIu64 " -> %{public}" PRIu64 "",
            pcmBufferInfo_.channelLayout, input->GetChannelLayout());
        pcmBufferInfo_.channelLayout = input->GetChannelLayout();
        isPCMBufferInfoUpdated = true;
    }

    // if other bitwidth is supported, add check here

    return isPCMBufferInfoUpdated;
}


bool HpaeMixerNode::CheckUpdateInfoForDisConnect()
{
    struct UpdateCheck {
        std::string name;
        uint32_t &currentVal;
        uint32_t newVal;
    } checks[] = {
        {"channel count", pcmBufferInfo_.ch, DEFAULT_CHANNEL_COUNT},
        {"frame len", pcmBufferInfo_.frameLen, DEFAULT_FRAME_LEN},
        {"sample rate", pcmBufferInfo_.rate, DEFAULT_SAMPLE_RATE}
    };

    bool isPCMBufferInfoUpdated = false;
    
    for (auto& check : checks) {
        if (check.currentVal != check.newVal) {
            AUDIO_INFO_LOG("Update %{public}s: %{public}d -> %{public}d",
                check.name.c_str(), check.currentVal, check.newVal);
            check.currentVal = check.newVal;
            isPCMBufferInfoUpdated = true;
        }
    }

    if (pcmBufferInfo_.channelLayout != AudioChannelLayout::CH_LAYOUT_STEREO) {
        AUDIO_INFO_LOG("Update channel layout %{public}" PRIu64 " -> %{public}" PRIu64 "",
            pcmBufferInfo_.channelLayout, AudioChannelLayout::CH_LAYOUT_STEREO);
        pcmBufferInfo_.channelLayout = AudioChannelLayout::CH_LAYOUT_STEREO;
        isPCMBufferInfoUpdated = true;
    }

    // if other bitwidth is supported, add check here

    return isPCMBufferInfoUpdated;
}

void HpaeMixerNode::DrainProcess()
{
    if (GetPreOutNum() != 0) {
        waitFrames_ = 0;
    } else {
        waitFrames_++;
        if (waitFrames_ == WAIT_FRAMES_NUM) {
            waitFrames_ = 0;
            auto statusCallback = GetNodeStatusCallback().lock();
            if (statusCallback) {
                AUDIO_INFO_LOG("trigger callback to disconnect");
                statusCallback->OnDisConnectProcessCluster(GetSceneType());
            }
        }
    }
}

uint64_t HpaeMixerNode::GetLatency(uint32_t sessionId)
{
    CHECK_AND_RETURN_RET(limiter_ != nullptr, 0);
    return limiter_->GetLatency() * AUDIO_US_PER_MS;
}

void HpaeMixerNode::SetCollaborationStateToMixNode(CollaborationState isCollaborationEnabled)
{
    AUDIO_INFO_LOG("SetCollaborationStateToMixNode: %{public}d", isCollaborationEnabled);
    isCollaborationEnabled_ = isCollaborationEnabled;
}
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
