/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
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

#ifndef AUDIO_EFFECT_CHAIN_H
#define AUDIO_EFFECT_CHAIN_H

#include <atomic>

#include "audio_effect.h"

#ifdef SENSOR_ENABLE
#include "audio_head_tracker.h"
#endif
#ifdef WINDOW_MANAGER_ENABLE
#include "audio_effect_rotation.h"
#endif
#include "audio_effect_volume.h"

namespace OHOS {
namespace AudioStandard {

struct AudioEffectProcInfo {
    bool headTrackingEnabled;
    bool btOffloadEnabled;
};

class AudioEffectChain {
public:
#ifdef SENSOR_ENABLE
    AudioEffectChain(std::string scene, std::shared_ptr<HeadTracker> headTracker);
#else
    AudioEffectChain(std::string scene);
#endif
    ~AudioEffectChain();
    void SetEffectMode(const std::string &mode);
    void SetExtraSceneType(const std::string &extraSceneType);
    void SetFoldState(const std::string &foldState);
    void SetLidState(const std::string &lidState);
    void SetSystemLoadState(const std::string &systemLoadState);
    void SetEffectCurrSceneType(AudioEffectScene currSceneType);
    void SetSpatializationSceneType(AudioSpatializationSceneType spatializationSceneType);
    void SetSpatializationEnabled(bool enabled);
    void SetSpatializationEnabledForFading(bool enabled);
    void AddEffectHandle(AudioEffectHandle effectHandle, AudioEffectLibrary *libHandle, AudioEffectScene currSceneType,
        const std::string &effectName, const std::string &property);
    void ApplyEffectChain(float *bufIn, float *bufOut, uint32_t frameLen, AudioEffectProcInfo procInfo);
    void ApplyEffectChainObserved579(float *bufIn, float *bufOut, uint32_t frameLen,
        AudioEffectProcInfo procInfo, bool &identityCopy);
    void UpdateBufferConfig(uint32_t &channels, uint64_t &channelLayout);
    bool IsEmptyEffectHandles();
    int32_t UpdateMultichannelIoBufferConfig(const uint32_t &channels, const uint64_t &channelLayout);
    void StoreOldEffectChainInfo(std::string &sceneMode, AudioEffectConfig &ioBufferConfig);
    void InitEffectChain();
    void SetHeadTrackingDisabled();
    uint32_t GetLatency();
    int32_t GetPersonalizedSpatialUpdateState();
    int32_t UpdateEffectParam();
    void ResetIoBufferConfig();
    void SetFinalVolume(const float volume);
    float GetFinalVolume();
    void SetCurrVolume(const float volume);
    float GetCurrVolume();
    void SetFinalVolumeState(const bool state);
    bool GetFinalVolumeState();
    void SetSpatialDeviceType(AudioSpatialDeviceType spatialDeviceType);
    int32_t SetEffectProperty(const std::string &effect, const std::string &property);
    void SetStreamUsage(const int32_t streamUsage);
    int32_t updatePrimaryChannel();
    void GetInputChannelInfo(uint32_t &channels, uint64_t &channelLayout);
    bool CheckChannelLayoutByReplyInfo(AudioEffectTransInfo info);
    void SetCurrChannelNoCheck(const uint32_t channel);
    void SetCurrChannelLayoutNoCheck(const uint64_t channelLayout);
    void updateDumpName();
    void SetAbsVolumeStateToEffectChain(const bool absVolumeState);
    void SetEarphoneProduct(int32_t earphoneProduct);
    void SetOutdoorMode(const std::string &outdoorMode);
    void SetSuperLoudnessMode(const std::string &superLoudnessMode);
    void SetStereoEnhancementMode(const std::string &stereoEnhancementMode);
    bool IsEffectChainFading();
    void SetFrontendAppType(const std::string &frontendAppType);
    void SetPersonalizedSpatializationEnabled(const bool &personalizedSpatializationEnabled);
    const std::string& GetSceneType() const { return sceneType_; }
private:
    AudioEffectConfig GetIoBufferConfig();
    void ReleaseEffectChain();
    int32_t SetEffectParamToHandle(AudioEffectHandle handle, int32_t &replyData);
    void DumpEffectProcessData(std::string fileName, void *buffer, size_t len);
    int32_t UpdateMultichannelIoBufferConfigInner();
    int32_t UpdateEffectParamInner();
    void CrossFadeProcess(float *bufOut, uint32_t frameLen);
    void BuildEffectParamData(int32_t *data);

    std::mutex reloadMutex_;
    std::string sceneType_ = "";
    std::string effectMode_ = "";
    uint32_t latency_ = 0;
    int32_t personalizedSpatialUpdateState_ = 0;
    uint32_t extraEffectChainType_ = 0;
    uint32_t foldState_ = 0;
    uint32_t lidState_ = 0;
    uint32_t stereoEnhancementMode_ = 0;
    uint32_t systemLoadState_ = 0;
    StreamUsage streamUsage_ = STREAM_USAGE_INVALID;
    AudioEffectScene currSceneType_ = SCENE_MUSIC;
    std::vector<AudioEffectHandle> standByEffectHandles_;
    std::vector<std::string> effectNames_;
    std::vector<AudioEffectLibrary *> libHandles_;
    AudioEffectConfig ioBufferConfig_ = {};
    AudioEffectConfig preIoBufferConfig_ = {};
    AudioBuffer audioBufIn_ = {};
    AudioBuffer audioBufOut_ = {};
    FILE *dumpFileInput_ = nullptr;
    FILE *dumpFileOutput_ = nullptr;
    float finalVolume_ = 0.0f;
    float currVolume_ = 0.0f;
    bool sendFinalVolumeState_ = false;
    AudioSpatialDeviceType spatialDeviceType_{ EARPHONE_TYPE_OTHERS };
    AudioSpatializationSceneType spatializationSceneType_ = SPATIALIZATION_SCENE_TYPE_MUSIC;
    bool spatializationEnabled_ = false;
    std::string dumpNameIn_ = "";
    std::string dumpNameOut_ = "";
    bool spatializationEnabledFading_ = false;
    int32_t fadingCounts_ = 0;
    uint32_t currChannelNoCheck_ = STEREO;
    uint64_t currchannelLayoutNoCheck_ = CH_LAYOUT_STEREO;
    std::vector<float> effectBuffer_;
    bool absVolumeState_ = true;
    int32_t earphoneProduct_ = 0;
    int32_t outdoorMode_ = 0;
    int32_t superLoudnessMode_ = 0;
    int32_t frontendAppType_ = 0;
    bool personalizedSpatializationEnabled_ = false;

#ifdef SENSOR_ENABLE
    std::shared_ptr<HeadTracker> headTracker_;
#endif
};

} // namespace AudioStandard
} // namespace OHOS
#endif // AUDIO_EFFECT_CHAIN_H