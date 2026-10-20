/*
 * Copyright (c) 2023-2025 Huawei Device Co., Ltd.
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

#include "audio_utils.h"
#include "audio_engine_log.h"
#ifdef SUPPORT_OLD_ENGINE
#include "pa_adapter_manager.h"
#endif
#include "hpae_adapter_manager.h"
#include "pro_audio_stream_manager.h"
#include "hw_decoding_adapter_manager.h"

namespace OHOS {
namespace AudioStandard {
IStreamManager &IStreamManager::GetPlaybackManager(ManagerType managerType)
{
    int32_t enableNewRoute = 0;
    GetSysPara("persist.multimedia.audio.enable_new_route", enableNewRoute);
    switch (managerType) {
        case DIRECT_PLAYBACK:
            if (enableNewRoute != 1) {
                static HpaeAdapterManager directManager(managerType);
                return directManager;
            }
            static ProAudioStreamManager directManager(DIRECT_PLAYBACK);
            return directManager;
        case VOIP_PLAYBACK:
            if (enableNewRoute != 1) {
                static HpaeAdapterManager voipManager(managerType);
                return voipManager;
            }
            static ProAudioStreamManager voipManager(VOIP_PLAYBACK);
            return voipManager;
        case HWDECODING_PLAYBACK:
            static HWDecodingStreamManager hwDecodingManger;
            return hwDecodingManger;
        case AUDIO_VIVID_3DA_DIRECT_PLAYBACK:
            static ProAudioStreamManager cabin3DADirectManager(AUDIO_VIVID_3DA_DIRECT_PLAYBACK);
            return cabin3DADirectManager;
        case PLAYBACK:
        default:
#ifdef SUPPORT_OLD_ENGINE
            int32_t engineFlag = GetEngineFlag();
            if (engineFlag == 1) {
                static HpaeAdapterManager adapterManager(PLAYBACK);
                return adapterManager;
            } else {
                static PaAdapterManager adapterManager(PLAYBACK);
                return adapterManager;
            }
#else
            static HpaeAdapterManager adapterManager(PLAYBACK);
            return adapterManager;
#endif
    }
}

IStreamManager &IStreamManager::GetDupPlaybackManager()
{
#ifdef SUPPORT_OLD_ENGINE
    int32_t engineFlag = GetEngineFlag();
    if (engineFlag == 1) {
        static HpaeAdapterManager adapterManager(DUP_PLAYBACK);
        return adapterManager;
    } else {
        static PaAdapterManager adapterManager(DUP_PLAYBACK);
        return adapterManager;
    }
#else
        static HpaeAdapterManager adapterManager(DUP_PLAYBACK);
        return adapterManager;
#endif
}

IStreamManager &IStreamManager::GetDualPlaybackManager()
{
#ifdef SUPPORT_OLD_ENGINE
    int32_t engineFlag = GetEngineFlag();
    if (engineFlag == 1) {
        static HpaeAdapterManager adapterManager(DUAL_PLAYBACK);
        return adapterManager;
    } else {
        static PaAdapterManager adapterManager(DUAL_PLAYBACK);
        return adapterManager;
    }
#else
        static HpaeAdapterManager adapterManager(DUAL_PLAYBACK);
        return adapterManager;
#endif
}

IStreamManager &IStreamManager::GetRecorderManager()
{
#ifdef SUPPORT_OLD_ENGINE
    int32_t engineFlag = GetEngineFlag();
    if (engineFlag == 1) {
        static HpaeAdapterManager adapterManager(RECORDER);
        return adapterManager;
    } else {
        static PaAdapterManager adapterManager(RECORDER);
        return adapterManager;
    }
#else
        static HpaeAdapterManager adapterManager(RECORDER);
        return adapterManager;
#endif
}
} // namespace AudioStandard
} // namespace OHOS
