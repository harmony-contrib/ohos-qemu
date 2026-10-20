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
#ifndef HPAE_AUDIOFORMAT_CONVERTER_H
#define HPAE_AUDIOFORMAT_CONVERTER_H
#include "audio_stream_info.h"
#include "hpae_plugin_node.h"
#include "channel_converter.h"
#include "audio_proresampler.h"
#ifdef ENABLE_HOOK_PCM
    #include "hpae_pcm_dumper.h"
#endif
namespace OHOS {
namespace AudioStandard {
namespace HPAE {
class HpaeAudioFormatConverterNode : public HpaePluginNode {
public:
    HpaeAudioFormatConverterNode(HpaeNodeInfo preNodeInfo, HpaeNodeInfo nodeInfo);
    virtual ~HpaeAudioFormatConverterNode();
    void RegisterCallback(INodeFormatInfoCallback *callback);
    void DoProcess() override;
    void ConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>> &preNode, HpaeNodeInfo &nodeInfo) override;
    void DisConnectWithInfo(const std::shared_ptr<OutputNode<HpaePcmBuffer*>> &preNode,
        HpaeNodeInfo &nodeInfo) override;
    uint64_t GetLatency(uint32_t sessionId = 0) override;
    void SetDownmixNormalization(bool normalizing);
    void SetUpmixCoef(float coef);
    void FlushBuffers();
    void SetSourceBufferType(HpaeSourceBufferType type);
protected:
    HpaePcmBuffer* SignalProcess(const std::vector<HpaePcmBuffer*>& inputs) override;
private:
    bool CheckUpdateInInfo(HpaePcmBuffer *input);
    bool CheckUpdateOutInfo();
    void CheckAndUpdateInfo(HpaePcmBuffer *input);
    void UpdateTmpOutPcmBufferInfo(const PcmBufferInfo &outPcmBufferInfo);

    // --- Dual-buffer mechanism for non-standard sample rate handling ---
    bool AppendToUnprocessedBuffer(const float *data, uint32_t frameLen, uint32_t channels);
    bool AppendToProcessedBuffer(const float *data, uint32_t frameLen, uint32_t channels);
    void PullAheadUntilThresholdOrFailure(uint32_t inputFrameLen);
    void ProcessResampleLoop();
    bool ExtractOutputFromProcessedBuffer();
    bool RemoveConsumedInputFrames(uint32_t consumedFrames, uint32_t channels);
    bool CompactProcessedBuffer(uint32_t channels);
    bool CanAppendProcessedFrames(uint32_t frames, uint32_t channels);
    bool CanAcceptInputFrames(uint32_t frames, uint32_t channels) const;
    void MoveUnprocessedToProcessed(uint32_t channels);
    bool TryPullOneFrame();
    uint32_t CalculateResamplerInputThreshold() const;
    void InitDualBuffer();
    int32_t ResampleWithChannelConversion(float *srcData, uint32_t inFrameLen,
        float *dstData, uint32_t outFrameLen, uint32_t resamplerChannels, ProResampler::ProcessResult &result);

    // --- Refactoring helpers (sub-50-line extraction targets) ---
    void ProcessSameRateChannelConversion(uint32_t inCh, uint32_t outCh);
    void ProcessDiffRateResample(uint32_t inCh, uint32_t outCh, uint32_t inRate, uint32_t outRate);
    void AccumulateInputAndPullAhead(HpaePcmBuffer *input);
    HpaePcmBuffer* ProcessAndExtractOutput(HpaePcmBuffer *input);
    void ReconfigTmpOutForChannelConversion(uint32_t inCh, uint32_t outCh, uint32_t maxOutFrames);
    bool UpdateOutChannelInfo(uint32_t numChannels, AudioChannelLayout channelLayout);

    PcmBufferInfo pcmBufferInfo_;
    HpaePcmBuffer converterOutput_;
    HpaeNodeInfo preNodeInfo_;
    std::unique_ptr<ProResampler> resampler_ = nullptr;
    ChannelConverter channelConverter_;
    HpaePcmBuffer tmpOutBuf_; // cache between resample and converter
    // if there is render effect, the effect node decides the output format of converter node
    INodeFormatInfoCallback *nodeFormatInfoCallback_ = nullptr;

    // Unprocessed input accumulation buffer (interleaved float, input sample rate)
    std::vector<float> unprocessedBuffer_;
    Onset579::Spans unprocessedOrigins579_;
    Onset579::Spans processedOrigins579_;
    uint32_t unprocessedFrames_ = 0;
    bool resamplerFailed_ = false;
    uint32_t bufferedState_ = PCM_BUFFER_STATE_INVALID;

    // Processed output buffer (interleaved float, output sample rate)
    std::vector<float> processedBuffer_;
    uint32_t processedFrames_ = 0;
    uint32_t processedReadPos_ = 0;

    // Threshold: minimum input frames to trigger a resampler call
    // 441 for 11025Hz, 801 for 8010Hz, 960 for 48000Hz
    uint32_t resamplerInputThreshold_ = 0;

    // 20ms output frame count at output sample rate (e.g., 960 for 48000Hz)
    uint32_t outputFrameLen20ms_ = 0;

    // Temporary buffer for resampler output (sized per call, reused)
    std::vector<float> resamplerOutBuf_;

    // Pull-ahead credit counter: caps upstream pulls to prevent buffer bloat.
    // Decremented on each successful pull, incremented when output is consumed downstream.
    uint32_t pullAheadCredit_ = 0;
    uint32_t pullAheadMaxCredit_ = 0;

    float frameLenInMs_ = 0.0f;
#ifdef ENABLE_HOOK_PCM
    std::unique_ptr<HpaePcmDumper> outputPcmDumper_ = nullptr;
#endif
};

} // HPAE
} // AudioStandard
} // OHOS
#endif
