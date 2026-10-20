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

#ifndef HPAE_SINK_INPUT_NODE_H
#define HPAE_SINK_INPUT_NODE_H
#include <memory>
#include <atomic>
#include <optional>
#include <string>
#include "hpae_msg_channel.h"
#include "hpae_node.h"
#include "hpae_pcm_buffer.h"
#include "audio_info.h"
#include "i_renderer_stream.h"
#include "i_effect_instance.h"
#include "linear_pos_time_model.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
typedef void (*AppCallbackFunc)(void *pHndl);

// Attach-state for session-bound effect (e.g. AISS).
// The manager owns the IEffectInstance lifecycle; the node holds a weak reference.
struct SessionEffectAttachState {
    bool enabled = false;
    std::string effectName;
    std::weak_ptr<IEffectInstance> instance;
    AudioEffectConfig config;
};

class HpaeSinkInputNode : public OutputNode<HpaePcmBuffer *> {
public:
    HpaeSinkInputNode(HpaeNodeInfo &nodeInfo);
    virtual ~HpaeSinkInputNode();
    virtual void DoProcess() override;
    virtual bool Reset() override;     // no implement, virtual class
    virtual bool ResetAll() override;  // no implement, virtual class
    std::shared_ptr<HpaeNode> GetSharedInstance() override;
    OutputPort<HpaePcmBuffer *> *GetOutputPort() override;
    bool RegisterWriteCallback(const std::weak_ptr<IStreamCallback> &callback);
    void Flush();
    bool Drain();
    int32_t SetState(HpaeSessionState renderState);
    HpaeSessionState GetState();

    int32_t GetCurrentPosition(uint64_t &framePosition, std::vector<uint64_t> &timestamp);
    void RewindHistoryBuffer(uint64_t rewindTime, uint64_t hdiFramePosition = 0);
    // Ensure history buffer is at least preheatFrames for AISS (non-Offload path)
    void EnsureHistoryBufferForAiss(uint32_t preheatFrames);

    void SetAppUid(int32_t appUid);
    int32_t GetAppUid();
    bool GetKeepRunning();

    void SetIsLowLatency(bool isLowLatency);
    bool GetIsLowLatency();

    void SetOffloadEnabled(bool offloadEnable);
    bool GetOffloadEnabled();
    void SetOffloadType(int32_t offloadType);
    int32_t GetOffloadType();
    int32_t SetLoudnessGain(float loudnessGain);
    float GetLoudnessGain();
    void SetSpeed(float speed);
    float GetSpeed();
    uint64_t GetLatency();
    bool IsDrain();
    bool QueryUnderrun();
    int32_t OnStreamInfoChange(bool needata = true);
    void NotifyOffloadHdiPos(const std::pair<uint64_t, TimePoint> &hdiPos);
    void TriggerClientWake();
    void SetDirect(bool isDirect);
    bool GetDirect() const noexcept;
    bool GetIsNonStandardSampleRate() const;
    void SetSessionEffectAttachState(const SessionEffectAttachState &state);
    void ClearSessionEffectAttachState();
    bool HasSessionEffectAttachState() const;
    std::optional<SessionEffectAttachState> GetSessionEffectAttachState() const;
    // Called by manager on SE preheat start/stop notification; when true, OnStreamInfoChange skips forcing client data
    void SetSessionEffectPreheatActive(bool active) { sessionEffectPreheatActive_ = active; }
    void SetNodeInfo(HpaeNodeInfo& nodeInfo) override;

    bool isConnected_ = false;
    HpaeProcessorType connectedProcessorType_ = HPAE_SCENE_UNCONNECTED;
private:
    int32_t GetDataFromSharedBuffer();
    void CheckAndDestroyHistoryBuffer();
    bool ReadToAudioBuffer(int32_t &ret);
    std::weak_ptr<IStreamCallback> writeCallback_;
    AudioCallBackStreamInfo streamInfo_;
    PcmBufferInfo pcmBufferInfo_;
    PcmBufferInfo emptyBufferInfo_;
    HpaePcmBuffer inputAudioBuffer_;
    HpaePcmBuffer emptyAudioBuffer_;
    OutputPort<HpaePcmBuffer *> outputStream_;
    std::vector<int8_t> interleveData_;
    uint64_t totalFrames_;
    bool isDrain_ = false;
    HpaeSessionState state_ = HPAE_SESSION_NEW;
    int32_t appUid_ = -1;
    std::unique_ptr<HpaePcmBuffer> historyBuffer_;
    bool offloadEnable_ = false;
    int32_t offloadType_ = OFFLOAD_DEFAULT;
    float loudnessGain_ = 0.0f;
    float speed_ = 1.0f;
    std::atomic<uint64_t> hdiFramePosition_ = 0;
    std::atomic<uint64_t> rewindTime_ = 0;
    uint32_t standbyCounter_ = 0;
    bool isLowLatency_ = false;
    bool isDirect_ = false;
    bool isNonStandardSampleRate_ = false;
    std::optional<SessionEffectAttachState> sessionEffectAttachState_;
    bool sessionEffectPreheatActive_ = false;
};

}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS

#endif
