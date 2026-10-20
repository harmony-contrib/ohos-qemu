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

#ifndef I_STREAM_MANAGER_H
#define I_STREAM_MANAGER_H

#include <optional>
#include <string_view>

#include "i_renderer_stream.h"
#include "i_capturer_stream.h"

namespace OHOS {
namespace AudioStandard {
enum ManagerType : int32_t {
    PLAYBACK = 0,
    DUP_PLAYBACK,
    DUAL_PLAYBACK,
    DIRECT_PLAYBACK,
    VOIP_PLAYBACK,
    EAC3_PLAYBACK,
    HWDECODING_PLAYBACK,
    RECORDER,
    AUDIO_VIVID_3DA_DIRECT_PLAYBACK,
};

class IStreamManager {
public:
    virtual ~IStreamManager() = default;

    static IStreamManager &GetPlaybackManager(ManagerType managerType = PLAYBACK);
    static IStreamManager &GetRecorderManager();
    static IStreamManager &GetDupPlaybackManager();
    static IStreamManager &GetDualPlaybackManager();

    virtual int32_t CreateRender(AudioProcessConfig processConfig, std::shared_ptr<IRendererStream> &stream,
        std::optional<std::string_view> originDeviceName = std::nullopt) = 0;
    virtual int32_t ReleaseRender(uint32_t streamIndex_) = 0;
    virtual int32_t StartRender(uint32_t streamIndex) = 0;
    virtual int32_t StartRenderWithSyncId(uint32_t streamIndex, const int32_t &syncId)
    {
        return StartRender(streamIndex);
    }
    virtual int32_t StopRender(uint32_t streamIndex) = 0;
    virtual int32_t PauseRender(uint32_t streamIndex, bool isStandby = false) = 0;
    virtual int32_t TriggerStartIfNecessary() = 0;
    virtual int32_t GetStreamCount() const noexcept = 0;
    virtual int32_t CreateCapturer(AudioProcessConfig processConfig, std::shared_ptr<ICapturerStream> &stream) = 0;
    virtual int32_t ReleaseCapturer(uint32_t streamIndex_) = 0;
    virtual int32_t AddUnprocessStream(int32_t appUid) = 0;
    virtual uint64_t GetLatency() noexcept = 0;
    virtual void GetAllSinkInputs(std::vector<SinkInput> &sinkInputs) = 0;
    virtual int32_t GetSessionIdAndRemove(uint32_t paIndex, uint32_t &sessionId) = 0;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // I_STREAM_MANAGER_H
