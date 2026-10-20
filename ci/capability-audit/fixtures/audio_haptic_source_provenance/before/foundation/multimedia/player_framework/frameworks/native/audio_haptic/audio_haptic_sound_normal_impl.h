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

#ifndef AUDIO_HAPTIC_SOUND_NORMAL_IMPL_H
#define AUDIO_HAPTIC_SOUND_NORMAL_IMPL_H

#include "audio_haptic_sound.h"
#include "audio_haptic_playback_session.h"
#include "player.h"

namespace OHOS {
namespace Media {
class AudioHapticSoundNormalImpl : public AudioHapticSound,
    public std::enable_shared_from_this<AudioHapticSoundNormalImpl> {
public:
    AudioHapticSoundNormalImpl(const AudioSource& audioSource, const bool &muteAudio,
        const AudioStandard::StreamUsage &streamUsage, const int32_t &rendererFlags = 0);
    ~AudioHapticSoundNormalImpl();

    // AudioHapticSound override
    int32_t PrepareSound() override;
    int32_t StartSound(const int32_t &audioHapticSyncId = 0) override;
    int32_t StopSound() override;
    int32_t ReleaseSound() override;
    int32_t SetVolume(float volume) override;
    int32_t SetLoop(bool loop) override;
    int32_t GetAudioCurrentTime() override;
    int32_t SetAudioHapticSoundCallback(const std::shared_ptr<AudioHapticSoundCallback> &callback) override;

    // Private normal-mode hook, selected through the real latency/factory branch.
    int32_t SetPlaybackCallback(const std::shared_ptr<AudioHapticPlaybackCallback> &callback);
    int32_t PrepareForStart();
    void SetAVPlayerState(const std::shared_ptr<AudioHapticPlaybackSession> &session, AudioHapticPlayerState state);
    void NotifyPreparedEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session);
    void NotifyErrorEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session, int32_t errorCode);
    void NotifyFirstFrameEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session, uint64_t latency);
    void NotifyInterruptEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session,
        AudioStandard::InterruptEvent &event);
    void NotifyEndOfStreamEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool isLoop);

    // Retained implementation entry points for legacy standalone sound callers.
    void SetAVPlayerState(AudioHapticPlayerState playerState);
    void NotifyPreparedEvent();
    void NotifyErrorEvent(int32_t errorCode);
    void NotifyFirstFrameEvent(uint64_t latency);
    void NotifyInterruptEvent(AudioStandard::InterruptEvent &interruptEvent);
    void NotifyEndOfStreamEvent(const bool &isLoop);

private:
    int32_t LoadAVPlayer();
    int32_t ResetAVPlayer();
    int32_t PrepareForStartInternal();
    std::shared_ptr<AudioHapticSoundCallback> GetLegacyCallback();
    int32_t FailPreparation(int32_t errorCode);
    void ReleaseBackend(AudioHapticSessionEnd reason);
    bool IsCurrentSession(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool allowError = false) const;
    int32_t ReleaseSoundInternal();
    void ReleaseAVPlayer();
    int32_t OpenAudioSource();
    int32_t ExtractFd(const std::string& audioUri);

    AudioSource audioSource_;
    bool muteAudio_ = false;
    AudioStandard::StreamUsage streamUsage_ = AudioStandard::STREAM_USAGE_UNKNOWN;
    int32_t rendererFlags_ = 0;
    float volume_ = 1.0f;
    bool loop_ = false;
    AudioSource configuredAudioSource_;
    AudioSource pinnedAudioSource_;
    std::atomic<AudioHapticPlayerState> playerState_ = AudioHapticPlayerState::STATE_NEW;

    std::weak_ptr<AudioHapticSoundCallback> audioHapticPlayerCallback_;

    std::mutex audioHapticPlayerLock_;
    // Never call the player/user while holding callbackMutex_ or prepareMutex_.
    std::mutex callbackMutex_;
    std::shared_ptr<AudioHapticPlaybackSession> playbackSession_;
    std::weak_ptr<AudioHapticPlaybackCallback> playbackCallback_;
    bool isStarting_ = false;
    bool hasPendingFirstFrame_ = false;
    uint64_t pendingFirstFrameLatency_ = 0;
    bool errorAdmitted_ = false;

    // var for avplayer
    std::shared_ptr<Media::Player> avPlayer_ = nullptr;
    std::shared_ptr<PlayerCallback> avPlayerCallback_ = nullptr;
    int32_t fileDes_ = -1;
    bool isPrepared_ = false;
    bool isReleased_ = false;
    bool isUnsupportedFile_ = false;
    std::mutex prepareMutex_;
    std::condition_variable prepareCond_;
    int32_t audioHapticSyncId_ = 0;
};

class AHSoundNormalCallback : public PlayerCallback {
public:
    explicit AHSoundNormalCallback(std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl);
    AHSoundNormalCallback(std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl,
        std::shared_ptr<AudioHapticPlaybackSession> session);
    virtual ~AHSoundNormalCallback() = default;

    // PlayerCallback override
    void OnError(int32_t errorCode, const std::string &errorMsg) override;
    void OnInfo(Media::PlayerOnInfoType type, int32_t extra, const Media::Format &infoBody) override;

private:
    void HandleStateChangeEvent(int32_t extra, const Format &infoBody);
    void HandleAudioInterruptEvent(int32_t extra, const Format &infoBody);
    void HandleAudioFirstFrameEvent(int32_t extra, const Format &infoBody);
    void HandleEOSEvent(int32_t extra, const Format &infoBody);

    std::weak_ptr<AudioHapticSoundNormalImpl> soundNormalImpl_;
    const std::shared_ptr<AudioHapticPlaybackSession> session_;
    // Retain the private callback layout; each event computes its own local state.
    const AudioHapticPlayerState playerState_ = AudioHapticPlayerState::STATE_NEW;
};
} // namespace Media
} // namespace OHOS
#endif // AUDIO_HAPTIC_SOUND_NORMAL_IMPL_H
