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

#include "audio_haptic_player_impl.h"

#include <cstdint>
#include <chrono>
#include <unistd.h>
#include <random>

#include "parameter.h"

#include "audio_haptic_sound_low_latency_impl.h"
#include "audio_haptic_sound_normal_impl.h"

#include "audio_haptic_log.h"
#include "media_errors.h"
#include "media_monitor_manager.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticPlayerImpl"};
}

namespace OHOS {
namespace Media {
const int32_t LOAD_WAIT_SECONDS = 2;
const int32_t LOAD_WAIT_SECONDS_FOR_LOOP = 40;
const int32_t NORMAL_LOOP_FIRST_WAIT_MS = 80;
const int32_t NORMAL_LOOP_FOLLOW_WAIT_MS = 40;

static int32_t GenerateSyncId()
{
    static constexpr uint8_t pidBits = 8;        // Number of bits allocated for the Process ID
    static constexpr uint8_t randomBits = 8;     // Number of bits allocated for the random value
    static constexpr uint8_t timeBits = 15;      // Number of bits allocated for the time difference

    static constexpr uint32_t pidMask = (1 << pidBits) - 1;      // Mask for PID (0xFF for 8 bits)
    static constexpr uint32_t randomMask = (1 << randomBits) - 1; // Mask for random value (0xFF for 8 bits)
    static constexpr uint32_t timeMask = (1 << timeBits) - 1;    // Mask for time difference (0xFFFFFF for 24 bits)

    static thread_local pid_t pid = getpid();
    static thread_local auto startTime = std::chrono::steady_clock::now();
    static thread_local std::mt19937 gen(std::random_device{}());
    // Use constants to define the distribution range
    static thread_local std::uniform_int_distribution<uint16_t> dist(0, randomMask);

    auto now = std::chrono::steady_clock::now();
    auto duration = now - startTime;
    auto micros = std::chrono::duration_cast<std::chrono::microseconds>(duration).count();

    uint32_t pidUnsigned = static_cast<uint32_t>(pid);
    uint64_t microsUnsigned = static_cast<uint64_t>(micros);

    return
        ((microsUnsigned & timeMask) << (pidBits + randomBits)) | // Shift time part by 16 bits (8+8)
        ((pidUnsigned & pidMask) << randomBits) |                 // Shift PID part by 8 bits
        (dist(gen) & randomMask);                                  // Random value occupies the lowest 8 bits
}

static bool IsSupportDSP(void)
{
    constexpr const char* supportDspKey = "const.multimedia.audio.support_hadware_audio_haptic_sync";
    constexpr const uint32_t paramTrueLen = 4; // "true" 4bytes
    constexpr const uint32_t paramFalseLen = 5; // "false" 5bytes
    constexpr const char* paramTrue = "true";
    constexpr const char* paramFalse = "false";

    char result[paramFalseLen + 1] = {0};
    //  Returns the number of bytes of the system parameter if the operation is successful.
    int len = GetParameter(supportDspKey, paramFalse, result, paramFalseLen + 1);
    CHECK_AND_RETURN_RET_LOG(len == paramFalseLen || len == paramTrueLen, false, "GetParameter len is invalid.");

    if (strncmp(result, paramTrue, paramTrueLen) == 0) {
        MEDIA_LOGW("AudioHapticPlayerImpl support DSP!");
        return true;
    }
    MEDIA_LOGW("AudioHapticPlayerImpl doesn't support DSP!");
    return false;
}

std::mutex AudioHapticPlayerFactory::createPlayerMutex_;

std::shared_ptr<AudioHapticPlayer> AudioHapticPlayerFactory::CreateAudioHapticPlayer(
    const AudioHapticPlayerParam &param)
{
    std::lock_guard<std::mutex> lock(createPlayerMutex_);
    // Create audio haptic player using the param.
    std::shared_ptr<AudioHapticPlayerImpl> audioHapticPlayer = std::make_shared<AudioHapticPlayerImpl>();
    audioHapticPlayer->SetPlayerParam(param);
    audioHapticPlayer->LoadPlayer();
    return audioHapticPlayer;
}

std::mutex AudioHapticSound::createAudioHapticSoundMutex_;

std::shared_ptr<AudioHapticSound> AudioHapticSound::CreateAudioHapticSound(
    const AudioLatencyMode &latencyMode, const AudioSource& audioSource, const bool &muteAudio,
    const AudioStandard::StreamUsage &streamUsage, const bool &parallelPlayFlag, const int32_t &rendererFlags)
{
    if (latencyMode != AUDIO_LATENCY_MODE_NORMAL && latencyMode != AUDIO_LATENCY_MODE_FAST) {
        MEDIA_LOGE("Invalid param: the latency mode %{public}d is unsupported.", latencyMode);
        return nullptr;
    }

    std::lock_guard<std::mutex> lock(createAudioHapticSoundMutex_);
    std::shared_ptr<AudioHapticSound> audioHapticSound = nullptr;
    switch (latencyMode) {
        case AUDIO_LATENCY_MODE_NORMAL:
            audioHapticSound =
                std::make_shared<AudioHapticSoundNormalImpl>(audioSource, muteAudio, streamUsage, rendererFlags);
            break;
        case AUDIO_LATENCY_MODE_FAST:
            audioHapticSound = std::make_shared<AudioHapticSoundLowLatencyImpl>(
                audioSource, muteAudio, streamUsage, parallelPlayFlag);
            break;
        default:
            MEDIA_LOGE("Invalid param: the latency mode %{public}d is unsupported.", latencyMode);
            break;
    }
    return audioHapticSound;
}

AudioHapticPlayerImpl::AudioHapticPlayerImpl()
    : latencyMode_(AUDIO_LATENCY_MODE_NORMAL),
      muteAudio_(false),
      muteHaptic_(false)
{
    isSupportDSPSync_ = IsSupportDSP();
}

AudioHapticPlayerImpl::~AudioHapticPlayerImpl()
{
    if (playerState_ != AudioHapticPlayerState::STATE_RELEASED) {
        ReleaseVibrator();
    }
}

void AudioHapticPlayerImpl::SetPlayerParam(const AudioHapticPlayerParam &param)
{
    muteAudio_ = param.options.muteAudio;
    muteHaptic_ = param.options.muteHaptics;
    parallelPlayFlag_ = param.options.parallelPlayFlag;
    audioSource_ = param.audioSource;
    hapticSource_ = param.hapticSource;
    latencyMode_ = param.latencyMode;
    streamUsage_ = param.streamUsage;
    isMockMode_ = param.isMockMode;
}

void AudioHapticPlayerImpl::LoadPlayer()
{
    // Load audio player
    int32_t rendererFlags = AudioStandard::AUDIO_FLAG_NORMAL;
    if (isMockMode_) {
        rendererFlags = AudioStandard::AUDIO_FLAG_VKB_ALL_RING;
    }
    auto sound = AudioHapticSound::CreateAudioHapticSound(
        latencyMode_, audioSource_, muteAudio_, streamUsage_, parallelPlayFlag_, rendererFlags);
    std::shared_ptr<AudioHapticSound> previousSound;
    {
        // Ordinary sound readers use this API mutex. GetTime uses atomic_load.
        std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
        previousSound = std::atomic_exchange(&audioHapticSound_, sound);
    }
    // Never release an old sound/backend inside the publication operation or mutex.
    previousSound.reset();
    CHECK_AND_RETURN_LOG(sound != nullptr, "Failed to create audio haptic sound instance");
    auto callback = std::make_shared<AudioHapticSoundCallbackImpl>(shared_from_this());
    soundCallback_ = callback;
    (void)sound->SetAudioHapticSoundCallback(soundCallback_);
    if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL) {
        // The factory above returns this exact concrete type for NORMAL. No RTTI.
        auto normal = std::static_pointer_cast<AudioHapticSoundNormalImpl>(sound);
        (void)normal->SetPlaybackCallback(callback);
    }

    // Load vibrator
    audioHapticVibrator_ = AudioHapticVibrator::CreateAudioHapticVibrator(*this);
    CHECK_AND_RETURN_LOG(audioHapticVibrator_ != nullptr, "Failed to create audio haptic vibrator instance");
}

bool AudioHapticPlayerImpl::IsMuted(const AudioHapticType &audioHapticType) const
{
    if (audioHapticType == AUDIO_HAPTIC_TYPE_AUDIO) {
        return muteAudio_;
    } else if (audioHapticType == AUDIO_HAPTIC_TYPE_HAPTIC) {
        return muteHaptic_;
    }
    MEDIA_LOGE("IsMuted: invalid audioHapticType %{public}d", audioHapticType);
    return false;
}

int32_t AudioHapticPlayerImpl::Prepare()
{
    int32_t result = MSERR_OK;
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(audioHapticSound_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic sound is nullptr");
    CHECK_AND_RETURN_RET_LOG(audioSource_.audioUri != "" || audioSource_.fd > INVALID_FD,
        MSERR_OPEN_FILE_FAILED, "Invalid val: audioSource");
    result = audioHapticSound_->PrepareSound();
    CHECK_AND_RETURN_RET_LOG(result == MSERR_OK, result, "Failed to load audio file");

    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic vibrator is nullptr");
    result = audioHapticVibrator_->PreLoad(hapticSource_, streamUsage_);
    CHECK_AND_RETURN_RET_LOG(result == MSERR_OK, result, "Failed to load vobration file");

    playerState_ = AudioHapticPlayerState::STATE_PREPARED;
    return MSERR_OK;
}

int32_t AudioHapticPlayerImpl::Start()
{
    int32_t result = MSERR_OK;
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);

    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic vibrator is nullptr");
    CHECK_AND_RETURN_RET_LOG(audioHapticSound_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic sound is nullptr");
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RUNNING, result,
        "Audio haptic already running");

    // If DSP synchronization is supported, generate the syncId before starting
    if (isSupportDSPSync_) {
        audioHapticSyncId_ = GenerateSyncId();
    }
    
    if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL) {
        // Install the next real source incarnation before rearming the waiter.
        auto normal = std::static_pointer_cast<AudioHapticSoundNormalImpl>(audioHapticSound_);
        result = normal->PrepareForStart();
        if (result != MSERR_OK) {
            RetireNormalPlayback(AudioHapticSessionEnd::PREPARE_FAILED);
            StopVibrate();
            return result;
        }
    }
    if (vibrateThread_ == nullptr) {
        ResetVibrateState();
        vibrateThread_ = std::make_shared<std::thread>([this] { StartVibrate(); });
    }
    result = audioHapticSound_->StartSound(audioHapticSyncId_.load());
    SendHapticPlayerEvent(result, "START_HAPTIC_PLAYER");
    if (result != MSERR_OK) {
        // A failed Play cannot publish a pending first frame or survive retry.
        RetireNormalPlayback(AudioHapticSessionEnd::START_FAILED);
        StopVibrate();
        return result;
    }

    playerState_ = AudioHapticPlayerState::STATE_RUNNING;
    if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL) {
        std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
        const auto &session = normalPlaybackSession_;
        (void)session; // Logging may compile out in a controlled dependency build.
        MEDIA_LOGI("AHPublication stage=start-confirmed scope=normal player=%{public}p session=%{public}p "
            "backend=%{public}p end=%{public}d confirmed=%{public}d", this, session.get(),
            session ? reinterpret_cast<void *>(session->backendDiagnosticIdentity) : nullptr,
            session ? static_cast<int32_t>(session->end.load()) : -1,
            session ? static_cast<int32_t>(session->playConfirmed.load()) : 0);
    }
    return result;
}

int32_t AudioHapticPlayerImpl::Stop()
{
    int32_t result = MSERR_OK;
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);

    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic vibrator is nullptr");
    RetireNormalPlayback(AudioHapticSessionEnd::STOPPED);
    StopVibrate();

    CHECK_AND_RETURN_RET_LOG(audioHapticSound_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic sound is nullptr");
    result = audioHapticSound_->StopSound();
    CHECK_AND_RETURN_RET_LOG(result == MSERR_OK, result, "Failed to stop sound.");

    playerState_ = AudioHapticPlayerState::STATE_STOPPED;
    return result;
}

int32_t AudioHapticPlayerImpl::Release()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, MSERR_OK,
        "The audio haptic player has been released.");

    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic vibrator is nullptr");
    RetireNormalPlayback(AudioHapticSessionEnd::RELEASED);
    ReleaseVibratorInternal();

    CHECK_AND_RETURN_RET_LOG(audioHapticSound_ != nullptr, MSERR_INVALID_OPERATION,
        "Audio haptic sound is nullptr");
    ReleaseSound();

    playerState_ = AudioHapticPlayerState::STATE_RELEASED;
    return MSERR_OK;
}

void AudioHapticPlayerImpl::ReleaseVibratorInternal()
{
    if (audioHapticVibrator_ != nullptr) {
        audioHapticVibrator_->StopVibrate();
    }
    {
        // When player is releasing，notify vibrate thread immediately
        std::lock_guard<std::mutex> lockVibrate(waitStartVibrateMutex_);
        canStartVibrate_ = true;
        isVibrationStopped_ = true;
        condStartVibrate_.notify_one();
    }
    if (vibrateThread_ != nullptr && vibrateThread_->joinable()) {
        vibrateThread_->join();
    }
    vibrateThread_.reset();
    if (audioHapticVibrator_ != nullptr) {
        (void)audioHapticVibrator_->Release();
        audioHapticVibrator_ = nullptr;
    }
}

void AudioHapticPlayerImpl::ReleaseVibrator()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    ReleaseVibratorInternal();
}

void AudioHapticPlayerImpl::ReleaseSound()
{
    // Caller holds the API mutex. Unpublish before native Release can reenter GetTime.
    auto sound = std::atomic_exchange(&audioHapticSound_, std::shared_ptr<AudioHapticSound> {});
    if (sound != nullptr) {
        (void)sound->ReleaseSound();
    }
    soundCallback_ = nullptr;
    {
        std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
        normalPlaybackSession_.reset();
    }
    // Local sound destruction occurs outside the atomic operation and wait mutex.
}

int32_t AudioHapticPlayerImpl::SetVolume(float volume)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetVolume %{public}f", volume);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    if (volume < 0.0f || volume > 1.0f) {
        MEDIA_LOGE("SetVolume: the volume value is invalid.");
        return MSERR_INVALID_VAL;
    }

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    int32_t result = MSERR_OK;
    volume_ = volume;
    if (audioHapticSound_ == nullptr) {
        MEDIA_LOGW("Audio haptic sound is nullptr!");
        return result;
    }
    float actualVolume = volume_ * (muteAudio_ ? 0 : 1);
    result = audioHapticSound_->SetVolume(actualVolume);

    if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL &&
        (streamUsage_ == AudioStandard::StreamUsage::STREAM_USAGE_VOICE_RINGTONE ||
        streamUsage_ == AudioStandard::StreamUsage::STREAM_USAGE_RINGTONE ||
        streamUsage_ == AudioStandard::StreamUsage::STREAM_USAGE_VOICE_TRANSFER_RINGTONE) &&
        playerState_ == AudioHapticPlayerState::STATE_RUNNING && !isMockMode_ &&
        std::abs(volume_ - 0.0f) <= std::numeric_limits<float>::epsilon()) {
        // only for the call manager ringtone
        StopVibrate();
    }

    return result;
}

bool AudioHapticPlayerImpl::IsHapticsRampSupported()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    if (audioHapticVibrator_ != nullptr) {
        return audioHapticVibrator_->IsHapticsCustomSupported();
    }
    return false;
}

bool AudioHapticPlayerImpl::IsHapticsIntensityAdjustmentSupported()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    if (audioHapticVibrator_ != nullptr) {
        return audioHapticVibrator_->IsHapticsCustomSupported();
    }
    return false;
}

int32_t AudioHapticPlayerImpl::EnableHapticsInSilentMode(bool enable)
{
    int32_t result = MSERR_OK;
    MEDIA_LOGI("AudioHapticPlayerImpl::EnableHapticsInSilentMode %{public}d", enable);
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);

    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RUNNING, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player is running.");

    if (audioHapticVibrator_ == nullptr) {
        return ERR_OPERATE_NOT_ALLOWED;
    }

    audioHapticVibrator_->EnableHapticsInSilentMode(enable);
    return result;
}

int32_t AudioHapticPlayerImpl::SetHapticIntensity(float intensity)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetHapticIntensity %{public}f", intensity);

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr && audioHapticVibrator_->IsHapticsCustomSupported(),
        NOT_SUPPORTED_CODE, "Function is not supported in current device");

    if (intensity < 1.0f || intensity > 100.0f) {
        MEDIA_LOGE("SetHapticIntensity: the intensity value is invalid.");
        return MSERR_INVALID_VAL;
    }

    return audioHapticVibrator_->SetHapticIntensity(intensity);
}

int32_t AudioHapticPlayerImpl::SetHapticsFeature(const HapticsFeature &feature)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetHapticsFeature %{public}d", feature);

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr, ERR_OPERATE_NOT_ALLOWED, "audioHapticVibrator_ is null");
    CHECK_AND_RETURN_RET_LOG(!isGentle_.load(), ERR_OPERATE_NOT_ALLOWED, "already gentle");

    int32_t result = audioHapticVibrator_->SetHapticsFeature(feature);
    CHECK_AND_RETURN_RET_LOG(result == MSERR_OK, result, "SetHapticsFeature error");
    isGentle_.store(true);

    return result;
}

int32_t AudioHapticPlayerImpl::SetHapticsRamp(int32_t duration, float startIntensity, float endIntensity)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetHapticsRamp %{public}d, %{public}f, %{public}f",
        duration, startIntensity, endIntensity);

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    CHECK_AND_RETURN_RET_LOG(!isRamp_.load(), ERR_OPERATE_NOT_ALLOWED, "already ramp");
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RUNNING, ERR_OPERATE_NOT_ALLOWED,
        "can't set when playing haptics");
    CHECK_AND_RETURN_RET_LOG(audioHapticVibrator_ != nullptr && audioHapticVibrator_->IsHapticsCustomSupported(),
        NOT_SUPPORTED_CODE, "Function is not supported in current device");

    // duration not less than 100ms
    if (duration < 100) {
        MEDIA_LOGE("AudioHapticPlayerImpl::SetHapticsRamp: the duration value is invalid.");
        return MSERR_INVALID_VAL;
    }

    if (startIntensity < 1.0f || startIntensity > 100.0f) {
        MEDIA_LOGE("AudioHapticPlayerImpl::SetHapticsRamp: the startIntensity value is invalid.");
        return MSERR_INVALID_VAL;
    }

    if (endIntensity < 1.0f || endIntensity > 100.0f) {
        MEDIA_LOGE("AudioHapticPlayerImpl::SetHapticsRamp: the endIntensity value is invalid.");
        return MSERR_INVALID_VAL;
    }

    int32_t result = audioHapticVibrator_->SetHapticsRamp(duration, startIntensity, endIntensity);
    CHECK_AND_RETURN_RET_LOG(result == MSERR_OK, result, "SetHapticsRamp error");
    isRamp_.store(true);

    return result;
}

int32_t AudioHapticPlayerImpl::SetLoop(bool loop)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetLoop %{public}d", loop);
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    CHECK_AND_RETURN_RET_LOG(playerState_ != AudioHapticPlayerState::STATE_RELEASED, ERR_OPERATE_NOT_ALLOWED,
        "The audio haptic player has been released.");
    int32_t result = MSERR_OK;
    loop_.store(loop);
    if (audioHapticSound_ == nullptr) {
        MEDIA_LOGW("Audio haptic sound is nullptr!");
        return result;
    }
    result = audioHapticSound_->SetLoop(loop);
    return result;
}

HapticsMode AudioHapticPlayerImpl::GetHapticsMode() const
{
    return hapticsMode_;
}

void AudioHapticPlayerImpl::SetHapticsMode(HapticsMode hapticsMode)
{
    MEDIA_LOGI("AudioHapticPlayerImpl::SetHapticsMode %{public}d", hapticsMode);
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    hapticsMode_ = hapticsMode;
}

int32_t AudioHapticPlayerImpl::SetAudioHapticPlayerCallback(
    const std::shared_ptr<AudioHapticPlayerCallback> &playerCallback)
{
    if (playerCallback == nullptr) {
        MEDIA_LOGE("The audio haptic player callback is nullptr.");
        return MSERR_INVALID_VAL;
    }

    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    std::lock_guard<std::mutex> lockCallback(callbackMutex_);
    audioHapticPlayerCallback_ = playerCallback;
    return MSERR_OK;
}

int32_t AudioHapticPlayerImpl::GetAudioCurrentTime()
{
    // Do not acquire the API mutex: the vibration worker may hold its wait mutex.
    auto sound = std::atomic_load(&audioHapticSound_);
    CHECK_AND_RETURN_RET_LOG(sound != nullptr, -1, "Audio haptic sound is nullptr");
    return sound->GetAudioCurrentTime(); // Strong snapshot; no publication lock held.
}

int32_t AudioHapticPlayerImpl::GetDelayTime(int32_t playedTimes)
{
    // normal mode needs to calc waiting time, fast mode start vib immediatelly
    if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL) {
        if (playedTimes > 0) {
            return NORMAL_LOOP_FOLLOW_WAIT_MS;
        }

        return NORMAL_LOOP_FIRST_WAIT_MS;
    }

    return 0;
}

int32_t AudioHapticPlayerImpl::StartVibrate()
{
    if (muteHaptic_) {
        MEDIA_LOGI("StartVibrate: muteHaptic is true. No need to vibrate");
        SendHapticPlayerEvent(MSERR_OK, "NO_NEED_VIBRATE");
        return MSERR_OK;
    }

    MEDIA_LOGI("Enter StartVibrate()");
    std::unique_lock<std::mutex> lockWait(waitStartVibrateMutex_);
    int32_t playedTimes = 0;
    do {
        int32_t waitTime = loop_.load() ? LOAD_WAIT_SECONDS_FOR_LOOP : LOAD_WAIT_SECONDS;
        bool waitResult = condStartVibrate_.wait_for(lockWait, std::chrono::seconds(waitTime),
            [this]() { return canStartVibrate_ || isVibrationStopped_; });
        if (!waitResult) {
            MEDIA_LOGE("StartVibrate: Failed to start vibrate (time out).");
            SendHapticPlayerEvent(MSERR_INVALID_OPERATION, "VIBRATE_TIME_OUT");
            return MSERR_INVALID_OPERATION;
        }
        if (isVibrationStopped_) {
            MEDIA_LOGI("StartVibrate: audio haptic player has been stopped.");
            SendHapticPlayerEvent(MSERR_OK, "HAPTIC_PLAYER_STOP");
            return MSERR_OK;
        }

        canStartVibrate_ = false; // reset for next time.
        int32_t hapticDelay = audioHapticVibrator_->GetDelayTime();
        int32_t notSupportDelay = (static_cast<int32_t>(this->audioLatency_) - hapticDelay) > 0 ?
            static_cast<int32_t>(this->audioLatency_) - hapticDelay : 0;
        int32_t delayMS = isSupportDSPSync_ ? GetDelayTime(playedTimes) : notSupportDelay;
        MEDIA_LOGI("Triggering the vibration delayMS: %{public}d", delayMS);
        waitResult = condStartVibrate_.wait_for(lockWait, std::chrono::milliseconds(delayMS),
            [this]() { return isVibrationStopped_.load(); });
        if (isVibrationStopped_) {
            MEDIA_LOGI("StartVibrate: audio haptic player has been stopped.");
            SendHapticPlayerEvent(MSERR_OK, "HAPTIC_PLAYER_STOP");
            return MSERR_OK;
        }
        MEDIA_LOGI("The first frame of audio is about to start. Triggering the vibration.");
        isVibrationRunning_.store(true);
        audioHapticVibrator_->SetAudioHapticSyncId(audioHapticSyncId_.load());
        if (latencyMode_ == AUDIO_LATENCY_MODE_NORMAL) {
            // StartVibrateForAVPlayer waits for the real pattern to finish.
            // Stop/Release must acquire this admission lock to retire the
            // immutable Session and cancel that wait. Never hold it across
            // normal-mode playback; the vibrator's own stopped state resolves
            // the cancel-before-start race, and Release joins before destruction.
            lockWait.unlock();
            audioHapticVibrator_->StartVibrate(latencyMode_);
            lockWait.lock();
        } else {
            audioHapticVibrator_->StartVibrate(latencyMode_);
        }
        isVibrationRunning_.store(false);
        playedTimes++;
    } while (loop_.load() && !isVibrationStopped_);

    SendHapticPlayerEvent(MSERR_OK, "START_VIBRATE");
    return MSERR_OK;
}

void AudioHapticPlayerImpl::StopVibrate()
{
    CHECK_AND_RETURN_LOG(!isVibrationStopped_, "Vibrate not start before.");
    MEDIA_LOGI("Stop vibrate for audio haptic player right now.");
    if (audioHapticVibrator_ != nullptr) {
        audioHapticVibrator_->StopVibrate();
    } else {
        MEDIA_LOGW("The audio haptic vibrator is nullptr!");
    }
    {
        std::lock_guard<std::mutex> lockVibrate(waitStartVibrateMutex_);
        isVibrationStopped_ = true;
        condStartVibrate_.notify_one();
    }
    if (vibrateThread_ != nullptr && vibrateThread_->joinable()) {
        vibrateThread_->join();
    }
    vibrateThread_.reset();
}

void AudioHapticPlayerImpl::ResetVibrateState()
{
    {
        std::lock_guard<std::mutex> lockVibrate(waitStartVibrateMutex_);
        // Discard pending first-frame data before arming a new playback.
        canStartVibrate_ = false;
        audioLatency_ = 0;
        isVibrationStopped_ = false;
    }
    if (audioHapticVibrator_ != nullptr) {
        audioHapticVibrator_->ResetStopState();
    } else {
        MEDIA_LOGW("The audio haptic vibrator is nullptr!");
    }
}

std::shared_ptr<AudioHapticPlayerCallback> AudioHapticPlayerImpl::GetPlayerCallback()
{
    std::lock_guard<std::mutex> lock(callbackMutex_);
    return audioHapticPlayerCallback_.lock();
}

void AudioHapticPlayerImpl::SetPublicationCallback(const std::shared_ptr<AudioHapticPublicationCallback> &callback)
{
    std::lock_guard<std::mutex> lock(callbackMutex_);
    publicationCallback_ = callback;
}

std::shared_ptr<AudioHapticPublicationCallback> AudioHapticPlayerImpl::GetPublicationCallback()
{
    std::lock_guard<std::mutex> lock(callbackMutex_);
    return publicationCallback_.lock();
}

void AudioHapticPlayerImpl::RetireNormalPlayback(AudioHapticSessionEnd reason)
{
    std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
    if (normalPlaybackSession_ != nullptr) { normalPlaybackSession_->end.store(reason); }
}

void AudioHapticPlayerImpl::PlaybackCreated(const std::shared_ptr<AudioHapticPlaybackSession> &session)
{
    std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
    if (normalPlaybackSession_ != nullptr) { normalPlaybackSession_->end.store(AudioHapticSessionEnd::REPLACED); }
    normalPlaybackSession_ = session;
    MEDIA_LOGI("AHPublication stage=created scope=normal player=%{public}p session=%{public}p backend=%{public}p",
        this, session.get(), session ? reinterpret_cast<void *>(session->backendDiagnosticIdentity) : nullptr);
}

void AudioHapticPlayerImpl::PlaybackFirstFrame(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    uint64_t latency)
{
    if (isVibrationRunning_.load() && (hapticsMode_ == HapticsMode::HAPTICS_MODE_NON_SYNC_ONCE ||
        hapticsMode_ == HapticsMode::HAPTICS_MODE_NON_SYNC)) { return; }
    std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
    CHECK_AND_RETURN_LOG(session != nullptr && normalPlaybackSession_ == session &&
        session->end.load() == AudioHapticSessionEnd::LIVE && session->playConfirmed.load() &&
        !isVibrationStopped_.load(), "Discard stale/unconfirmed source first frame");
    canStartVibrate_ = true;
    audioLatency_ = latency;
    condStartVibrate_.notify_one();
}

void AudioHapticPlayerImpl::PlaybackEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    {
        std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
        CHECK_AND_RETURN_LOG(normalPlaybackSession_ == session, "Discard stale source EOS admission");
    }
    std::thread([player = weak_from_this(), session, isLoop]() {
        if (auto owner = player.lock()) { owner->HandlePlaybackEndOfStream(session, isLoop); }
    }).detach();
}

void AudioHapticPlayerImpl::HandlePlaybackEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    std::shared_ptr<AudioHapticPlayerCallback> callback;
    std::shared_ptr<AudioHapticPublicationCallback> publication;
    {
        std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
        {
            std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
            CHECK_AND_RETURN_LOG(session != nullptr && normalPlaybackSession_ == session &&
                session->playConfirmed.load() && session->end.load() ==
                    (isLoop ? AudioHapticSessionEnd::LIVE : AudioHapticSessionEnd::ENDED) &&
                playerState_ != AudioHapticPlayerState::STATE_RELEASED &&
                playerState_ != AudioHapticPlayerState::STATE_STOPPED, "Discard retired/failed source EOS worker");
        }
        if (!isLoop) {
            StopVibrate();
            playerState_ = AudioHapticPlayerState::STATE_STOPPED;
        } else if (isSupportDSPSync_) {
            audioHapticSyncId_++;
        }
        callback = GetPlayerCallback();
        publication = GetPublicationCallback();
    }
    // User code may immediately call Start/Release; no internal mutex is held.
    if (publication != nullptr) {
        MEDIA_LOGI("AHPublication stage=native-sink scope=normal event=EndOfStream player=%{public}p "
            "session=%{public}p backend=%{public}p end=%{public}d", this, session.get(),
            reinterpret_cast<void *>(session->backendDiagnosticIdentity), static_cast<int32_t>(session->end.load()));
        publication->OnSessionEndOfStream(session, isLoop);
    } else if (callback != nullptr) { callback->OnEndOfStream(); }
}

void AudioHapticPlayerImpl::PlaybackInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    const AudioStandard::InterruptEvent &event)
{
    {
        std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
        CHECK_AND_RETURN_LOG(normalPlaybackSession_ == session, "Discard stale source interrupt admission");
    }
    std::thread([player = weak_from_this(), session, event]() {
        if (auto owner = player.lock()) { owner->HandlePlaybackInterrupt(session, event); }
    }).detach();
}

void AudioHapticPlayerImpl::HandlePlaybackInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    const AudioStandard::InterruptEvent &event)
{
    std::shared_ptr<AudioHapticPlayerCallback> callback;
    std::shared_ptr<AudioHapticPublicationCallback> publication;
    {
        std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
        {
            std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
            CHECK_AND_RETURN_LOG(session != nullptr && normalPlaybackSession_ == session &&
                session->end.load() == AudioHapticSessionEnd::INTERRUPTED &&
                playerState_ != AudioHapticPlayerState::STATE_RELEASED &&
                playerState_ != AudioHapticPlayerState::STATE_STOPPED, "Discard retired source interrupt worker");
        }
        StopVibrate();
        playerState_ = AudioHapticPlayerState::STATE_STOPPED;
        callback = GetPlayerCallback();
        publication = GetPublicationCallback();
        SendHapticPlayerEvent(MSERR_OK, "INTERRUPT_HAPTIC_PLAYER");
    }
    if (publication != nullptr) {
        MEDIA_LOGI("AHPublication stage=native-sink scope=normal event=Interrupt player=%{public}p "
            "session=%{public}p backend=%{public}p end=%{public}d", this, session.get(),
            reinterpret_cast<void *>(session->backendDiagnosticIdentity), static_cast<int32_t>(session->end.load()));
        publication->OnSessionInterrupt(session, event);
    } else if (callback != nullptr) { callback->OnInterrupt(event); }
}

void AudioHapticPlayerImpl::PlaybackError(const std::shared_ptr<AudioHapticPlaybackSession> &session, int32_t errorCode)
{
    std::shared_ptr<AudioHapticPlayerCallback> callback;
    {
        std::lock_guard<std::mutex> lockWait(waitStartVibrateMutex_);
        CHECK_AND_RETURN_LOG(session != nullptr && normalPlaybackSession_ == session &&
            session->end.load() == AudioHapticSessionEnd::ERROR, "Discard stale source error");
        callback = GetPlayerCallback();
    }
    // Preserve an admitted real preparation error even if a retry starts later.
    // Dispatch asynchronously BEFORE normal wakes Prepare, so reentrant user
    // code cannot prevent the callback thread from releasing that waiter.
    std::thread([session, callback, errorCode]() {
        if (session != nullptr && callback != nullptr) { callback->OnError(errorCode); }
    }).detach();
}

void AudioHapticPlayerImpl::NotifyInterruptEvent(const AudioStandard::InterruptEvent &interruptEvent)
{
    std::thread(HandleInterruptEventThreadFunc, shared_from_this()).detach();
    auto cb = GetPlayerCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyInterruptEvent for napi object or caller");
        cb->OnInterrupt(interruptEvent);
    } else {
        MEDIA_LOGE("NotifyInterruptEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticPlayerImpl::NotifyEndOfStreamEvent()
{
    MEDIA_LOGI("NotifyEndOfStreamEvent");
    std::thread (HandleEndOfStreamEventThreadFunc, shared_from_this()).detach();
    auto cb = GetPlayerCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyEndOfStreamEvent for napi object or caller");
        cb->OnEndOfStream();
    } else {
        MEDIA_LOGE("NotifyEndOfStreamEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticPlayerImpl::HandleEndOfStreamEventThreadFunc(std::weak_ptr<AudioHapticPlayerImpl> player)
{
    std::shared_ptr<AudioHapticPlayerImpl> playerPtr = player.lock();
    if (playerPtr != nullptr) {
        playerPtr->HandleEndOfStreamEvent();
    }
}

void AudioHapticPlayerImpl::HandleEndOfStreamEvent()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    if (playerState_ == AudioHapticPlayerState::STATE_RELEASED) {
        MEDIA_LOGE("The audio haptic player has been released!");
        return;
    }

    if (playerState_ == AudioHapticPlayerState::STATE_STOPPED) {
        MEDIA_LOGE("The audio haptic player has been stopped!");
        return;
    }

    if (!loop_.load()) {
        StopVibrate();
        playerState_ = AudioHapticPlayerState::STATE_STOPPED;
        return;
    }

    // Triggered only if new synchronization is supported.
    // Low-latency path doesn't trigger EOS during looping; use normal path only.
    if (isSupportDSPSync_) {
        audioHapticSyncId_++;
    }
}

void AudioHapticPlayerImpl::HandleInterruptEventThreadFunc(std::weak_ptr<AudioHapticPlayerImpl> player)
{
    std::shared_ptr<AudioHapticPlayerImpl> playerPtr = player.lock();
    CHECK_AND_RETURN_LOG(playerPtr != nullptr, "playerPtr is nullptr");
    playerPtr->HandleInterruptEvent();
}

void AudioHapticPlayerImpl::HandleInterruptEvent()
{
    std::lock_guard<std::mutex> lock(audioHapticPlayerLock_);
    StopVibrate();
    playerState_ = AudioHapticPlayerState::STATE_STOPPED;
    SendHapticPlayerEvent(MSERR_OK, "INTERRUPT_HAPTIC_PLAYER");
}

void AudioHapticPlayerImpl::NotifyErrorEvent(int32_t errCode)
{
    auto cb = GetPlayerCallback();
    if (cb != nullptr) {
        MEDIA_LOGI("NotifyErrorEvent for napi object or caller. errCode: %{public}d", errCode);
        cb->OnError(errCode);
    } else {
        MEDIA_LOGE("NotifyErrorEvent: audioHapticPlayerCallback_ is nullptr");
    }
}

void AudioHapticPlayerImpl::NotifyFirstFrame(const uint64_t &latency)
{
    NotifyStartVibrate(latency);
}

void AudioHapticPlayerImpl::NotifyStartVibrate(const uint64_t &latency)
{
    if (isVibrationRunning_.load() &&
        (hapticsMode_ == HapticsMode::HAPTICS_MODE_NON_SYNC_ONCE ||
        hapticsMode_ == HapticsMode::HAPTICS_MODE_NON_SYNC)) {
        MEDIA_LOGI("The non sync vibration is already running.");
        return;
    }
    std::lock_guard<std::mutex> lock(this->waitStartVibrateMutex_);
    CHECK_AND_RETURN_LOG(!isVibrationStopped_.load(), "Ignore first frame after vibration stopped");
    this->canStartVibrate_ = true;
    this->audioLatency_ = latency;
    this->condStartVibrate_.notify_one();
}

void AudioHapticPlayerImpl::SendHapticPlayerEvent(const int32_t &errorCode, const std::string &strEvent)
{
    std::shared_ptr<Media::MediaMonitor::EventBean> bean = std::make_shared<Media::MediaMonitor::EventBean>(
        Media::MediaMonitor::ModuleId::AUDIO, Media::MediaMonitor::EventId::HAPTIC_PLAYER,
        Media::MediaMonitor::EventType::HAPTIC_PLAYER_EVENT);
    bean->Add("ERROR_CODE", errorCode);
    bean->Add("ERROR_REASON", strEvent);
    Media::MediaMonitor::MediaMonitorManager::GetInstance().WriteLogMsg(bean);
}

// Callback class symbols
AudioHapticSoundCallbackImpl::AudioHapticSoundCallbackImpl(std::shared_ptr<AudioHapticPlayerImpl> audioHapticPlayerImpl)
    : audioHapticPlayerImpl_(audioHapticPlayerImpl) {}

void AudioHapticSoundCallbackImpl::OnPlaybackCreated(const std::shared_ptr<AudioHapticPlaybackSession> &session)
{
    if (auto player = audioHapticPlayerImpl_.lock()) { player->PlaybackCreated(session); }
}
void AudioHapticSoundCallbackImpl::OnPlaybackFirstFrame(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    uint64_t latency)
{
    if (auto player = audioHapticPlayerImpl_.lock()) { player->PlaybackFirstFrame(session, latency); }
}
void AudioHapticSoundCallbackImpl::OnPlaybackEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    if (auto player = audioHapticPlayerImpl_.lock()) { player->PlaybackEndOfStream(session, isLoop); }
}
void AudioHapticSoundCallbackImpl::OnPlaybackInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    const AudioStandard::InterruptEvent &event)
{
    if (auto player = audioHapticPlayerImpl_.lock()) { player->PlaybackInterrupt(session, event); }
}
void AudioHapticSoundCallbackImpl::OnPlaybackError(const std::shared_ptr<AudioHapticPlaybackSession> &session, int32_t code)
{
    if (auto player = audioHapticPlayerImpl_.lock()) { player->PlaybackError(session, code); }
}

void AudioHapticSoundCallbackImpl::OnEndOfStream()
{
    MEDIA_LOGI("OnEndOfStream reported from audio haptic sound.");
    std::shared_ptr<AudioHapticPlayerImpl> player = audioHapticPlayerImpl_.lock();
    if (player == nullptr) {
        MEDIA_LOGE("The audio haptic player has been released.");
        return;
    }
    player->NotifyEndOfStreamEvent();
}

void AudioHapticSoundCallbackImpl::OnError(int32_t errorCode)
{
    MEDIA_LOGE("OnError reported from audio haptic sound: %{public}d", errorCode);
    std::shared_ptr<AudioHapticPlayerImpl> player = audioHapticPlayerImpl_.lock();
    if (player == nullptr) {
        MEDIA_LOGE("The audio haptic player has been released.");
        return;
    }
    player->NotifyErrorEvent(errorCode);
}

void AudioHapticSoundCallbackImpl::OnInterrupt(const AudioStandard::InterruptEvent &interruptEvent)
{
    MEDIA_LOGI("OnInterrupt from audio haptic sound. hintType: %{public}d", interruptEvent.hintType);
    std::shared_ptr<AudioHapticPlayerImpl> player = audioHapticPlayerImpl_.lock();
    if (player == nullptr) {
        MEDIA_LOGE("The audio haptic player has been released.");
        return;
    }
    player->NotifyInterruptEvent(interruptEvent);
}

void AudioHapticSoundCallbackImpl::OnFirstFrameWriting(uint64_t latency)
{
    MEDIA_LOGI("OnFirstFrameWriting from audio haptic sound. Latency %{public}" PRIu64 "", latency);
    std::shared_ptr<AudioHapticPlayerImpl> player = audioHapticPlayerImpl_.lock();
    if (player == nullptr) {
        MEDIA_LOGE("The audio haptic player has been released.");
        return;
    }

    player->NotifyFirstFrame(latency);
}
} // namesapce AudioStandard
} // namespace OHOS
