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
#define LOG_TAG "HpaeSourceInputNode"
#endif

#include <cinttypes>
#include <thread>
#include "hpae_source_input_node.h"
#include "hpae_format_convert.h"
#include "hpae_node_common.h"
#include "audio_errors.h"
#include "audio_utils.h"
#include "audio_stream_enum.h"
#include "capturer_clock_manager.h"
#include "audio_engine_log.h"
#include "stream_dfx_manager.h"

#define BYTE_SIZE_SAMPLE_U8 1
#define BYTE_SIZE_SAMPLE_S16 2
#define BYTE_SIZE_SAMPLE_S24 3
#define BYTE_SIZE_SAMPLE_S32 4
#define FRAME_DURATION_DEFAULT (20 * SOURCE_PERIOD_SIZE)
#define MILLISECOND_PER_SECOND 1000

namespace OHOS {
namespace AudioStandard {
namespace HPAE {

static std::string TransSourceBufferTypeToString(const HpaeSourceBufferType &type)
{
    if (type == HPAE_SOURCE_BUFFER_TYPE_MIC) {
        return "MIC";
    } else if (type == HPAE_SOURCE_BUFFER_TYPE_EC) {
        return "EC";
    } else if (type == HPAE_SOURCE_BUFFER_TYPE_MICREF) {
        return "MICREF";
    }
    return "DEFAULT";
}

HpaeSourceInputNode::HpaeSourceInputNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo), sourceInputNodeType_(nodeInfo.sourceInputNodeType)
{
    HpaeSourceBufferType sourceBufferType = nodeInfo.sourceBufferType;
    nodeInfoMap_.emplace(sourceBufferType, nodeInfo);
    frameByteSizeMap_.emplace(
        sourceBufferType, nodeInfo.frameLen * nodeInfo.channels * GetSizeFromFormat(nodeInfo.format));
    nodeInfoMap_[sourceBufferType].frameLen = FRAME_DURATION_DEFAULT * nodeInfo.samplingRate / MILLISECOND_PER_SECOND;
    pcmBufferInfoMap_.emplace(
        sourceBufferType, PcmBufferInfo(nodeInfoMap_[sourceBufferType].channels,
        nodeInfoMap_[sourceBufferType].frameLen, nodeInfoMap_[sourceBufferType].samplingRate));
    inputAudioBufferMap_.emplace(sourceBufferType, HpaePcmBuffer(pcmBufferInfoMap_.at(sourceBufferType)));
    inputAudioBufferMap_.at(sourceBufferType).SetSourceBufferType(sourceBufferType);
    capturerFrameDataMap_.emplace(sourceBufferType, frameByteSizeMap_.at(sourceBufferType));
    outputStreamMap_.emplace(sourceBufferType, this);
    historyDataMap_.emplace(sourceBufferType, 0);
    historyRemainSizeMap_.emplace(sourceBufferType, 0);
    if (sourceInputNodeType_ == HPAE_SOURCE_EC) {
        fdescMap_.emplace(sourceBufferType,
            FrameDesc{capturerFrameDataMap_.at(sourceBufferType).data(), frameByteSizeMap_.at(sourceBufferType)});
        fdescMap_.emplace(HPAE_SOURCE_BUFFER_TYPE_DEFAULT, FrameDesc{nullptr, 0});
    }
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeSourceInputNode[" + TransSourceBufferTypeToString(nodeInfo.sourceBufferType) + "]");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

void HpaeSourceInputNode::UpdateSourceInputMapCancatMicEc()
{
    CHECK_AND_RETURN(concatMicEcFlag_);
    HpaeSourceBufferType micType = HPAE_SOURCE_BUFFER_TYPE_MIC;
    HpaeSourceBufferType ecType = HPAE_SOURCE_BUFFER_TYPE_EC;
    HpaeNodeInfo micInfo = nodeInfoMap_[micType];
    HpaeNodeInfo ecInfo = nodeInfoMap_[ecType];
    nodeInfoMap_.clear();
    micInfo.channels = static_cast<AudioChannel>(micInfo.channels + ecInfo.channels);
    nodeInfoMap_.emplace(micType, micInfo);
    nodeInfoMap_.emplace(ecType, ecInfo);
    pcmBufferInfoMap_.clear();
    pcmBufferInfoMap_.emplace(micType, PcmBufferInfo(micInfo.channels, micInfo.frameLen, micInfo.samplingRate));
    inputAudioBufferMap_.clear();
    inputAudioBufferMap_.emplace(micType, HpaePcmBuffer(pcmBufferInfoMap_.at(micType)));
    inputAudioBufferMap_.at(micType).SetSourceBufferType(micType);
    outputStreamMap_.clear();
    outputStreamMap_.emplace(micType, this);
    historyDataMap_.clear();
    historyRemainSizeMap_.clear();
    concatDataBuffer_.resize(micInfo.channels * micInfo.frameLen * GetSizeFromFormat(micInfo.format));
    AUDIO_INFO_LOG("mic:%{public}d, ec:%{public}d, concatBufferSize:%{public}d", micInfo.channels,
        ecInfo.channels, static_cast<uint32_t>(concatDataBuffer_.size()));
#ifdef ENABLE_HOOK_PCM
    outputPcmDumper_ = std::make_unique<HpaePcmDumper>("HpaeSourceInputNodeOut_id" +
        std::to_string(GetSessionId()) +
        "_ch_" + std::to_string(micInfo.channels) +
        "_rate_" + std::to_string(micInfo.samplingRate) +
        "_bit_4.pcm");
#endif
}

void HpaeSourceInputNode::SetConcatMicEcFlag(HpaeNodeInfo &nodeInfo)
{
    CHECK_AND_RETURN((nodeInfo.sourceType == SOURCE_TYPE_UNPROCESSED_VOICE_ASSISTANT) ||
        nodeInfo.sourceType == SOURCE_TYPE_VOICE_RECOGNITION);
    concatMicEcFlag_ = true;
#ifdef ENABLE_HOOK_PCM
    inputPcmDumperMap_.emplace(nodeInfo.sourceBufferType, std::make_unique<HpaePcmDumper>(
        "HpaeSourceInputNodeIn_id" + std::to_string(GetSessionId()) +
        "_ch_" + std::to_string(nodeInfo.channels) +
        "_rate_" + std::to_string(nodeInfo.samplingRate) +
        "_bit_1_" + TransSourceBufferTypeToString(nodeInfo.sourceBufferType) + ".pcm"));
#endif
}

HpaeSourceInputNode::HpaeSourceInputNode(std::vector<HpaeNodeInfo> &nodeInfos)
    : HpaeNode(*nodeInfos.begin()), sourceInputNodeType_((*nodeInfos.begin()).sourceInputNodeType)
{
    for (auto nodeInfo : nodeInfos) {
        HpaeSourceBufferType sourceBufferType = nodeInfo.sourceBufferType;
        SetConcatMicEcFlag(nodeInfo);
        nodeInfoMap_.emplace(sourceBufferType, nodeInfo);
        frameByteSizeMap_.emplace(
            sourceBufferType, nodeInfo.frameLen * nodeInfo.channels * GetSizeFromFormat(nodeInfo.format));
        nodeInfoMap_[sourceBufferType].frameLen =
            FRAME_DURATION_DEFAULT * nodeInfo.samplingRate / MILLISECOND_PER_SECOND;
        pcmBufferInfoMap_.emplace(
            sourceBufferType, PcmBufferInfo(nodeInfoMap_[sourceBufferType].channels,
            nodeInfoMap_[sourceBufferType].frameLen, nodeInfoMap_[sourceBufferType].samplingRate));
        inputAudioBufferMap_.emplace(sourceBufferType, HpaePcmBuffer(pcmBufferInfoMap_.at(sourceBufferType)));
        inputAudioBufferMap_.at(sourceBufferType).SetSourceBufferType(sourceBufferType);
        capturerFrameDataMap_.emplace(sourceBufferType, frameByteSizeMap_.at(sourceBufferType));
        fdescMap_.emplace(sourceBufferType,
            FrameDesc{capturerFrameDataMap_.at(sourceBufferType).data(), frameByteSizeMap_.at(sourceBufferType)});
        outputStreamMap_.emplace(sourceBufferType, this);
        historyDataMap_.emplace(sourceBufferType, 0);
        historyRemainSizeMap_.emplace(sourceBufferType, 0);
    }
    UpdateSourceInputMapCancatMicEc();
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeSourceInputNode[MIC_EC]");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeSourceInputNode::~HpaeSourceInputNode()
{
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

void HpaeSourceInputNode::SetBufferValid(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes)
{
    CHECK_AND_RETURN_LOG(inputAudioBufferMap_.find(bufferType) != inputAudioBufferMap_.end(),
        "set buffer valid with error type");
    inputAudioBufferMap_.at(bufferType).SetBufferValid(true);
    uint32_t byteSize = nodeInfoMap_.at(bufferType).channels * nodeInfoMap_.at(bufferType).frameLen *
        static_cast<uint32_t>(GetSizeFromFormat(nodeInfoMap_.at(bufferType).format));
    if (replyBytes != byteSize) {
        AUDIO_WARNING_LOG("DoProcess(), request size[%{public}zu][%{public}u], reply size[%{public}" PRIu64 "]",
            frameByteSizeMap_.at(bufferType), byteSize, replyBytes);
        AUDIO_WARNING_LOG("DoProcess(), if reply != request, just drop now");
        inputAudioBufferMap_.at(bufferType).SetBufferValid(false);
    }
}

void HpaeSourceInputNode::DoProcessInner(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes)
{
    AUDIO_DEBUG_LOG("DoProcessInner, replyBytes: %{public}" PRIu64, replyBytes);
    // todo: do not convert to float in SourceInputNode
    ConvertToFloat(nodeInfoMap_.at(bufferType).format,
        nodeInfoMap_.at(bufferType).channels * nodeInfoMap_.at(bufferType).frameLen,
        capturerFrameDataMap_.at(bufferType).data(),
        inputAudioBufferMap_.at(bufferType).GetPcmDataBuffer());
    if (inputAudioBufferMap_.at(bufferType).IsValid()) {
        outputStreamMap_.at(bufferType).WriteDataToOutput(&inputAudioBufferMap_.at(bufferType));
    }
}

void HpaeSourceInputNode::DoProcessMicInner(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes)
{
    AUDIO_DEBUG_LOG("DoProcessMicInner, replyBytes: %{public}" PRIu64, replyBytes);
    if (isInjecting_ && replyBytes == 0 && audioCapturerSource_->GetArmUsbDeviceStatus() != 1) {
        AUDIO_WARNING_LOG("HpaeSourceInputNode::DoProcessMicInner injecting need sleep");
        std::this_thread::sleep_for(std::chrono::milliseconds(FRAME_DURATION_DEFAULT));
        return;
    }
    auto &historyData = historyDataMap_.at(bufferType);
    uint32_t byteSize = nodeInfoMap_.at(bufferType).channels * nodeInfoMap_.at(bufferType).frameLen *
        static_cast<uint32_t>(GetSizeFromFormat(nodeInfoMap_.at(bufferType).format));
    if ((bufferType == HPAE_SOURCE_BUFFER_TYPE_MIC || bufferType == HPAE_SOURCE_BUFFER_TYPE_DEFAULT) &&
        historyRemainSizeMap_.at(bufferType) == 0) {
        return;
    } else if (historyRemainSizeMap_.at(bufferType) < byteSize) {
        historyData.insert(historyData.end(), byteSize - historyRemainSizeMap_.at(bufferType), 0);
        historyRemainSizeMap_.at(bufferType) = byteSize;
    }

    // todo: do not convert to float in SourceInputNode
    ConvertToFloat(nodeInfoMap_.at(bufferType).format,
        nodeInfoMap_.at(bufferType).channels * nodeInfoMap_.at(bufferType).frameLen,
        historyData.data(), inputAudioBufferMap_.at(bufferType).GetPcmDataBuffer());
    historyRemainSizeMap_[bufferType] -= byteSize;
    // drop data has been written
    historyData.erase(historyData.begin(), historyData.begin() + byteSize);
    outputStreamMap_.at(bufferType).WriteDataToOutput(&inputAudioBufferMap_.at(bufferType));
}

static bool CheckEcAndMicRefReplyValid(const uint64_t &requestBytes, const uint64_t replyBytes)
{
    return replyBytes != 0 && requestBytes == replyBytes;
}

void HpaeSourceInputNode::DumpInput(HpaeSourceBufferType &micType, HpaeSourceBufferType &ecType,
    const uint64_t &replyBytes, const uint64_t &replyBytesEc)
{
#ifdef ENABLE_HOOK_PCM
    CHECK_AND_RETURN_LOG(
        inputPcmDumperMap_.find(micType) != inputPcmDumperMap_.end() && inputPcmDumperMap_.at(micType),
        "can not find mic type");
    inputPcmDumperMap_.at(micType)->Dump((int8_t *)capturerFrameDataMap_.at(micType).data(), replyBytes);
    CHECK_AND_RETURN_LOG(
        inputPcmDumperMap_.find(ecType) != inputPcmDumperMap_.end() && inputPcmDumperMap_.at(ecType),
        "can not find ec type");
    inputPcmDumperMap_.at(ecType)->Dump((int8_t *)capturerFrameDataMap_.at(ecType).data(), replyBytesEc);
#endif
}

void HpaeSourceInputNode::DumpOutput(HpaeSourceBufferType &micType)
{
#ifdef ENABLE_HOOK_PCM
    CHECK_AND_RETURN_LOG(outputPcmDumper_, "outputPcmDumper_ is nullptr");
    float *outputData = inputAudioBufferMap_.at(micType).GetPcmDataBuffer();
    outputPcmDumper_->Dump((int8_t *) outputData,
        nodeInfoMap_.at(micType).channels * nodeInfoMap_.at(micType).frameLen * sizeof(float));
#endif
}

void HpaeSourceInputNode::ConCatMicEcAndPushData(const uint64_t &replyBytes, const uint64_t replyBytesEc)
{
    HpaeSourceBufferType micType = HPAE_SOURCE_BUFFER_TYPE_MIC;
    HpaeSourceBufferType ecType = HPAE_SOURCE_BUFFER_TYPE_EC;
    CHECK_AND_RETURN_LOG(
        CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(micType), replyBytes),
        "mic replyBytes[%{public}u] is enough", static_cast<uint32_t>(replyBytes));
    CHECK_AND_RETURN_LOG(
        CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(ecType), replyBytesEc),
        "ec replyBytesEc[%{public}u] is enough", static_cast<uint32_t>(replyBytesEc));
    DumpInput(micType, ecType, replyBytes, replyBytesEc);

    uint32_t framelen = nodeInfoMap_.at(micType).frameLen;
    uint32_t totalChannel = nodeInfoMap_.at(micType).channels;
    uint32_t micChannel = totalChannel - nodeInfoMap_.at(ecType).channels;
    uint32_t ecChannel = nodeInfoMap_.at(ecType).channels;
    uint32_t micFormatSize = static_cast<uint32_t>(GetSizeFromFormat(nodeInfoMap_.at(micType).format));
    uint32_t ecFormatSize = static_cast<uint32_t>(GetSizeFromFormat(nodeInfoMap_.at(ecType).format));

    for (uint32_t i = 0; i < framelen; i++) {
        size_t frameStart = static_cast<size_t>(i) * totalChannel * micFormatSize;
        size_t micFrameStart = static_cast<size_t>(i) * micChannel * micFormatSize;
        size_t ecFrameStart = static_cast<size_t>(i) * ecChannel * micFormatSize;

        for (uint32_t j = 0; j < micChannel; j++) {
            size_t destOffset = frameStart + j * micFormatSize;
            size_t srcOffset = micFrameStart + j * micFormatSize;
            int32_t ret = memcpy_s(concatDataBuffer_.data() + destOffset, micFormatSize,
                capturerFrameDataMap_.at(micType).data() + srcOffset, micFormatSize);
            CHECK_AND_RETURN_LOG(ret == SUCCESS, "memcpy mic data failed");
        }

        for (uint32_t j = 0; j < ecChannel; j++) {
            size_t destOffset = frameStart + (micChannel + j) * ecFormatSize;
            size_t srcOffset = ecFrameStart + j * ecFormatSize;
            int32_t ret = memcpy_s(concatDataBuffer_.data() + destOffset, ecFormatSize,
                capturerFrameDataMap_.at(ecType).data() + srcOffset, ecFormatSize);
            CHECK_AND_RETURN_LOG(ret == SUCCESS, "memcpy ec data failed");
        }
    }

    ConvertToFloat(nodeInfoMap_.at(micType).format,
        nodeInfoMap_.at(micType).channels * nodeInfoMap_.at(micType).frameLen,
        concatDataBuffer_.data(), inputAudioBufferMap_.at(micType).GetPcmDataBuffer());
    DumpOutput(micType);
    outputStreamMap_.at(micType).WriteDataToOutput(&inputAudioBufferMap_.at(micType));
}

void HpaeSourceInputNode::DoProcessInnerMicAndEc(const uint64_t &replyBytes, const uint64_t replyBytesEc)
{
    if (concatMicEcFlag_) {
        ConCatMicEcAndPushData(replyBytes, replyBytesEc);
    } else {
        PushDataToBuffer(HPAE_SOURCE_BUFFER_TYPE_MIC, replyBytes);
        DoProcessMicInner(HPAE_SOURCE_BUFFER_TYPE_MIC, replyBytes);
        CHECK_AND_RETURN_LOG(
            CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(HPAE_SOURCE_BUFFER_TYPE_EC), replyBytesEc),
            "same ec request != reply");
        DoProcessInner(HPAE_SOURCE_BUFFER_TYPE_EC, replyBytesEc);
    }
}

void HpaeSourceInputNode::DoProcess()
{
    Trace trace("[" + std::to_string(GetNodeId()) + "]HpaeSourceInputNode::DoProcess " + GetTraceInfo());
    CHECK_AND_RETURN_LOG(audioCapturerSource_ != nullptr,
        "audioCapturerSource_ is nullptr NodeId: %{public}u", GetNodeId());
    uint64_t replyBytes = 0;
    if (GetNodeInfo().routeFlag == AUDIO_INPUT_FLAG_INTERPHONE) {
        return;
    }
    if (sourceInputNodeType_ == HpaeSourceInputNodeType::HPAE_SOURCE_MIC_EC) {
        uint64_t replyBytesEc = 0;
        audioCapturerSource_->CaptureFrameWithEc(&fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_MIC), replyBytes,
                                                 &fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_EC), replyBytesEc);
        DoProcessInnerMicAndEc(replyBytes, replyBytesEc);
    } else if (sourceInputNodeType_ == HpaeSourceInputNodeType::HPAE_SOURCE_OFFLOAD) {
        uint64_t replyBytesEc = 0;
        audioCapturerSource_->CaptureFrameWithEc(&fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_MIC), replyBytes,
                                                 &fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_EC), replyBytesEc);
        CHECK_AND_RETURN_LOG(
            CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(HPAE_SOURCE_BUFFER_TYPE_EC), replyBytesEc),
            "same offload ec request != reply");
        DoProcessInner(HPAE_SOURCE_BUFFER_TYPE_EC, replyBytesEc);
    } else {
        HpaeSourceBufferType sourceBufferType = nodeInfoMap_.begin()->second.sourceBufferType;
        if (sourceInputNodeType_ == HPAE_SOURCE_EC) {
            uint64_t replyBytesUnused = 0;
            audioCapturerSource_->CaptureFrameWithEc(&fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_DEFAULT), replyBytesUnused,
                                                     &fdescMap_.at(HPAE_SOURCE_BUFFER_TYPE_EC), replyBytes);
            CHECK_AND_RETURN_LOG(CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(sourceBufferType), replyBytes),
                "ec request != reply");
            DoProcessInner(sourceBufferType, replyBytes);
        } else if (sourceInputNodeType_ == HPAE_SOURCE_MICREF) {
            audioCapturerSource_->CaptureFrame(capturerFrameDataMap_.at(sourceBufferType).data(),
                (uint64_t)frameByteSizeMap_.at(sourceBufferType), replyBytes);
            CHECK_AND_RETURN_LOG(CheckEcAndMicRefReplyValid(frameByteSizeMap_.at(sourceBufferType), replyBytes),
                "micref request != reply");
            DoProcessInner(sourceBufferType, replyBytes);
        } else if (sourceInputNodeType_ == HPAE_SOURCE_MIC &&
            (sourceBufferType == HPAE_SOURCE_BUFFER_TYPE_MIC ||
             sourceBufferType == HPAE_SOURCE_BUFFER_TYPE_DEFAULT)) {
            ProcessAssembledMic(sourceBufferType);
        } else {
            ReadDataFromSource(sourceBufferType, replyBytes);
            DoProcessMicInner(sourceBufferType, replyBytes);
        }
    }
}

bool HpaeSourceInputNode::Reset()
{
    micFrameAssembler_.Invalidate();
    return true;
}

bool HpaeSourceInputNode::ResetAll()
{
    micFrameAssembler_.Invalidate();
    return true;
}

std::shared_ptr<HpaeNode> HpaeSourceInputNode::GetSharedInstance()
{
    return shared_from_this();
}

OutputPort<HpaePcmBuffer *> *HpaeSourceInputNode::GetOutputPort()
{
    std::unordered_map<HpaeSourceBufferType, OutputPort<HpaePcmBuffer *>>::iterator it;
    if (sourceInputNodeType_ != HPAE_SOURCE_MIC_EC) {
        it = outputStreamMap_.begin();
    } else {
        it = outputStreamMap_.find(HPAE_SOURCE_BUFFER_TYPE_MIC);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != outputStreamMap_.end(), nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "outStreamMap_ is empty", false),
        "outStreamMap_ is empty");
    return &(it->second);
}

OutputPort<HpaePcmBuffer *> *HpaeSourceInputNode::GetOutputPort(HpaeNodeInfo &nodeInfo, bool isDisConnect)
{
    auto it = outputStreamMap_.find(nodeInfo.sourceBufferType);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != outputStreamMap_.end(), nullptr,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "can't find nodeKey in outStreamMap_", false),
        "can't find nodeKey in outStreamMap_, sourceBufferType = %{public}d", nodeInfo.sourceBufferType);
    return &(it->second);
}

HpaeSourceBufferType HpaeSourceInputNode::GetOutputPortBufferType(HpaeNodeInfo &nodeInfo)
{
    auto it = outputStreamMap_.find(nodeInfo.sourceBufferType);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != outputStreamMap_.end(), HPAE_SOURCE_BUFFER_TYPE_DEFAULT,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "can't find nodeKey in outStreamMap_", false),
        "can't find nodeKey in outStreamMap_, sourceBufferType = %{public}d", nodeInfo.sourceBufferType);
    // todo: rewrite this function
    if (sourceInputNodeType_ == HpaeSourceInputNodeType::HPAE_SOURCE_MIC_EC) {
        if (nodeInfo.sourceBufferType == HPAE_SOURCE_BUFFER_TYPE_MIC) {
            return HPAE_SOURCE_BUFFER_TYPE_MIC;
        } else {
            return HPAE_SOURCE_BUFFER_TYPE_EC;
        }
    } else {
        return inputAudioBufferMap_.at(nodeInfo.sourceBufferType).GetSourceBufferType();
    }
}

int32_t HpaeSourceInputNode::GetCapturerSourceAdapter(
    const std::string &deviceClass, const SourceType &sourceType, const std::string &info)
{
    captureId_ = HDI_INVALID_ID;
    if (info.empty()) {
        captureId_ = HdiAdapterManager::GetInstance().GetCaptureIdByDeviceClass(
            deviceClass, sourceType, HDI_ID_INFO_DEFAULT, true, GetNodeInfo().routeFlag);
    } else {
        captureId_ = HdiAdapterManager::GetInstance().GetCaptureIdByDeviceClass(
            deviceClass, sourceType, info, true, GetNodeInfo().routeFlag);
    }
    audioCapturerSource_ = HdiAdapterManager::GetInstance().GetCaptureSource(captureId_, true);
    if (audioCapturerSource_ == nullptr) {
        AUDIO_ERR_LOG("get source fail, deviceClass: %{public}s, info: %{public}s, captureId_: %{public}u",
            deviceClass.c_str(), info.c_str(), captureId_);
        HdiAdapterManager::GetInstance().ReleaseId(captureId_);
        return ERROR;
    }
    return SUCCESS;
}

int32_t HpaeSourceInputNode::GetCapturerSourceInstance(const std::string &deviceClass, const std::string &deviceNetId,
    const SourceType &sourceType, const std::string &sourceName, const std::string &busAddress)
{
    if (!busAddress.empty()) {
        return GetCapturerSourceAdapter(deviceClass, sourceType, busAddress);
    }
    if (sourceType == SOURCE_TYPE_WAKEUP || sourceName == HDI_ID_INFO_EC || sourceName == HDI_ID_INFO_MIC_REF) {
        return GetCapturerSourceAdapter(deviceClass, sourceType, sourceName);
    }
    return GetCapturerSourceAdapter(deviceClass, sourceType, deviceNetId);
}

int32_t HpaeSourceInputNode::CapturerSourceInit(IAudioSourceAttr &attr)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    Trace trace("HpaeSourceInputNode::CapturerSourceInit");
    if (audioCapturerSource_->IsInited()) {
        SetSourceState(STREAM_MANAGER_IDLE);
#ifdef IS_EMULATOR
        AUDIO_INFO_LOG("do start and stop");
        if (sourceInputNodeType_ == HPAE_SOURCE_MIC || sourceInputNodeType_ == HPAE_SOURCE_MIC_EC) {
            audioCapturerSource_->Start();
            audioCapturerSource_->Stop();
        }
#endif
        return SUCCESS;
    }

    audioSourceAttr_ = attr;
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->Init(attr) == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::CREATE, ERR_OPERATION_FAILED),
            "Source init fail", false),
        "Source init fail");
    SetSourceState(STREAM_MANAGER_IDLE);
#ifdef IS_EMULATOR
    // Due to the peculiar implementation of the emulator's HDI,
    // an initial start and stop sequence is required to circumvent protential issues and ensure proper functionality.
    AUDIO_INFO_LOG("do start and stop");
    if (sourceInputNodeType_ == HPAE_SOURCE_MIC || sourceInputNodeType_ == HPAE_SOURCE_MIC_EC) {
        audioCapturerSource_->Start();
        audioCapturerSource_->Stop();
    }
#endif
    return SUCCESS;
}

int32_t HpaeSourceInputNode::CapturerSourceDeInit()
{
    micFrameAssembler_.Invalidate();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::RELEASE, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    Trace trace("HpaeSourceInputNode::CapturerSourceDeInit");
    if (audioCapturerSource_->IsInited()) {
        audioCapturerSource_->DeInit();
    }
    audioCapturerSource_ = nullptr;
    HdiAdapterManager::GetInstance().ReleaseId(captureId_);
    return SUCCESS;
}

int32_t HpaeSourceInputNode::CapturerSourceFlush(void)
{
    micFrameAssembler_.Invalidate();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::FLUSH, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->IsInited(), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::FLUSH, ERR_ILLEGAL_STATE),
            "invalid source state", false),
        "invalid source state");
    return audioCapturerSource_->Flush();
}

int32_t HpaeSourceInputNode::CapturerSourcePause(void)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::PAUSE, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->IsInited(), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::PAUSE, ERR_ILLEGAL_STATE),
            "invalid source state", false),
        "invalid source state");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->Pause() == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::PAUSE, ERR_OPERATION_FAILED),
            "Source pause fail", false),
        "Source pause fail");
    SetSourceState(STREAM_MANAGER_SUSPENDED);
    return SUCCESS;
}

int32_t HpaeSourceInputNode::CapturerSourceReset(void)
{
    micFrameAssembler_.Invalidate();
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::STOP, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    return audioCapturerSource_->Reset();
}

int32_t HpaeSourceInputNode::CapturerSourceResume(void)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::START, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->Resume() == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::START, ERR_OPERATION_FAILED),
            "Source resume fail", false),
        "Source resume fail");
    SetSourceState(STREAM_MANAGER_RUNNING);
    return SUCCESS;
}

int32_t HpaeSourceInputNode::CapturerSourceStart(void)
{
    micFrameAssembler_.Invalidate();
    Trace trace("HpaeSourceInputNode::CapturerSourceStart");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::START, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->IsInited(), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::START, ERR_ILLEGAL_STATE),
            "invalid source state", false),
        "invalid source state");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->Start() == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::RECORD,
                BusinessScenario::START, ERR_OPERATION_FAILED),
            "Source start fail", false),
        "Source start fail");
    SetSourceState(STREAM_MANAGER_RUNNING);
    return SUCCESS;
}

int32_t HpaeSourceInputNode::CapturerSourceStop(void)
{
    micFrameAssembler_.Invalidate();
    Trace trace("HpaeSourceInputNode::CapturerSourceStop");
    SetSourceState(STREAM_MANAGER_SUSPENDED);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::STOP, ERR_NULL_POINTER),
            "invalid audioCapturerSource", false),
        "invalid audioCapturerSource");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(audioCapturerSource_->IsInited(), ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::STOP, ERR_ILLEGAL_STATE),
            "invalid source state", false),
        "invalid source state");
    if (audioCapturerSource_->Stop() != SUCCESS) {
        AUDIO_ERR_LOG("stop error, sourceInputNode[%{public}u]", sourceInputNodeType_);
    }
    return SUCCESS;
}

StreamManagerState HpaeSourceInputNode::GetSourceState(void)
{
    return state_;
}

int32_t HpaeSourceInputNode::SetSourceState(StreamManagerState sourceState)
{
    HILOG_COMM_INFO("[SetSourceState]Source[%{public}s] state change:"
        "[%{public}s]-->[%{public}s]", GetDeviceClass().c_str(), ConvertStreamManagerState2Str(state_).c_str(),
        ConvertStreamManagerState2Str(sourceState).c_str());
    state_ = sourceState;
    return SUCCESS;
}

size_t HpaeSourceInputNode::GetOutputPortNum()
{
    std::unordered_map<HpaeSourceBufferType, OutputPort<HpaePcmBuffer *>>::iterator it;
    if (sourceInputNodeType_ != HPAE_SOURCE_MIC_EC) {
        it = outputStreamMap_.begin();
    } else {
        it = outputStreamMap_.find(HPAE_SOURCE_BUFFER_TYPE_MIC);
    }
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != outputStreamMap_.end(), 0,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "outStreamMap_ is empty", false),
        "outStreamMap_ is empty");
    return it->second.GetInputNum();
}

size_t HpaeSourceInputNode::GetOutputPortNum(HpaeNodeInfo &nodeInfo)
{
    auto it = outputStreamMap_.find(nodeInfo.sourceBufferType);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != outputStreamMap_.end(), 0,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "can't find nodeKey in outStreamMap_", false),
        "can't find nodeKey in outStreamMap_");
    return it->second.GetInputNum();
}

HpaeSourceInputNodeType HpaeSourceInputNode::GetSourceInputNodeType()
{
    return sourceInputNodeType_;
}

void HpaeSourceInputNode::SetSourceInputNodeType(HpaeSourceInputNodeType type)
{
    sourceInputNodeType_ = type;
}

HpaeNodeInfo &HpaeSourceInputNode::GetNodeInfoWithInfo(HpaeSourceBufferType &type)
{
    auto it = nodeInfoMap_.find(type);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(it != nodeInfoMap_.end(), nodeInfoMap_.begin()->second,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::RECORD,
                BusinessScenario::QUERY, ERR_NULL_POINTER),
            "can't find nodeKey in nodeInfoMap_", false),
        "can't find nodeKey in nodeInfoMap_");
    return it->second;
}

void HpaeSourceInputNode::UpdateAppsUidAndSessionId(std::vector<int32_t> &appsUid, std::vector<int32_t> &sessionsId)
{
    CHECK_AND_RETURN_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID,
        "audioCapturerSource_ is nullptr");
    CHECK_AND_RETURN_LOG(audioCapturerSource_->IsInited(), "invalid source state");
    audioCapturerSource_->UpdateAppsUid(appsUid);
    std::shared_ptr<AudioSourceClock> clock =
        CapturerClockManager::GetInstance().GetAudioSourceClock(captureId_);
    if (clock != nullptr) {
        clock->UpdateSessionId(sessionsId);
    }
}

void HpaeSourceInputNode::UpdateAppsTokenId(const std::vector<uint32_t> &appsTokenId)
{
    CHECK_AND_RETURN_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID,
        "audioCapturerSource_ is nullptr");

    CHECK_AND_RETURN_LOG(audioCapturerSource_->IsInited(), "invalid source state");
    audioCapturerSource_->UpdateAppsTokenId(appsTokenId);
}

uint32_t HpaeSourceInputNode::GetCaptureId() const
{
    return captureId_;
}

void HpaeSourceInputNode::ProcessAssembledMic(const HpaeSourceBufferType &bufferType)
{
    const auto &info = nodeInfoMap_.at(bufferType);
    const size_t sampleFrameBytes = info.channels * static_cast<size_t>(GetSizeFromFormat(info.format));
    const size_t outputBytes = info.frameLen * sampleFrameBytes;
    const size_t capacity = frameByteSizeMap_.at(bufferType);
    const uint64_t lease = micFrameAssembler_.Begin(outputBytes, sampleFrameBytes, capacity);
    CHECK_AND_RETURN_LOG(lease != 0, "invalid ordinary MIC frame geometry");
    std::vector<char> input(capacity);
    while (!micFrameAssembler_.HasFrame(lease)) {
        CHECK_AND_RETURN_LOG(micFrameAssembler_.IsCurrent(lease), "discard retired ordinary MIC read lease");
        uint64_t actualBytes = 0;
        // Keep this read outside the assembler lock, so a lifecycle transition
        // can invalidate its lease without waiting for an HDI call to return.
        int32_t ret = audioCapturerSource_->CaptureFrame(input.data(), capacity, actualBytes);
        const bool valid = ret == SUCCESS && actualBytes != 0 && actualBytes <= capacity &&
            actualBytes % sampleFrameBytes == 0;
        backoffController_.HandleResult(valid);
        CHECK_AND_RETURN_LOG(valid, "ordinary MIC read incomplete/error ret:%{public}d bytes:%{public}" PRIu64,
            ret, actualBytes);
        CHECK_AND_RETURN_LOG(micFrameAssembler_.Append(lease, input.data(), static_cast<size_t>(actualBytes)),
            "discard retired ordinary MIC read");
    }
    micFrameAssembler_.PublishFrame(lease, [this, &info, &bufferType](char *frame) {
        ConvertToFloat(info.format, info.channels * info.frameLen, frame,
            inputAudioBufferMap_.at(bufferType).GetPcmDataBuffer());
        outputStreamMap_.at(bufferType).WriteDataToOutput(&inputAudioBufferMap_.at(bufferType));
    });
}

void HpaeSourceInputNode::ReadDataFromSource(const HpaeSourceBufferType &bufferType, uint64_t &replyBytes)
{
    uint32_t byteSize = nodeInfoMap_.at(bufferType).channels * nodeInfoMap_.at(bufferType).frameLen *
        static_cast<uint32_t>(GetSizeFromFormat(nodeInfoMap_.at(bufferType).format));
    while (historyRemainSizeMap_[bufferType] < byteSize) {
        int32_t ret = audioCapturerSource_->CaptureFrame(capturerFrameDataMap_.at(bufferType).data(),
            (uint64_t)frameByteSizeMap_.at(bufferType), replyBytes);
        if (sourceInputNodeType_ == HPAE_SOURCE_MIC) { // micref not sleep
            backoffController_.HandleResult(ret == SUCCESS);
        }
        CHECK_AND_RETURN_LOG(replyBytes != 0, "replyBytes is 0");
        PushDataToBuffer(bufferType, replyBytes);
    }
}

void HpaeSourceInputNode::PushDataToBuffer(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes)
{
    auto &historyData = historyDataMap_.at(bufferType);
    auto newData = capturerFrameDataMap_.at(bufferType).data();
    historyData.insert(historyData.end(), newData, newData + replyBytes);
    historyRemainSizeMap_[bufferType] += replyBytes;
}

void HpaeSourceInputNode::SetInjectState(bool isInjecting)
{
    isInjecting_ = isInjecting;
}

void HpaeSourceInputNode::NotifyStreamChangeToSource(StreamChangeType change,
    uint32_t sessionId, SourceType source, CapturerState state, uint32_t appUid, bool mute, bool mixWithWakeUp)
{
    CHECK_AND_RETURN_LOG(audioCapturerSource_ != nullptr && captureId_ != HDI_INVALID_ID,
        "audioCapturerSource_ is nullptr");
    CHECK_AND_RETURN_LOG(audioCapturerSource_->IsInited(), "invalid source state");
    audioCapturerSource_->NotifyStreamChangeToSource(change, sessionId, source, state, appUid, mute, mixWithWakeUp);
}
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
