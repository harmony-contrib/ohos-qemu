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
#define LOG_TAG "HpaeSinkInputNode"
#endif

#include <iostream>
#include <cinttypes>
#include "hpae_sink_input_node.h"
#include "hpae_format_convert.h"
#include "hpae_node_common.h"
#include "audio_errors.h"
#include "audio_utils.h"
#include "audio_performance_monitor.h"
#include "audio_engine_log.h"
#include "stream_dfx_manager.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
const std::string DEVICE_CLASS_OFFLOAD = "offload";
const std::string DEVICE_CLASS_REMOTE_OFFLOAD = "remote_offload";

HpaeSinkInputNode::HpaeSinkInputNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo),
      pcmBufferInfo_(nodeInfo.channels, nodeInfo.frameLen, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
        nodeInfo.customSampleRate, (uint64_t)nodeInfo.channelLayout),
      emptyBufferInfo_(nodeInfo.channels, 0, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
        nodeInfo.customSampleRate, (uint64_t)nodeInfo.channelLayout),
      inputAudioBuffer_(pcmBufferInfo_), emptyAudioBuffer_(emptyBufferInfo_), outputStream_(this),
      interleveData_(nodeInfo.frameLen * nodeInfo.channels * GetSizeFromFormat(nodeInfo.format)),
      totalFrames_(0)
{
    AUDIO_INFO_LOG("sessionId %{public}d, channelcount %{public}d, channelLayout %{public}" PRIu64 ", "
        "frameLen %{public}d", nodeInfo.sessionId, inputAudioBuffer_.GetChannelCount(),
        inputAudioBuffer_.GetChannelLayout(), inputAudioBuffer_.GetFrameLen());

    if (nodeInfo.historyFrameCount > 0) {
        PcmBufferInfo pcmInfo = PcmBufferInfo{
            nodeInfo.channels, nodeInfo.frameLen, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
            nodeInfo.customSampleRate, nodeInfo.channelLayout, nodeInfo.historyFrameCount};
        pcmInfo.isMultiFrames = true;
        historyBuffer_ = std::make_unique<HpaePcmBuffer>(pcmInfo);
        AUDIO_INFO_LOG("historybuffer created");
    } else {
        historyBuffer_ = nullptr;
    }
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeSinkInputNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
    isNonStandardSampleRate_ = IsNonStandardSampleRate(nodeInfo.GetEffectiveSampleRate());
}

HpaeSinkInputNode::~HpaeSinkInputNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

void HpaeSinkInputNode::CheckAndDestroyHistoryBuffer()
{
    HpaeNodeInfo nodeInfo = GetNodeInfo();
    // historyBuffer_ has no data, check if historyFrameCount is 0 and destroy it
    if (nodeInfo.historyFrameCount == 0) {
        if (historyBuffer_) {
            AUDIO_INFO_LOG("historyBuffer_ useless, destroy it");
        }
        historyBuffer_ = nullptr;
    } else if (historyBuffer_ == nullptr) {  // this case need to create historyBuffer_
        PcmBufferInfo pcmInfo = PcmBufferInfo{
            nodeInfo.channels, nodeInfo.frameLen, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
            nodeInfo.customSampleRate, nodeInfo.channelLayout, nodeInfo.historyFrameCount};
        pcmInfo.isMultiFrames = true;
        historyBuffer_ = std::make_unique<HpaePcmBuffer>(pcmInfo);
        AUDIO_INFO_LOG("historybuffer created");
    }
}

int32_t HpaeSinkInputNode::GetDataFromSharedBuffer()
{
    return OnStreamInfoChange(true);
}

bool HpaeSinkInputNode::ReadToAudioBuffer(int32_t &ret)
{
    auto nodeCallback = GetNodeStatusCallback().lock();
    if ((GetDeviceClass() == DEVICE_CLASS_OFFLOAD || GetDeviceClass() == DEVICE_CLASS_REMOTE_OFFLOAD) &&
        !offloadEnable_) {
        ret = ERR_OPERATION_FAILED;
        AUDIO_WARNING_LOG("The session %{public}u offloadEnable is false, not request data", GetSessionId());
    } else {
        Onset579::ClearRead();
        ret = GetDataFromSharedBuffer();
        // if historyBuffer has enough data, write to outputStream
        if (!streamInfo_.needData && historyBuffer_) {
            historyBuffer_->GetFrameData(inputAudioBuffer_);
            outputStream_.WriteDataToOutput(&inputAudioBuffer_);
            inputAudioBuffer_.SetBufferValid(true); // historyBuffer always valid
            return false; // do not continue in DoProcess!
        }
        CheckAndDestroyHistoryBuffer();
        if (nodeCallback && ret) {
            nodeCallback->OnNodeStatusUpdate(GetSessionId(), OPERATION_UNDERFLOW);
            if (isDrain_) {
                AUDIO_INFO_LOG("OnNodeStatusUpdate Drain sessionId:%{public}u", GetSessionId());
                nodeCallback->OnNodeStatusUpdate(GetSessionId(), OPERATION_DRAINED);
                isDrain_ = false;
            }
            standbyCounter_++;
        } else {
            standbyCounter_ = 0;
        }
    }
    inputAudioBuffer_.SetBufferValid(ret ? false : true);
    return true; // continue in DoProcess!
}

void HpaeSinkInputNode::DoProcess()
{
    Trace trace("[" + std::to_string(GetSessionId()) + "]HpaeSinkInputNode::DoProcess " + GetTraceInfo());

    int32_t ret = SUCCESS;

    if (!ReadToAudioBuffer(ret)) {
        return;
    }
    
    inputAudioBuffer_.Origins579().Clear();
    if (ret == SUCCESS) {
        inputAudioBuffer_.Origins579() = Onset579::TakeRead(appUid_, GetSessionId(), GetFrameLen());
    }
    ConvertToFloat(
        GetBitWidth(), GetChannelCount() * GetFrameLen(), interleveData_.data(), inputAudioBuffer_.GetPcmDataBuffer());
    AudioPipeType  pipeType = ConvertDeviceClassToPipe(GetDeviceClass());
    if (ret != 0) {
        if (pipeType != PIPE_TYPE_UNKNOWN) {
            AudioPerformanceMonitor::GetInstance().RecordSilenceState(GetSessionId(), true, pipeType,
                static_cast<uint32_t>(appUid_));
        }
        Trace underflowTrace("[" + std::to_string(GetSessionId()) + "]HpaeSinkInputNode::DoProcess underflow");
        memset_s(inputAudioBuffer_.GetPcmDataBuffer(), inputAudioBuffer_.Size(), 0, inputAudioBuffer_.Size());
    } else {
        if (pipeType != PIPE_TYPE_UNKNOWN) {
            AudioPerformanceMonitor::GetInstance().RecordSilenceState(GetSessionId(), false, pipeType,
                static_cast<uint32_t>(appUid_));
        }
        totalFrames_ += GetFrameLen();
        if (historyBuffer_) {
            historyBuffer_->StoreFrameData(inputAudioBuffer_);
        }
    }
    outputStream_.WriteDataToOutput(&inputAudioBuffer_);
}

bool HpaeSinkInputNode::Reset()
{
    return true;
}

bool HpaeSinkInputNode::ResetAll()
{
    return true;
}

std::shared_ptr<HpaeNode> HpaeSinkInputNode::GetSharedInstance()
{
    return shared_from_this();
}

OutputPort<HpaePcmBuffer *> *HpaeSinkInputNode::GetOutputPort()
{
    return &outputStream_;
}

bool HpaeSinkInputNode::RegisterWriteCallback(const std::weak_ptr<IStreamCallback> &callback)
{
    writeCallback_ = callback;
    OnStreamInfoChange(false);
    return true;
}
// reset historyBuffer
void HpaeSinkInputNode::Flush()
{
    if (GetNodeInfo().historyFrameCount == 0) {
        historyBuffer_ = nullptr;
    } else if (historyBuffer_ && historyBuffer_->GetFrames() == GetNodeInfo().historyFrameCount) {
        historyBuffer_->Reset();
    } else {
        HpaeNodeInfo nodeInfo = GetNodeInfo();
        PcmBufferInfo pcmInfo = PcmBufferInfo{
            nodeInfo.channels, nodeInfo.frameLen, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
            nodeInfo.customSampleRate, nodeInfo.channelLayout, nodeInfo.historyFrameCount};
        pcmInfo.isMultiFrames = true;
        historyBuffer_ = std::make_unique<HpaePcmBuffer>(pcmInfo);
    }
}

bool HpaeSinkInputNode::Drain()
{
    isDrain_ = true;
    return true;
}

int32_t HpaeSinkInputNode::SetState(HpaeSessionState renderState)
{
    HILOG_COMM_INFO("[SetState]Sink[%{public}s]->Session[%{public}u - %{public}d] state change:"
        "[%{public}s]-->[%{public}s]", GetDeviceClass().c_str(), GetSessionId(), GetStreamType(),
        ConvertSessionState2Str(state_).c_str(), ConvertSessionState2Str(renderState).c_str());
    state_ = renderState;
    return SUCCESS;
}

HpaeSessionState HpaeSinkInputNode::GetState()
{
    return state_;
}

void HpaeSinkInputNode::SetAppUid(int32_t appUid)
{
    appUid_ = appUid;
}

int32_t HpaeSinkInputNode::GetAppUid()
{
    return appUid_;
}

bool HpaeSinkInputNode::GetKeepRunning()
{
    return GetNodeInfo().keepRunning;
}

void HpaeSinkInputNode::SetIsLowLatency(bool isLowLatency)
{
    isLowLatency_ = isLowLatency;
}

bool HpaeSinkInputNode::GetIsLowLatency()
{
    return isLowLatency_;
}

void HpaeSinkInputNode::RewindHistoryBuffer(uint64_t rewindTime, uint64_t hdiFramePosition)
{
    CHECK_AND_RETURN_LOG(historyBuffer_, "historyBuffer_ is nullptr");
    hdiFramePosition_.store(hdiFramePosition);
    AUDIO_INFO_LOG("rewind %{public}zu frames", ConvertUsToFrameCount(rewindTime, GetNodeInfo()));
    rewindTime_.store(rewindTime);
    historyBuffer_->RewindBuffer(ConvertUsToFrameCount(rewindTime, GetNodeInfo()));
    OnStreamInfoChange(false);
}

void HpaeSinkInputNode::EnsureHistoryBufferForAiss(uint32_t preheatFrames)
{
    if (offloadEnable_) return;  // Offload already has sufficient buffer
    if (historyBuffer_ && historyBuffer_->GetFrames() >= preheatFrames) return;
    HpaeNodeInfo nodeInfo = GetNodeInfo();
    PcmBufferInfo pcmInfo = PcmBufferInfo{
        nodeInfo.channels, nodeInfo.frameLen,
        nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate : nodeInfo.customSampleRate,
        nodeInfo.channelLayout, preheatFrames};
    pcmInfo.isMultiFrames = true;
    historyBuffer_ = std::make_unique<HpaePcmBuffer>(pcmInfo);
    AUDIO_INFO_LOG("AISS: historyBuffer allocated for %{public}u frames", preheatFrames);
}

void HpaeSinkInputNode::NotifyOffloadHdiPos(const std::pair<uint64_t, TimePoint> &hdiPos)
{
    auto writeCallback = writeCallback_.lock();
    CHECK_AND_RETURN_LOG(writeCallback, "writeCallback is null, Id: %{public}d fatal err", GetSessionId());
    writeCallback->OnNotifyHdiData(hdiPos);
}

void HpaeSinkInputNode::TriggerClientWake()
{
    auto streamCallback = writeCallback_.lock();
    if (streamCallback) {
        streamCallback->TriggerClientWake();
    }
}

void HpaeSinkInputNode::SetOffloadEnabled(bool offloadEnable)
{
    offloadEnable_ = offloadEnable;
}

bool HpaeSinkInputNode::GetOffloadEnabled()
{
    return offloadEnable_;
}

void HpaeSinkInputNode::SetOffloadType(int32_t offloadType)
{
    offloadType_ = offloadType;
}

int32_t HpaeSinkInputNode::GetOffloadType()
{
    return offloadType_;
}

void HpaeSinkInputNode::SetDirect(bool isDirect)
{
    isDirect_ = isDirect;
}

bool HpaeSinkInputNode::GetDirect() const noexcept
{
    return isDirect_;
}

bool HpaeSinkInputNode::GetIsNonStandardSampleRate() const
{
    return isNonStandardSampleRate_;
}

void HpaeSinkInputNode::SetNodeInfo(HpaeNodeInfo& nodeInfo)
{
    // If frameLen changed, reset pcm bufer
    if (nodeInfo.frameLen != pcmBufferInfo_.frameLen) {
        AUDIO_INFO_LOG("reste pcm buffer: old len %{public}u, new len %{public}u",
            pcmBufferInfo_.frameLen, nodeInfo.frameLen);
        pcmBufferInfo_.frameLen = nodeInfo.frameLen;
        inputAudioBuffer_.ReConfig(pcmBufferInfo_);
        interleveData_.resize(nodeInfo.frameLen * nodeInfo.channels * GetSizeFromFormat(nodeInfo.format));

        if (nodeInfo.historyFrameCount > 0) {
            PcmBufferInfo pcmInfo = PcmBufferInfo{
                nodeInfo.channels, nodeInfo.frameLen, nodeInfo.customSampleRate == 0 ? nodeInfo.samplingRate :
                nodeInfo.customSampleRate, nodeInfo.channelLayout, nodeInfo.historyFrameCount};
            pcmInfo.isMultiFrames = true;
            historyBuffer_ = std::make_unique<HpaePcmBuffer>(pcmInfo);
            AUDIO_INFO_LOG("historybuffer re-created for new frameLen");
        } else {
            historyBuffer_ = nullptr;
        }
    }
    HpaeNode::SetNodeInfo(nodeInfo);
    isNonStandardSampleRate_ = IsNonStandardSampleRate(nodeInfo.GetEffectiveSampleRate());
}

int32_t HpaeSinkInputNode::SetLoudnessGain(float loudnessGain)
{
    loudnessGain_ = loudnessGain;
    return SUCCESS;
}

float HpaeSinkInputNode::GetLoudnessGain()
{
    return loudnessGain_;
}

void HpaeSinkInputNode::SetSpeed(float speed)
{
    speed_ = speed;
}

float HpaeSinkInputNode::GetSpeed()
{
    return speed_;
}

uint64_t HpaeSinkInputNode::GetLatency()
{
    uint64_t samples = historyBuffer_ ? historyBuffer_->GetCurFrames() * GetFrameLen() : 0;
    return samples * AUDIO_US_PER_SECOND / GetSampleRate();
}

int32_t HpaeSinkInputNode::OnStreamInfoChange(bool isPullData)
{
    auto writeCallback = writeCallback_.lock();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(writeCallback, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "writeCallback is null, fatal err", false),
        "writeCallback is null, Id: %{public}d fatal err", GetSessionId());
    bool needData = !(historyBuffer_ && historyBuffer_->GetCurFrames()) && isPullData;
    // offload / direct / non-standard sample rate / SE preheating: never force data
    bool forceData = (offloadEnable_ || isDirect_ || isNonStandardSampleRate_
                      || sessionEffectPreheatActive_) ? false : true;
    uint64_t latency = 0;
    OffloadCallbackData callbackData;
    auto nodeCallback = GetNodeStatusCallback().lock();
    if (nodeCallback) {
        nodeCallback->OnRequestLatency(GetSessionId(), latency);
        callbackData = nodeCallback->GetOffloadCallbackData();
    }
    latency += GetLatency();
    streamInfo_ = {
        .framePosition = totalFrames_,
        .hdiFramePosition = hdiFramePosition_.exchange(0),
        .rewindTime = rewindTime_.exchange(0),
        .framesWritten = totalFrames_,
        .latency = latency,
        .inputData = interleveData_.data(),
        .requestDataLen = interleveData_.size(),
        .deviceClass = GetDeviceClass(),
        .deviceNetId = GetDeviceNetId(),
        .needData = needData,
        .forceData = forceData,
        .writePos_ = callbackData.writePos_,
        .isWriteFirst_ = callbackData.isFlush_,
        .isLowLatency = isLowLatency_
    };
    ClockTime::GetAllTimeStamp(streamInfo_.timestamp);
    return writeCallback->OnStreamData(streamInfo_);
}

bool HpaeSinkInputNode::QueryUnderrun()
{
    auto writeCallback = writeCallback_.lock();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(writeCallback, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "writeCallback is null, fatal err", false),
        "writeCallback is null, Id: %{public}d fatal err", GetSessionId());
    return writeCallback->OnQueryUnderrun();
}

bool HpaeSinkInputNode::IsDrain()
{
    return isDrain_;
}

void HpaeSinkInputNode::SetSessionEffectAttachState(const SessionEffectAttachState &state)
{
    sessionEffectAttachState_ = state;
}

void HpaeSinkInputNode::ClearSessionEffectAttachState()
{
    sessionEffectAttachState_.reset();
}

bool HpaeSinkInputNode::HasSessionEffectAttachState() const
{
    return sessionEffectAttachState_.has_value();
}

std::optional<SessionEffectAttachState> HpaeSinkInputNode::GetSessionEffectAttachState() const
{
    return sessionEffectAttachState_;
}

}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
