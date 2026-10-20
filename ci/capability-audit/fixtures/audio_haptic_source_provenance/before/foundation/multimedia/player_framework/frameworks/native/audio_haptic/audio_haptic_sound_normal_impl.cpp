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

#include "audio_haptic_player_impl.h"
#include "audio_haptic_sound_normal_impl.h"

#include <fcntl.h>
#include <utility>

#include "audio_haptic_log.h"
#include "directory_ex.h"
#include "media_errors.h"
#include "player.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticSoundNormalImpl"};
}

namespace OHOS {
namespace Media {
const int32_t LOAD_WAIT_SECONDS = 2;

AudioHapticSoundNormalImpl::AudioHapticSoundNormalImpl(const AudioSource& audioSource, const bool &muteAudio,
    const AudioStandard::StreamUsage &streamUsage, const int32_t &rendererFlags)
    : audioSource_(audioSource),
      muteAudio_(muteAudio),
      streamUsage_(streamUsage),
      rendererFlags_(rendererFlags)
{
}

AudioHapticSoundNormalImpl::~AudioHapticSoundNormalImpl()
{
    // A failed replacement may leave only the independently pinned source FD.
    (void)ReleaseSoundInternal();
}

int32_t AudioHapticSoundNormalImpl::LoadAVPlayer()
{
    auto backend = PlayerFactory::CreatePlayer();
    CHECK_AND_RETURN_RET_LOG(backend != nullptr, MSERR_INVALID_VAL, "Failed to create AvPlayer instance");
    auto session = std::make_shared<AudioHapticPlaybackSession>(backend);
    auto callback = std::make_shared<AHSoundNormalCallback>(shared_from_this(), session);
    int32_t ret = backend->SetPlayerCallback(callback); // Exactly once on this fresh IDLE backend.
    if (ret != MSERR_OK) {
        session->end.store(AudioHapticSessionEnd::PREPARE_FAILED);
        (void)backend->Release();
        return ret;
    }
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    {
        std::lock_guard<std::mutex> lock(callbackMutex_);
        playbackSession_ = session;
        isStarting_ = false;
        hasPendingFirstFrame_ = false;
        pendingFirstFrameLatency_ = 0;
        errorAdmitted_ = false;
        target = playbackCallback_.lock();
    }
    avPlayer_ = backend;
    avPlayerCallback_ = callback;
    configuredAudioSource_ = {};
    playerState_ = AudioHapticPlayerState::STATE_NEW;
    if (target != nullptr) { target->OnPlaybackCreated(session); }
    return MSERR_OK;
}

int32_t AudioHapticSoundNormalImpl::PrepareSound()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    {
        std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
        CHECK_AND_RETURN_RET_LOG(!isReleased_, MSERR_INVALID_OPERATION, "The avplayer has been released.");
    }
    CHECK_AND_RETURN_RET_LOG(!audioSource_.empty(), MSERR_OPEN_FILE_FAILED, "The audio source is empty");
    return ResetAVPlayer();
}

int32_t AudioHapticSoundNormalImpl::OpenAudioSource()
{
    if (fileDes_ >= 0 && !(audioSource_ != pinnedAudioSource_)) { return MSERR_OK; }
    const auto audioUri = audioSource_.audioUri;
    const auto audioFd = audioSource_.fd;
    CHECK_AND_RETURN_RET_LOG(!audioUri.empty() || audioFd > FILE_DESCRIPTOR_INVALID, MSERR_OPEN_FILE_FAILED,
        "The audio uri is empty or the fd is invalid");
    int32_t pinnedFd = -1;
    if (!audioUri.empty()) {
        int32_t oldFd = ExtractFd(audioUri);
        if (oldFd != FILE_DESCRIPTOR_INVALID) {
            pinnedFd = dup(oldFd);
        } else {
            std::string absFilePath;
            CHECK_AND_RETURN_RET_LOG(PathToRealPath(audioUri, absFilePath), MSERR_OPEN_FILE_FAILED,
                "file is not real path, file path: %{private}s", audioUri.c_str());
            CHECK_AND_RETURN_RET_LOG(!absFilePath.empty(), MSERR_OPEN_FILE_FAILED, "Empty canonical source path");
            pinnedFd = open(absFilePath.c_str(), O_RDONLY | O_CLOEXEC);
        }
    } else {
        pinnedFd = dup(audioFd);
    }
    CHECK_AND_RETURN_RET_LOG(pinnedFd > FILE_DESCRIPTOR_INVALID, MSERR_OPEN_FILE_FAILED,
        "Prepare: Invalid fileDes for avplayer.");
    if (fileDes_ >= 0) { (void)close(fileDes_); }
    fileDes_ = pinnedFd;
    pinnedAudioSource_ = audioSource_; // Includes the original offset/length, not a later caller-FD lookup.
    return MSERR_OK;
}

int32_t AudioHapticSoundNormalImpl::ResetAVPlayer()
{
    // A real fresh backend has no old Play callbacks and must not Reset(IDLE).
    ReleaseBackend(AudioHapticSessionEnd::REPLACED);
    {
        std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
        CHECK_AND_RETURN_RET_LOG(!isReleased_, MSERR_INVALID_OPERATION, "The avplayer has been released.");
        isPrepared_ = false;
        isUnsupportedFile_ = false;
    }
    int32_t ret = LoadAVPlayer();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Failed to create independent AVPlayer");
    ret = OpenAudioSource();
    if (ret != MSERR_OK) { return FailPreparation(ret); }
    ret = avPlayer_->SetSource(fileDes_, pinnedAudioSource_.offset, pinnedAudioSource_.length);
    if (ret != MSERR_OK) { return FailPreparation(MSERR_OPEN_FILE_FAILED); }
    Format format;
    format.PutIntValue(PlayerKeys::CONTENT_TYPE, AudioStandard::CONTENT_TYPE_UNKNOWN);
    format.PutIntValue(PlayerKeys::STREAM_USAGE, streamUsage_);
    if (rendererFlags_ != 0) { format.PutIntValue(PlayerKeys::RENDERER_FLAG, rendererFlags_); }
    ret = avPlayer_->SetParameter(format);
    if (ret != MSERR_OK) { return FailPreparation(ret); }
    ret = avPlayer_->PrepareAsync();
    if (ret != MSERR_OK) { return FailPreparation(ret); }
    {
        std::unique_lock<std::mutex> lockPrepare(prepareMutex_);
        prepareCond_.wait_for(lockPrepare, std::chrono::seconds(LOAD_WAIT_SECONDS),
            [this]() { return isPrepared_ || isReleased_ || isUnsupportedFile_; });
        if (isReleased_) { ret = MSERR_INVALID_OPERATION; }
        else if (isUnsupportedFile_) { ret = MSERR_UNSUPPORT_FILE; }
        else if (!isPrepared_) { ret = MSERR_OPEN_FILE_FAILED; }
    }
    if (ret != MSERR_OK) { return FailPreparation(ret); }
    float actualVolume = volume_ * (muteAudio_ ? 0 : 1);
    (void)avPlayer_->SetVolume(actualVolume, actualVolume);
    (void)avPlayer_->SetLooping(loop_);
    configuredAudioSource_ = audioSource_;
    playerState_ = AudioHapticPlayerState::STATE_PREPARED;
    return MSERR_OK;
}


int32_t AudioHapticSoundNormalImpl::StartSound(const int32_t &audioHapticSyncId)
{
    std::unique_lock<std::mutex> lock(audioHapticPlayerLock_);
    int32_t ret = PrepareForStartInternal();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Prepare independent playback failed");
    audioHapticSyncId_ = audioHapticSyncId;
    Format format;
    format.PutIntValue(PlayerKeys::PLAYER_AUDIO_HAPTICS_SYNC_ID, audioHapticSyncId_);
    ret = avPlayer_->SetParameter(format);
    if (ret != MSERR_OK) {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        playbackSession_->end.store(AudioHapticSessionEnd::START_FAILED);
        return ret;
    }
    std::shared_ptr<AudioHapticPlaybackSession> session;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        session = playbackSession_;
        CHECK_AND_RETURN_RET_LOG(IsCurrentSession(session), MSERR_START_FAILED, "Playback was retired before Play");
        session->playIssued.store(true);
        isStarting_ = true;
        hasPendingFirstFrame_ = false;
    }
    ret = avPlayer_->Play();
    AudioHapticPlayerImpl::SendHapticPlayerEvent(ret, "AVPLAYER_START_FAILED");
    bool pending = false;
    uint64_t latency = 0;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        isStarting_ = false;
        session->playConfirmed.store(ret == MSERR_OK);
        if (ret != MSERR_OK) { session->end.store(AudioHapticSessionEnd::START_FAILED); }
        pending = ret == MSERR_OK && IsCurrentSession(session) && hasPendingFirstFrame_;
        latency = pendingFirstFrameLatency_;
        hasPendingFirstFrame_ = false;
    }
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_START_FAILED, "Start failed %{public}d", ret);
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (IsCurrentSession(session)) { playerState_ = AudioHapticPlayerState::STATE_RUNNING; }
    }
    lock.unlock();
    if (pending) { NotifyFirstFrameEvent(session, latency); }
    return MSERR_OK;
}

int32_t AudioHapticSoundNormalImpl::StopSound()
{
    MEDIA_LOGI("StopSound with AVPlayer");
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(avPlayer_ != nullptr && playerState_ != AudioHapticPlayerState::STATE_INVALID,
        MSERR_INVALID_VAL, "StopAVPlayer: no available AVPlayer_");

    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (playbackSession_ != nullptr) { playbackSession_->end.store(AudioHapticSessionEnd::STOPPED); }
        hasPendingFirstFrame_ = false;
    }
    if (playerState_ != AudioHapticPlayerState::STATE_STOPPED) {
        (void)avPlayer_->Stop();
    }

    playerState_ = AudioHapticPlayerState::STATE_STOPPED;
    return MSERR_OK;
}

int32_t AudioHapticSoundNormalImpl::ReleaseSound()
{
    MEDIA_LOGI("ReleaseSound with AVPlayer");
    return ReleaseSoundInternal();
}

int32_t AudioHapticSoundNormalImpl::ReleaseSoundInternal()
{
    MEDIA_LOGI("Enter ReleaseSoundInternal().");
    {
        std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
        isReleased_ = true;
        prepareCond_.notify_one();
    }
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, MSERR_OK,
        "The audio haptic player for normal mode has been released.");
    ReleaseAVPlayer();
    playerState_ = AudioHapticPlayerState::STATE_RELEASED;
    return MSERR_OK;
}

void AudioHapticSoundNormalImpl::ReleaseAVPlayer()
{
    ReleaseBackend(AudioHapticSessionEnd::RELEASED);
    if (fileDes_ >= 0) { (void)close(fileDes_); fileDes_ = -1; }
    pinnedAudioSource_ = {};
}

int32_t AudioHapticSoundNormalImpl::SetVolume(float volume)
{
    MEDIA_LOGI("AudioHapticSoundNormalImpl::SetVolume %{public}f", volume);
    if (volume < 0.0f || volume > 1.0f) {
        MEDIA_LOGE("SetVolume: the volume value is invalid.");
        return MSERR_INVALID_VAL;
    }

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    int32_t result = MSERR_OK;
    volume_ = volume;

    if (playerState_ != AudioHapticPlayerState::STATE_PREPARED &&
        playerState_ != AudioHapticPlayerState::STATE_RUNNING) {
        MEDIA_LOGI("Audio haptic player is not prepared or running. No need to modify player");
        return result;
    }

    float actualVolume = volume_ * (muteAudio_ ? 0 : 1);
    result = avPlayer_->SetVolume(actualVolume, actualVolume);
    return result;
}

int32_t AudioHapticSoundNormalImpl::SetLoop(bool loop)
{
    MEDIA_LOGI("AudioHapticSoundNormalImpl::SetLoop %{public}d", loop);
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    int32_t result = MSERR_OK;
    loop_ = loop;

    if (playerState_ != AudioHapticPlayerState::STATE_PREPARED &&
        playerState_ != AudioHapticPlayerState::STATE_RUNNING) {
        MEDIA_LOGI("Audio haptic player is not prepared or running. No need to modify player");
        return result;
    }

    result = avPlayer_->SetLooping(loop_);
    return result;
}

int32_t AudioHapticSoundNormalImpl::GetAudioCurrentTime()
{
    std::shared_ptr<Player> backend;
    {
        // The vibration worker may hold its wait mutex here. Do not take the
        // normal API mutex: LoadAVPlayer announces a session in the opposite direction.
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (playbackSession_ != nullptr) { backend = playbackSession_->backend.lock(); }
    }
    if (backend == nullptr) {
        MEDIA_LOGE("GetAudioCurrentTime: no current AVPlayer backend");
        return -1;
    }
    int32_t currentTime = -1;
    (void)backend->GetCurrentTime(currentTime);
    return currentTime;
}

int32_t AudioHapticSoundNormalImpl::SetAudioHapticSoundCallback(
    const std::shared_ptr<AudioHapticSoundCallback> &callback)
{
    if (callback == nullptr) {
        MEDIA_LOGE("The audio haptic player callback is nullptr.");
        return MSERR_INVALID_VAL;
    }

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    audioHapticPlayerCallback_ = callback;
    return MSERR_OK;
}

std::shared_ptr<AudioHapticSoundCallback> AudioHapticSoundNormalImpl::GetLegacyCallback()
{
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    return audioHapticPlayerCallback_.lock();
}

int32_t AudioHapticSoundNormalImpl::SetPlaybackCallback(const std::shared_ptr<AudioHapticPlaybackCallback> &callback)
{
    CHECK_AND_RETURN_RET_LOG(callback != nullptr, MSERR_INVALID_VAL, "Null private playback callback");
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    CHECK_AND_RETURN_RET_LOG(playbackSession_ == nullptr, MSERR_INVALID_OPERATION, "Do not rebind a live backend");
    playbackCallback_ = callback;
    return MSERR_OK;
}

bool AudioHapticSoundNormalImpl::IsCurrentSession(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool allowError) const
{
    // Caller holds callbackMutex_. Identity originates at the real backend creation.
    return session != nullptr && playbackSession_ == session &&
        (session->end.load() == AudioHapticSessionEnd::LIVE ||
            (allowError && (session->end.load() == AudioHapticSessionEnd::ERROR ||
                (session->end.load() == AudioHapticSessionEnd::INTERRUPTED && !session->playIssued.load()))));
}

void AudioHapticSoundNormalImpl::ReleaseBackend(AudioHapticSessionEnd reason)
{
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (playbackSession_ != nullptr) { playbackSession_->end.store(reason); }
        playbackSession_.reset();
        isStarting_ = false;
        hasPendingFirstFrame_ = false;
    }
    if (avPlayer_ != nullptr) { (void)avPlayer_->Release(); avPlayer_.reset(); }
    avPlayerCallback_.reset();
    configuredAudioSource_ = {};
}

int32_t AudioHapticSoundNormalImpl::FailPreparation(int32_t errorCode)
{
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    if (playbackSession_ != nullptr) { playbackSession_->end.store(AudioHapticSessionEnd::PREPARE_FAILED); }
    hasPendingFirstFrame_ = false;
    return errorCode;
}

int32_t AudioHapticSoundNormalImpl::PrepareForStart()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    return PrepareForStartInternal();
}

int32_t AudioHapticSoundNormalImpl::PrepareForStartInternal()
{
    {
        std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
        CHECK_AND_RETURN_RET_LOG(!isReleased_, MSERR_INVALID_OPERATION, "The avplayer has been released.");
    }
    CHECK_AND_RETURN_RET_LOG(!audioSource_.empty(), MSERR_OPEN_FILE_FAILED, "The audio source is invalid");
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (playerState_ == AudioHapticPlayerState::STATE_RUNNING && IsCurrentSession(playbackSession_)) {
            return MSERR_START_FAILED;
        }
    }
    bool keepPrepared = false;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        keepPrepared = avPlayer_ != nullptr && IsCurrentSession(playbackSession_) &&
            !playbackSession_->playIssued.load() && playerState_ == AudioHapticPlayerState::STATE_PREPARED &&
            !(audioSource_ != configuredAudioSource_);
    }
    return keepPrepared ? MSERR_OK : ResetAVPlayer();
}

void AudioHapticSoundNormalImpl::SetAVPlayerState(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    AudioHapticPlayerState state)
{
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    bool interruptedPrepare = session != nullptr && playbackSession_ == session && !session->playIssued.load() &&
        session->end.load() == AudioHapticSessionEnd::INTERRUPTED && state == AudioHapticPlayerState::STATE_PREPARED;
    CHECK_AND_RETURN_LOG(IsCurrentSession(session) || interruptedPrepare, "Stale backend state event");
    if (state == AudioHapticPlayerState::STATE_INVALID) {
        auto expected = AudioHapticSessionEnd::LIVE;
        CHECK_AND_RETURN_LOG(session->end.compare_exchange_strong(expected, AudioHapticSessionEnd::ERROR),
            "Do not overwrite explicit retirement with a late state error");
    }
    playerState_ = state;
}

void AudioHapticSoundNormalImpl::NotifyPreparedEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session)
{
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    bool interruptedPrepare = session != nullptr && playbackSession_ == session && !session->playIssued.load() &&
        session->end.load() == AudioHapticSessionEnd::INTERRUPTED;
    CHECK_AND_RETURN_LOG(IsCurrentSession(session) || interruptedPrepare, "Stale backend prepared event");
    std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
    if (!isReleased_) { isPrepared_ = true; prepareCond_.notify_one(); }
}

void AudioHapticSoundNormalImpl::NotifyErrorEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    int32_t errorCode)
{
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    std::shared_ptr<AudioHapticSoundCallback> legacy;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        CHECK_AND_RETURN_LOG(IsCurrentSession(session, true) && !errorAdmitted_, "Stale or duplicate backend error");
        auto expected = session->end.load();
        CHECK_AND_RETURN_LOG(expected == AudioHapticSessionEnd::LIVE || expected == AudioHapticSessionEnd::ERROR ||
            (expected == AudioHapticSessionEnd::INTERRUPTED && !session->playIssued.load()),
            "Explicit retirement won before error admission");
        if (expected != AudioHapticSessionEnd::ERROR) {
            CHECK_AND_RETURN_LOG(session->end.compare_exchange_strong(expected, AudioHapticSessionEnd::ERROR),
                "Do not overwrite explicit retirement with a late error");
        }
        errorAdmitted_ = true;
        hasPendingFirstFrame_ = false;
        target = playbackCallback_.lock();
        if (target == nullptr) { legacy = audioHapticPlayerCallback_.lock(); }
    }
    // Admission snapshots a real error before waking Prepare; the private target
    // queues user notification and never waits for/reenters the API thread here.
    if (target != nullptr) { target->OnPlaybackError(session, errorCode); }
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        if (playbackSession_ != session) { return; }
        if (static_cast<MediaServiceErrCode>(errorCode) == MSERR_UNSUPPORT_FILE) {
            std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
            isUnsupportedFile_ = true;
            prepareCond_.notify_one();
        }
    }
    if (legacy != nullptr) { legacy->OnError(errorCode); }
}

void AudioHapticSoundNormalImpl::NotifyFirstFrameEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    uint64_t latency)
{
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    std::shared_ptr<AudioHapticSoundCallback> legacy;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        CHECK_AND_RETURN_LOG(IsCurrentSession(session) && session->playIssued.load(), "Stale/nonplaying backend first frame");
        if (isStarting_) {
            pendingFirstFrameLatency_ = latency;
            hasPendingFirstFrame_ = true;
            return;
        }
        CHECK_AND_RETURN_LOG(session->playConfirmed.load(), "Unconfirmed Play first frame");
        target = playbackCallback_.lock();
        if (target == nullptr) { legacy = audioHapticPlayerCallback_.lock(); }
    }
    if (target != nullptr) { target->OnPlaybackFirstFrame(session, latency); }
    else if (legacy != nullptr) { legacy->OnFirstFrameWriting(latency); }
}

void AudioHapticSoundNormalImpl::NotifyInterruptEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    AudioStandard::InterruptEvent &event)
{
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    std::shared_ptr<AudioHapticSoundCallback> legacy;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        CHECK_AND_RETURN_LOG(IsCurrentSession(session), "Stale backend interrupt");
        auto expected = AudioHapticSessionEnd::LIVE;
        CHECK_AND_RETURN_LOG(session->end.compare_exchange_strong(expected, AudioHapticSessionEnd::INTERRUPTED),
            "Do not overwrite explicit retirement with a late interrupt");
        hasPendingFirstFrame_ = false;
        target = playbackCallback_.lock();
        if (target == nullptr) { legacy = audioHapticPlayerCallback_.lock(); }
    }
    if (target != nullptr) { target->OnPlaybackInterrupt(session, event); }
    else if (legacy != nullptr) { legacy->OnInterrupt(event); }
}

void AudioHapticSoundNormalImpl::NotifyEndOfStreamEvent(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    std::shared_ptr<AudioHapticPlaybackCallback> target;
    std::shared_ptr<AudioHapticSoundCallback> legacy;
    {
        std::lock_guard<std::mutex> lockCallback(callbackMutex_);
        CHECK_AND_RETURN_LOG(IsCurrentSession(session) && session->playIssued.load(), "Stale/nonplaying backend EOS");
        if (!isLoop) {
            auto expected = AudioHapticSessionEnd::LIVE;
            CHECK_AND_RETURN_LOG(session->end.compare_exchange_strong(expected, AudioHapticSessionEnd::ENDED),
                "Do not overwrite explicit retirement with a late EOS");
            playerState_ = AudioHapticPlayerState::STATE_STOPPED;
            hasPendingFirstFrame_ = false;
        }
        target = playbackCallback_.lock();
        if (target == nullptr) { legacy = audioHapticPlayerCallback_.lock(); }
    }
    if (target != nullptr) { target->OnPlaybackEndOfStream(session, isLoop); }
    else if (legacy != nullptr) { legacy->OnEndOfStream(); }
}

void AudioHapticSoundNormalImpl::SetAVPlayerState(AudioHapticPlayerState playerState)
{
    MEDIA_LOGI("SetAVPlayerState, state %{public}d", playerState);
    playerState_ = playerState;
}

void AudioHapticSoundNormalImpl::NotifyPreparedEvent()
{
    std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
    isPrepared_ = true;
    prepareCond_.notify_one();
}

void AudioHapticSoundNormalImpl::NotifyErrorEvent(int32_t errorCode)
{
    MediaServiceErrCode mediaErr = static_cast<MediaServiceErrCode>(errorCode);
    if (mediaErr == MSERR_UNSUPPORT_FILE) {
        std::lock_guard<std::mutex> lockPrepare(prepareMutex_);
        isUnsupportedFile_ = true;
        prepareCond_.notify_one();
    }

    auto cb = GetLegacyCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyFirstFrameEvent for audio haptic player");
        cb->OnError(errorCode);
    } else {
        MEDIA_LOGE("NotifyFirstFrameEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticSoundNormalImpl::NotifyFirstFrameEvent(uint64_t latency)
{
    auto cb = GetLegacyCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyFirstFrameEvent for audio haptic player");
        cb->OnFirstFrameWriting(latency);
    } else {
        MEDIA_LOGE("NotifyFirstFrameEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticSoundNormalImpl::NotifyInterruptEvent(AudioStandard::InterruptEvent &interruptEvent)
{
    auto cb = GetLegacyCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyInterruptEvent for audio haptic player");
        cb->OnInterrupt(interruptEvent);
    } else {
        MEDIA_LOGE("NotifyInterruptEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticSoundNormalImpl::NotifyEndOfStreamEvent(const bool &isLoop)
{
    MEDIA_LOGI("NotifyEndOfStreamEvent");
    if (!isLoop) {
        playerState_ = AudioHapticPlayerState::STATE_STOPPED;
    }
    auto cb = GetLegacyCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyEndOfStreamEvent for audio haptic player");
        cb->OnEndOfStream();
    } else {
        MEDIA_LOGE("NotifyEndOfStreamEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

int32_t AudioHapticSoundNormalImpl::ExtractFd(const std::string& audioUri)
{
    const std::string prefix = "fd://";
    if (audioUri.size() <= prefix.size() || audioUri.substr(0, prefix.length()) != prefix) {
        MEDIA_LOGW("ExtractFd: Input does not start with the required prefix.");
        return FILE_DESCRIPTOR_INVALID;
    }

    std::string numberPart = audioUri.substr(prefix.length());
    for (char c : numberPart) {
        if (!std::isdigit(c)) {
            MEDIA_LOGE("ExtractFd: The part after the prefix is not all digits.");
            return FILE_DESCRIPTOR_INVALID;
        }
    }

    int32_t fd = atoi(numberPart.c_str());
    return fd > FILE_DESCRIPTOR_INVALID ? fd : FILE_DESCRIPTOR_INVALID;
}

// Callback class symbols
AHSoundNormalCallback::AHSoundNormalCallback(std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl)
    : soundNormalImpl_(soundNormalImpl), session_(nullptr) {}

AHSoundNormalCallback::AHSoundNormalCallback(std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl,
    std::shared_ptr<AudioHapticPlaybackSession> session)
    : soundNormalImpl_(soundNormalImpl), session_(std::move(session)) {}

void AHSoundNormalCallback::OnError(int32_t errorCode, const std::string &errorMsg)
{
    CHECK_AND_RETURN_LOG(session_ != nullptr, "Unbound AVPlayer callback");
    MEDIA_LOGE("OnError reported from AVPlayer: %{public}d", errorCode);
    std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl = soundNormalImpl_.lock();
    if (soundNormalImpl == nullptr) {
        MEDIA_LOGE("The audio haptic player for normal mode has been released.");
        return;
    }
    soundNormalImpl->NotifyErrorEvent(session_, errorCode);
}

void AHSoundNormalCallback::OnInfo(Media::PlayerOnInfoType type, int32_t extra, const Media::Format &infoBody)
{
    CHECK_AND_RETURN_LOG(session_ != nullptr, "Unbound AVPlayer callback");
    if (type == INFO_TYPE_STATE_CHANGE) {
        MEDIA_LOGI("OnInfo: state change reported from AVPlayer.");
        HandleStateChangeEvent(extra, infoBody);
    } else if (type == INFO_TYPE_INTERRUPT_EVENT) {
        MEDIA_LOGI("OnInfo: interrupt event reported from AVPlayer.");
        HandleAudioInterruptEvent(extra, infoBody);
    } else if (type == INFO_TYPE_AUDIO_FIRST_FRAME) {
        MEDIA_LOGI("OnInfo: first frame event reported from AVPlayer.");
        HandleAudioFirstFrameEvent(extra, infoBody);
    } else if (type == INFO_TYPE_EOS) {
        HandleEOSEvent(extra, infoBody);
    } else {
        return;
    }
}

void AHSoundNormalCallback::HandleStateChangeEvent(int32_t extra, const Format &infoBody)
{
    MEDIA_LOGI("HandleStateChangeEvent from AVPlayer");
    PlayerStates avPlayerState = static_cast<PlayerStates>(extra);
    AudioHapticPlayerState eventState = playerState_; // Immutable initial value, never another event's state.
    switch (avPlayerState) {
        case PLAYER_STATE_ERROR:
            eventState = AudioHapticPlayerState::STATE_INVALID;
            break;
        case PLAYER_IDLE:
        case PLAYER_INITIALIZED:
        case PLAYER_PREPARING:
            eventState = AudioHapticPlayerState::STATE_NEW;
            break;
        case PLAYER_PREPARED:
            eventState = AudioHapticPlayerState::STATE_PREPARED;
            break;
        case PLAYER_STARTED:
            eventState = AudioHapticPlayerState::STATE_RUNNING;
            break;
        case PLAYER_PAUSED:
            eventState = AudioHapticPlayerState::STATE_PAUSED;
            break;
        case PLAYER_STOPPED:
        case PLAYER_PLAYBACK_COMPLETE:
            eventState = AudioHapticPlayerState::STATE_STOPPED;
            break;
        default:
            return; // No state mapping: do not replay another callback's transition.
    }
    std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl = soundNormalImpl_.lock();
    if (soundNormalImpl == nullptr) {
        MEDIA_LOGE("The audio haptic player for normal mode has been released.");
        return;
    }
    soundNormalImpl->SetAVPlayerState(session_, eventState);

    if (avPlayerState == PLAYER_PREPARED) {
        soundNormalImpl->NotifyPreparedEvent(session_);
    }
}

void AHSoundNormalCallback::HandleAudioInterruptEvent(int32_t extra, const Format &infoBody)
{
    MEDIA_LOGI("HandleAudioInterruptEvent from AVPlayer");
    AudioStandard::InterruptEvent interruptEvent;
    int32_t eventTypeValue = 0;
    int32_t forceTypeValue = 0;
    int32_t hintTypeValue = 0;
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_TYPE, eventTypeValue);
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_FORCE, forceTypeValue);
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_HINT, hintTypeValue);
    interruptEvent.eventType = static_cast<AudioStandard::InterruptType>(eventTypeValue);
    interruptEvent.forceType = static_cast<AudioStandard::InterruptForceType>(forceTypeValue);
    interruptEvent.hintType = static_cast<AudioStandard::InterruptHint>(hintTypeValue);

    std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl = soundNormalImpl_.lock();
    if (soundNormalImpl == nullptr) {
        MEDIA_LOGE("The audio haptic player for normal mode has been released.");
        return;
    }
    soundNormalImpl->NotifyInterruptEvent(session_, interruptEvent);
}

void AHSoundNormalCallback::HandleAudioFirstFrameEvent(int32_t extra, const Format &infoBody)
{
    int64_t value = 0;
    CHECK_AND_RETURN_LOG(infoBody.GetLongValue(PlayerKeys::AUDIO_FIRST_FRAME, value) && value >= 0,
        "Invalid audio first frame latency");
    uint64_t latency = static_cast<uint64_t>(value);
    MEDIA_LOGI("HandleAudioFirstFrameEvent from AVPlayer. Latency %{public}" PRIu64 "", latency);
    std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl = soundNormalImpl_.lock();
    if (soundNormalImpl == nullptr) {
        MEDIA_LOGE("The audio haptic player for normal mode has been released.");
        return;
    }
    soundNormalImpl->NotifyFirstFrameEvent(session_, latency);
}

void AHSoundNormalCallback::HandleEOSEvent(int32_t extra, const Format &infoBody)
{
    MEDIA_LOGI("AHSoundNormalCallback::HandleEOSEvent from AVPlayer");
    
    std::shared_ptr<AudioHapticSoundNormalImpl> soundNormalImpl = soundNormalImpl_.lock();
    if (soundNormalImpl == nullptr) {
        MEDIA_LOGE("The audio haptic player for normal mode has been released.");
        return;
    }
    soundNormalImpl->NotifyEndOfStreamEvent(session_, static_cast<bool>(extra));
}

} // namesapce AudioStandard
} // namespace OHOS