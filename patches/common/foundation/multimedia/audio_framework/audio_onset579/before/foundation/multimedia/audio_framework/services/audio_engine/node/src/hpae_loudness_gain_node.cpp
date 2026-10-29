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
#define LOG_TAG "HpaeLoudnessGainNode"
#endif

#include <dlfcn.h>
#include <cinttypes>
#include <cmath>
#include "hpae_loudness_gain_node.h"
#include "hpae_pcm_buffer.h"
#include "audio_utils.h"
#include "audio_errors.h"
#include "audio_effect_log.h"
#include "stream_dfx_manager.h"

namespace OHOS {
namespace AudioStandard {
namespace HPAE {
static const std::string LOUDNESSGAIN_PATH = "/system/lib64/libaudio_integration_loudness.z.so";
static constexpr float EPSILON = 1e-6f;
static constexpr float DB_TO_AMPLITUDE_BASE = 10.0f;
static constexpr float DB_TO_AMPLITUDE_DIVISOR = 20.0f;
static constexpr uint64_t DEFAULT_LATENCY_IN_US = 5000;
static const AudioEffectDescriptor LOUDNESS_DESCRIPTOR = {
    .libraryName = "loudness",
    .effectName = "loudness",
};

static inline bool IsFloatValueEqual(float a, float b)
{
    return std::abs(a - b) < EPSILON;
}

static inline float LoudnessDbToLinearGain(float loudnessGainDb)
{
    return std::pow(DB_TO_AMPLITUDE_BASE, loudnessGainDb / DB_TO_AMPLITUDE_DIVISOR);
}

HpaeLoudnessGainNode::HpaeLoudnessGainNode(HpaeNodeInfo &nodeInfo) : HpaeNode(nodeInfo), HpaePluginNode(nodeInfo),
    pcmBufferInfo_(nodeInfo.channels, nodeInfo.frameLen, nodeInfo.samplingRate, nodeInfo.channelLayout),
    loudnessGainOutput_(pcmBufferInfo_)
{
    AUDIO_INFO_LOG("created");
    dlHandle_ = dlopen(LOUDNESSGAIN_PATH.c_str(), 1);
    if (!dlHandle_) {
        AUDIO_ERR_LOG("<log error> dlopen lib %{public}s Fail", LOUDNESSGAIN_PATH.c_str());
    } else {
        AUDIO_INFO_LOG("<log info> dlopen lib %{public}s successful", LOUDNESSGAIN_PATH.c_str());
    }
    dlerror();

    audioEffectLibHandle_ = static_cast<AudioEffectLibrary *>(dlsym(dlHandle_,
        AUDIO_EFFECT_LIBRARY_INFO_SYM_AS_STR));
    if (!audioEffectLibHandle_) {
        AUDIO_ERR_LOG("<log error> dlsym failed: error: %{public}s", dlerror());
        dlclose(dlHandle_);
        dlHandle_ = nullptr;
    }
    AUDIO_INFO_LOG("<log info> dlsym lib %{public}s successful", LOUDNESSGAIN_PATH.c_str());

#ifdef ENABLE_HIDUMP_DFX
    SetNodeName("hpaeLoudnessGainNode");
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(true, GetNodeInfo());
    }
#endif
}

HpaeLoudnessGainNode::~HpaeLoudnessGainNode()
{
    if (handle_ && audioEffectLibHandle_) {
        audioEffectLibHandle_->releaseEffect(handle_);
        handle_ = nullptr;
    }
    if (dlHandle_) {
        dlclose(dlHandle_);
        dlHandle_ = nullptr;
        audioEffectLibHandle_ = nullptr;
    }
#ifdef ENABLE_HIDUMP_DFX
    AUDIO_INFO_LOG("NodeId: %{public}u NodeName: %{public}s destructed.",
        GetNodeId(), GetNodeName().c_str());
    if (auto callback = GetNodeStatusCallback().lock()) {
        callback->OnNotifyDfxNodeAdmin(false, GetNodeInfo());
    }
#endif
}

HpaePcmBuffer *HpaeLoudnessGainNode::SignalProcess(const std::vector<HpaePcmBuffer *> &inputs)
{
    Trace trace("HpaeLoudnessGainNode::SignalProcess");

    CHECK_AND_CALL_FUNC_RETURN_RET_LOG((!inputs.empty()) && inputs[0], &silenceData_,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_NULL_POINTER),
            "input is empty", false),
        "NodeId %{public}d, sessionId %{public}d input is empty", GetNodeId(), GetSessionId());

    CHECK_AND_RETURN_RET((!IsFloatValueEqual(loudnessGain_, 0.0f)), inputs[0]);
    CheckUpdateInfo(inputs[0]);
    if (!dlHandle_ || !audioEffectLibHandle_) {
        float *pcmDataBuffer = inputs[0]->GetPcmDataBuffer();
        uint32_t bufferSize = inputs[0]->GetFrameLen() * inputs[0]->GetChannelCount();
        float *dataBuffer = loudnessGainOutput_.GetPcmDataBuffer();
        for (uint32_t i = 0; i < bufferSize; i++) {
            dataBuffer[i] = pcmDataBuffer[i] * linearGain_;
        }
    } else {
        AudioBuffer inBuffer = {
            .frameLength = inputs[0]->GetFrameLen(),
            .raw = inputs[0]->GetPcmDataBuffer(),
            .metaData = nullptr
        };
        AudioBuffer outBuffer = {
            .frameLength = inputs[0]->GetFrameLen(),
            .raw = loudnessGainOutput_.GetPcmDataBuffer(),
            .metaData = nullptr
        };
        CHECK_AND_RETURN_RET(handle_, inputs[0]);
        int32_t ret = (*handle_)->process(handle_, &inBuffer, &outBuffer);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, inputs[0],
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_OPERATION_FAILED),
            "loudness algo lib process failed", false),
            "loudness algo lib process failed, ret: %{public}d", ret);
    }

    loudnessGainOutput_.SetBufferState(inputs[0]->GetBufferState());
    return &loudnessGainOutput_;
}

void HpaeLoudnessGainNode::CheckUpdateInfo(HpaePcmBuffer *input)
{
    CHECK_AND_RETURN(pcmBufferInfo_.ch != input->GetChannelCount() ||
        pcmBufferInfo_.frameLen != input->GetFrameLen() ||
        pcmBufferInfo_.rate != input->GetSampleRate() ||
        pcmBufferInfo_.channelLayout != input->GetChannelLayout());
    AUDIO_INFO_LOG("Update pcmBufferInfo_: channel count: %{public}u -> %{public}u, frame len: %{public}u -> "
        "%{public}u, sample rate: %{public}u -> %{public}u, channel layout: %{public}" PRIu64 " -> %{public}" PRIu64,
        pcmBufferInfo_.ch, input->GetChannelCount(), pcmBufferInfo_.frameLen, input->GetFrameLen(),
        pcmBufferInfo_.rate, input->GetSampleRate(), pcmBufferInfo_.channelLayout, input->GetChannelLayout());
    pcmBufferInfo_.ch = input->GetChannelCount();
    pcmBufferInfo_.frameLen = input->GetFrameLen();
    pcmBufferInfo_.rate = input->GetSampleRate();
    pcmBufferInfo_.channelLayout = input->GetChannelLayout();
    
    loudnessGainOutput_.ReConfig(pcmBufferInfo_);
    silenceData_.ReConfig(pcmBufferInfo_);
    silenceData_.SetBufferSilence(true);
    CHECK_AND_RETURN_LOG(handle_, "no handle.");

    uint32_t replyData = 0;
    AudioEffectConfig ioBufferConfig;
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &ioBufferConfig};
    ioBufferConfig.inputCfg = {pcmBufferInfo_.rate, pcmBufferInfo_.ch, DATA_FORMAT_F32, pcmBufferInfo_.channelLayout,
        ENCODING_PCM};
    ioBufferConfig.outputCfg = ioBufferConfig.inputCfg;
    int32_t ret = (*handle_)->command(handle_, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_LOG(ret == 0, "Loudness algo lib EFFECT_CMD_SET_CONFIG failed");
}

int32_t HpaeLoudnessGainNode::ReleaseHandle(float loudnessGain)
{
    AUDIO_INFO_LOG("Releasing...");
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(handle_, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::CREATE, ERR_NULL_POINTER),
            "no handle.", false),
        "no handle.");
    int32_t ret = audioEffectLibHandle_->releaseEffect(handle_);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_STATE_INCONSISTENT, OperationType::PLAY,
                BusinessScenario::RELEASE, ERR_OPERATION_FAILED),
            "handle releasing failed.", false),
        "handle releasing failed, ret: %{public}d", ret);
    handle_ = nullptr;
    loudnessGain_ = loudnessGain;
    return SUCCESS;
}

int32_t HpaeLoudnessGainNode::SetLoudnessGain(float loudnessGain)
{
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(!IsFloatValueEqual(loudnessGain_, loudnessGain), SUCCESS,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::CREATE,
                ERR_INVALID_PARAM), "same loudnessGain, skip", false),
        "SetLoudnessGain: Same loudnessGain: %{public}f", loudnessGain);
    AUDIO_INFO_LOG("loudnessGain changed from %{public}f to %{public}f", loudnessGain_, loudnessGain);
    if (!dlHandle_ || !audioEffectLibHandle_) {
        linearGain_ = LoudnessDbToLinearGain(loudnessGain);
        loudnessGain_ = loudnessGain;
        return SUCCESS;
    }
    
    if (IsFloatValueEqual(loudnessGain, 0.0f)) {
        return ReleaseHandle(loudnessGain);
    }

    uint32_t replyData = 0;
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};

    if (IsFloatValueEqual(loudnessGain_, 0.0f)) {
        AUDIO_INFO_LOG("Creating handle...");
        int32_t ret = audioEffectLibHandle_->createEffect(LOUDNESS_DESCRIPTOR, &handle_);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, ERROR,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::CREATE,
                    ERR_OPERATION_FAILED), "loudness lib handle create failed", false),
            "loudness lib handle create failed, ret: %{public}d", ret);
        AudioEffectConfig ioBufferConfig;
        AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &ioBufferConfig};
        ioBufferConfig.inputCfg = {pcmBufferInfo_.rate, pcmBufferInfo_.ch, DATA_FORMAT_F32,
            pcmBufferInfo_.channelLayout, ENCODING_PCM};
        ioBufferConfig.outputCfg = ioBufferConfig.inputCfg;
        ret = (*handle_)->command(handle_, EFFECT_CMD_INIT, &cmdInfo, &replyInfo);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, ERROR,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::START,
                    ERR_OPERATION_FAILED), "Loudness algo lib EFFECT_CMD_INIT failed", false),
            "Loudness algo lib EFFECT_CMD_INIT failed, ret: %{public}d", ret);
        ret = (*handle_)->command(handle_, EFFECT_CMD_ENABLE, &cmdInfo, &replyInfo);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, ERROR,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::START,
                    ERR_OPERATION_FAILED), "Loudness algo lib EFFECT_CMD_ENABLE failed", false),
            "Loudness algo lib EFFECT_CMD_ENABLE failed, ret: %{public}d", ret);
        ret = (*handle_)->command(handle_, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
        CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == 0, ERROR,
            StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
                BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::CREATE,
                    ERR_INVALID_PARAM), "Loudness algo lib EFFECT_CMD_SET_CONFIG failed", false),
            "Loudness algo lib EFFECT_CMD_SET_CONFIG failed, ret: %{public}d", ret);
    }
    std::vector<uint8_t> paramBuffer(sizeof(AudioEffectParam) + MAX_PARAM_INDEX * sizeof(int32_t));
    AudioEffectParam *effectParam = reinterpret_cast<AudioEffectParam*>(paramBuffer.data());
    effectParam->status = 0;
    effectParam->paramSize = sizeof(int32_t);
    effectParam->valueSize = 0;
    int32_t *data = &(effectParam->data[0]);
    data[COMMAND_CODE_INDEX] = EFFECT_SET_PARAM;
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(
        memcpy_s(&data[LOUDNESS_GAIN_INDEX], sizeof(float), &loudnessGain, sizeof(float)) == 0, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY,
                BusinessScenario::SEND_DATA, ERR_INVALID_PARAM), "memcpy failed", false),
        "memcpy failed");

    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectParam) + sizeof(int32_t) * MAX_PARAM_INDEX, effectParam};
    int32_t ret = (*handle_)->command(handle_, EFFECT_CMD_SET_PARAM, &cmdInfo, &replyInfo);
    CHECK_AND_CALL_FUNC_RETURN_RET_LOG(ret == SUCCESS, ERROR,
        StreamDfxManager::GetInstance().SendAudioErrorEvent(static_cast<int32_t>(getuid()),
            BuildErrorCode(ProblemCategory::FAULT_NO_SOUND, OperationType::PLAY, BusinessScenario::SEND_DATA,
                ERR_OPERATION_FAILED), "Loudness algo lib EFFECT_CMD_SET_PARAM failed", false),
        "Loudness algo lib EFFECT_CMD_SET_PARAM failed, ret: %{public}d", ret);
    loudnessGain_ = loudnessGain;

    return SUCCESS;
}

float HpaeLoudnessGainNode::GetLoudnessGain()
{
    return loudnessGain_;
}

bool HpaeLoudnessGainNode::IsLoudnessAlgoOn()
{
    return handle_ != nullptr;
}

uint64_t HpaeLoudnessGainNode::GetLatency(uint32_t sessionId)
{
    CHECK_AND_RETURN_RET(handle_ != nullptr, 0);
    return DEFAULT_LATENCY_IN_US;
}

}  // namespace HPAE
}  // namespace AudioStandard
}  // namespace OHOS
