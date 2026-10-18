#pragma once
#include "audio_haptic_player.h"
#include "audio_haptic_publication_callback.h"
#include "media_errors.h"
// Controlled native transport implementing the actual complete public interface.
// Actual player CPP/private NAPI header/common CPP/callback CPP stay unmodified.
namespace OHOS { namespace Media {
class AudioHapticPlayerImpl final : public AudioHapticPlayer {
public:
    int32_t startResult=MSERR_OK, stopResult=MSERR_OK, releaseResult=MSERR_OK;
    int starts=0, stops=0, releases=0;
    bool IsMuted(const AudioHapticType &) const override { return false; }
    int32_t Prepare() override { return MSERR_OK; }
    int32_t Start() override { ++starts; return startResult; }
    int32_t Stop() override { ++stops; return stopResult; }
    int32_t Release() override { ++releases; return releaseResult; }
    int32_t SetVolume(float) override { return MSERR_OK; }
    int32_t SetHapticIntensity(float) override { return MSERR_OK; }
    int32_t SetLoop(bool) override { return MSERR_OK; }
    int32_t SetAudioHapticPlayerCallback(const std::shared_ptr<AudioHapticPlayerCallback> &) override { return MSERR_OK; }
    int32_t GetAudioCurrentTime() override { return 0; }
    HapticsMode GetHapticsMode() const override { return HAPTICS_MODE_SYNC; }
    void SetHapticsMode(HapticsMode) override {}
    int32_t EnableHapticsInSilentMode(bool) override { return MSERR_OK; }
    bool IsHapticsIntensityAdjustmentSupported() override { return true; }
    bool IsHapticsRampSupported() override { return true; }
    int32_t SetHapticsRamp(int32_t,float,float) override { return MSERR_OK; }
    int32_t SetHapticsFeature(const HapticsFeature &) override { return MSERR_OK; }
    void SetPublicationCallback(const std::shared_ptr<AudioHapticPublicationCallback> &) {}
};
} }
