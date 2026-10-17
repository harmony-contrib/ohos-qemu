#pragma once
#include "audio_haptic_sound.h"
#include "media_errors.h"
namespace OHOS { namespace Media {
// This test does not implement or claim fast-path execution; NORMAL must never select this dependency.
class AudioHapticSoundLowLatencyImpl : public AudioHapticSound { public:
 AudioHapticSoundLowLatencyImpl(const AudioSource&,const bool&,const AudioStandard::StreamUsage&,const bool&){assert(false);}
 int32_t PrepareSound()override{return MSERR_INVALID_OPERATION;} int32_t StartSound(const int32_t&)override{return MSERR_INVALID_OPERATION;}
 int32_t StopSound()override{return 0;}int32_t ReleaseSound()override{return 0;}int32_t SetVolume(float)override{return 0;}
 int32_t SetLoop(bool)override{return 0;}int32_t GetAudioCurrentTime()override{return 0;}
 int32_t SetAudioHapticSoundCallback(const std::shared_ptr<AudioHapticSoundCallback>&)override{return 0;}
}; } }
