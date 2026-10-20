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
#define LOG_TAG "HpaeLimiterNode"
#endif

#include "hpae_limiter_node.h"
#include "audio_errors.h"
#include "audio_engine_log.h"
#include "cinttypes"
#include "audio_utils.h"
#include "stream_dfx_manager.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
HpaeLimiterNode::HpaeLimiterNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
    pcmBufferInfo_(nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate, nodeInfo.channelLayout),
    limiterOutput_(pcmBufferInfo_)
{
    limiterOutput_.SetSplitStreamType(nodeInfo.GetSplitStreamType());
    limiterOutput_.SetAudioStreamType(nodeInfo.streamType);
    limiterOutput_.SetAudioStreamUsage(nodeInfo.effectInfo.streamUsage);
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeLimiterNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeLimiterNode::~HpaeLimiterNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

int32_t HpaeLimiterNode::SetupAudioLimiter()
{
    if (limiter_ != nullptr) {
        AUDIO_INFO_LOG("NodeId: %{public}d, limiter has already been setup!", GetNodeId());
        return ERROR;
    }
    return InitAudioLimiter();
}

int32_t HpaeLimiterNode::InitAudioLimiter()
{
    limiter_ = std::make_unique<AudioLimiter>(GetNodeId());
    // limiter only supports float format
    int32_t ret = limiter_->SetConfig(GetFrameLen() * GetChannelCount() * sizeof(float), sizeof(float),
        GetSampleRate(), GetChannelCount());
    if (ret == SUCCESS) {
        AUDIO_INFO_LOG("NodeId: %{public}d, limiter init success!", GetNodeId());
    } else {
        limiter_ = nullptr;
        AUDIO_ERR_LOG("NodeId: %{public}d, limiter init failed!", GetNodeId());
    }
    return ret;
}

uint64_t HpaeLimiterNode::GetLatency(uint32_t sessionId)
{
    CHECK_AND_RETURN_RET(limiter_ != nullptr, 0);
    return limiter_->GetLatency() * AUDIO_US_PER_MS;
}

HpaePcmBuffer *HpaeLimiterNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    Trace trace("HpaeLimiterNode::SignalProcess");
    limiterOutput_.Reset();
    if (inputs.empty() || !inputs[0]) {
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "limiter input is empty", false);
        AUDIO_WARNING_LOG("NodeId %{public}d, sessionId %{public}d input is empty", GetNodeId(), GetSessionId());
        return &limiterOutput_;
    }
    CHECK_AND_RETURN_RET(inputs[0]->IsValid(), inputs[0]);
    if (limiter_ == nullptr) {
        Trace trace("HpaeLimiterNode::SignalProcess::NoneLimiter");
        return inputs[0];
    }
    uint32_t bufferSize = inputs[0]->GetFrameLen() * inputs[0]->GetChannelCount();
    // Process with limiter
    limiter_->ProcessObserved579(bufferSize, inputs[0]->GetPcmDataBuffer(), limiterOutput_.GetPcmDataBuffer(),
        inputs[0]->Origins579(), limiterOutput_.Origins579());
    limiterOutput_.SetBufferState(inputs[0]->GetBufferState());
    return &limiterOutput_;
}
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
