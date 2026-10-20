/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under the Apache License, Version 2.0. */
#ifndef AUDIO_HAPTIC_PUBLICATION_CALLBACK_H
#define AUDIO_HAPTIC_PUBLICATION_CALLBACK_H
#include "audio_haptic_playback_session.h"
namespace OHOS { namespace Media {
// Component-private optional endpoint. Public AudioHapticPlayer/Callback vtables
// and legacy native/fast delivery remain unchanged. This is never an epoch read
// at callback delivery: each event owns its actual backend Session from source.
class AudioHapticPublicationCallback {
public:
    virtual ~AudioHapticPublicationCallback() = default;
    virtual void OnSessionEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool isLoop) = 0;
    virtual void OnSessionInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
        const AudioStandard::InterruptEvent &event) = 0;
};
inline bool IsAudioHapticPublicationLive(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool eos, bool isLoop)
{
    if (session == nullptr) { return true; } // unchanged legacy/fast event, not a normal Session claim
    if (!session->playConfirmed.load()) { return false; }
    const auto reason = session->end.load();
    if (!eos) { return reason == AudioHapticSessionEnd::INTERRUPTED; }
    // A loop may naturally end before its queued per-period notification is
    // delivered. Preserve that same-incarnation notification, but no retired one.
    return reason == AudioHapticSessionEnd::ENDED || (isLoop && reason == AudioHapticSessionEnd::LIVE);
}
} }
#endif
