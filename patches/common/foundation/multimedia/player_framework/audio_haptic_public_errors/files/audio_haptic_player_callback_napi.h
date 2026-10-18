/*
 * Copyright (C) 2023 Huawei Device Co., Ltd.
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

#ifndef AUDIO_HAPTIC_PLAYER_CALLBACK_NAPI_H
#define AUDIO_HAPTIC_PLAYER_CALLBACK_NAPI_H

#include "audio_info.h"
#include "napi/native_api.h"
#include "napi/native_node_api.h"

#include "audio_haptic_log.h"
#include "audio_haptic_player.h"
#include "audio_haptic_publication_callback.h"
#include "audio_haptic_common_napi.h"

namespace OHOS {
namespace Media {
class AudioHapticPlayerCallbackNapi : public AudioHapticPlayerCallback, public AudioHapticPublicationCallback {
public:
    explicit AudioHapticPlayerCallbackNapi(napi_env env);
    ~AudioHapticPlayerCallbackNapi();
    void SaveCallbackReference(const std::string &callbackName, napi_value callback);
    void RemoveCallbackReference(const std::string &callbackName);
    void OnInterrupt(const AudioStandard::InterruptEvent &interruptEvent) override;
    void OnEndOfStream(void) override;
    void OnError(int32_t errorCode) override;
    void OnSessionEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool isLoop) override;
    void OnSessionInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
        const AudioStandard::InterruptEvent &interruptEvent) override;
private:
    struct AudioHapticPlayerJsCallback {
        std::shared_ptr<AutoRef> callback = nullptr;
        std::string callbackName = "unknown";
        std::shared_ptr<AudioHapticPlaybackSession> playbackSession;
        bool loopEOS = false;
        void *callbackIdentity = nullptr;
        AudioStandard::InterruptEvent interruptEvent;
    };

    void QueueInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
        const AudioStandard::InterruptEvent &interruptEvent);
    void QueueEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool isLoop);
    void OnInterruptJsCallback(std::unique_ptr<AudioHapticPlayerJsCallback> &jsCb);
    void OnEndOfStreamJsCallback(std::unique_ptr<AudioHapticPlayerJsCallback> &jsCb);

    std::mutex cbMutex_;
    napi_env env_ = nullptr;
    std::shared_ptr<AutoRef> audioInterruptCb_ = nullptr;
    std::shared_ptr<AutoRef> endOfStreamCb_ = nullptr;
};
} // namespace Media
} // namespace OHOS
#endif // AUDIO_HAPTIC_PLAYER_CALLBACK_NAPI_H
