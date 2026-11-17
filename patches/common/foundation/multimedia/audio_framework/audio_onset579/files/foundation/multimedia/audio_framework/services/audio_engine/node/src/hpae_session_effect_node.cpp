/*
 * Copyright (c) 2026 Huawei Device Co., Ltd.
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
#define LOG_TAG "HpaeSessionEffectNode"
#endif

#include "hpae_session_effect_node.h"
#include "audio_engine_log.h"
#include "hpae_node_common.h"
#include <algorithm>
#include <atomic>
#include <cinttypes>
#include <limits>

namespace OHOS {
namespace AudioStandard {
namespace HPAE {

namespace {
static constexpr uint32_t BACKOFF_MULTIPLIER = 2;
static constexpr uint32_t PREHEAT_NO_DATA_TIMEOUT_MS = 100;
static constexpr uint32_t RAW_BYPASS_FIFO_EXTRA_FRAMES = 2;
static constexpr uint32_t RAW_BYPASS_FIFO_MIN_FRAMES = 2;
static constexpr uint32_t RAW_BYPASS_FULL_WAIT_MS = 1;
static constexpr uint32_t RAW_BYPASS_POP_WAIT_MS = 5;

bool GetBytesPerFrame(size_t channels, size_t &bytesPerFrame)
{
    if (channels == 0 || channels > std::numeric_limits<size_t>::max() / sizeof(float)) {
        return false;
    }
    bytesPerFrame = channels * sizeof(float);
    return true;
}

bool GetPcmByteLen(size_t frameLen, size_t channels, size_t &byteLen)
{
    size_t sampleCount = 0;
    if (channels == 0 || frameLen > std::numeric_limits<size_t>::max() / channels) {
        return false;
    }
    sampleCount = frameLen * channels;
    if (sampleCount > std::numeric_limits<size_t>::max() / sizeof(float)) {
        return false;
    }
    byteLen = sampleCount * sizeof(float);
    return true;
}

bool HasValidPcmInput(const std::vector<HpaePcmBuffer *> &inputs)
{
    return !inputs.empty() && inputs[0] != nullptr && inputs[0]->IsValid();
}

} // namespace

static const char *StatusToString(HpaeSessionEffectNode::STATUS s)
{
    switch (s) {
        case HpaeSessionEffectNode::STATUS::IDLE: return "IDLE";
        case HpaeSessionEffectNode::STATUS::WARMING_UP: return "WARMING_UP";
        case HpaeSessionEffectNode::STATUS::INTERCEPTING: return "INTERCEPTING";
        case HpaeSessionEffectNode::STATUS::ACTIVE: return "ACTIVE";
        case HpaeSessionEffectNode::STATUS::STOPPING: return "STOPPING";
        default: return "UNKNOWN";
    }
}

HpaeSessionEffectNode::HpaeSessionEffectNode(HpaeNodeInfo &nodeInfo)
    : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
      tailOutputBufferInfo_{nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate},
      tailOutputData_{tailOutputBufferInfo_},
      rawBypassBufferInfo_{nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate},
      rawBypassBuffer_{rawBypassBufferInfo_},
      rawBypassOutputBufferInfo_{nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate},
      rawBypassOutputData_{rawBypassOutputBufferInfo_}
{
#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeSessionEffectNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
    AUDIO_INFO_LOG("SessionId:%{public}u created", GetSessionId());
}

HpaeSessionEffectNode::~HpaeSessionEffectNode()
{
    StopPreheatThread();
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
    effectInstance_.reset();
    AUDIO_INFO_LOG("SessionId:%{public}u destructing", GetSessionId());
}

HpaePcmBuffer *HpaeSessionEffectNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    if (inputs.empty() || inputs[0] == nullptr) {
        return nullptr;
    }

    // --- Phase 3C: Close SE crossfade ---
    if (closeCrossfadePending_) {
        return ProcessCloseCrossfade(inputs);
    }

    HpaePcmBuffer *result = nullptr;

    STATUS processingStatus = status_;
    if (!effectInstance_) {
        result = inputs[0];
    } else {
        switch (processingStatus) {
            case STATUS::IDLE:
                result = inputs[0];
                break;
            case STATUS::WARMING_UP:
                result = &silenceData_;
                break;
            case STATUS::INTERCEPTING:
                result = ProcessIntercepting(inputs);
                break;
            case STATUS::ACTIVE:
                result = ProcessActive(inputs);
                break;
            case STATUS::STOPPING:
                // Closing node bypasses to upstream dry (the close crossfade block, if any,
                // was already produced while closeCrossfadePending_ was true).
                result = inputs[0];
                break;
            default:
                result = inputs[0];
                break;
        }
    }

    return result;
}

void HpaeSessionEffectNode::StartCloseCrossfade()
{
    // Only an ACTIVE effect has queued wet output worth crossfading; IDLE/other just bypass.
    closeCrossfadePending_ = effectInstance_ != nullptr && status_ == STATUS::ACTIVE;
    status_ = STATUS::STOPPING;
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessCloseCrossfade(const std::vector<HpaePcmBuffer *> &inputs)
{
    closeCrossfadePending_ = false;
    HpaePcmBuffer *dryOutput = inputs[0];
    tailOutputData_.Reset();

    size_t frameLen = dryOutput->GetFrameLen();
    size_t inputChannels = audioConfig_.inputCfg.channels;
    size_t outputChannels = audioConfig_.outputCfg.channels != 0 ?
        audioConfig_.outputCfg.channels : inputChannels;
    CHECK_AND_RETURN_RET(frameLen != 0 && inputChannels != 0 && outputChannels == inputChannels &&
        dryOutput->GetChannelCount() == inputChannels &&
        tailOutputData_.GetChannelCount() == outputChannels &&
        tailOutputData_.GetFrameLen() == frameLen, dryOutput);

    size_t byteLen = 0;
    CHECK_AND_RETURN_RET(GetPcmByteLen(frameLen, inputChannels, byteLen) &&
        byteLen <= static_cast<size_t>(std::numeric_limits<int32_t>::max()) &&
        dryOutput->DataSize() == byteLen && tailOutputData_.DataSize() == byteLen, dryOutput);

    // Drain the wet output queued before close (do NOT feed this dry block back into the
    // closing algorithm). Only a full aligned wet block is mixed; otherwise pass dry through.
    if (effectInstance_ != nullptr) {
        int32_t readRet = effectInstance_->ReadOutput(
            reinterpret_cast<uint8_t *>(tailOutputData_.GetPcmDataBuffer()), byteLen);
        if (readRet == static_cast<int32_t>(byteLen)) {
            ApplyCrossfadeMix(dryOutput->GetPcmDataBuffer(),
                tailOutputData_.GetPcmDataBuffer(), frameLen, inputChannels);
            dryOutput->SetBufferValid(true);
            dryOutput->SetBufferSilence(false);
        }
    }
    tailOutputData_.Reset();
    AccountOutput(byteLen);
    // Stay STOPPING — FinalizeClose (next queue cycle) owns the actual node deletion.
    return dryOutput;
}

bool HpaeSessionEffectNode::IsCloseCrossfadePending() const
{
    return closeCrossfadePending_;
}

uint64_t HpaeSessionEffectNode::GetLatency(uint32_t sessionId)
{
    (void)sessionId;
    if (totalBytesIn_ <= totalBytesOut_) {
        return 0;
    }
    return BytesToLatencyUs(totalBytesIn_ - totalBytesOut_);
}

uint64_t HpaeSessionEffectNode::BytesToLatencyUs(size_t bytes) const
{
    uint32_t channels = audioConfig_.inputCfg.channels;
    uint32_t sampleRate = audioConfig_.inputCfg.samplingRate;
    size_t bytesPerFrame = 0;
    if (sampleRate == 0 || !GetBytesPerFrame(channels, bytesPerFrame)) {
        return 0;
    }
    uint64_t frames = bytes / bytesPerFrame;
    return frames * 1000000ULL / sampleRate;
}

void HpaeSessionEffectNode::ResetAccounting()
{
    totalBytesIn_ = 0;
    totalBytesOut_ = 0;
    paddingBytesIn_ = 0;
    pendingRawBypassBlocks_.store(0);
    stats_.Reset();
}

void HpaeSessionEffectNode::ResetTailPaddingState()
{
    activeNoDataStart_.reset();
    activeTailPaddingFrames_ = 0;
}

void HpaeSessionEffectNode::ReconfigOutputBuffers(const AudioEffectConfig &config)
{
    uint32_t samplingRate = config.outputCfg.samplingRate != 0 ?
        config.outputCfg.samplingRate : config.inputCfg.samplingRate;
    uint32_t channels = config.outputCfg.channels != 0 ? config.outputCfg.channels : config.inputCfg.channels;
    if (samplingRate == 0 || channels == 0) {
        AUDIO_WARNING_LOG("ReconfigOutputBuffers skipped: samplingRate=%{public}u channels=%{public}u",
            samplingRate, channels);
        return;
    }

    uint32_t frameLen = static_cast<uint32_t>(CalculateFrameLenBySampleRate(samplingRate));
    uint64_t channelLayout = config.outputCfg.channelLayout != 0 ?
        config.outputCfg.channelLayout : config.inputCfg.channelLayout;
    PcmBufferInfo pcmBufferInfo(channels, frameLen, samplingRate, channelLayout);

    silenceData_.ReConfig(pcmBufferInfo);
    silenceData_.Reset();
    silenceData_.SetBufferValid(false);
    silenceData_.SetBufferSilence(true);
    silenceData_.SetSplitStreamType(GetNodeInfo().GetSplitStreamType());
    silenceData_.SetAudioStreamType(GetNodeInfo().streamType);
    silenceData_.SetAudioStreamUsage(GetNodeInfo().effectInfo.streamUsage);

    tailOutputBufferInfo_ = pcmBufferInfo;
    tailOutputData_.ReConfig(tailOutputBufferInfo_);

    HpaeNodeInfo nodeInfo = GetNodeInfo();
    nodeInfo.samplingRate = static_cast<AudioSamplingRate>(samplingRate);
    nodeInfo.channels = static_cast<AudioChannel>(channels);
    nodeInfo.frameLen = frameLen;
    nodeInfo.channelLayout = static_cast<AudioChannelLayout>(channelLayout);
    SetNodeInfo(nodeInfo);
#ifdef ENABLE_HIDUMP_DFX
    if (auto callBack = GetNodeStatusCallback().lock()) {
        callBack->OnNotifyDfxNodeInfoChanged(GetNodeId(), GetNodeInfo());
    }
#endif
    AUDIO_INFO_LOG("ReconfigOutputBuffers: samplingRate=%{public}u channels=%{public}u frameLen=%{public}u",
        samplingRate, channels, frameLen);
}

void HpaeSessionEffectNode::ReconfigRawBypassBuffers(const AudioEffectConfig &config)
{
    uint32_t samplingRate = config.inputCfg.samplingRate != 0 ?
        config.inputCfg.samplingRate : static_cast<uint32_t>(GetSampleRate());
    uint32_t channels = config.inputCfg.channels != 0 ? config.inputCfg.channels : GetChannelCount();
    uint32_t frameLen = static_cast<uint32_t>(GetFrameLen());
    CHECK_AND_RETURN_LOG(samplingRate != 0 && channels != 0 && frameLen != 0,
        "ReconfigRawBypassBuffers skipped: samplingRate=%{public}u channels=%{public}u "
        "frameLen=%{public}u", samplingRate, channels, frameLen);
    size_t frameBytes = 0;
    uint32_t rawFrames = RAW_BYPASS_FIFO_MIN_FRAMES;
    if (GetPcmByteLen(frameLen, channels, frameBytes) && frameBytes != 0) {
        size_t targetFrames = prebufTargetBytes_ / frameBytes + RAW_BYPASS_FIFO_EXTRA_FRAMES;
        rawFrames = static_cast<uint32_t>(std::max<size_t>(targetFrames, RAW_BYPASS_FIFO_MIN_FRAMES));
    }

    rawBypassBufferInfo_ = PcmBufferInfo(channels, frameLen, samplingRate,
        config.inputCfg.channelLayout, rawFrames);
    rawBypassBufferInfo_.isMultiFrames = true;
    rawBypassOutputBufferInfo_ = PcmBufferInfo(channels, frameLen, samplingRate, config.inputCfg.channelLayout);
    interceptingRawData_.assign(frameBytes / sizeof(float), 0.0f);

    {
        std::lock_guard<std::mutex> lock(rawBypassMutex_);
        rawBypassBuffer_.ReConfig(rawBypassBufferInfo_);
        rawBypassOutputData_.ReConfig(rawBypassOutputBufferInfo_);
        rawBypassBuffer_.Reset();
        rawBypassOutputData_.Reset();
    }
    rawBypassCv_.notify_all();
}

void HpaeSessionEffectNode::ClearRawBypassBuffer()
{
    {
        std::lock_guard<std::mutex> lock(rawBypassMutex_);
        rawBypassBuffer_.Reset();
        pendingRawBypassBlocks_.store(0, std::memory_order_relaxed);
    }
    rawBypassCv_.notify_all();
}

bool HpaeSessionEffectNode::WaitRawBypassBufferWritable()
{
    std::unique_lock<std::mutex> lock(rawBypassMutex_);
    rawBypassCv_.wait_for(lock, std::chrono::milliseconds(RAW_BYPASS_FULL_WAIT_MS), [this]() {
        return stopRequested_.load() || rawBypassBuffer_.GetCurFrames() < rawBypassBuffer_.GetFrames();
    });
    return !stopRequested_.load() && rawBypassBuffer_.GetCurFrames() < rawBypassBuffer_.GetFrames();
}

bool HpaeSessionEffectNode::PushRawBypassBuffer(HpaePcmBuffer *buf)
{
    CHECK_AND_RETURN_RET(buf != nullptr && buf->IsValid(), false);
    // Bypass not required yet (first warmup): succeed without enqueueing upstream data.
    CHECK_AND_RETURN_RET(!rawBypassNeeded_, true);
    bool pushed = false;
    {
        std::lock_guard<std::mutex> lock(rawBypassMutex_);
        if (rawBypassBuffer_.GetCurFrames() < rawBypassBuffer_.GetFrames()) {
            pushed = rawBypassBuffer_.PushFrameData(*buf);
        }
    }
    if (pushed) {
        rawBypassCv_.notify_all();
    }
    return pushed;
}

HpaePcmBuffer *HpaeSessionEffectNode::PopRawBypassBuffer()
{
    CHECK_AND_RETURN_RET(!rawBypassNeeded_, nullptr);
    std::unique_lock<std::mutex> lock(rawBypassMutex_);
    auto hasData = [this]() { return stopRequested_.load() || rawBypassBuffer_.GetCurFrames() > 0; };
    if (rawBypassBuffer_.GetCurFrames() == 0) {
        rawBypassCv_.wait_for(lock, std::chrono::milliseconds(RAW_BYPASS_POP_WAIT_MS), hasData);
    }
    bool popped = rawBypassBuffer_.GetFrameData(rawBypassOutputData_);
    CHECK_AND_RETURN_RET(popped, nullptr);
    rawBypassOutputData_.SetBufferValid(true);
    rawBypassOutputData_.SetBufferSilence(false);
    rawBypassOutputData_.SetSplitStreamType(GetNodeInfo().GetSplitStreamType());
    rawBypassOutputData_.SetAudioStreamType(GetNodeInfo().streamType);
    rawBypassOutputData_.SetAudioStreamUsage(GetNodeInfo().effectInfo.streamUsage);
    lock.unlock();
    rawBypassCv_.notify_all();
    return &rawBypassOutputData_;
}

bool HpaeSessionEffectNode::WriteRawBypassOutput()
{
    HpaePcmBuffer *rawOut = PopRawBypassBuffer();
    CHECK_AND_RETURN_RET(rawOut != nullptr, false);
    outputStream_.WriteDataToOutput(ProcessRawBypassOutput(rawOut));
    return true;
}

bool HpaeSessionEffectNode::HandleWarmingUpRawBypass()
{
    if (prebufFilled_.load()) {
        AUDIO_INFO_LOG("[SE::SessionEffectNode] WARMING_UP->INTERCEPTING reason=prebuffer filled "
            "sessionId=%{public}u prebufBytes=%{public}zu",
            GetSessionId(), prebufTargetBytes_);
        status_ = STATUS::INTERCEPTING;
        return false;
    }
    if (!WriteRawBypassOutput()) {
        stats_.underrunCount++;
        outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
    }
    return true;
}

int32_t HpaeSessionEffectNode::CreateEffectWithInstance(const std::string &effectName,
    std::shared_ptr<IEffectInstance> instance, const AudioEffectConfig &config,
    bool aissSwitchEnabled)
{
    if (instance == nullptr) {
        return static_cast<int32_t>(SessionEffectErrCode::ERR_EFFECT_CREATE_FAILED);
    }
    effectInstance_ = std::move(instance);
    effectName_ = effectName;
    audioConfig_ = config;
    ReconfigOutputBuffers(config);
    UpdatePrebufTargetBytes();
    ReconfigRawBypassBuffers(config);
    // SetAissEnabledSync enables algorithm routing (raw bypass off) during first warmup; other
    // create paths (move-stream / attach-state rebind) keep the default raw bypass on. Algorithm
    // output or a stop transitions it back on (see PreheatThreadFunc / ProcessInterceptingRaw).
    if (aissSwitchEnabled) {
        rawBypassNeeded_ = false;
    }
    AUDIO_INFO_LOG("create effect with instance %{public}s", effectName.c_str());
    return 0;
}

int32_t HpaeSessionEffectNode::DropEffect()
{
    StopPreheatThread();  // Always join if joinable
    if (effectInstance_) {
        effectInstance_->Flush();
        effectInstance_->StopEffect();  // DISABLE if not already
    }
    AUDIO_INFO_LOG("[SE::SessionEffectNode] %s→IDLE reason=DropEffect sessionId=%{public}u",
        StatusToString(status_), GetSessionId());
    effectInstance_.reset();
    status_ = STATUS::IDLE;
    prebufTargetBytes_ = 0;
    preheatSuspendedForGraphSwitch_ = false;
    ClearRawBypassBuffer();
    ResetAccounting();
    ResetTailPaddingState();
    return 0;
}

int32_t HpaeSessionEffectNode::DetachEffectForReload()
{
    StopPreheatThread();
    // Reload keeps the logical binding alive; skip StopEffect and reset runtime state for fresh recreation.
    AUDIO_INFO_LOG("[SE::SessionEffectNode] %s→IDLE reason=ReloadDetach sessionId=%{public}u",
        StatusToString(status_), GetSessionId());
    effectInstance_.reset();
    status_ = STATUS::IDLE;
    closeCrossfadePending_ = false;
    isPaused_ = false;
    preheatSuspendedForGraphSwitch_ = false;
    stopRequested_ = false;
    prebufFilled_.store(false);
    warmupStartTime_ = std::chrono::steady_clock::time_point {};
    pauseAccumulatedUs_ = 0;
    pauseStartTime_ = std::chrono::steady_clock::time_point {};
    preheatNoDataStartTime_ = std::chrono::steady_clock::time_point {};
    prebufTargetBytes_ = 0;
    ClearRawBypassBuffer();
    ResetAccounting();
    ResetTailPaddingState();
    return 0;
}

std::shared_ptr<IEffectInstance> HpaeSessionEffectNode::GetEffectInstance() const
{
    return effectInstance_;
}

std::string HpaeSessionEffectNode::GetEffectName() const
{
    return effectName_;
}

AudioEffectConfig HpaeSessionEffectNode::GetAudioConfig() const
{
    return audioConfig_;
}

size_t HpaeSessionEffectNode::GetPrebufTargetBytes() const
{
    return prebufTargetBytes_;
}

void HpaeSessionEffectNode::UpdatePrebufTargetBytes()
{
    prebufTargetBytes_ = 0;
    if (effectInstance_ == nullptr) {
        return;
    }

    uint32_t preheatFrames = effectInstance_->GetPreheatFrames();
    size_t frameLen = GetFrameLen();
    size_t frameBytes = 0;
    if (!GetPcmByteLen(frameLen, audioConfig_.inputCfg.channels, frameBytes)) {
        AUDIO_WARNING_LOG("UpdatePrebufTargetBytes failed: frameLen=%{public}zu channels=%{public}u",
            frameLen, audioConfig_.inputCfg.channels);
        return;
    }
    if (frameBytes != 0 && preheatFrames > std::numeric_limits<size_t>::max() / frameBytes) {
        AUDIO_WARNING_LOG("UpdatePrebufTargetBytes overflow: preheatFrames=%{public}u frameBytes=%{public}zu",
            preheatFrames, frameBytes);
        return;
    }

    prebufTargetBytes_ = static_cast<size_t>(preheatFrames) * frameBytes;
    AUDIO_INFO_LOG("Prebuf target=%{public}zu preheatFrames=%{public}u",
        prebufTargetBytes_, preheatFrames);
}

void HpaeSessionEffectNode::RestartPreheat()
{
    stopRequested_ = false;
    prebufFilled_ = false;
    ClearRawBypassBuffer();
    if (prebufTargetBytes_ > 0) {
        StartPreheatThread();
    } else {
        prebufFilled_ = true;
    }
}

void HpaeSessionEffectNode::NotifyPreheatStateChanged(bool active)
{
    auto callback = GetNodeInfo().statusCallback.lock();
    if (callback) {
        callback->OnSessionEffectPreheatStateChanged(GetSessionId(), active);
    }
}

int32_t HpaeSessionEffectNode::StartEffect()
{
    if (!effectInstance_) return 0;

    // Resume from pause
    if (isPaused_) {
        isPaused_ = false;
        auto now = std::chrono::steady_clock::now();
        pauseAccumulatedUs_ += static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(now - pauseStartTime_).count());

        if (status_ == STATUS::WARMING_UP) {
            // Restart preheat thread with the target computed at effect creation.
            RestartPreheat();
            ResetTailPaddingState();
            AUDIO_INFO_LOG("StartEffect resume: WARMING_UP, restart preheat, prebuf=%{public}zu",
                prebufTargetBytes_);
        } else {
            // INTERCEPTING / ACTIVE: just clear isPaused_, DoProcess resumes naturally
            AUDIO_INFO_LOG("StartEffect resume: status=%{public}d", static_cast<int>(status_));
        }
        return 0;
    }

    // A closing (STOPPING) node must not be re-warmed by Start; FinalizeClose still owns its
    // deletion. (A paused-STOPPING node already cleared isPaused_ via the resume branch above.)
    CHECK_AND_RETURN_RET(status_ != STATUS::STOPPING, 0);

    AUDIO_INFO_LOG("StartEffect: prebufTargetBytes_=%{public}zu", prebufTargetBytes_);

    // Keep warmup timestamp for pause/resume bookkeeping; skip is based on raw bypass blocks.
    warmupStartTime_ = std::chrono::steady_clock::now();
    pauseAccumulatedUs_ = 0;

    // Enter WARMING_UP and start preheat thread (skip if no preheat needed)
    status_ = STATUS::WARMING_UP;
    ResetTailPaddingState();
    RestartPreheat();

    return 0;
}

int32_t HpaeSessionEffectNode::PauseEffect()
{
    if (!effectInstance_) return 0;

    // Join preheat thread if running (WARMING_UP)
    if (status_ == STATUS::WARMING_UP) {
        StopPreheatThread();
    }
    ClearRawBypassBuffer();

    // Set paused flag — status_ preserved for resume
    isPaused_ = true;
    pauseStartTime_ = std::chrono::steady_clock::now();

    // Key: do NOT call effectInstance_->StopEffect() (no DISABLE)
    // This preserves algorithm state and caches for resume
    AUDIO_INFO_LOG("PauseEffect: paused, status=%{public}d", static_cast<int>(status_));
    return 0;
}

int32_t HpaeSessionEffectNode::FlushEffect()
{
    if (!effectInstance_) return 0;
    int32_t ret = effectInstance_->Flush();
    pauseAccumulatedUs_ = 0;
    ClearRawBypassBuffer();
    ResetAccounting();
    ResetTailPaddingState();

    if (isPaused_) {
        // Paused: reset to IDLE, clear isPaused_ (Seek scenario → full restart on next Start)
        status_ = STATUS::IDLE;
        isPaused_ = false;
        AUDIO_INFO_LOG("FlushEffect: paused → reset to IDLE");
    } else if (status_ == STATUS::WARMING_UP) {
        // WARMING_UP: stop preheat thread first (avoid data race), then restart preheat
        StopPreheatThread();
        warmupStartTime_ = std::chrono::steady_clock::now();
        RestartPreheat();
        AUDIO_INFO_LOG("FlushEffect: WARMING_UP restart preheat, prebufTarget=%{public}zu", prebufTargetBytes_);
    } else if (status_ == STATUS::INTERCEPTING || status_ == STATUS::ACTIVE) {
        status_ = STATUS::WARMING_UP;
        ResetTailPaddingState();
        warmupStartTime_ = std::chrono::steady_clock::now();
        RestartPreheat();
        AUDIO_INFO_LOG("FlushEffect: restart preheat, prebufTarget=%{public}zu", prebufTargetBytes_);
    }
    // IDLE + not paused: only reset counters (already done above)

    return ret;
}

int32_t HpaeSessionEffectNode::SetParameter(int32_t type, float value)
{
    return effectInstance_ ? effectInstance_->SetParameter(type, value) : 0;
}

void HpaeSessionEffectNode::DoProcess()
{
    // Paused: output silence, don't pull upstream
    if (isPaused_) {
        outputStream_.WriteDataToOutput(PrepareSilenceBuffer(silenceData_));
        return;
    }

    // Auto-trigger IDLE→WARMING_UP on first DoProcess when effect instance is bound
    if (status_ == STATUS::IDLE && effectInstance_ != nullptr) {
        StartEffect();
    }

    if (status_ == STATUS::WARMING_UP && HandleWarmingUpRawBypass()) {
        return;
    }
    if (status_ == STATUS::INTERCEPTING) {
        HpaePcmBuffer *rawOut = PopRawBypassBuffer();
        if (rawOut != nullptr) {
            outputStream_.WriteDataToOutput(ProcessInterceptingRaw(rawOut, false));
            return;
        }
    }

    // Normal flow: pull upstream → SignalProcess (with timing)
    auto t0 = std::chrono::steady_clock::now();
    HpaePcmBuffer *tempOut = nullptr;
    std::vector<HpaePcmBuffer *> &preOutputs = inputStream_.ReadPreOutputData();
    bool hasInput = !preOutputs.empty() && preOutputs[0] != nullptr;
    if (hasInput) {
        tempOut = enableProcess_ ? SignalProcess(preOutputs) : preOutputs[0];
    } else if (!enableProcess_) {
        tempOut = SignalProcess(preOutputs);
    } else if (!hasInput && status_ == STATUS::ACTIVE) {
        tempOut = ProcessActiveNoInput();
    }
    outputStream_.WriteDataToOutput(tempOut != nullptr ? tempOut : &silenceData_);
    auto dt = std::chrono::steady_clock::now() - t0;
    float ms = std::chrono::duration<float, std::milli>(dt).count();
    stats_.lastProcessMs = ms;
    if (ms > stats_.maxProcessMs) {
        stats_.maxProcessMs = ms;
    }

    // Threshold report
    if (stats_.framesProcessed >= statsReportThreshold_ && statsReportThreshold_ > 0) {
        AUDIO_INFO_LOG("[SE::SessionEffectNode] stats: %{public}s sessionId=%{public}u",
            stats_.ToString().c_str(), GetSessionId());
        stats_.Reset();
    }
}

void HpaeSessionEffectNode::StartPreheatThread()
{
    if (preheatThread_.joinable()) {
        StopPreheatThread();
    }
    stopRequested_ = false;
    NotifyPreheatStateChanged(true); // set flag before spawn so the thread cannot pull before it takes effect
    preheatThread_ = std::thread(&HpaeSessionEffectNode::PreheatThreadFunc, this);
    AUDIO_INFO_LOG("PreheatThread started for %{public}s", effectName_.c_str());
}

void HpaeSessionEffectNode::PreheatThreadFunc()
{
    AUDIO_INFO_LOG("PreheatThread running, actively pulling upstream data");
    uint32_t backoffMs = 0;
    bool noDataTimerActive = false;
    std::chrono::steady_clock::time_point noDataStartTime;

    while (!stopRequested_) {
        if (effectInstance_ == nullptr) {
            AUDIO_WARNING_LOG("PreheatThread exiting: effectInstance is null");
            break;
        }
        CHECK_AND_CONTINUE(WaitRawBypassBufferWritable());

        std::vector<HpaePcmBuffer *> &upstreamData = inputStream_.ReadPreOutputData();

        bool hasData = HasValidPcmInput(upstreamData);
        if (hasData) {
            bool pushed = PushRawBypassBuffer(upstreamData[0]);
            size_t fedBytes = pushed ? FeedInputFromBuffer(upstreamData[0]) : 0;
            if (fedBytes > 0) {
                noDataTimerActive = false;
                backoffMs = 0;
            } else {
                OnNoDataReceived(noDataTimerActive, noDataStartTime, backoffMs);
            }
        } else {
            OnNoDataReceived(noDataTimerActive, noDataStartTime, backoffMs);
        }

        if (stopRequested_) {
            break;
        }

        size_t inputLevel = effectInstance_->GetInputLevel();
        if (inputLevel >= prebufTargetBytes_) {
            AUDIO_INFO_LOG("Prebuf filled: %{public}zu >= %{public}zu",
                inputLevel, prebufTargetBytes_);
            break;
        }
        if (noDataTimerActive && HandleNoDataTimeout(inputLevel)) {
            break;
        }
    }

    rawBypassNeeded_ = rawBypassNeeded_ || stopRequested_;
    prebufFilled_.store(true);
    AUDIO_INFO_LOG("PreheatThread exiting, stopRequested=%{public}d", stopRequested_.load());
}

void HpaeSessionEffectNode::OnNoDataReceived(bool &noDataTimerActive,
    std::chrono::steady_clock::time_point &noDataStartTime, uint32_t &backoffMs)
{
    static constexpr uint32_t MAX_BACKOFF_MS = 20;

    if (!noDataTimerActive) {
        noDataTimerActive = true;
        noDataStartTime = std::chrono::steady_clock::now();
        preheatNoDataStartTime_ = noDataStartTime;
    }
    backoffMs = backoffMs == 0 ? 1 : std::min(backoffMs * BACKOFF_MULTIPLIER, MAX_BACKOFF_MS);
    std::this_thread::sleep_for(std::chrono::milliseconds(backoffMs));
}

bool HpaeSessionEffectNode::HandleNoDataTimeout(size_t inputLevel)
{
    auto noDataDuration = std::chrono::steady_clock::now() - preheatNoDataStartTime_;
    if (noDataDuration < std::chrono::milliseconds(PREHEAT_NO_DATA_TIMEOUT_MS)) {
        return false;
    }
    if (stopRequested_) {
        return true;
    }
    if (inputLevel >= prebufTargetBytes_) {
        return true;
    }
    size_t paddingBytes = prebufTargetBytes_;
    paddingBytes -= inputLevel;
    int32_t ret = FeedPaddingInput(paddingBytes);
    if (ret != 0) {
        AUDIO_WARNING_LOG("PreheatThread FeedPaddingInput failed: %{public}d", ret);
    }
    AUDIO_INFO_LOG("PreheatThread no-data timeout, padding=%{public}zu", paddingBytes);
    return true;
}

void HpaeSessionEffectNode::StopPreheatThread()
{
    if (!preheatThread_.joinable()) return;
    stopRequested_ = true;
    rawBypassCv_.notify_all();
    preheatThread_.join();
    AUDIO_INFO_LOG("PreheatThread joined");
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessIntercepting(const std::vector<HpaePcmBuffer *> &inputs)
{
    CHECK_AND_RETURN_RET(!inputs.empty(), &silenceData_);
    return ProcessInterceptingRaw(inputs[0], true);
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessRawBypassOutput(HpaePcmBuffer *rawBuf)
{
    CHECK_AND_RETURN_RET(rawBuf != nullptr, &silenceData_);
    size_t byteLen = 0;
    CHECK_AND_RETURN_RET(GetPcmByteLen(rawBuf->GetFrameLen(), audioConfig_.inputCfg.channels, byteLen), &silenceData_);
    rawBuf->SetBufferValid(true);
    rawBuf->SetBufferSilence(false);
    AccountOutput(byteLen);
    pendingRawBypassBlocks_.fetch_add(1, std::memory_order_relaxed);
    return rawBuf;
}

void HpaeSessionEffectNode::ConsumePendingRawBypassBlocks(size_t skipRequest, uint32_t skipRemaining)
{
    size_t remaining = std::min<size_t>(skipRemaining, skipRequest);
    size_t consumed = skipRequest - remaining;
    if (consumed == 0) {
        return;
    }

    size_t current = pendingRawBypassBlocks_.load(std::memory_order_relaxed);
    while (current > 0) {
        size_t next = current > consumed ? current - consumed : 0;
        CHECK_AND_RETURN(!pendingRawBypassBlocks_.compare_exchange_weak(current, next, std::memory_order_relaxed));
    }
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessInterceptingRaw(HpaePcmBuffer *inputBuf, bool feedInput)
{
    CHECK_AND_RETURN_RET(inputBuf != nullptr && effectInstance_ != nullptr, &silenceData_);
    size_t channels = audioConfig_.inputCfg.channels;
    size_t byteLen = 0;
    CHECK_AND_RETURN_RET(GetPcmByteLen(inputBuf->GetFrameLen(), channels, byteLen), &silenceData_);

    size_t sampleCount = static_cast<size_t>(inputBuf->GetFrameLen()) * channels;
    CHECK_AND_RETURN_RET(interceptingRawData_.size() >= sampleCount, &silenceData_);

    std::copy_n(inputBuf->GetPcmDataBuffer(), sampleCount, interceptingRawData_.data());
    if (feedInput) {
        FeedInputFromBuffer(inputBuf);
    }

    size_t skipRequest = pendingRawBypassBlocks_.load(std::memory_order_relaxed);
    skipRequest = std::min<size_t>(skipRequest, std::numeric_limits<uint32_t>::max());
    uint32_t skipFrames = static_cast<uint32_t>(skipRequest);
    int32_t ret = effectInstance_->ReadOutput(
        reinterpret_cast<uint8_t *>(inputBuf->GetPcmDataBuffer()), byteLen,
        &skipFrames);
    ConsumePendingRawBypassBlocks(skipRequest, skipFrames);
    if (ret > 0) {
        inputBuf->Origins579().Unknown(); // actual opaque delayed/wet algorithm output
        inputBuf->SetBufferValid(true);
        inputBuf->SetBufferSilence(false);
        ApplyInterceptingFadeIn(inputBuf->GetPcmDataBuffer(), interceptingRawData_.data(), sampleCount);
        status_ = STATUS::ACTIVE;
        rawBypassNeeded_ = true;
        pendingRawBypassBlocks_.store(0);
        AccountOutput(byteLen);
        NotifyPreheatStateChanged(false);
        return inputBuf;
    }
    CHECK_AND_RETURN_RET(!rawBypassNeeded_, PrepareSilenceBuffer(silenceData_));
    std::copy_n(interceptingRawData_.data(), sampleCount, inputBuf->GetPcmDataBuffer());
    return ProcessRawBypassOutput(inputBuf);
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessActive(const std::vector<HpaePcmBuffer *> &inputs)
{
    HpaePcmBuffer *inputBuf = inputs[0];
    size_t channels = audioConfig_.inputCfg.channels;
    size_t byteLen = inputBuf->GetFrameLen() * channels * sizeof(float);

    // Continue feeding upstream data to algorithm
    size_t fedBytes = FeedInputFromBuffer(inputBuf);
    if (fedBytes > 0) {
        ResetTailPaddingState();
    }

    HpaePcmBuffer *output = ReadAlgoOutput(inputBuf, byteLen);
    if (output == inputBuf) {
        AccountOutput(byteLen);
    }
    return output;
}

HpaePcmBuffer *HpaeSessionEffectNode::ProcessActiveNoInput()
{
    if (!effectInstance_ || status_ != STATUS::ACTIVE) {
        return PrepareSilenceBuffer(silenceData_);
    }

    size_t channels = tailOutputData_.GetChannelCount();
    if (audioConfig_.inputCfg.channels != channels) {
        AUDIO_WARNING_LOG("ProcessActiveNoInput channel mismatch: config=%{public}u buffer=%{public}zu",
            audioConfig_.inputCfg.channels, channels);
        return PrepareSilenceBuffer(silenceData_);
    }
    size_t byteLen = 0;
    if (!GetPcmByteLen(tailOutputData_.GetFrameLen(), channels, byteLen)) {
        return PrepareSilenceBuffer(silenceData_);
    }

    auto now = std::chrono::steady_clock::now();
    if (!activeNoDataStart_.has_value()) {
        activeNoDataStart_ = now;
    } else {
        auto noDataDuration = std::chrono::duration_cast<std::chrono::milliseconds>(now - *activeNoDataStart_);
        if (noDataDuration >= std::chrono::milliseconds(ACTIVE_NO_DATA_PADDING_DELAY_MS) &&
            activeTailPaddingFrames_ < ACTIVE_TAIL_PADDING_MAX_FRAMES) {
            int32_t ret = FeedPaddingInput(byteLen);
            activeTailPaddingFrames_++;
            (void)ret;
        }
    }

    tailOutputData_.Reset();
    tailOutputData_.SetBufferValid(true);
    tailOutputData_.SetBufferSilence(false);
    HpaePcmBuffer *output = ReadAlgoOutput(&tailOutputData_, byteLen);
    if (output != &silenceData_) {
        AccountOutput(byteLen);
    }
    return output;
}

size_t HpaeSessionEffectNode::FeedInputFromBuffer(HpaePcmBuffer *buf)
{
    if (buf == nullptr || !buf->IsValid() || effectInstance_ == nullptr) {
        return 0;
    }

    size_t channels = audioConfig_.inputCfg.channels;
    size_t byteLen = 0;
    if (!GetPcmByteLen(buf->GetFrameLen(), channels, byteLen)) {
        return 0;
    }
    if (byteLen > 0) {
        int32_t ret = effectInstance_->FeedInput(
            reinterpret_cast<const uint8_t *>(buf->GetPcmDataBuffer()), byteLen);
        if (ret != 0) {
            AUDIO_WARNING_LOG("FeedInput failed: %{public}d", ret);
            stats_.processErrors++;
            return 0;
        }
        totalBytesIn_ += byteLen;
        size_t bytesPerFrame = 0;
        if (GetBytesPerFrame(audioConfig_.inputCfg.channels, bytesPerFrame)) {
            stats_.framesProcessed += static_cast<int64_t>(byteLen / bytesPerFrame);
        }
        return byteLen;
    }
    return 0;
}

int32_t HpaeSessionEffectNode::FeedPaddingInput(size_t byteLen)
{
    if (!effectInstance_ || byteLen == 0) {
        return 0;
    }

    uint32_t sampleRate = audioConfig_.inputCfg.samplingRate;
    size_t paddingFrameLen = static_cast<size_t>(CalculateFrameLenBySampleRate(sampleRate));
    size_t channels = audioConfig_.inputCfg.channels;
    size_t chunkByteLen = 0;
    CHECK_AND_RETURN_RET_LOG((GetPcmByteLen(paddingFrameLen, channels, chunkByteLen) && chunkByteLen != 0), -1,
        "FeedPaddingInput invalid chunk: channels=%{public}u", audioConfig_.inputCfg.channels);
    std::vector<uint8_t> padding(chunkByteLen, 0);
    size_t remaining = byteLen;
    while (remaining > 0) {
        size_t cur = std::min(remaining, chunkByteLen);
        int32_t ret = effectInstance_->FeedInput(padding.data(), cur);
        if (ret != 0) {
            AUDIO_WARNING_LOG("FeedPaddingInput failed: %{public}d", ret);
            stats_.processErrors++;
            return ret;
        }
        paddingBytesIn_ += cur;
        remaining -= cur;
    }
    return 0;
}

void HpaeSessionEffectNode::AccountOutput(size_t byteLen)
{
    totalBytesOut_ += byteLen;
    size_t bytesPerFrame = 0;
    if (GetBytesPerFrame(audioConfig_.inputCfg.channels, bytesPerFrame)) {
        stats_.framesOutput += static_cast<int64_t>(byteLen / bytesPerFrame);
    }
}

HpaePcmBuffer *HpaeSessionEffectNode::ReadAlgoOutput(HpaePcmBuffer *inputBuf, size_t byteLen)
{
    int32_t ret = effectInstance_->ReadOutput(
        reinterpret_cast<uint8_t *>(inputBuf->GetPcmDataBuffer()), byteLen);
    if (ret > 0) {
        inputBuf->Origins579().Unknown(); // actual opaque delayed/wet algorithm output
        inputBuf->SetBufferValid(true);
        inputBuf->SetBufferSilence(false);
        return inputBuf;
    }
    // No output → return silence
    stats_.underrunCount++;
    return PrepareSilenceBuffer(silenceData_);
}

void HpaeSessionEffectNode::CloseSessionEffectCore()
{
    // Step 1: Join preheat thread if running
    StopPreheatThread();

    // Step 2: Calculate pipeline latency and trigger RewindBuffer callback
    uint64_t latencyUs = GetLatency();
    if (latencyUs > 0) {
        auto callback = GetNodeInfo().statusCallback.lock();
        if (callback) {
            callback->OnRewindBuffer(GetSessionId(), latencyUs);
            AUDIO_INFO_LOG("CloseSE: OnRewindBuffer sessionId=%{public}u latency=%{public}" PRIu64 "us",
                GetSessionId(), latencyUs);
        }
    }

    // Step 3: Flush algorithm caches (StopEffect is NOT called here intentionally;
    // it will be called by DropEffect or destructor which follows this function)
    if (effectInstance_) {
        effectInstance_->Flush();
    }
    ResetAccounting();
    // Step 4: Enter bypass mode
    ClearRawBypassBuffer();
    status_ = STATUS::IDLE;
    isPaused_ = false;
    AUDIO_INFO_LOG("CloseSE: node bypass, sessionId=%{public}u", GetSessionId());
}

void HpaeSessionEffectNode::ApplyInterceptingFadeIn(float *algoOutput, const float *rawInput, size_t sampleCount)
{
    CHECK_AND_RETURN(!rawBypassNeeded_);
    for (size_t i = 0; i < sampleCount; ++i) {
        float t = static_cast<float>(i + 1) / static_cast<float>(sampleCount);
        algoOutput[i] = rawInput[i] * (1.0f - t) + algoOutput[i] * t;
    }
}

void HpaeSessionEffectNode::ApplyCrossfadeMix(float *dryOutput, const float *wetInput,
    size_t frameLen, size_t channels)
{
    // Per-frame wet→dry: t advances once per frame, shared by all channels in that frame.
    // First frame is fully wet, last frame is fully dry.
    for (size_t frame = 0; frame < frameLen; ++frame) {
        float t = static_cast<float>(frame + 1) / static_cast<float>(frameLen);
        for (size_t channel = 0; channel < channels; ++channel) {
            size_t index = frame * channels + channel;
            dryOutput[index] = wetInput[index] * (1.0f - t) + dryOutput[index] * t;
        }
    }
}

void HpaeSessionEffectNode::PrepareMoveStream()
{
    CloseSessionEffectCore();
    AUDIO_INFO_LOG("PrepareMoveStream: sessionId=%{public}u ready for move", GetSessionId());
}

void HpaeSessionEffectNode::SuspendSessionEffectPreheatForGraphSwitch()
{
    if (status_ == STATUS::WARMING_UP) {
        StopPreheatThread();
        preheatSuspendedForGraphSwitch_ = true;
        AUDIO_INFO_LOG("[SE] Preheat suspended for graph switch, session=%{public}u", GetSessionId());
    }
}

void HpaeSessionEffectNode::ResumeSessionEffectPreheatForGraphSwitch()
{
    if (!preheatSuspendedForGraphSwitch_) {
        return;
    }
    preheatSuspendedForGraphSwitch_ = false;
    if (status_ == STATUS::WARMING_UP && effectInstance_) {
        RestartPreheat();
        AUDIO_INFO_LOG("[SE] Preheat resumed after graph switch, session=%{public}u", GetSessionId());
    }
}

}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
