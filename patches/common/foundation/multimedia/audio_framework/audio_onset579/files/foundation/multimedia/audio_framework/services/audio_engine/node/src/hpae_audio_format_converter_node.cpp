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
#define LOG_TAG "HpaeAudioFormatConverterNode"
#endif

#include "hpae_audio_format_converter_node.h"
#include "audio_utils.h"
#include <cinttypes>
#include <limits>
#include <cmath>
#include "audio_effect_log.h"
#include "hpae_node_common.h"
#include "stream_dfx_manager.h"
#include "securec.h"
namespace OHOS {
namespace AudioStandard {
namespace HPAE {
namespace {
constexpr uint32_t REASAMPLE_QUAILTY = 1;
constexpr uint32_t MAX_INPUT_FRAMES = SAMPLE_RATE_384000 * 10; // same bound as ProResampler
constexpr uint32_t CUSTOM_SAMPLE_RATE_MULTIPLES = 50;
constexpr uint32_t SAMPLE_RATE_11025 = 11025;
constexpr uint32_t FRAME_LEN_40MS = 40;
constexpr uint32_t FRAME_LEN_100MS = 100;
constexpr uint32_t UNPROCESSED_BUFFER_CAPACITY_MULTIPLIER = 2;
constexpr uint32_t PROCESSED_BUFFER_CAPACITY_MULTIPLIER = 2;
constexpr uint32_t PROCESSED_BUFFER_COMPACTION_DIVISOR = 2;
}
HpaeAudioFormatConverterNode::HpaeAudioFormatConverterNode(HpaeNodeInfo preNodeInfo, HpaeNodeInfo nodeInfo)
    : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
    pcmBufferInfo_(nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate, nodeInfo.channelLayout),
    converterOutput_(pcmBufferInfo_), preNodeInfo_(preNodeInfo), tmpOutBuf_(pcmBufferInfo_)
{
    int32_t enableNewRoute = 0;
    GetSysPara("persist.multimedia.audio.enable_new_route", enableNewRoute);
    frameLenInMs_ = enableNewRoute != 1 ?
        static_cast<float>(nodeInfo.frameLen * MILLISECOND_PER_SECOND) / static_cast<float>(nodeInfo.samplingRate) :
        static_cast<float>(FRAME_LEN_20MS);
    converterOutput_.SetSplitStreamType(preNodeInfo.GetSplitStreamType());
    // use ProResamppler as default
    resampler_ = std::make_unique<ProResampler>(preNodeInfo.customSampleRate == 0 ? preNodeInfo.samplingRate :
        preNodeInfo.customSampleRate, nodeInfo.samplingRate,
        std::min(preNodeInfo.channels, nodeInfo.channels), REASAMPLE_QUAILTY);

    UpdateTmpOutPcmBufferInfo(pcmBufferInfo_);
    
    AudioChannelInfo inChannelInfo = {
        .channelLayout = preNodeInfo.channelLayout,
        .numChannels = preNodeInfo.channels,
    };
    AudioChannelInfo outChannelInfo = {
        .channelLayout = nodeInfo.channelLayout,
        .numChannels = nodeInfo.channels,
    };

    // for now, work at float32le by default
    channelConverter_.SetParam(inChannelInfo, outChannelInfo, SAMPLE_F32LE, true);
    InitDualBuffer();
    AUDIO_INFO_LOG("node id %{public}d, sessionid %{public}d, "
        "input: bitformat %{public}d, frameLen %{public}d, sample rate %{public}d, channels %{public}d,"
        "channelLayout %{public}" PRIu64 ", output: bitformat %{public}d, frameLen %{public}d, sample rate %{public}d,"
        "channels %{public}d, channelLayout %{public}" PRIu64 "", GetNodeId(), GetSessionId(),
        preNodeInfo.format, preNodeInfo.frameLen, preNodeInfo.customSampleRate == 0 ? preNodeInfo.samplingRate :
        preNodeInfo.customSampleRate, inChannelInfo.numChannels,
        inChannelInfo.channelLayout, nodeInfo.format, nodeInfo.frameLen, nodeInfo.samplingRate,
        outChannelInfo.numChannels, outChannelInfo.channelLayout);

#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeAudioFormatConverterNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeAudioFormatConverterNode::~HpaeAudioFormatConverterNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

void HpaeAudioFormatConverterNode::RegisterCallback(INodeFormatInfoCallback *callback)
{
    nodeFormatInfoCallback_ = callback;
}

void HpaeAudioFormatConverterNode::DoProcess()
{
    auto rate = "rate[" + std::to_string(GetSampleRate()) + "]_";
    auto ch = "ch[" + std::to_string(GetChannelCount()) + "]_";
    auto len = "len[" + std::to_string(GetFrameLen()) + "]";
    Trace trace("[" + std::to_string(GetSessionId()) + "]HpaeAudioFormatConverterNode::DoProcess "
        + rate + ch + len);
    if (resamplerFailed_ || resampler_ == nullptr) {
        outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
        return;
    }
    // PullOutputData consumes the next block and exposes no size/peek contract.
    // Drain cached work first, without guessing the next input's frame count.
    if (enableProcess_) {
        ProcessResampleLoop();
        if (resamplerFailed_) {
            outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
            return;
        }
        if (processedFrames_ >= outputFrameLen20ms_) {
            converterOutput_.Reset();
            if (ExtractOutputFromProcessedBuffer()) {
                converterOutput_.SetBufferState(bufferedState_);
                outputStream_.WriteDataToOutput(&converterOutput_);
            } else {
                outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
            }
            return;
        }
        if (unprocessedFrames_ >= resamplerInputThreshold_) {
            // A blocked output queue must not cause another consuming upstream pull.
            outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
            return;
        }
    }
    std::vector<HpaePcmBuffer *> &preOutputs = inputStream_.ReadPreOutputData();
    bool hasPreOutput = !preOutputs.empty() && preOutputs[0] != nullptr;
    bool hasValidInput = hasPreOutput && preOutputs[0]->IsValid();
    AUDIO_DEBUG_LOG("NodeId %{public}d: hasValidInput=%{public}d, enableProcess=%{public}d, "
        "processedFrames=%{public}u, outputFrameLen20ms=%{public}u, unprocessedFrames=%{public}u, "
        "credit=%{public}u/%{public}u, threshold=%{public}u",
        GetNodeId(), hasValidInput, enableProcess_, processedFrames_, outputFrameLen20ms_,
        unprocessedFrames_, pullAheadCredit_, pullAheadMaxCredit_, resamplerInputThreshold_);
    if (resampler_ == nullptr) {
        AUDIO_ERR_LOG("NodeId %{public}d resampler_ is nullptr", GetNodeId());
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::GENERAL,
                BusinessScenario::QUERY, ERR_NULL_POINTER), "resampler_ is nullptr", false);
        outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
        return;
    }
    if (hasPreOutput) {
        // make sure size of silenceData_, tmpOutput_, and ConverterOutput_ is correct
        CheckAndUpdateInfo(preOutputs[0]);
        if (resamplerFailed_) {
            outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
            return;
        }
    }
    if (hasValidInput && enableProcess_) {
        HpaePcmBuffer *tempOut = SignalProcess(preOutputs);
        outputStream_.WriteDataToOutput(tempOut);
        return;
    }
    // drain processedBuffer_ with buffer state propagation
    if (processedFrames_ >= outputFrameLen20ms_ && enableProcess_) {
        converterOutput_.Reset();
        if (ExtractOutputFromProcessedBuffer()) {
            converterOutput_.SetBufferState(bufferedState_);
            AUDIO_DEBUG_LOG("NodeId %{public}d: drain processedBuffer_, "
                "remaining %{public}u frames", GetNodeId(), processedFrames_);
            outputStream_.WriteDataToOutput(&converterOutput_);
            return;
        }
    }
    AUDIO_DEBUG_LOG("NodeId %{public}d: output silence, "
        "hasValidInput=%{public}d, enableProcess=%{public}d, processedFrames=%{public}u",
        GetNodeId(), hasValidInput, enableProcess_, processedFrames_);
    outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
}

void HpaeAudioFormatConverterNode::AccumulateInputAndPullAhead(HpaePcmBuffer *input)
{
    float *srcData = input->GetPcmDataBuffer();
    uint32_t inputFrameLen = input->GetFrameLen();
    uint32_t inputChannels = input->GetChannelCount();
    if (inputChannels != channelConverter_.GetInChannelInfo().numChannels ||
        !CanAcceptInputFrames(inputFrameLen, inputChannels) ||
        static_cast<uint64_t>(inputFrameLen) * inputChannels * sizeof(float) > input->Size()) {
        resamplerFailed_ = true;
        return;
    }

    // Step 1: Append input data to unprocessedBuffer_
    if (!AppendToUnprocessedBuffer(srcData, inputFrameLen, inputChannels)) {
        resamplerFailed_ = true;
        return;
    }
    unprocessedOrigins579_.Append(input->Origins579(), unprocessedFrames_ - input->GetFrameLen());
    bufferedState_ = input->GetBufferState();

    // Step 1b: Pull-Ahead -- if not enough data accumulated and credit available, actively pull from upstream
    AudioChannelInfo inChannelInfo = channelConverter_.GetInChannelInfo();
    AudioChannelInfo outChannelInfo = channelConverter_.GetOutChannelInfo();
    bool needsAccumulation = (resampler_->GetInRate() != resampler_->GetOutRate());
    AUDIO_DEBUG_LOG("NodeId %{public}d: inRate=%{public}u->outRate=%{public}u, "
        "inCh=%{public}u->outCh=%{public}u, inputFrameLen=%{public}u, unprocessedFrames=%{public}u, "
        "threshold=%{public}u, credit=%{public}u/%{public}u, needsAccumulation=%{public}d",
        GetNodeId(), resampler_->GetInRate(), resampler_->GetOutRate(),
        inChannelInfo.numChannels, outChannelInfo.numChannels, inputFrameLen,
        unprocessedFrames_, resamplerInputThreshold_, pullAheadCredit_, pullAheadMaxCredit_,
        needsAccumulation);
    if (resampler_ != nullptr && pullAheadCredit_ > 0 &&
        unprocessedFrames_ < resamplerInputThreshold_ && needsAccumulation) {
        PullAheadUntilThresholdOrFailure(inputFrameLen);
    }

    // If credit exhausted and no output available, pull one more uncredited frame
    // to prevent deadlock where neither pull nor output can make progress
    if ((pullAheadCredit_ == 0) && (unprocessedFrames_ < resamplerInputThreshold_) && (processedFrames_ == 0)) {
        TryPullOneFrame();
    }
}

HpaePcmBuffer* HpaeAudioFormatConverterNode::ProcessAndExtractOutput(HpaePcmBuffer *input)
{
    // Step 2: Conditionally resample -- drain unprocessedBuffer_ into processedBuffer_
    ProcessResampleLoop();
    if (resamplerFailed_) {
        return PrepareSilenceBuffer(silenceData_);
    }

    // Step 3: Extract 20ms output from processedBuffer_ into converterOutput_
    converterOutput_.Reset();
    if (!ExtractOutputFromProcessedBuffer()) {
        AUDIO_DEBUG_LOG("NodeId %{public}d: insufficient output, "
            "processedFrames=%{public}u < outputFrameLen20ms=%{public}u, returning silence",
            GetNodeId(), processedFrames_, outputFrameLen20ms_);
        return PrepareSilenceBuffer(silenceData_);
    }

    AUDIO_DEBUG_LOG("NodeId %{public}d: output success, "
        "extracted %{public}u frames, remaining processedFrames=%{public}u",
        GetNodeId(), outputFrameLen20ms_, processedFrames_);

#ifdef ENABLE_HOOK_PCM
    if (outputPcmDumper_ != nullptr) {
        outputPcmDumper_->CheckAndReopenHandle();
        outputPcmDumper_->Dump((int8_t *)converterOutput_.GetPcmDataBuffer(),
            converterOutput_.GetFrameLen() * sizeof(float) * channelConverter_.GetOutChannelInfo().numChannels);
    }
#endif
    converterOutput_.SetBufferState(bufferedState_);
    return &converterOutput_;
}

HpaePcmBuffer *HpaeAudioFormatConverterNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    if (inputs.size() != 1) {
        AUDIO_WARNING_LOG("error inputs size is not eqaul to 1, SessionId:%{public}d", GetSessionId());
    }
#ifdef ENABLE_HOOK_PCM
    if (!outputPcmDumper_) {
        outputPcmDumper_ = std::make_unique<HpaePcmDumper>(
            "HpaeConverterNodeOutput_id_" + std::to_string(GetSessionId()) + "_nodeId_" + std::to_string(GetNodeId()) +
            "_ch_" + std::to_string(GetChannelCount()) +
            "_rate_" + std::to_string(GetSampleRate()) + "_" + GetTime() + ".pcm");
    }
#endif

    if (resamplerFailed_) {
        return PrepareSilenceBuffer(silenceData_);
    }
    AccumulateInputAndPullAhead(inputs[0]);
    return ProcessAndExtractOutput(inputs[0]);
}

bool HpaeAudioFormatConverterNode::UpdateOutChannelInfo(uint32_t numChannels, AudioChannelLayout channelLayout)
{
    AudioChannelInfo curOutChannelInfo = channelConverter_.GetOutChannelInfo();
    AudioChannelInfo newOutChannelInfo = {
        .channelLayout = (AudioChannelLayout)channelLayout,
        .numChannels = numChannels,
    };
    HILOG_COMM_INFO("[CheckUpdateOutInfo]NodeId %{public}d, update out channels and channelLayout: "
        "channels %{public}d -> %{public}d", GetNodeId(), curOutChannelInfo.numChannels, numChannels);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(channelConverter_.SetOutChannelInfo(newOutChannelInfo) == MIX_ERR_SUCCESS, false,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::GENERAL, BusinessScenario::SEND_DATA,
                ERR_ILLEGAL_STATE), "Fail to set output channel info", false),
        "NodeId: %{public}d, Fail to set output channel info from effectNode!", GetNodeId());
    uint32_t resampleChannels = std::min(channelConverter_.GetInChannelInfo().numChannels, numChannels);
    if (resampleChannels != resampler_->GetChannels()) {
        AUDIO_INFO_LOG("NodeId: %{public}d, Update resampler work channel from effectNode!", GetNodeId());
        if (resampler_->UpdateChannels(resampleChannels) != EOK) {
            resamplerFailed_ = true;
            return false;
        }
    }
    return true;
}

// return true if output info is updated
bool HpaeAudioFormatConverterNode::CheckUpdateOutInfo()
{
    if (nodeFormatInfoCallback_ == nullptr) {
        return false;
    }

    AudioBasicFormat basicFormat;
    basicFormat.rate = preNodeInfo_.samplingRate;

    // if there exists an effect node, converter node output is common input of loudness node and effectnode
    // Must check loudness node input before effectnode
    nodeFormatInfoCallback_->GetNodeInputFormatInfo(preNodeInfo_.sessionId, basicFormat);

    uint32_t numChannels = basicFormat.audioChannelInfo.numChannels;
    AudioChannelLayout channelLayout = basicFormat.audioChannelInfo.channelLayout;
    AudioSamplingRate sampleRate = basicFormat.rate;
    if (numChannels == 0) {
        // set to node info, which is device output info
        AUDIO_WARNING_LOG("Fail to check format info from down stream nodes");
        numChannels = GetChannelCount();
        channelLayout = GetChannelLayout();
        sampleRate = GetSampleRate();
    }

    AudioChannelInfo curOutChannelInfo = channelConverter_.GetOutChannelInfo();
    if ((curOutChannelInfo.numChannels == numChannels) && (curOutChannelInfo.channelLayout == channelLayout) &&
        (sampleRate == resampler_->GetOutRate())) {
        return false;
    }
    // update channel info
    if (curOutChannelInfo.numChannels != numChannels || curOutChannelInfo.channelLayout != channelLayout) {
        if (!UpdateOutChannelInfo(numChannels, channelLayout)) {
            return false;
        }
    }
    // update sample rate
    uint32_t oldOutRate = resampler_->GetOutRate();
    if (oldOutRate != sampleRate) {
        HILOG_COMM_INFO("[CheckUpdateOutInfo]NodeId: %{public}d, update output sample rate: "
            "%{public}d -> %{public}d", GetNodeId(), oldOutRate, sampleRate);
        if (resampler_->UpdateRates(resampler_->GetInRate(), sampleRate) != EOK) {
            resamplerFailed_ = true;
            return false;
        }
    }

    HpaeNodeInfo nodeInfo = GetNodeInfo();
    nodeInfo.channels = (AudioChannel)numChannels;
    nodeInfo.channelLayout = (AudioChannelLayout)channelLayout;
    uint32_t newOutRate = resampler_->GetOutRate();
    nodeInfo.samplingRate = (AudioSamplingRate)newOutRate;
    // Proportionally update frameLen when output rate changes to preserve time duration
    if (oldOutRate != 0 && oldOutRate != newOutRate) {
        nodeInfo.frameLen = static_cast<uint32_t>(
            static_cast<uint64_t>(nodeInfo.frameLen) * newOutRate / oldOutRate);
    }
    SetNodeInfo(nodeInfo);
    return true;
}

// update channel info from processCluster. For now sample rate will not change
bool HpaeAudioFormatConverterNode::CheckUpdateInInfo(HpaePcmBuffer *input)
{
    uint32_t numChannels = input->GetChannelCount();
    uint64_t channelLayout = input->GetChannelLayout();
    uint32_t sampleRate = input->GetSampleRate();
    AudioChannelInfo curInChannelInfo = channelConverter_.GetInChannelInfo();
    bool isInfoUpdated = false;
    // update channels and channelLayout
    if ((curInChannelInfo.numChannels != numChannels) || (curInChannelInfo.channelLayout != channelLayout)) {
        HILOG_COMM_INFO("[CheckUpdateInInfo]NodeId %{public}d: Update innput channel info from pcmBufferInfo, "
            "channels: %{public}d -> %{public}d, channellayout: %{public}" PRIu64 " -> %{public}" PRIu64 ".",
            GetNodeId(), curInChannelInfo.numChannels, numChannels, curInChannelInfo.channelLayout, channelLayout);

        AudioChannelInfo newInChannelInfo = {
            .channelLayout = (AudioChannelLayout)channelLayout,
            .numChannels = numChannels,
        };
        if (channelConverter_.SetInChannelInfo(newInChannelInfo) != MIX_ERR_SUCCESS) {
            resamplerFailed_ = true;
            return false;
        }
        preNodeInfo_.channelLayout = (AudioChannelLayout)channelLayout;
        preNodeInfo_.channels = (AudioChannel)numChannels;

        uint32_t resampleChannels = std::min(numChannels, channelConverter_.GetOutChannelInfo().numChannels);
        if (resampleChannels != resampler_->GetChannels()) {
            AUDIO_INFO_LOG("NodeId %{public}d: Update resampler work channel from effectNode!", GetNodeId());
            if (resampler_->UpdateChannels(resampleChannels) != EOK) {
            resamplerFailed_ = true;
            return false;
        }
        }
        isInfoUpdated = true;
    }
    // update sample rate
    if (sampleRate != resampler_->GetInRate()) {
        HILOG_COMM_INFO("[CheckUpdateInInfo]NodeId %{public}d: Update resampler input sample rate: "
            "%{public}d -> %{public}d", GetNodeId(), resampler_->GetInRate(), sampleRate);
        preNodeInfo_.samplingRate = (AudioSamplingRate)sampleRate;
        preNodeInfo_.frameLen = CalculateFrameLenBySampleRate(sampleRate);
        if (resampler_->UpdateRates(sampleRate, resampler_->GetOutRate()) != EOK) {
            resamplerFailed_ = true;
            return false;
        }
        isInfoUpdated = true;
    }
    return isInfoUpdated;
}

void HpaeAudioFormatConverterNode::UpdateTmpOutPcmBufferInfo(const PcmBufferInfo &outPcmBufferInfo)
{
    if (outPcmBufferInfo.ch == preNodeInfo_.channels || outPcmBufferInfo.rate == resampler_->GetInRate()) {
        // do not need tmpOutput Buffer
        return;
    }
    PcmBufferInfo tmpOutPcmBufferInfo = outPcmBufferInfo;
    if (outPcmBufferInfo.ch < preNodeInfo_.channels) { // downmix, then resample
        tmpOutPcmBufferInfo.rate = resampler_->GetInRate();
        tmpOutPcmBufferInfo.frameLen = preNodeInfo_.frameLen;
    } else { // resample, then upmix
        tmpOutPcmBufferInfo.ch = preNodeInfo_.channels;
    }
    AUDIO_INFO_LOG("NodeId: %{public}d, updated tmp buffer rate %{public}d, frameLen %{public}d, channels %{public}d",
        GetNodeId(), tmpOutPcmBufferInfo.rate, tmpOutPcmBufferInfo.frameLen, tmpOutPcmBufferInfo.ch);
    tmpOutBuf_.ReConfig(tmpOutPcmBufferInfo);
}

void HpaeAudioFormatConverterNode::CheckAndUpdateInfo(HpaePcmBuffer *input)
{
    bool isInfoUpdated = CheckUpdateInInfo(input);
    bool isOutInfoUpdated = CheckUpdateOutInfo();
    if (resamplerFailed_ || ((!isInfoUpdated) && (!isOutInfoUpdated))) {
        return;
    }

    AudioChannelInfo outChannelInfo = channelConverter_.GetOutChannelInfo();
    PcmBufferInfo outPcmBufferInfo = pcmBufferInfo_; // isMultiFrames_ and frame_ are inheritated from sinkInputNode
    outPcmBufferInfo.ch = outChannelInfo.numChannels;
    outPcmBufferInfo.rate = resampler_->GetOutRate();
    {
        uint32_t curInRate = resampler_->GetInRate();
        uint32_t curOutRate = resampler_->GetOutRate();
        outPcmBufferInfo.frameLen = (curInRate == curOutRate) ? GetFrameLen() :
            static_cast<uint32_t>(curOutRate * frameLenInMs_ / MILLISECOND_PER_SECOND);
    }
    outPcmBufferInfo.channelLayout = outChannelInfo.channelLayout;

    AUDIO_INFO_LOG("NodeId %{public}d: output or input format info is changed, update tmp PCM buffer info!",
        GetNodeId());
    UpdateTmpOutPcmBufferInfo(outPcmBufferInfo);
    InitDualBuffer();

    if (isOutInfoUpdated) {
        AUDIO_INFO_LOG("NodeId %{public}d: output format info is changed, update output PCM buffer info!", GetNodeId());
        converterOutput_.ReConfig(outPcmBufferInfo);
        silenceData_.ReConfig(outPcmBufferInfo);
        // reconfig need reset valid
        silenceData_.SetBufferValid(false);
        silenceData_.SetBufferSilence(true);
#ifdef ENABLE_HIDUMP_DFX
        if (auto callBack = GetNodeStatusCallback().lock()) {
            callBack->OnNotifyDfxNodeInfoChanged(GetNodeId(), GetNodeInfo());
        }
#endif
// update PCM dumper
#ifdef ENABLE_HOOK_PCM
    outputPcmDumper_ = std::make_unique<HpaePcmDumper>(
        "HpaeConverterNodeOutput_id_" + std::to_string(GetSessionId()) +
        + "_nodeId_" + std::to_string(GetNodeId()) +
        "_ch_" + std::to_string(GetChannelCount()) + "_rate_" +
        std::to_string(GetSampleRate()) + "_" + GetTime() + ".pcm");
#endif
    }
}

void HpaeAudioFormatConverterNode::ReconfigTmpOutForChannelConversion(uint32_t inCh, uint32_t outCh,
    uint32_t maxOutFrames)
{
    PcmBufferInfo tmpOutPcmBufferInfo;
    if (inCh > outCh) {
        // Downmix first, then resample: tmpOutBuf_ holds downmixed input at inRate
        tmpOutPcmBufferInfo.ch = inCh;
        tmpOutPcmBufferInfo.rate = resampler_->GetInRate();
        tmpOutPcmBufferInfo.frameLen = resamplerInputThreshold_;
    } else {
        // Resample first, then upmix: tmpOutBuf_ holds resampled output at outRate
        tmpOutPcmBufferInfo.ch = inCh;
        tmpOutPcmBufferInfo.rate = resampler_->GetOutRate();
        tmpOutPcmBufferInfo.frameLen = maxOutFrames;
    }
    tmpOutPcmBufferInfo.channelLayout = static_cast<uint64_t>(channelConverter_.GetInChannelInfo().channelLayout);
    tmpOutBuf_.ReConfig(tmpOutPcmBufferInfo);
}

void HpaeAudioFormatConverterNode::InitDualBuffer()
{
    unprocessedOrigins579_.Clear();
    processedOrigins579_.Clear();
    if (resampler_ == nullptr) {
        return;
    }
    uint32_t inputChannels = channelConverter_.GetInChannelInfo().numChannels;
    uint32_t outputChannels = channelConverter_.GetOutChannelInfo().numChannels;
    if (resampler_->GetInRate() < SAMPLE_RATE_8000 || resampler_->GetInRate() > SAMPLE_RATE_384000 ||
        resampler_->GetOutRate() < SAMPLE_RATE_8000 || resampler_->GetOutRate() > SAMPLE_RATE_384000 ||
        inputChannels == 0 || inputChannels > 16 || outputChannels == 0 || outputChannels > 16 ||
        !std::isfinite(frameLenInMs_) || frameLenInMs_ <= 0 ||
        static_cast<double>(resampler_->GetInRate()) * frameLenInMs_ / MILLISECOND_PER_SECOND > MAX_INPUT_FRAMES ||
        static_cast<double>(resampler_->GetOutRate()) * frameLenInMs_ / MILLISECOND_PER_SECOND > MAX_INPUT_FRAMES) {
        resamplerFailed_ = true;
        return;
    }
    resamplerInputThreshold_ = CalculateResamplerInputThreshold();
    uint32_t outRate = resampler_->GetOutRate();
    uint32_t inRate = resampler_->GetInRate();
    // Same-rate path (e.g., low-latency 5ms): use node's actual output frameLen to match converterOutput_ buffer
    outputFrameLen20ms_ = (inRate == outRate) ? GetFrameLen() :
        static_cast<uint32_t>(outRate * frameLenInMs_ / MILLISECOND_PER_SECOND);

    uint64_t checkedMaxOut = static_cast<uint64_t>(resamplerInputThreshold_) * outRate / inRate;
    if (resamplerInputThreshold_ == 0 || resamplerInputThreshold_ > MAX_INPUT_FRAMES ||
        outputFrameLen20ms_ == 0 || outputFrameLen20ms_ > MAX_INPUT_FRAMES ||
        checkedMaxOut == 0 || checkedMaxOut > MAX_INPUT_FRAMES) {
        resamplerFailed_ = true;
        return;
    }
    AudioChannelInfo inChannelInfo = channelConverter_.GetInChannelInfo();
    AudioChannelInfo outChannelInfo = channelConverter_.GetOutChannelInfo();
    uint32_t inCh = inChannelInfo.numChannels;
    uint32_t outCh = outChannelInfo.numChannels;

    // unprocessedBuffer_ stores data at inCh per frame
    size_t unprocessedCapacity = static_cast<size_t>(resamplerInputThreshold_) *
        UNPROCESSED_BUFFER_CAPACITY_MULTIPLIER * inCh;
    unprocessedBuffer_.resize(unprocessedCapacity, 0.0f);
    unprocessedFrames_ = 0;
    bufferedState_ = PCM_BUFFER_STATE_INVALID;

    // processedBuffer_ and resamplerOutBuf_ store data at outCh per frame
    uint32_t maxOutFrames = static_cast<uint32_t>(
        static_cast<uint64_t>(resamplerInputThreshold_) * resampler_->GetOutRate() / resampler_->GetInRate());
    size_t processedCapacity = static_cast<size_t>(maxOutFrames) *
        PROCESSED_BUFFER_CAPACITY_MULTIPLIER * outCh;
    processedBuffer_.resize(processedCapacity, 0.0f);
    processedFrames_ = 0;
    processedReadPos_ = 0;

    size_t resamplerOutCapacity = static_cast<size_t>(maxOutFrames) * outCh;
    resamplerOutBuf_.resize(resamplerOutCapacity, 0.0f);

    // Initialize pull-ahead credit: max 20ms output chunks one threshold input produces
    if (outputFrameLen20ms_ > 0) {
        pullAheadMaxCredit_ = maxOutFrames / outputFrameLen20ms_;
    } else {
        pullAheadMaxCredit_ = 0;
    }
    pullAheadCredit_ = pullAheadMaxCredit_;

    // Resize tmpOutBuf_ for channel conversion paths
    if (inCh != outCh) {
        ReconfigTmpOutForChannelConversion(inCh, outCh, maxOutFrames);
    }

    AUDIO_INFO_LOG("NodeId %{public}d: InitDualBuffer threshold=%{public}u, outputFrameLen20ms=%{public}u, "
        "maxOutFrames=%{public}u, outCh=%{public}u, inCh=%{public}u", GetNodeId(), resamplerInputThreshold_,
        outputFrameLen20ms_, maxOutFrames, outCh, inCh);
}

uint32_t HpaeAudioFormatConverterNode::CalculateResamplerInputThreshold() const
{
    if (resampler_ == nullptr) {
        return 0;
    }
    uint32_t inRate = resampler_->GetInRate();
    uint32_t outRate = resampler_->GetOutRate();
    if (inRate == outRate) {
        return static_cast<uint32_t>(inRate * frameLenInMs_ / MILLISECOND_PER_SECOND);
    }
    // Find the minimum span that produces exact output at outRate.
    // This avoids rounding errors in the resampler output.
    // 11025Hz: 441 * 48000 / 11025 = 1920 (exact)
    // 8010Hz:  801 * 48000 / 8010 = 4800 (exact)
    if (inRate == SAMPLE_RATE_11025) {
        return inRate * FRAME_LEN_40MS / MILLISECOND_PER_SECOND; // 441
    } else if (inRate % CUSTOM_SAMPLE_RATE_MULTIPLES != 0) {
        return inRate * FRAME_LEN_100MS / MILLISECOND_PER_SECOND; // e.g., 801 for 8010Hz
    } else {
        return static_cast<uint32_t>(inRate * frameLenInMs_ / MILLISECOND_PER_SECOND); // standard 20ms
    }
}

bool HpaeAudioFormatConverterNode::AppendToUnprocessedBuffer(const float *data, uint32_t frameLen,
    uint32_t channels)
{
    if (resamplerFailed_ || frameLen == 0 || data == nullptr || !CanAcceptInputFrames(frameLen, channels)) {
        return false;
    }
    size_t samplesToAdd = static_cast<size_t>(frameLen) * channels;
    size_t requiredSize = (static_cast<size_t>(unprocessedFrames_) + frameLen) * channels;
    uintptr_t source = reinterpret_cast<uintptr_t>(data);
    uintptr_t storage = reinterpret_cast<uintptr_t>(unprocessedBuffer_.data());
    size_t sourceBytes = samplesToAdd * sizeof(float);
    size_t storageBytes = unprocessedBuffer_.capacity() * sizeof(float);
    if (source > UINTPTR_MAX - sourceBytes || storage > UINTPTR_MAX - storageBytes ||
        (source < storage + storageBytes && storage < source + sourceBytes)) {
        return false; // growth must not invalidate an aliased source
    }
    if (requiredSize > unprocessedBuffer_.max_size()) {
        return false;
    }
    // One actual input block may exceed the initial 2-threshold capacity.
    // Retain the entire block; no further pull occurs until buffered work drains.
    if (unprocessedBuffer_.size() < requiredSize) {
        resamplerFailed_ = true; // also remains latched if allocation unwinds
        unprocessedBuffer_.resize(requiredSize, 0.0f);
        if (unprocessedBuffer_.size() < requiredSize) {
            return false;
        }
        resamplerFailed_ = false; // acquired storage; the copy is still checked below
    }
    if (unprocessedBuffer_.size() < requiredSize) {
        AUDIO_ERR_LOG("NodeId %{public}d: AppendToUnprocessedBuffer buffer overflow, "
            "size=%{public}zu, required=%{public}zu", GetNodeId(), unprocessedBuffer_.size(), requiredSize);
        return false;
    }
    errno_t ret = memcpy_s(unprocessedBuffer_.data() + static_cast<size_t>(unprocessedFrames_) * channels,
        (unprocessedBuffer_.size() - static_cast<size_t>(unprocessedFrames_) * channels) * sizeof(float),
        data, samplesToAdd * sizeof(float));
    if (ret != EOK) {
        AUDIO_ERR_LOG("NodeId %{public}d: AppendToUnprocessedBuffer memcpy_s failed", GetNodeId());
        return false;
    }
    unprocessedFrames_ += frameLen;
    if (pullAheadCredit_ > 0) {
        pullAheadCredit_--;
    }
    AUDIO_DEBUG_LOG("NodeId %{public}d: AppendToUnprocessedBuffer added %{public}u frames @%{public}u ch, "
        "total unprocessedFrames=%{public}u", GetNodeId(), frameLen, channels, unprocessedFrames_);
    return true;
}

bool HpaeAudioFormatConverterNode::AppendToProcessedBuffer(const float *data, uint32_t frameLen, uint32_t channels)
{
    if (data == nullptr || !CanAppendProcessedFrames(frameLen, channels)) {
        return false;
    }
    size_t offset = (static_cast<size_t>(processedReadPos_) + processedFrames_) * channels;
    size_t samples = static_cast<size_t>(frameLen) * channels;
    if (samples != 0 && memcpy_s(processedBuffer_.data() + offset,
        (processedBuffer_.size() - offset) * sizeof(float), data, samples * sizeof(float)) != EOK) {
        return false;
    }
    if (resampler_ != nullptr && resampler_->GetInRate() == resampler_->GetOutRate()) {
        processedOrigins579_.Append(unprocessedOrigins579_.Slice(0, frameLen), processedFrames_);
    } else {
        // General resampler filter-history ownership is not a 1:1 frame map.
        // Leave the selected route unproven rather than estimate its latency.
        processedOrigins579_.Unknown();
    }
    processedFrames_ += frameLen;
    return true;
}

bool HpaeAudioFormatConverterNode::TryPullOneFrame()
{
    if (resamplerFailed_ || unprocessedFrames_ >= resamplerInputThreshold_) {
        return false;
    }
    auto &newInputs = inputStream_.ReadPreOutputData();
    if (newInputs.empty() || newInputs[0] == nullptr || !newInputs[0]->IsValid()) {
        return false;
    }
    HpaePcmBuffer *input = newInputs[0];
    uint32_t frames = input->GetFrameLen();
    uint32_t channels = input->GetChannelCount();
    if (channels != channelConverter_.GetInChannelInfo().numChannels ||
        input->GetSampleRate() != resampler_->GetInRate() ||
        !CanAcceptInputFrames(frames, channels) ||
        static_cast<uint64_t>(frames) * channels * sizeof(float) > input->Size() ||
        !AppendToUnprocessedBuffer(input->GetPcmDataBuffer(), frames, channels)) {
        resamplerFailed_ = true;
        return false;
    }
    unprocessedOrigins579_.Append(input->Origins579(), unprocessedFrames_ - input->GetFrameLen());
    bufferedState_ = input->GetBufferState();
    return true;
}

void HpaeAudioFormatConverterNode::PullAheadUntilThresholdOrFailure(uint32_t inputFrameLen)
{
    if (inputFrameLen == 0 || pullAheadCredit_ == 0) {
        return;
    }

    uint32_t pullCount = 0;

    AUDIO_DEBUG_LOG("NodeId %{public}d: PullAhead start, unprocessedFrames=%{public}u, threshold=%{public}u, "
        "credit=%{public}u", GetNodeId(), unprocessedFrames_, resamplerInputThreshold_, pullAheadCredit_);

    while (pullAheadCredit_ > 0 && unprocessedFrames_ < resamplerInputThreshold_) {
        if (!TryPullOneFrame()) {
            AUDIO_DEBUG_LOG("NodeId %{public}d: PullAhead stopped, upstream underflow after %{public}u pulls",
                GetNodeId(), pullCount);
            break;
        }
        pullCount++;
    }

    if (pullCount > 0) {
        AUDIO_DEBUG_LOG("NodeId %{public}d: PullAhead pulled %{public}u extra frames, "
            "unprocessedFrames=%{public}u, remaining credit=%{public}u",
            GetNodeId(), pullCount, unprocessedFrames_, pullAheadCredit_);
    }
}

bool HpaeAudioFormatConverterNode::CanAppendProcessedFrames(uint32_t frames, uint32_t channels)
{
    if (channels == 0 || channels > 16 || processedFrames_ > UINT32_MAX - frames) {
        resamplerFailed_ = true;
        return false;
    }
    uint64_t endFrames = static_cast<uint64_t>(processedReadPos_) + processedFrames_ + frames;
    if (endFrames > processedBuffer_.size() / channels && processedReadPos_ != 0) {
        if (!CompactProcessedBuffer(channels)) {
            resamplerFailed_ = true;
            return false;
        }
        endFrames = static_cast<uint64_t>(processedFrames_) + frames;
    }
    return endFrames <= processedBuffer_.size() / channels;
}

bool HpaeAudioFormatConverterNode::CanAcceptInputFrames(uint32_t frames, uint32_t channels) const
{
    return channels != 0 && channels <= 16 && frames <= MAX_INPUT_FRAMES &&
        resamplerInputThreshold_ != 0 &&
        static_cast<uint64_t>(unprocessedFrames_) + frames <=
        static_cast<uint64_t>(MAX_INPUT_FRAMES) + resamplerInputThreshold_ &&
        frames <= UINT32_MAX - unprocessedFrames_ &&
        static_cast<uint64_t>(unprocessedFrames_) + frames <=
        std::numeric_limits<size_t>::max() / channels / sizeof(float);
}


void HpaeAudioFormatConverterNode::ProcessSameRateChannelConversion(uint32_t inCh, uint32_t outCh)
{
    if (resamplerFailed_ || resamplerInputThreshold_ == 0 || inCh == 0 || inCh > 16 || outCh == 0 || outCh > 16) {
        resamplerFailed_ = true;
        return;
    }
    while (unprocessedFrames_ >= resamplerInputThreshold_) {
        uint32_t frames = resamplerInputThreshold_;
        if (!CanAppendProcessedFrames(frames, outCh)) {
            break; // bounded output backpressure, before processing input
        }
        size_t samples = static_cast<size_t>(frames) * outCh;
        if (resamplerOutBuf_.size() < samples) {
            resamplerOutBuf_.resize(samples, 0.0f);
        }
        ProResampler::ProcessResult result;
        int32_t ret = ResampleWithChannelConversion(unprocessedBuffer_.data(), frames,
            resamplerOutBuf_.data(), frames, resampler_->GetChannels(), result);
        if (ret != EOK || !result.valid || result.consumedFrames != frames ||
            !AppendToProcessedBuffer(resamplerOutBuf_.data(), result.outputFrames, outCh) ||
            !RemoveConsumedInputFrames(result.consumedFrames, inCh)) {
            resamplerFailed_ = true;
            break;
        }
    }
}

void HpaeAudioFormatConverterNode::ProcessDiffRateResample(uint32_t inCh, uint32_t outCh,
    uint32_t inRate, uint32_t outRate)
{
    if (resamplerFailed_ || inRate == 0 || outRate == 0 || resamplerInputThreshold_ == 0 ||
        inCh == 0 || inCh > 16 || outCh == 0 || outCh > 16) {
        resamplerFailed_ = true;
        return;
    }
    while (unprocessedFrames_ >= resamplerInputThreshold_) {
        uint32_t requestedIn = resamplerInputThreshold_;
        uint64_t requestedOut = static_cast<uint64_t>(requestedIn) * outRate / inRate;
        if (requestedOut == 0 || requestedOut > UINT32_MAX) {
            resamplerFailed_ = true;
            break;
        }
        uint32_t outFrames = static_cast<uint32_t>(requestedOut);
        if (!CanAppendProcessedFrames(outFrames, outCh)) {
            break; // no filter state advanced
        }
        if (outFrames > std::numeric_limits<size_t>::max() / outCh / sizeof(float)) {
            resamplerFailed_ = true;
            break;
        }
        size_t samples = static_cast<size_t>(outFrames) * outCh;
        if (resamplerOutBuf_.size() < samples) {
            resamplerOutBuf_.resize(samples, 0.0f);
        }
        ProResampler::ProcessResult result;
        int32_t ret = ResampleWithChannelConversion(unprocessedBuffer_.data(), requestedIn,
            resamplerOutBuf_.data(), outFrames, resampler_->GetChannels(), result);
        if (ret != EOK || !result.valid || result.consumedFrames > requestedIn ||
            result.outputFrames > outFrames || result.producedFrames > result.outputFrames ||
            result.paddingFrames != result.outputFrames - result.producedFrames ||
            (result.consumedFrames == 0 && result.producedFrames == 0)) {
            resamplerFailed_ = true; // unknown progress; never manufacture a padding-only loop
            break;
        }
        if (!AppendToProcessedBuffer(resamplerOutBuf_.data(), result.outputFrames, outCh) ||
            !RemoveConsumedInputFrames(result.consumedFrames, inCh)) {
            resamplerFailed_ = true; // state advanced: do not run this input again
            break;
        }
        if (result.consumedFrames == 0) {
            break; // finite history output without new consumption; no busy loop
        }
    }
}

void HpaeAudioFormatConverterNode::ProcessResampleLoop()
{
    if (resampler_ == nullptr || resamplerFailed_) {
        return;
    }

    AudioChannelInfo inChannelInfo = channelConverter_.GetInChannelInfo();
    AudioChannelInfo outChannelInfo = channelConverter_.GetOutChannelInfo();
    uint32_t inCh = inChannelInfo.numChannels;
    uint32_t outCh = outChannelInfo.numChannels;
    uint32_t inRate = resampler_->GetInRate();
    uint32_t outRate = resampler_->GetOutRate();

    AUDIO_DEBUG_LOG("NodeId %{public}d: inRate=%{public}u, outRate=%{public}u, "
        "inCh=%{public}u, outCh=%{public}u, unprocessedFrames=%{public}u, threshold=%{public}u, "
        "processedFrames=%{public}u",
        GetNodeId(), inRate, outRate, inCh, outCh, unprocessedFrames_,
        resamplerInputThreshold_, processedFrames_);

    // Same-rate path: handle channel conversion
    if (inRate == outRate) {
        if (inCh == outCh) {
            // Same rate, same channels -- pure passthrough
            if (unprocessedFrames_ > 0) {
                AUDIO_DEBUG_LOG("NodeId %{public}d: passthrough "
                    "%{public}u frames", GetNodeId(), unprocessedFrames_);
            }
            MoveUnprocessedToProcessed(outCh);  // outCh == inCh here
        } else {
            // Same rate, different channels -- need channel conversion only
            ProcessSameRateChannelConversion(inCh, outCh);
        }
        return;
    }

    // Different rates -- resample (possibly with channel conversion)
    ProcessDiffRateResample(inCh, outCh, inRate, outRate);
}

int32_t HpaeAudioFormatConverterNode::ResampleWithChannelConversion(float *srcData, uint32_t inFrameLen,
    float *dstData, uint32_t outFrameLen, uint32_t resamplerChannels, ProResampler::ProcessResult &result)
{
    result = {};
    uint32_t inCh = channelConverter_.GetInChannelInfo().numChannels;
    uint32_t outCh = channelConverter_.GetOutChannelInfo().numChannels;
    if (srcData == nullptr || dstData == nullptr || inCh == 0 || inCh > 16 || outCh == 0 || outCh > 16 ||
        resamplerChannels != std::min(inCh, outCh) ||
        inFrameLen > std::numeric_limits<size_t>::max() / inCh / sizeof(float) ||
        outFrameLen > std::numeric_limits<size_t>::max() / outCh / sizeof(float)) {
        return RESAMPLER_ERR_INVALID_ARG;
    }
    size_t inBytes = static_cast<size_t>(inFrameLen) * inCh * sizeof(float);
    size_t outBytes = static_cast<size_t>(outFrameLen) * outCh * sizeof(float);
    bool sameRate = resampler_->GetInRate() == resampler_->GetOutRate();
    int32_t ret = EOK;
    if (sameRate) {
        if (inFrameLen != outFrameLen) {
            return RESAMPLER_ERR_INVALID_ARG;
        }
        ret = inCh == outCh ? memcpy_s(dstData, outBytes, srcData, inBytes) :
            channelConverter_.Process(inFrameLen, srcData, inBytes, dstData, outBytes);
        if (ret == EOK) {
            result.consumedFrames = inFrameLen;
            result.producedFrames = outFrameLen;
            result.outputFrames = outFrameLen;
            result.valid = true;
        }
        return ret;
    }
    if (inCh == outCh) {
        return resampler_->ProcessWithCounts(srcData, inFrameLen, dstData, outFrameLen, result);
    }
    if (tmpOutBuf_.GetPcmDataBuffer() == nullptr) {
        return RESAMPLER_ERR_INVALID_ARG;
    }
    if (inCh > outCh) {
        ret = channelConverter_.Process(inFrameLen, srcData, inBytes,
            tmpOutBuf_.GetPcmDataBuffer(), tmpOutBuf_.Size());
        if (ret != EOK) {
            return ret; // never advance the filter with failed channel-conversion data
        }
        return resampler_->ProcessWithCounts(tmpOutBuf_.GetPcmDataBuffer(), inFrameLen,
            dstData, outFrameLen, result);
    }
    size_t tmpBytes = static_cast<size_t>(outFrameLen) * resamplerChannels * sizeof(float);
    if (tmpBytes > tmpOutBuf_.Size()) {
        return RESAMPLER_ERR_OVERFLOW;
    }
    ret = resampler_->ProcessWithCounts(srcData, inFrameLen, tmpOutBuf_.GetPcmDataBuffer(), outFrameLen, result);
    if (ret != EOK) {
        return ret;
    }
    ret = channelConverter_.Process(result.outputFrames, tmpOutBuf_.GetPcmDataBuffer(), tmpOutBuf_.Size(),
        dstData, outBytes);
    if (ret != EOK) {
        result.valid = false; // input may already have been consumed
    }
    return ret;
}

bool HpaeAudioFormatConverterNode::ExtractOutputFromProcessedBuffer()
{
    if (processedFrames_ < outputFrameLen20ms_) {
        AUDIO_DEBUG_LOG("NodeId %{public}d: ExtractOutput insufficient data, have=%{public}u, need=%{public}u",
            GetNodeId(), processedFrames_, outputFrameLen20ms_);
        return false;
    }
    uint32_t channels = converterOutput_.GetChannelCount();
    float *dstData = converterOutput_.GetPcmDataBuffer();
    uint32_t copySamples = outputFrameLen20ms_ * channels;
    errno_t ret = memcpy_s(dstData, converterOutput_.Size(),
        processedBuffer_.data() + static_cast<size_t>(processedReadPos_) * channels,
        copySamples * sizeof(float));
    if (ret != EOK) {
        resamplerFailed_ = true;
        AUDIO_ERR_LOG("NodeId %{public}d: ExtractOutput memcpy_s failed", GetNodeId());
        return false;
    }
    converterOutput_.Origins579() = processedOrigins579_.Slice(0, outputFrameLen20ms_);
    processedOrigins579_.Consume(outputFrameLen20ms_);
    processedReadPos_ += outputFrameLen20ms_;
    processedFrames_ -= outputFrameLen20ms_;
    if (processedFrames_ == 0) {
        processedReadPos_ = 0;
    } else if (processedReadPos_ > processedBuffer_.size() / (channels * PROCESSED_BUFFER_COMPACTION_DIVISOR)) {
        if (!CompactProcessedBuffer(channels)) {
            resamplerFailed_ = true;
            return false;
        }
    }
    AUDIO_DEBUG_LOG("NodeId %{public}d: ExtractOutput success, remaining processedFrames=%{public}u",
        GetNodeId(), processedFrames_);
    // Return one credit: data has been consumed downstream
    if (pullAheadCredit_ < pullAheadMaxCredit_) {
        pullAheadCredit_++;
    }
    return true;
}

bool HpaeAudioFormatConverterNode::RemoveConsumedInputFrames(uint32_t consumedFrames, uint32_t channels)
{
    if (consumedFrames > unprocessedFrames_ || channels == 0 || channels > 16 ||
        unprocessedFrames_ > unprocessedBuffer_.size() / channels) {
        return false;
    }
    unprocessedOrigins579_.Consume(consumedFrames);
    uint32_t remainingFrames = unprocessedFrames_ - consumedFrames;
    if (remainingFrames == 0) {
        unprocessedFrames_ = 0;
        return true;
    }
    size_t srcOffset = static_cast<size_t>(consumedFrames) * channels;
    size_t remainingSamples = static_cast<size_t>(remainingFrames) * channels;
    if (memmove_s(unprocessedBuffer_.data(), unprocessedBuffer_.size() * sizeof(float),
        unprocessedBuffer_.data() + srcOffset, remainingSamples * sizeof(float)) != EOK) {
        return false;
    }
    unprocessedFrames_ = remainingFrames;
    return true;
}

bool HpaeAudioFormatConverterNode::CompactProcessedBuffer(uint32_t channels)
{
    if (channels == 0 || channels > 16 ||
        static_cast<uint64_t>(processedReadPos_) + processedFrames_ > processedBuffer_.size() / channels) {
        return false;
    }
    size_t samples = static_cast<size_t>(processedFrames_) * channels;
    if (samples != 0 && memmove_s(processedBuffer_.data(), processedBuffer_.size() * sizeof(float),
        processedBuffer_.data() + static_cast<size_t>(processedReadPos_) * channels,
        samples * sizeof(float)) != EOK) {
        return false;
    }
    processedReadPos_ = 0;
    return true;
}

void HpaeAudioFormatConverterNode::MoveUnprocessedToProcessed(uint32_t channels)
{
    if (channels == 0 || channels > 16 || unprocessedFrames_ > unprocessedBuffer_.size() / channels) {
        resamplerFailed_ = true;
        return;
    }
    if (!CanAppendProcessedFrames(0, channels)) {
        return;
    }
    size_t freeFrames = processedBuffer_.size() / channels - processedReadPos_ - processedFrames_;
    uint32_t frames = static_cast<uint32_t>(std::min(static_cast<size_t>(unprocessedFrames_), freeFrames));
    if (frames != 0 && (!AppendToProcessedBuffer(unprocessedBuffer_.data(), frames, channels) ||
        !RemoveConsumedInputFrames(frames, channels))) {
        resamplerFailed_ = true;
    }
}

void HpaeAudioFormatConverterNode::SetSourceBufferType(HpaeSourceBufferType type)
{
    converterOutput_.SetSourceBufferType(type);
}

void HpaeAudioFormatConverterNode::ConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>> &preNode,
    HpaeNodeInfo &nodeInfo)
{
    inputStream_.Connect(preNode->GetSharedInstance(), preNode->GetOutputPort(nodeInfo));
    converterOutput_.SetSourceBufferType(nodeInfo.sourceBufferType);
#ifdef ENABLE_HIDUMP_DFX
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeInfo(true, preNode->GetSharedInstance()->GetNodeId(), GetNodeId());
    }
#endif
}
void HpaeAudioFormatConverterNode::DisConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>> &preNode,
    HpaeNodeInfo &nodeInfo)
{
    inputStream_.DisConnect(preNode->GetOutputPort(nodeInfo, true));
#ifdef ENABLE_HIDUMP_DFX
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeInfo(false, preNode->GetSharedInstance()->GetNodeId(), GetNodeId());
    }
#endif
}

uint64_t HpaeAudioFormatConverterNode::GetLatency(uint32_t sessionId)
{
    if (resampler_ == nullptr) {
        return 0;
    }
    // Dual-buffer latency: unprocessed input at input rate + processed output at output rate
    uint32_t inRate = resampler_->GetInRate();
    uint32_t outRate = resampler_->GetOutRate();
    uint64_t latencyUs = 0;
    if (inRate != 0) {
        latencyUs += static_cast<uint64_t>(unprocessedFrames_) * AUDIO_US_PER_SECOND / inRate;
    }
    if (outRate != 0) {
        latencyUs += static_cast<uint64_t>(processedFrames_) * AUDIO_US_PER_SECOND / outRate;
    }
    return latencyUs;
}

void HpaeAudioFormatConverterNode::SetDownmixNormalization(bool normalizing)
{
    channelConverter_.SetDownmixNormalization(normalizing);
}

void HpaeAudioFormatConverterNode::SetUpmixCoef(float coef)
{
    channelConverter_.SetUpmixCoef(coef);
}

void HpaeAudioFormatConverterNode::FlushBuffers()
{
    unprocessedOrigins579_.Clear();
    processedOrigins579_.Clear();
    AUDIO_INFO_LOG("NodeId %{public}d: FlushBuffers, discarding "
        "unprocessedFrames=%{public}u, processedFrames=%{public}u",
        GetNodeId(), unprocessedFrames_, processedFrames_);
    unprocessedFrames_ = 0;
    processedFrames_ = 0;
    processedReadPos_ = 0;
    pullAheadCredit_ = pullAheadMaxCredit_;
    bufferedState_ = PCM_BUFFER_STATE_INVALID;
    resamplerFailed_ = resampler_ == nullptr || resampler_->ResetWithStatus() != EOK;
}
} // Hpae
} // AudioStandard
} // OHOS