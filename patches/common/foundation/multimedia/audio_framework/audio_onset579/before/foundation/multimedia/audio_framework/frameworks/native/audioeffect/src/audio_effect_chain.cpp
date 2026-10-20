/*
 * Copyright (c) 2024-2025 Huawei Device Co., Ltd.
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
#define LOG_TAG "AudioEffectChain"
#endif

#include "audio_effect_chain.h"
#include "audio_effect.h"
#include "audio_errors.h"
#include "audio_effect_log.h"
#include "audio_dump_pcm.h"
#include "securec.h"
#include "media_monitor_manager.h"
#include "audio_effect_map.h"
#include "audio_utils.h"
#include <cinttypes>

namespace OHOS {
namespace AudioStandard {

static constexpr uint32_t DEFAULT_SAMPLE_RATE = 48000;
static constexpr uint32_t MAX_UINT_VOLUME = 65535;
static constexpr uint32_t DEFAULT_NUM_CHANNEL = STEREO;
static constexpr uint64_t DEFAULT_NUM_CHANNELLAYOUT = CH_LAYOUT_STEREO;
static constexpr int32_t CROSS_FADE_FRAME_COUNT = 5;
static constexpr int32_t DEFAULT_FRAME_LEN = 960;
static constexpr int32_t MAX_CHANNEL_NUM = 16;

#ifdef SENSOR_ENABLE
AudioEffectChain::AudioEffectChain(std::string scene, std::shared_ptr<HeadTracker> headTracker)
    : effectBuffer_(MAX_CHANNEL_NUM * DEFAULT_FRAME_LEN)
{
    const std::unordered_map<AudioEffectMode, std::string> &audioSupportedSceneModes = GetAudioSupportedSceneModes();

    sceneType_ = scene;
    effectMode_ = audioSupportedSceneModes.find(EFFECT_DEFAULT)->second;
    audioBufIn_.frameLength = 0;
    audioBufOut_.frameLength = 0;
    ioBufferConfig_.inputCfg.samplingRate = DEFAULT_SAMPLE_RATE;
    ioBufferConfig_.inputCfg.channels = DEFAULT_NUM_CHANNEL;
    ioBufferConfig_.inputCfg.format = DATA_FORMAT_F32;
    ioBufferConfig_.inputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    ioBufferConfig_.outputCfg.samplingRate = DEFAULT_SAMPLE_RATE;
    ioBufferConfig_.outputCfg.channels = DEFAULT_NUM_CHANNEL;
    ioBufferConfig_.outputCfg.format = DATA_FORMAT_F32;
    ioBufferConfig_.outputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    headTracker_ = headTracker;
    dumpNameIn_ = "dump_effect_in_" + scene + "_"
        + std::to_string(ioBufferConfig_.inputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.inputCfg.channels) + "_4_"
        + GetTime() + ".pcm";
    dumpNameOut_ = "dump_effect_out_" + scene + "_"
        + std::to_string(ioBufferConfig_.outputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.outputCfg.channels) + "_4_"
        + GetTime() + ".pcm";
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpNameIn_, &dumpFileInput_);
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpNameOut_, &dumpFileOutput_);
}
#else
AudioEffectChain::AudioEffectChain(std::string scene)
    : effectBuffer_(MAX_CHANNEL_NUM * DEFAULT_FRAME_LEN)
{
    const std::unordered_map<AudioEffectMode, std::string> &audioSupportedSceneModes = GetAudioSupportedSceneModes();

    sceneType_ = scene;
    effectMode_ = audioSupportedSceneModes.find(EFFECT_DEFAULT)->second;
    audioBufIn_.frameLength = 0;
    audioBufOut_.frameLength = 0;
    ioBufferConfig_.inputCfg.samplingRate = DEFAULT_SAMPLE_RATE;
    ioBufferConfig_.inputCfg.channels = DEFAULT_NUM_CHANNEL;
    ioBufferConfig_.inputCfg.format = DATA_FORMAT_F32;
    ioBufferConfig_.inputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    ioBufferConfig_.outputCfg.samplingRate = DEFAULT_SAMPLE_RATE;
    ioBufferConfig_.outputCfg.channels = DEFAULT_NUM_CHANNEL;
    ioBufferConfig_.outputCfg.format = DATA_FORMAT_F32;
    ioBufferConfig_.outputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    dumpNameIn_ = "dump_effect_in_" + scene + "_"
        + std::to_string(ioBufferConfig_.inputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.inputCfg.channels) + "_4_"
        + GetTime() + ".pcm";
    dumpNameOut_ = "dump_effect_out_" + scene + "_"
        + std::to_string(ioBufferConfig_.outputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.outputCfg.channels) + "_4_"
        + GetTime() + ".pcm";
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpNameIn_, &dumpFileInput_);
    DumpFileUtil::OpenDumpFile(DumpFileUtil::DUMP_SERVER_PARA, dumpNameOut_, &dumpFileOutput_);
}
#endif

AudioEffectChain::~AudioEffectChain()
{
    ReleaseEffectChain();
    DumpFileUtil::CloseDumpFile(&dumpFileInput_);
    DumpFileUtil::CloseDumpFile(&dumpFileOutput_);
}

void AudioEffectChain::SetEffectMode(const std::string &mode)
{
    effectMode_ = mode;
}

void AudioEffectChain::SetExtraSceneType(const std::string &extraSceneType)
{
    CHECK_AND_RETURN_LOG(StringConverter(extraSceneType, extraEffectChainType_),
        "convert invalid extraSceneType: %{public}s", extraSceneType.c_str());
}

void AudioEffectChain::SetFoldState(const std::string &foldState)
{
    CHECK_AND_RETURN_LOG(StringConverter(foldState, foldState_),
        "convert invalid foldState: %{public}s", foldState.c_str());
}

void AudioEffectChain::SetLidState(const std::string &lidState)
{
    CHECK_AND_RETURN_LOG(StringConverter(lidState, lidState_),
        "convert invalid lidState: %{public}s", lidState.c_str());
}

void AudioEffectChain::SetStereoEnhancementMode(const std::string &stereoEnhancementMode)
{
    AUDIO_INFO_LOG("stereoEnhancementMode: %{public}s", stereoEnhancementMode.c_str());
    CHECK_AND_RETURN_LOG(StringConverter(stereoEnhancementMode, stereoEnhancementMode_),
        "convert invalid stereoEnhancementMode: %{public}s", stereoEnhancementMode.c_str());
}

void AudioEffectChain::SetSystemLoadState(const std::string &systemLoadState)
{
    CHECK_AND_RETURN_LOG(StringConverter(systemLoadState, systemLoadState_),
        "convert invalid systemLoadState: %{public}s", systemLoadState.c_str());
}

void AudioEffectChain::SetEffectCurrSceneType(AudioEffectScene currSceneType)
{
    currSceneType_ = currSceneType;
}

void AudioEffectChain::SetSpatializationSceneType(AudioSpatializationSceneType spatializationSceneType)
{
    spatializationSceneType_ = spatializationSceneType;
}

void AudioEffectChain::SetSpatializationEnabled(bool enabled)
{
    spatializationEnabled_ = enabled;
    spatializationEnabledFading_ = enabled;
}

void AudioEffectChain::SetSpatializationEnabledForFading(bool enabled)
{
    std::lock_guard<std::mutex> lock(reloadMutex_);
    CHECK_AND_RETURN_LOG(spatializationEnabledFading_ != enabled,
        "no need to update spatialization enabled for fading: %{public}d", enabled);
    spatializationEnabledFading_ = enabled;
    fadingCounts_ = CROSS_FADE_FRAME_COUNT;
}

void AudioEffectChain::SetStreamUsage(const int32_t streamUsage)
{
    streamUsage_ = static_cast<StreamUsage>(streamUsage);
}

void AudioEffectChain::ReleaseEffectChain()
{
    std::lock_guard<std::mutex> lock(reloadMutex_);
    for (uint32_t i = 0; i < standByEffectHandles_.size() && i < libHandles_.size(); ++i) {
        if (!libHandles_[i]) {
            continue;
        }
        if (!standByEffectHandles_[i]) {
            continue;
        }
        if (!libHandles_[i]->releaseEffect) {
            continue;
        }
        libHandles_[i]->releaseEffect(standByEffectHandles_[i]);
    }
    standByEffectHandles_.clear();
    libHandles_.clear();
}

int32_t AudioEffectChain::SetEffectParamToHandle(AudioEffectHandle handle, int32_t &replyData)
{
    AudioEffectConfig tmpIoBufferConfig = ioBufferConfig_;
    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &tmpIoBufferConfig};
    int32_t replyDatas[2] = {replyData, 0};
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyDatas};
    std::vector<uint8_t> paramBuffer((sizeof(AudioEffectParam) + MAX_PARAM_CAPACITY * sizeof(int32_t)), 0);
    // Set param
    AudioEffectParam *effectParam = reinterpret_cast<AudioEffectParam*>(paramBuffer.data());
    CHECK_AND_RETURN_RET_LOG(effectParam != nullptr, ERROR, "effectParam is null");
    effectParam->status = 0;
    effectParam->paramSize = sizeof(int32_t);
    effectParam->valueSize = 0;
    int32_t *data = &(effectParam->data[0]);
    BuildEffectParamData(data);
    AUDIO_INFO_LOG("set param to handle, sceneType: %{public}d, effectMode: %{public}d, rotation: %{public}d, "
        "volume: %{public}d, extraSceneType: %{public}d, spatialDeviceType: %{public}d, spatializationSceneType: "
        "%{public}d, spatializationEnabled: %{public}d, streamUsage: %{public}d, absVolumeState: %{public}d, "
        "earphoneProduct: %{public}d, outdoorMode: %{public}d, superLoudnessMode: %{public}d, "
        "systemLoadState: %{public}d, frontendAppType: %{public}d, personalizedSpatitalizationEnabled: %{public}d ",
        data[SCENE_TYPE_INDEX], data[EFFECT_MODE_INDEX], data[ROTATION_INDEX], data[VOLUME_INDEX],
        data[EXTRA_SCENE_TYPE_INDEX], data[SPATIAL_DEVICE_TYPE_INDEX], data[SPATIALIZATION_SCENE_TYPE_INDEX],
        data[SPATIALIZATION_ENABLED_INDEX], data[STREAM_USAGE_INDEX], data[ABS_VOLUME_STATE], data[EARPHONE_PRODUCT],
        data[OUTDOOR_MODE], data[SUPER_LOUDNESS_MODE], data[SYSTEMLOAD_STATE_INDEX], data[FRONTEND_APP_TYPE],
        data[PERSONALIZED_SPATIALIZATION_ENABLED]);
    cmdInfo = {sizeof(AudioEffectParam) + sizeof(int32_t) * MAX_PARAM_INDEX, effectParam};
    int32_t ret = (*handle)->command(handle, EFFECT_CMD_SET_PARAM, &cmdInfo, &replyInfo);
    replyData = replyDatas[0];
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "[%{public}s] with mode [%{public}s], NUM_SET_EFFECT_PARAM fail",
        sceneType_.c_str(), effectMode_.c_str());
    personalizedSpatialUpdateState_ += replyDatas[1];

    cmdInfo = {sizeof(AudioEffectConfig), &tmpIoBufferConfig};
    ret = (*handle)->command(handle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
    CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, ret, "EFFECT_CMD_GET_CONFIG fail, ret is %{public}d", ret);

    ioBufferConfig_.outputCfg.channels = tmpIoBufferConfig.outputCfg.channels;
    ioBufferConfig_.outputCfg.channelLayout = tmpIoBufferConfig.outputCfg.channelLayout;
    AUDIO_INFO_LOG("[%{public}s] with mode [%{public}s], output channels: %{public}u, channelLayout: %{public}" PRIu64,
        sceneType_.c_str(), effectMode_.c_str(), ioBufferConfig_.outputCfg.channels,
        ioBufferConfig_.outputCfg.channelLayout);

    return SUCCESS;
}

void AudioEffectChain::BuildEffectParamData(int32_t *data)
{
    data[COMMAND_CODE_INDEX] = EFFECT_SET_PARAM;
    data[SCENE_TYPE_INDEX] = static_cast<int32_t>(currSceneType_);
    data[EFFECT_MODE_INDEX] = GetKeyFromValue(GetAudioSupportedSceneModes(), effectMode_);
#ifdef WINDOW_MANAGER_ENABLE
    std::shared_ptr<AudioEffectRotation> audioEffectRotation = AudioEffectRotation::GetInstance();
    if (audioEffectRotation == nullptr) {
        data[ROTATION_INDEX] = 0;
    } else {
        data[ROTATION_INDEX] = static_cast<int32_t>(audioEffectRotation->GetRotation());
    }
#else
    data[ROTATION_INDEX] = 0;
#endif
    data[VOLUME_INDEX] = static_cast<int32_t>(finalVolume_ * MAX_UINT_VOLUME);
    data[EXTRA_SCENE_TYPE_INDEX] = static_cast<int32_t>(extraEffectChainType_);
    data[SPATIAL_DEVICE_TYPE_INDEX] = spatialDeviceType_;
    data[SPATIALIZATION_SCENE_TYPE_INDEX] = spatializationSceneType_;
    data[SPATIALIZATION_ENABLED_INDEX] = spatializationEnabled_;
    data[STREAM_USAGE_INDEX] = streamUsage_;
    data[FOLD_STATE_INDEX] = static_cast<int32_t>(foldState_);
    data[LID_STATE_INDEX] = static_cast<int32_t>(lidState_);
    data[ABS_VOLUME_STATE] = static_cast<int32_t>(absVolumeState_);
    data[EARPHONE_PRODUCT] = static_cast<int32_t>(earphoneProduct_);
    data[OUTDOOR_MODE] = static_cast<int32_t>(outdoorMode_);
    data[SUPER_LOUDNESS_MODE] = static_cast<int32_t>(superLoudnessMode_);
    data[SYSTEMLOAD_STATE_INDEX] = static_cast<int32_t>(systemLoadState_);
    data[FRONTEND_APP_TYPE] = static_cast<int32_t>(frontendAppType_);
    data[STEREO_ENHANCEMENT_INDEX] = static_cast<int32_t>(stereoEnhancementMode_);
    data[PERSONALIZED_SPATIALIZATION_ENABLED] = static_cast<int32_t>(personalizedSpatializationEnabled_);
}

int32_t AudioEffectChain::SetEffectProperty(const std::string &effect, const std::string &property)
{
    std::lock_guard<std::mutex> lock(reloadMutex_);
    int32_t ret = 0;
    int32_t size = static_cast<int32_t>(standByEffectHandles_.size());
    for (int32_t index = 0; index < size; index++) {
        auto &handle = standByEffectHandles_[index];
        auto const &effectName = effectNames_[index];
        if (effect == effectName) {
            int32_t replyData = 0;
            const char *propCstr = property.c_str();
            AudioEffectTransInfo cmdInfo = {sizeof(const char *), reinterpret_cast<void*>(&propCstr)};
            AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
            ret = (*handle)->command(handle, EFFECT_CMD_SET_PROPERTY, &cmdInfo, &replyInfo);
            CHECK_AND_RETURN_RET_LOG(ret == 0, ret,
                "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_SET_PROPERTY fail",
                sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());
        }
    }
    UpdateMultichannelIoBufferConfigInner();
    return ret;
}

static int32_t CheckHandleAndRelease(AudioEffectHandle handle, AudioEffectLibrary *libHandle, int32_t ret)
{
    if (ret != SUCCESS) {
        libHandle->releaseEffect(handle);
    }
    return ret;
}

void AudioEffectChain::AddEffectHandle(AudioEffectHandle handle, AudioEffectLibrary *libHandle,
    AudioEffectScene currSceneType, const std::string &effectName, const std::string &effectProperty)
{
    Trace trace("AudioEffectChain::AddEffectHandle currSceneType: " +
        std::to_string(static_cast<int32_t>(currSceneType)) + " effectName: " + effectName);
    int32_t ret;
    int32_t replyData = 0;
    int32_t latencyData = 0;
    currSceneType_ = currSceneType;
    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &ioBufferConfig_};
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};

    ret = (*handle)->command(handle, EFFECT_CMD_INIT, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
        "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_INIT fail",
        sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());
    ret = (*handle)->command(handle, EFFECT_CMD_ENABLE, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
        "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_ENABLE fail",
        sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());
    ret = SetEffectParamToHandle(handle, latencyData);
    CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
        "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_SET_PARAM fail",
        sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());

    if (!effectProperty.empty()) {
        const char *propCstr = effectProperty.c_str();
        cmdInfo = {sizeof(const char *), &propCstr};
        ret = (*handle)->command(handle, EFFECT_CMD_SET_PROPERTY, &cmdInfo, &replyInfo);
        CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
            "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_SET_PROPERTY fail",
            sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());
    }
    if (preIoBufferConfig_.inputCfg.channels == 0 && preIoBufferConfig_.inputCfg.channelLayout == 0) {
        preIoBufferConfig_ = ioBufferConfig_;
    }
    cmdInfo = {sizeof(AudioEffectConfig), &preIoBufferConfig_};
    ret = (*handle)->command(handle, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
        "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_SET_CONFIG fail",
        sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());

    ret = (*handle)->command(handle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
    CHECK_AND_RETURN_LOG(CheckHandleAndRelease(handle, libHandle, ret) == SUCCESS,
        "[%{public}s] with mode [%{public}s], %{public}s effect EFFECT_CMD_GET_CONFIG fail",
        sceneType_.c_str(), effectMode_.c_str(), effectName.c_str());
    preIoBufferConfig_.inputCfg = preIoBufferConfig_.outputCfg;
    ioBufferConfig_.outputCfg.channels = preIoBufferConfig_.outputCfg.channels;
    ioBufferConfig_.outputCfg.channelLayout = preIoBufferConfig_.outputCfg.channelLayout;

    standByEffectHandles_.emplace_back(handle);
    effectNames_.emplace_back(effectName);
    libHandles_.emplace_back(libHandle);
    latency_ += static_cast<uint32_t>(latencyData);
}

int32_t AudioEffectChain::UpdateEffectParam()
{
    Trace trace("AudioEffectChain::UpdateEffectParam");
    std::lock_guard<std::mutex> lock(reloadMutex_);
    return UpdateEffectParamInner();
}

void AudioEffectChain::ApplyEffectChain(float *bufIn, float *bufOut, uint32_t frameLen, AudioEffectProcInfo procInfo)
{
    Trace trace("AudioEffectChain::ApplyEffectChain");
    size_t inTotlen = frameLen * ioBufferConfig_.inputCfg.channels * sizeof(float);
    size_t outTotlen = frameLen * ioBufferConfig_.outputCfg.channels * sizeof(float);
    DumpFileUtil::WriteDumpFile(dumpFileInput_, static_cast<void *>(bufIn), inTotlen);
    DumpEffectProcessData(dumpNameIn_, static_cast<void *>(bufIn), inTotlen);

    if (IsEmptyEffectHandles()) {
        CHECK_AND_RETURN_LOG(memcpy_s(bufOut, outTotlen, bufIn, outTotlen) == 0, "memcpy error in apply effect");
        DumpFileUtil::WriteDumpFile(dumpFileOutput_, static_cast<void *>(bufOut), outTotlen);
        return;
    }

#ifdef SENSOR_ENABLE
    int32_t replyData = 0;
    auto imuData = headTracker_->GetHeadPostureData();
    AudioEffectTransInfo cmdInfo = {sizeof(HeadPostureData), &imuData};
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
#endif

    audioBufIn_.frameLength = frameLen;
    audioBufOut_.frameLength = frameLen;
    std::lock_guard<std::mutex> lock(reloadMutex_);
    for (size_t i = 0; i < standByEffectHandles_.size(); ++i) {
#ifdef SENSOR_ENABLE
        if ((!procInfo.btOffloadEnabled) && procInfo.headTrackingEnabled) {
            (*standByEffectHandles_[i])->command(standByEffectHandles_[i], EFFECT_CMD_SET_IMU, &cmdInfo, &replyInfo);
        }
#endif
        audioBufIn_.raw = i == 0 ? bufIn : effectBuffer_.data();
        audioBufOut_.raw = i == (standByEffectHandles_.size() - 1) ? bufOut : effectBuffer_.data();

        int32_t ret = (*standByEffectHandles_[i])->process(standByEffectHandles_[i], &audioBufIn_, &audioBufOut_);
        CHECK_AND_CONTINUE_LOG(ret == 0, "[%{public}s] with mode [%{public}s], either one of libs process fail",
            sceneType_.c_str(), effectMode_.c_str());
    }

    CrossFadeProcess(bufOut, frameLen);

    DumpFileUtil::WriteDumpFile(dumpFileOutput_, static_cast<void *>(bufOut), outTotlen);
}

void AudioEffectChain::UpdateBufferConfig(uint32_t &channels, uint64_t &channelLayout)
{
    channels = ioBufferConfig_.outputCfg.channels;
    channelLayout = ioBufferConfig_.outputCfg.channelLayout;
    CHECK_AND_RETURN(channelLayout == 0);
    if (channels == DEFAULT_NUM_CHANNEL) {
        channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    } else if (channels == CHANNEL_8) {
        channelLayout = CH_LAYOUT_5POINT1POINT2;
    }
}

bool AudioEffectChain::IsEmptyEffectHandles()
{
    std::lock_guard<std::mutex> lock(reloadMutex_);
    return standByEffectHandles_.size() == 0;
}

int32_t AudioEffectChain::UpdateMultichannelIoBufferConfig(const uint32_t &channels, const uint64_t &channelLayout)
{
    if (ioBufferConfig_.inputCfg.channels == channels && ioBufferConfig_.inputCfg.channelLayout == channelLayout) {
        return SUCCESS;
    }
    ioBufferConfig_.inputCfg.channels = channels;
    ioBufferConfig_.inputCfg.channelLayout = channelLayout;
    if (IsEmptyEffectHandles()) {
        return SUCCESS;
    }
    std::lock_guard<std::mutex> lock(reloadMutex_);
    UpdateMultichannelIoBufferConfigInner();
    return SUCCESS;
}

void AudioEffectChain::ResetIoBufferConfig()
{
    ioBufferConfig_.inputCfg.channels = DEFAULT_NUM_CHANNEL;
    ioBufferConfig_.inputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    dumpNameIn_ = "dump_effect_in_" + sceneType_ + "_"
        + std::to_string(ioBufferConfig_.inputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.inputCfg.channels) + "_4.pcm";
    dumpNameOut_ = "dump_effect_out_" + sceneType_ + "_"
        + std::to_string(ioBufferConfig_.outputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.outputCfg.channels) + "_4.pcm";
}

AudioEffectConfig AudioEffectChain::GetIoBufferConfig()
{
    return ioBufferConfig_;
}

void AudioEffectChain::StoreOldEffectChainInfo(std::string &sceneMode, AudioEffectConfig &ioBufferConfig)
{
    sceneMode = effectMode_;
    ioBufferConfig = GetIoBufferConfig();
    return;
}

uint32_t AudioEffectChain::GetLatency()
{
    return latency_;
}

int32_t AudioEffectChain::GetPersonalizedSpatialUpdateState()
{
    return personalizedSpatialUpdateState_;
}

void AudioEffectChain::DumpEffectProcessData(std::string fileName, void *buffer, size_t len)
{
    if (AudioDump::GetInstance().GetVersionType() == DumpFileUtil::BETA_VERSION) {
        AudioCacheMgr::GetInstance().CacheData(fileName, buffer, len);
    }
}

#ifdef SENSOR_ENABLE
void AudioEffectChain::SetHeadTrackingDisabled()
{
    if (IsEmptyEffectHandles()) {
        return;
    }

    std::lock_guard<std::mutex> lock(reloadMutex_);
    for (AudioEffectHandle handle : standByEffectHandles_) {
        int32_t replyData = 0;
        HeadPostureData imuDataDisabled = {1, 1.0, 0.0, 0.0, 0.0};
        AudioEffectTransInfo cmdInfo = {sizeof(HeadPostureData), &imuDataDisabled};
        AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
        int32_t ret = (*handle)->command(handle, EFFECT_CMD_SET_IMU, &cmdInfo, &replyInfo);
        if (ret != SUCCESS) {
            AUDIO_WARNING_LOG("SetHeadTrackingDisabled failed");
        }
    }
}
#endif

void AudioEffectChain::InitEffectChain()
{
    if (IsEmptyEffectHandles()) {
        return;
    }
    std::lock_guard<std::mutex> lock(reloadMutex_);
    for (AudioEffectHandle handle : standByEffectHandles_) {
        int32_t replyData = 0;
        AudioEffectTransInfo cmdInfo = {sizeof(int32_t), &replyData};
        AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
        int32_t ret = (*handle)->command(handle, EFFECT_CMD_ENABLE, &cmdInfo, &replyInfo);
        CHECK_AND_RETURN_LOG(ret == 0, "[%{public}s] with mode [%{public}s], either one of libs EFFECT_CMD_ENABLE fail",
            sceneType_.c_str(), effectMode_.c_str());
    }
}

void AudioEffectChain::SetFinalVolume(const float volume)
{
    finalVolume_ = volume;
}

float AudioEffectChain::GetFinalVolume()
{
    return finalVolume_;
}

void AudioEffectChain::SetCurrVolume(const float volume)
{
    currVolume_ = volume;
}

float AudioEffectChain::GetCurrVolume()
{
    return currVolume_;
}

void AudioEffectChain::SetFinalVolumeState(const bool state)
{
    sendFinalVolumeState_ = state;
}

bool AudioEffectChain::GetFinalVolumeState()
{
    return sendFinalVolumeState_;
}

void AudioEffectChain::SetSpatialDeviceType(AudioSpatialDeviceType spatialDeviceType)
{
    spatialDeviceType_ = spatialDeviceType;

    return;
}

void AudioEffectChain::SetCurrChannelNoCheck(const uint32_t channel)
{
    currChannelNoCheck_ = channel;
}

void AudioEffectChain::SetCurrChannelLayoutNoCheck(const uint64_t channelLayout)
{
    currchannelLayoutNoCheck_ = channelLayout;
}

void AudioEffectChain::GetInputChannelInfo(uint32_t &channels, uint64_t &channelLayout)
{
    channels = ioBufferConfig_.inputCfg.channels;
    channelLayout = ioBufferConfig_.inputCfg.channelLayout;
}

bool AudioEffectChain::CheckChannelLayoutByReplyInfo(AudioEffectTransInfo info)
{
    if (info.data == nullptr) {
        return false;
    }
    int32_t *channelLayoutSupportedFlage = static_cast<int32_t *>(info.data);
    if (*channelLayoutSupportedFlage != SUCCESS) {
        return false;
    }
    return true;
}

int32_t AudioEffectChain::updatePrimaryChannel()
{
    ioBufferConfig_.inputCfg.channels = currChannelNoCheck_;
    ioBufferConfig_.inputCfg.channelLayout = currchannelLayoutNoCheck_;
    int32_t replyData = -1;
    AudioEffectConfig tmpIoBufferConfig = ioBufferConfig_;
    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &tmpIoBufferConfig};
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
    AudioEffectHandle preHandle = nullptr;
    tmpIoBufferConfig.outputCfg.channels = 0;
    tmpIoBufferConfig.outputCfg.channelLayout = 0;
    bool isSupportedChannelLayoutFlage = true;
    for (AudioEffectHandle handle : standByEffectHandles_) {
        if (preHandle != nullptr) {
            int32_t ret = (*preHandle)->command(preHandle, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
            CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "Multichannel effect chain update EFFECT_CMD_SET_CONFIG fail");
            isSupportedChannelLayoutFlage = CheckChannelLayoutByReplyInfo(replyInfo);
            if (isSupportedChannelLayoutFlage == false) {
                ioBufferConfig_.inputCfg.channels = DEFAULT_NUM_CHANNEL;
                ioBufferConfig_.inputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
                AUDIO_INFO_LOG("currChannelLayout is not supported, change to default channelLayout");
                return ERROR;
            }

            ret = (*preHandle)->command(preHandle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
            CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "Multichannel effect chain update EFFECT_CMD_GET_CONFIG fail");
            tmpIoBufferConfig.inputCfg = tmpIoBufferConfig.outputCfg;
        }
        preHandle = handle;
    }
    tmpIoBufferConfig.outputCfg.channels = DEFAULT_NUM_CHANNEL;
    tmpIoBufferConfig.outputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    if (preHandle == nullptr) {
        return ERROR;
    }
    int32_t ret = (*preHandle)->command(preHandle, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "last effect update EFFECT_CMD_SET_CONFIG fail");
    isSupportedChannelLayoutFlage = CheckChannelLayoutByReplyInfo(replyInfo);
    if (isSupportedChannelLayoutFlage == false) {
        ioBufferConfig_.inputCfg.channels = DEFAULT_NUM_CHANNEL;
        ioBufferConfig_.inputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
        HILOG_COMM_INFO("[updatePrimaryChannel]currChannelLayout is not supported, change to default channelLayout");
        return ERROR;
    }

    ret = (*preHandle)->command(preHandle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "last effect update EFFECT_CMD_GET_CONFIG fail");

    ioBufferConfig_.outputCfg.channels = tmpIoBufferConfig.outputCfg.channels;
    ioBufferConfig_.outputCfg.channelLayout = tmpIoBufferConfig.outputCfg.channelLayout;
    updateDumpName(); // update dumpFile name(effect_in and effect_out)
    return SUCCESS;
}

void AudioEffectChain::updateDumpName()
{
    dumpNameIn_ = "dump_effect_in_" + sceneType_ + "_"
        + std::to_string(ioBufferConfig_.inputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.inputCfg.channels) + "_4.pcm";
    dumpNameOut_ = "dump_effect_out_" + sceneType_ + "_"
        + std::to_string(ioBufferConfig_.outputCfg.samplingRate) + "_"
        + std::to_string(ioBufferConfig_.outputCfg.channels) + "_4.pcm";
}

int32_t AudioEffectChain::UpdateMultichannelIoBufferConfigInner()
{
    if (updatePrimaryChannel() == SUCCESS) {
        return SUCCESS;
    }
    int32_t replyData = 0;
    AudioEffectConfig tmpIoBufferConfig = ioBufferConfig_;
    AudioEffectTransInfo cmdInfo = {sizeof(AudioEffectConfig), &tmpIoBufferConfig};
    AudioEffectTransInfo replyInfo = {sizeof(int32_t), &replyData};
    AudioEffectHandle preHandle = nullptr;
    tmpIoBufferConfig.outputCfg.channels = 0;
    tmpIoBufferConfig.outputCfg.channelLayout = 0;
    for (AudioEffectHandle handle : standByEffectHandles_) {
        if (preHandle != nullptr) {
            int32_t ret = (*preHandle)->command(preHandle, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
            CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "Multichannel effect chain update EFFECT_CMD_SET_CONFIG fail");

            ret = (*preHandle)->command(preHandle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
            CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "Multichannel effect chain update EFFECT_CMD_GET_CONFIG fail");
            tmpIoBufferConfig.inputCfg = tmpIoBufferConfig.outputCfg;
        }
        preHandle = handle;
    }
    tmpIoBufferConfig.outputCfg.channels = DEFAULT_NUM_CHANNEL;
    tmpIoBufferConfig.outputCfg.channelLayout = DEFAULT_NUM_CHANNELLAYOUT;
    if (preHandle == nullptr) {
        return ERROR;
    }
    int32_t ret = (*preHandle)->command(preHandle, EFFECT_CMD_SET_CONFIG, &cmdInfo, &replyInfo);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "last effect update EFFECT_CMD_SET_CONFIG fail");

    ret = (*preHandle)->command(preHandle, EFFECT_CMD_GET_CONFIG, &cmdInfo, &cmdInfo);
    CHECK_AND_RETURN_RET_LOG(ret == 0, ERROR, "last effect update EFFECT_CMD_GET_CONFIG fail");

    ioBufferConfig_.outputCfg.channels = tmpIoBufferConfig.outputCfg.channels;
    ioBufferConfig_.outputCfg.channelLayout = tmpIoBufferConfig.outputCfg.channelLayout;
    updateDumpName(); // update dumpFile name(effect_in and effect_out)
    return SUCCESS;
}

int32_t AudioEffectChain::UpdateEffectParamInner()
{
    Trace trace("AudioEffectChain::UpdateEffectParamInner");
    latency_ = 0;
    personalizedSpatialUpdateState_ = 0;
    for (AudioEffectHandle handle : standByEffectHandles_) {
        int32_t replyData;
        int32_t ret = SetEffectParamToHandle(handle, replyData);
        CHECK_AND_RETURN_RET_LOG(ret == 0, ret, "set EFFECT_CMD_SET_PARAM fail");
        AUDIO_DEBUG_LOG("Set Effect Param Scene Type: %{public}d Success", currSceneType_);
        latency_ += static_cast<uint32_t>(replyData);
    }
    UpdateMultichannelIoBufferConfigInner();
    return SUCCESS;
}

void AudioEffectChain::CrossFadeProcess(float *bufOut, uint32_t frameLen)
{
    if (fadingCounts_ == 0) {
        return;
    }

    int32_t channelNum = static_cast<int32_t>(ioBufferConfig_.outputCfg.channels);
    int32_t frameLength = static_cast<int32_t>(frameLen);

    // fading out to zero
    if (fadingCounts_ > 0) {
        for (int32_t i = 0; i < frameLength; ++i) {
            for (int32_t j = 0; j < channelNum; ++j) {
                bufOut[i * channelNum + j] *=
                    (fadingCounts_ * frameLength - i) / static_cast<float>(frameLength * CROSS_FADE_FRAME_COUNT);
            }
        }
        fadingCounts_--;
        // fading out finish, update spatialization enabled and start fading in
        if (fadingCounts_ == 0) {
            fadingCounts_ = -CROSS_FADE_FRAME_COUNT;
            spatializationEnabled_ = spatializationEnabledFading_;
            UpdateEffectParamInner();
            AUDIO_INFO_LOG("fading out finish, switch to %{public}d and start fading in", spatializationEnabled_);
        }
        return;
    }

    // fading in to one
    if (fadingCounts_ < 0) {
        for (int32_t i = 0; i < frameLength; ++i) {
            for (int32_t j = 0; j < channelNum; ++j) {
                bufOut[i * channelNum + j] *=
                    (1 + (fadingCounts_ * frameLength + i) / static_cast<float>(frameLength * CROSS_FADE_FRAME_COUNT));
            }
        }
        fadingCounts_++;
        // fading in finish, start normally processing
        if (fadingCounts_ == 0) {
            AUDIO_INFO_LOG("fading in finish, start normally processing for %{public}d", spatializationEnabled_);
        }
        return;
    }
}

void AudioEffectChain::SetAbsVolumeStateToEffectChain(const bool absVolumeState)
{
    absVolumeState_ = absVolumeState;
}

void AudioEffectChain::SetEarphoneProduct(int32_t earphoneProduct)
{
    earphoneProduct_ = earphoneProduct;
}

bool AudioEffectChain::IsEffectChainFading()
{
    return fadingCounts_ != 0;
}

void AudioEffectChain::SetOutdoorMode(const std::string &outdoorMode)
{
    CHECK_AND_RETURN_LOG(StringConverter(outdoorMode, outdoorMode_),
        "convert invalid outdoorMode: %{public}s", outdoorMode.c_str());
}

void AudioEffectChain::SetSuperLoudnessMode(const std::string &superLoudnessMode)
{
    if (superLoudnessMode == "music_on") {
        superLoudnessMode_ = 1;
    } else if (superLoudnessMode == "music_off") {
        superLoudnessMode_ = 0;
    }
}

void AudioEffectChain::SetFrontendAppType(const std::string &frontendAppType)
{
    CHECK_AND_RETURN_LOG(StringConverter(frontendAppType, frontendAppType_),
        "convert invalid frontendAppType: %{public}s", frontendAppType.c_str());
}

void AudioEffectChain::SetPersonalizedSpatializationEnabled(const bool &personalizedSpatializationEnabled)
{
    personalizedSpatializationEnabled_ = personalizedSpatializationEnabled;
}
} // namespace AudioStandard
} // namespace OHOS
