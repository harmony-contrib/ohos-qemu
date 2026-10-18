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

#ifndef HPAE_SOURCE_INTPUT_NODE_H
#define HPAE_SOURCE_INTPUT_NODE_H
#include <memory>
#include "hpae_backoff_controller.h"
#include "hpae_node.h"
#include "hpae_capture_frame_assembler.h"
#include "hpae_pcm_buffer.h"
#include "source/i_audio_capture_source.h"
#include "common/hdi_adapter_type.h"
#include "common/hdi_adapter_info.h"
#include "manager/hdi_adapter_manager.h"
#ifdef ENABLE_HOOK_PCM
#include "hpae_pcm_dumper.h"
#endif

namespace OHOS {
namespace AudioStandard {
namespace HPAE {

class HpaeSourceInputNode : public OutputNode<HpaePcmBuffer *> {
public:
    HpaeSourceInputNode(HpaeNodeInfo &nodeInfo);
    HpaeSourceInputNode(std::vector<HpaeNodeInfo> &nodeInfos);
    virtual ~HpaeSourceInputNode();
    virtual void DoProcess() override;
    virtual bool Reset() override;
    virtual bool ResetAll() override;
    std::shared_ptr<HpaeNode> GetSharedInstance() final;

    OutputPort<HpaePcmBuffer*> *GetOutputPort() final;
    OutputPort<HpaePcmBuffer*> *GetOutputPort(HpaeNodeInfo &nodeInfo, bool isDisConnect = false) final;
    HpaeSourceBufferType GetOutputPortBufferType(HpaeNodeInfo &nodeInfo) final;
    int32_t GetCapturerSourceInstance(const std::string &deviceClass, const std::string &deviceNetId,
        const SourceType &sourceType, const std::string &sourceName, const std::string &busAddress = "");
    int32_t CapturerSourceInit(IAudioSourceAttr &attr);
    int32_t CapturerSourceDeInit();
    int32_t CapturerSourceFlush(void);
    int32_t CapturerSourcePause(void);
    int32_t CapturerSourceReset(void);
    int32_t CapturerSourceResume(void);
    int32_t CapturerSourceStart(void);
    int32_t CapturerSourceStop(void);
    StreamManagerState GetSourceState(void);
    int32_t SetSourceState(StreamManagerState sourceState);
    size_t GetOutputPortNum();
    size_t GetOutputPortNum(HpaeNodeInfo &nodeInfo);
    HpaeSourceInputNodeType GetSourceInputNodeType();
    void SetSourceInputNodeType(HpaeSourceInputNodeType type);
    HpaeNodeInfo& GetNodeInfoWithInfo(HpaeSourceBufferType &type);
    void UpdateAppsUidAndSessionId(std::vector<int32_t> &appsUid, std::vector<int32_t> &sessionsId);
    void UpdateAppsTokenId(const std::vector<uint32_t> &appsTokenId);
    uint32_t GetCaptureId() const;
    void SetInjectState(bool isInjecting);
    void NotifyStreamChangeToSource(StreamChangeType change, uint32_t sessionId, SourceType source,
        CapturerState state, uint32_t appUid = INVALID_UID, bool mute = false, bool mixWithWakeUp = false);

private:
    int32_t GetCapturerSourceAdapter(
        const std::string &deviceClass, const SourceType &sourceType, const std::string &info);
    void SetBufferValid(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes);
    void DoProcessInner(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes);
    void DoProcessMicInner(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes);
    void ProcessAssembledMic(const HpaeSourceBufferType &bufferType);
    void ReadDataFromSource(const HpaeSourceBufferType &bufferType, uint64_t &replyBytes);
    void PushDataToBuffer(const HpaeSourceBufferType &bufferType, const uint64_t &replyBytes);
    void UpdateSourceInputMapCancatMicEc();
    void SetConcatMicEcFlag(HpaeNodeInfo &nodeInfo);
    void ConCatMicEcAndPushData(const uint64_t &replyBytes, const uint64_t replyBytesEc);
    void DoProcessInnerMicAndEc(const uint64_t &replyBytes, const uint64_t replyBytesEc);
    void DumpInput(HpaeSourceBufferType &micType, HpaeSourceBufferType &ecType,
        const uint64_t &replyBytes, const uint64_t &replyBytesEc);
    void DumpOutput(HpaeSourceBufferType &micType);

private:
    std::shared_ptr<IAudioCaptureSource> audioCapturerSource_ = nullptr;
    uint32_t captureId_ = HDI_INVALID_ID;
    IAudioSourceAttr audioSourceAttr_;
    std::string defaultSinkName_;
    std::string defaultSourceName_;
    StreamManagerState state_ = STREAM_MANAGER_NEW;
    HpaeSourceInputNodeType sourceInputNodeType_;

    std::unordered_map<HpaeSourceBufferType, OutputPort<HpaePcmBuffer *>> outputStreamMap_; // output port
    std::unordered_map<HpaeSourceBufferType, HpaeNodeInfo> nodeInfoMap_; // nodeInfo, portInfo
    std::unordered_map<HpaeSourceBufferType, PcmBufferInfo> pcmBufferInfoMap_; // bufferInfo
    // output buffer, fixed framelen of 20ms
    std::unordered_map<HpaeSourceBufferType, HpaePcmBuffer> inputAudioBufferMap_;
    // request data size of captureframe, maybe unequal to output buffer size
    std::unordered_map<HpaeSourceBufferType, size_t> frameByteSizeMap_;
    std::unordered_map<HpaeSourceBufferType, std::vector<char>> historyDataMap_; // store any size data for process
    std::unordered_map<HpaeSourceBufferType, size_t> historyRemainSizeMap_;      // size of stored data
    std::unordered_map<HpaeSourceBufferType, std::vector<char>> capturerFrameDataMap_; // input buffer
    std::unordered_map<HpaeSourceBufferType, FrameDesc> fdescMap_; // CaptureframeWithEc argument struct

    HpaeCaptureFrameAssembler micFrameAssembler_;
    bool isInjecting_ = false; // mark injecting state
    HpaeBackoffController backoffController_;
    bool concatMicEcFlag_ = false;
    std::vector<char> concatDataBuffer_;
#ifdef ENABLE_HOOK_PCM
    std::unordered_map<HpaeSourceBufferType, std::unique_ptr<HpaePcmDumper>> inputPcmDumperMap_;
    std::unique_ptr<HpaePcmDumper> outputPcmDumper_ = nullptr;
#endif
};
}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
#endif