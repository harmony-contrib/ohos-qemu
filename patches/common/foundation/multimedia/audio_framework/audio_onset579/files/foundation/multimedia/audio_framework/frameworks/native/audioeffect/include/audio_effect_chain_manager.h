/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
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


#ifndef AUDIO_EFFECT_CHAIN_MANAGER_H
#define AUDIO_EFFECT_CHAIN_MANAGER_H

#include <cstdio>
#include <cstdint>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include <mutex>
#include <set>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>

#include "audio_effect.h"
#include "audio_effect_chain.h"

#ifdef SENSOR_ENABLE
#include "audio_head_tracker.h"
#endif

#ifdef WINDOW_MANAGER_ENABLE
#include "audio_effect_rotation.h"
#endif
#include "audio_effect_volume.h"

namespace OHOS {
namespace AudioStandard {

class AudioEffectHdiParam;

const uint32_t DEFAULT_FRAMELEN = 1440;
const uint32_t DEFAULT_NUM_CHANNEL = STEREO;
const uint32_t DEFAULT_MCH_NUM_CHANNEL = CHANNEL_6;
const uint32_t DSP_MAX_NUM_CHANNEL = CHANNEL_16;
const uint64_t DEFAULT_NUM_CHANNELLAYOUT = CH_LAYOUT_STEREO;
const uint64_t DEFAULT_MCH_NUM_CHANNELLAYOUT = CH_LAYOUT_5POINT1;
const uint32_t BASE_TEN = 10;
const uint32_t SIZE_OF_SPATIALIZATION_STATE = 2;
const uint32_t MAX_UINT_VOLUME_NUM = 10000;
const uint32_t MAX_UINT_DSP_VOLUME = 65535;
constexpr int64_t MAX_HRTF_LENGTH = 10 * 1024 * 1024;

struct SessionEffectInfo {
    std::string sceneMode;
    std::string sceneType;
    uint32_t channels;
    uint64_t channelLayout;
    int32_t streamUsage;
    int32_t systemVolumeType;
    uint32_t renderId = 0;
    DeviceType deviceType = DEVICE_TYPE_INVALID;
};

struct ChannelOverrideValue {
    uint32_t inputChannels = DEFAULT_NUM_CHANNEL;
    uint64_t inputChannelLayout = DEFAULT_NUM_CHANNELLAYOUT;
};

struct EffectBufferAttr {
    float *bufIn;
    float *bufOut;
    int numChans;
    int frameLen;
    uint32_t outChannels;
    uint64_t outChannelLayout;

    EffectBufferAttr(float *bufIn, float *bufOut, int numChans, int frameLen, uint32_t outChannels,
        uint64_t outChannelLayout)
        : bufIn(bufIn),
          bufOut(bufOut),
          numChans(numChans),
          frameLen(frameLen),
          outChannels(outChannels),
          outChannelLayout(outChannelLayout)
    {
    }
    bool identityCopy579 = false;
};

enum SceneTypeOperation {
    ADD_SCENE_TYPE = 0,
    REMOVE_SCENE_TYPE = 1,
};

class AudioEffectChainManager {
public:
    AudioEffectChainManager();
    ~AudioEffectChainManager();
    static AudioEffectChainManager *GetInstance();
    void InitAudioEffectChainManager(const std::vector<EffectChain> &effectChains,
        const EffectChainManagerParam &effectChainManagerParam,
        const std::vector<std::shared_ptr<AudioEffectLibEntry>> &effectLibraryList);
    void ConstructEffectChainMgrMaps(const std::vector<EffectChain> &effectChains,
        const EffectChainManagerParam &effectChainManagerParam,
        const std::vector<std::shared_ptr<AudioEffectLibEntry>> &effectLibraryList);
    bool CheckAndAddSessionID(const std::string &sessionID);
    int32_t CreateAudioEffectChainDynamic(const std::string &sceneType);
    int32_t CreateAudioEffectChainDynamic(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    bool CheckAndRemoveSessionID(const std::string &sessionID);
    int32_t ReleaseAudioEffectChainDynamic(const std::string &sceneType);
    int32_t ReleaseAudioEffectChainDynamic(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    bool ExistAudioEffectChain(const std::string &sceneType, const std::string &effectMode);
    bool ExistAudioEffectChain(const std::string &sceneType, const std::string &effectMode,
        DeviceType deviceType, uint32_t renderId);
    int32_t ApplyAudioEffectChain(const std::string &sceneType, std::unique_ptr<EffectBufferAttr> &bufferAttr);
    int32_t ApplyAudioEffectChain(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId, std::unique_ptr<EffectBufferAttr> &bufferAttr);
    void SetOutputDeviceSink(int32_t device, const std::string &sinkName);
    bool GetOffloadEnabled();
    int32_t UpdateMultichannelConfig(const std::string &sceneType);
    int32_t UpdateMultichannelConfig(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    int32_t SetChannelOverride(const std::string &sceneType, uint32_t inputChannels, uint64_t inputChannelLayout);
    int32_t SetChannelOverride(const std::string &sceneType, DeviceType deviceType, uint32_t renderId,
        uint32_t inputChannels, uint64_t inputChannelLayout);
    int32_t ClearChannelOverride(const std::string &sceneType);
    int32_t ClearChannelOverride(const std::string &sceneType, DeviceType deviceType, uint32_t renderId);
    int32_t InitAudioEffectChainDynamic(const std::string &sceneType);
    int32_t InitAudioEffectChainDynamic(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    int32_t UpdateSpatializationState(AudioSpatializationState spatializationState);
    int32_t UpdateSpatialDeviceType(AudioSpatialDeviceType spatialDeviceType);
    int32_t SessionInfoMapAdd(const std::string &sessionID, const SessionEffectInfo &info);
    int32_t SessionInfoMapDelete(const std::string &sceneType, const std::string &sessionID);
    int32_t ReturnEffectChannelInfo(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    int32_t EffectRotationUpdate(const uint32_t rotationState);
    int32_t EffectVolumeUpdate();
    int32_t StreamVolumeUpdate(const std::string sessionIDString, const float streamVolume);
    uint32_t GetLatency(const std::string &sessionId);
    int32_t SetSpatializationSceneType(AudioSpatializationSceneType spatializationSceneType);
    int32_t SetEffectSystemVolume(const int32_t systemVolumeType, const float systemVolume);
    int32_t SetAbsVolumeStateToEffect(const bool absVolumeState);
    void ResetInfo();  // Use for testing temporarily.
    void UpdateDefaultAudioEffect();
    bool CheckSceneTypeMatch(const std::string &sinkSceneType, const std::string &sceneType);
    void UpdateParamExtra(const std::string &mainkey, const std::string &subkey, const std::string &value);
    void InitHdiState();
    void UpdateEffectBtOffloadSupported(const bool &isSupported);
    void SetPersonalizedSpatializationStateResultCallback(std::function<void(int32_t result)> callback);
    int32_t UpdateSceneTypeList(const std::string &sceneType, SceneTypeOperation operation);
    uint32_t GetSceneTypeToChainCount(const std::string &sceneType);
    int32_t SetAudioEffectProperty(const AudioEffectPropertyArray &propertyArray);
    int32_t GetAudioEffectProperty(AudioEffectPropertyArray &propertyArray);
    void UpdateStreamUsage();
    int32_t InitEffectBuffer(const std::string &sessionID);
    int32_t QueryEffectChannelInfo(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    void LoadEffectProperties();
    ProcessClusterOperation CheckProcessClusterInstances(const std::string &sceneType);
    int32_t GetOutputChannelInfo(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    int32_t GetOutputChannelInfo(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId, uint32_t &channels, uint64_t &channelLayout);
    int32_t DeleteStreamVolume(const std::string StringSessionID);
    bool ExistAudioEffectChainArm(const std::string sceneType, const AudioEffectMode effectMode);
    bool IsChannelLayoutSupportedForDspEffect(AudioChannelLayout channelLayout);
    void UpdateEarphoneProduct(int32_t earphoneProduct);
    void SetBypassSpatializationForStereo(bool bypass);
    bool IsSpatializationEnabledForChains();
    void SetInitEffectBufferFlag(const bool isNeedInitEffectBuffer);
    int32_t UpdatePersonalizedSpatializationEnabledToChains();
    int32_t UpdatePersonalizedSpatializationEnabledToHdi();
    int32_t UpdatePersonalizedHRTFBin(const int32_t &fd, const long &length);
    int32_t UpdatePersonalizedHRTFBinToArm(const int32_t &fd, const long &length);
    int32_t UpdatePersonalizedHRTFBinToHdi(const int32_t &fd, const long &length);
    int32_t QueryEffectChannelInfo(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId, uint32_t &channels, uint64_t &channelLayout);
    ProcessClusterOperation CheckProcessClusterInstances(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    bool ExistAudioEffectChainArm(const std::string sceneType, const AudioEffectMode effectMode,
        DeviceType deviceType, uint32_t renderId);
    int32_t UpdatePersonalizedSpatializationState(const bool personalizedSpatializationEnabled);
    int32_t UpdatePersonalizedSpatializationStateInner(const bool personalizedSpatializationEnabled);

private:
    int32_t SetAudioEffectChainDynamic(std::string &sceneType, const std::string &effectMode);
    int32_t SetAudioEffectChainDynamic(std::string &sceneType, const std::string &effectMode,
        DeviceType deviceType, uint32_t renderId);
    void UpdateSensorState();
    void DeleteAllChains();
    void RecoverAllChains();
    int32_t EffectDspVolumeUpdate(std::shared_ptr<AudioEffectVolume> audioEffectVolume);
    int32_t EffectApVolumeUpdate(std::shared_ptr<AudioEffectVolume> audioEffectVolume);
    int32_t SendEffectApVolume(std::shared_ptr<AudioEffectVolume> audioEffectVolume);
    void SetSpatializationSceneTypeToChains();
    bool HasRunningSessionForEffectChain(std::shared_ptr<AudioEffectChain> audioEffectChain);
    void SetSpatializationEnabledToChains();
    void SetSpkOffloadState();
    void UpdateCurrSceneType(AudioEffectScene &currSceneType, const std::string &sceneType);
    void FindMaxEffectChannels(const std::string &sceneType, const std::set<std::string> &sessions, uint32_t &channels,
        uint64_t &channelLayout);
    int32_t UpdateDeviceInfo(int32_t device, const std::string &sinkName);
    std::shared_ptr<AudioEffectChain> CreateAudioEffectChain(const std::string &sceneType, bool isPriorScene);
    bool CheckIfSpkDsp();
    int32_t CheckAndReleaseCommonEffectChain(const std::string &sceneType);
    int32_t CheckAndReleaseCommonEffectChain(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    void FindMaxSessionID(uint32_t &maxSessionID, std::string &sceneType,
        const std::string &scenePairType, std::set<std::string> &sessions);
    int32_t UpdateCurrSceneTypeAndStreamUsageForDsp();
    void SendAudioParamToHDI(HdiSetParamCommandCode code, const std::string &value, DeviceType device);
    void SendAudioParamToARM(HdiSetParamCommandCode code, const std::string &value);
    std::string GetDeviceTypeName();
    std::string GetDeviceTypeName(DeviceType deviceType);
    std::string GenerateEffectChainKey(const std::string &sceneType, DeviceType deviceType, uint32_t renderId);
    bool IsEffectChainStop(const std::string &sceneType, const std::string &sessionID);
    int32_t InitEffectBufferInner(const std::string &sessionID);
    int32_t InitAudioEffectChainDynamicInner(const std::string &sceneType);
    int32_t InitAudioEffectChainDynamicInner(const std::string &sceneType, DeviceType deviceType, uint32_t renderId);
    int32_t QueryEffectChannelInfoInner(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    int32_t SetAbsVolumeStateToEffectInner(const bool absVolumeState);
    int32_t EffectDspAbsVolumeStateUpdate(const bool absVolumeState);
    int32_t EffectApAbsVolumeStateUpdate(const bool absVolumeState);
    void UpdateDefaultAudioEffectInner();
    void UpdateDefaultAudioEffectByRenderId();
    void UpdateDefaultAudioEffectOldPath(uint32_t maxDefaultSessionID);
    void UpdateStreamUsageInner();
    void UpdateStreamUsageByRenderId();
    void FindMaxSessionIdPerRenderId(const std::set<std::string> &sessions,
        std::map<uint32_t, uint32_t> &renderIdToMaxSid,
        std::shared_ptr<AudioEffectVolume> audioEffectVolume);
    void UpdateStreamUsageByRenderIdMap(const std::string &sceneType,
        std::map<uint32_t, uint32_t> &renderIdToMaxSid);
    void UpdateStreamUsageForSpecialScene();
    void UpdateStreamUsageForPriorScene();
    int32_t DeleteStreamVolumeInner(const std::string StringSessionID);
#ifdef WINDOW_MANAGER_ENABLE
    int32_t EffectDspRotationUpdate(std::shared_ptr<AudioEffectRotation> audioEffectRotation,
        const uint32_t rotationState);
    int32_t EffectApRotationUpdate(std::shared_ptr<AudioEffectRotation> audioEffectRotation,
        const uint32_t rotationState);
#endif
    int32_t CreateAudioEffectChainDynamicInner(const std::string &sceneType);
    int32_t CreateAudioEffectChainDynamicInner(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    int32_t ReleaseAudioEffectChainDynamicInner(const std::string &sceneType);
    int32_t ReleaseAudioEffectChainDynamicInner(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    bool ExistAudioEffectChainInner(const std::string &sceneType, const std::string &effectMode);
    int32_t UpdateMultichannelConfigInner(const std::string &sceneType);
    int32_t UpdateMultichannelConfigInner(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    bool ConsultChannelOverride(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    bool ConsultChannelOverride(const std::string &sceneType, DeviceType deviceType, uint32_t renderId,
        uint32_t &channels, uint64_t &channelLayout);
    // Consult channel override by route key: self key first, then any peer route key that shares the
    // same AudioEffectChain instance (shared-chain equivalence class). Returns false when the chain for
    // `key` has not been created yet (defensive: override must not apply to a non-existent chain).
    bool ConsultChannelOverrideByKey(const std::string &key, uint32_t &channels, uint64_t &channelLayout);
    int32_t UpdateSpatializationStateInner(AudioSpatializationState spatializationState);
    int32_t SetHdiParam(const AudioEffectScene &sceneType);
    int32_t ReturnEffectChannelInfoInner(const std::string &sceneType, uint32_t &channels, uint64_t &channelLayout);
    int32_t ReturnEffectChannelInfoInner(const std::string &sceneType, DeviceType deviceType,
        uint32_t renderId, uint32_t &channels, uint64_t &channelLayout);
    int32_t EffectVolumeUpdateInner(std::shared_ptr<AudioEffectVolume> audioEffectVolume);
    void InitHdiStateInner();
    void UpdateSpatializationEnabled(AudioSpatializationState spatializationState);
    void ConfigureAudioEffectChain(std::shared_ptr<AudioEffectChain> audioEffectChain, const std::string &effectMode);
    int32_t NotifyAndCreateAudioEffectChain(const std::string &sceneType);
    int32_t NotifyAndCreateAudioEffectChain(const std::string &sceneType,
        DeviceType deviceType, uint32_t renderId);
    void WaitAndReleaseEffectChain(const std::string &sceneType, const std::string &sceneTypeAndDeviceKey,
        const std::string &defaultSceneTypeAndDeviceKey, int32_t ret);
    bool IsDeviceTypeSupportingSpatialization();
    void ActivateHeadTracking();
    void DeactivateHeadTracking();
    std::string GetEffectChainByMode(std::string effectChainKey);
    std::map<std::string, std::shared_ptr<AudioEffectLibEntry>> effectToLibraryEntryMap_;
    std::map<std::string, std::string> effectToLibraryNameMap_;
    std::map<std::string, std::vector<std::string>> effectChainToEffectsMap_;
    std::map<std::string, std::string> sceneTypeAndModeToEffectChainNameMap_;
    std::map<std::string, std::shared_ptr<AudioEffectChain>> sceneTypeToEffectChainMap_;
    std::map<std::string, int32_t> sceneTypeToEffectChainCountMap_;
    std::set<std::string> sessionIDSet_;
    std::map<std::string, std::set<std::string>> sceneTypeToSessionIDMap_;
    std::map<std::string, SessionEffectInfo> sessionIDToEffectInfoMap_;
    std::map<std::string, ChannelOverrideValue> channelOverrideMap_;
    std::map<std::string, int32_t> sceneTypeToEffectChainCountBackupMap_;
    std::set<std::string> sceneTypeToSpecialEffectSet_;
    std::map<uint32_t, std::set<std::string>> renderIdToEffectChainKeysMap_;
    std::vector<std::string> priorSceneList_;
    std::unordered_map<std::string, std::string> effectPropertyMap_;
    std::unordered_map<std::string, std::string> defaultPropertyMap_;
    std::vector<std::pair<std::string, int32_t>> sceneTypeCountList_;
    DeviceType deviceType_ = DEVICE_TYPE_SPEAKER;
    std::string deviceSink_ = "Speaker";
    std::string deviceClass_ = "";
    std::string extraSceneType_ = "0";
    std::string foldState_ = "0";
    std::string lidState_ = "0";
    std::string systemLoadState_ = "0";
    std::string maxSessionIDToSceneType_ = "";
    std::string maxDefaultSessionIDToSceneType_ = "";
    std::string outdoorMode_ = "0";
    std::string superLoudnessMode_ = "music_off";
    std::string stereoEnhancementMode_ = "0";
    bool isInitialized_ = false;
    std::mutex dynamicMutex_;
    std::atomic<bool> spatializationEnabled_ = false;
    bool headTrackingEnabled_ = false;
    bool btOffloadEnabled_ = false;
    bool spkOffloadEnabled_ = false;
    bool initializedLogFlag_ = true;
    bool btOffloadSupported_ = true;
    AudioSpatializationSceneType spatializationSceneType_ = SPATIALIZATION_SCENE_TYPE_MUSIC;
    bool isDefaultEffectChainExisted_ = false;
    int32_t maxEffectChainCount_ = 1;
    uint32_t maxSessionID_ = 0;
    AudioSpatialDeviceType spatialDeviceType_{ EARPHONE_TYPE_OTHERS };
    bool hasLoadedEffectProperties_ = false;
    std::condition_variable cv_;
    bool defaultEffectChainCreated_ = false;
    bool absVolumeState_ = true;
    int32_t currDspStreamUsage_ = -2;
    AudioEffectScene currDspSceneType_ = SCENE_INITIAL;
    int32_t earphoneProduct_ = 0;
    bool bypassSpatializationForStereo_ = false;
    bool isNeedInitEffectBuffer_ = true;
    bool personalizedSpatializationEnabled_ = false;
    std::function<void(int32_t result)> personalizedSpatializationStateResultCallback_ = nullptr;

#ifdef SENSOR_ENABLE
    std::shared_ptr<HeadTracker> headTracker_;
#endif

    std::shared_ptr<AudioEffectHdiParam> audioEffectHdiParam_;
    int8_t effectHdiInput_[SEND_HDI_COMMAND_LEN];
    std::string frontendAppType_ = "0";
};
}  // namespace AudioStandard
}  // namespace OHOS
#endif // AUDIO_EFFECT_CHAIN_MANAGER_H
