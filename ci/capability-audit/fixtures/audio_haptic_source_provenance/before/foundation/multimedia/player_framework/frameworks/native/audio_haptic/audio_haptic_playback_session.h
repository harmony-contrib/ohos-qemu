/* SPDX-License-Identifier: Apache-2.0 */
#ifndef AUDIO_HAPTIC_PLAYBACK_SESSION_H
#define AUDIO_HAPTIC_PLAYBACK_SESSION_H

#include <atomic>
#include <cstdint>
#include <memory>
#include "audio_haptic_sound.h"

namespace OHOS {
namespace Media {
class Player;
// Private implementation contract. No existing public/inner-API vtable changes.
enum class AudioHapticSessionEnd {
    LIVE, STOPPED, RELEASED, REPLACED, PREPARE_FAILED, START_FAILED, ERROR, ENDED, INTERRUPTED
};
struct AudioHapticPlaybackSession final {
    explicit AudioHapticPlaybackSession(const std::shared_ptr<Player> &player)
        : backend(player), backendDiagnosticIdentity(reinterpret_cast<uintptr_t>(player.get())) {}
    const std::weak_ptr<Player> backend; // Immutable identity of the real producer/IPC incarnation.
    // Diagnostic object address captured once at actual backend creation; never
    // a delivery-time current epoch. Addresses may be reused after full retirement.
    const uintptr_t backendDiagnosticIdentity;
    std::atomic<AudioHapticSessionEnd> end {AudioHapticSessionEnd::LIVE};
    std::atomic<bool> playIssued {false};
    std::atomic<bool> playConfirmed {false};
};
class AudioHapticPlaybackCallback {
public:
    virtual ~AudioHapticPlaybackCallback() = default;
    virtual void OnPlaybackCreated(const std::shared_ptr<AudioHapticPlaybackSession> &session) = 0;
    virtual void OnPlaybackFirstFrame(const std::shared_ptr<AudioHapticPlaybackSession> &session, uint64_t latency) = 0;
    virtual void OnPlaybackEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session, bool isLoop) = 0;
    virtual void OnPlaybackInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
        const AudioStandard::InterruptEvent &event) = 0;
    virtual void OnPlaybackError(const std::shared_ptr<AudioHapticPlaybackSession> &session, int32_t code) = 0;
};
} // namespace Media
} // namespace OHOS
#endif
