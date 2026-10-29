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
#ifndef HPAE_SINK_OUTPUT_NODE_H
#define HPAE_SINK_OUTPUT_NODE_H
#include <memory>
#include "hpae_node.h"
#include "hpae_pcm_buffer.h"
#include "audio_info.h"
#include "sink/i_audio_render_sink.h"
#include "common/hdi_adapter_info.h"
#include "manager/hdi_adapter_manager.h"
#include "high_resolution_timer.h"
#ifdef ENABLE_HOOK_PCM
#include "high_resolution_timer.h"
#endif
namespace OHOS {
namespace AudioStandard {
namespace HPAE {
typedef void (*AppCallbackFunc)(void *pHndl);

class HpaeSinkOutputNode : public InputNode<HpaePcmBuffer *> {
public:
    HpaeSinkOutputNode(HpaeNodeInfo &nodeInfo);
    virtual ~HpaeSinkOutputNode();
    virtual void DoProcess() override;
    virtual bool Reset() override;
    virtual bool ResetAll() override;
    void Connect(const std::shared_ptr<OutputNode<HpaePcmBuffer *>> &preNode) override;
    void DisConnect(const std::shared_ptr<OutputNode<HpaePcmBuffer *>> &preNode) override;
    void RegisterCurrentDeviceCallback(const std::function<void(bool)> &callback);
    int32_t GetRenderSinkInstance(const std::string &deviceClass, const std::string &deviceNetId,
        const std::string &macAddress = "");
    int32_t RenderSinkInit(IAudioSinkAttr &attr);
    int32_t RenderSinkDeInit();
    int32_t RenderSinkFlush(void);
    int32_t RenderSinkPause(void);
    int32_t RenderSinkReset(void);
    int32_t RenderSinkResume(void);
    int32_t RenderSinkStart(void);
    int32_t RenderSinkStop(void);
    int32_t RenderSinkSetPriPaPower(void);
    int32_t RenderSinkSetSyncId(int32_t syncId);
    size_t GetPreOutNum();
    // for ut test
    const char *GetRenderFrameData(void);
    StreamManagerState GetSinkState(void);
    int32_t SetSinkState(StreamManagerState sinkState);
    int32_t UpdateAppsUid(const std::vector<int32_t> &appsUid);
    uint32_t GetLatency();
    void NotifyStreamChangeToSink(StreamChangeType change,
        uint32_t sessionId, StreamUsage usage, RendererState state, uint32_t appUid = INVALID_UID);
    int32_t SetAuxiliarySinkEnable(bool isEnabled);
    uint32_t GetRenderId() const;
    DeviceType GetCurrentActiveDevice() const;
    void CheckAndSetCollDelayForRenderFrameFailed();
    void SetCollaborationState(CollaborationState isCollaborationEnabled);
private:
    void HandleRemoteTiming();
    void HandlePaPower(HpaePcmBuffer *pcmBuffer);
    void HandleHapticParam(uint64_t syncTime);
    bool ReadDataAndConvertFormat();
    void ResetPendingRenderData();
    InputPort<HpaePcmBuffer *> inputStream_;
    std::vector<char, AlignedAllocator<char, 16>> renderFrameData_; // 16 for alignment in byte
    std::vector<char, AlignedAllocator<char, 16>> renderFrameScratch_;
    
    // only for auxiliarysink
    int32_t GetAuxiliarySink(const std::string &deviceClass);
    int32_t AuxiliarySinkInit();
    int32_t AuxiliarySinkDeInit();
    void RenderFrameForAuxiliarySink(char *data, size_t bytes);
    void UpdateAuxiliarySinkState(StreamChangeType change,
        uint32_t sessionId, StreamUsage usage, RendererState state);
    std::shared_ptr<IAudioRenderSink> auxiliarySink_ = nullptr;
    std::atomic<bool> auxSinkEnable_ = false;
    StreamManagerState auxSinkState_ = STREAM_MANAGER_NEW;
    std::unordered_map<uint32_t, StreamUsage> sessionsWithAuxSinkInvalidFilter_;
    std::unordered_map<uint32_t, StreamUsage> sessionsWithAuxSinkValidFilter_;
    
    std::vector<float> interleveData_;
    std::shared_ptr<IAudioRenderSink> audioRendererSink_ = nullptr;
    uint32_t renderId_ = HDI_INVALID_ID;
    IAudioSinkAttr sinkOutAttr_;
    StreamManagerState state_ = STREAM_MANAGER_NEW;
    TimePoint remoteTimePoint_;
    std::chrono::milliseconds remoteSleepTime_ = std::chrono::milliseconds(0);
    int64_t silenceDataUs_ = 0;
    bool isOpenPaPower_ = true;
    bool isDisplayPaPowerState_ = false;
    uint32_t streamRunningNum_ = 0;
    bool isSyncIdSet_ = false;
    int32_t syncId_ = -1;
    uint32_t latency_ = 0;
    uint64_t renderFrameTimes_ = 0;
    size_t outputSize_ = 0;
    size_t currentSize_ = 0;
    size_t renderSize_ = 0;
    size_t pendingRenderSize_ = 0;
    bool renderWriteInvalid_ = false;
    uint64_t renderTimeRemainder_ = 0;
    HighResolutionTimer periodTimer_;
#ifdef ENABLE_HOOK_PCM
    HighResolutionTimer intervalTimer_;
#endif
    std::atomic<size_t> collRenderFrameFailedCount_ = 0;
    std::atomic<CollaborationState> collaborationState_ = COLLABORATION_CLOSE;
};

}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS

#endif