# AudioHaptic preparation and first-frame lifecycle

This component repairs the actual normal-mode AVPlayer and AudioHapticPlayer
lifecycle. It propagates Reset failures, clears previous asynchronous preparation
results before preparing again, reaps a vibration waiter when audio Start fails,
clears pending first-frame data when rearming, ignores callbacks while stopped,
and rejects missing/negative AVPlayer latency payloads.

The two whole-file hashes must match either the complete exported baseline or
the complete patched state. Mixed states, independent edits and symlinks fail
before mutation. The patch uses the pinned player_framework revision
`3d3b1231db27561e8978652d7ae867c12f488d9a` and standard component CLI:

```sh
bash patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle/apply.sh \
  --source-root /absolute/ohos --product arm64_virt
```

Root must register this component in the shared patch plan. It changes neither
the audio/vibrator backend nor public capability claims. The focused test
`ci/capability-audit/test_batch_media_audio_haptic_lifecycle.py` executes nine
actual source functions under ASan/UBSan with controlled dependencies, reproduces
the original failures and checks exact installer behavior. These are host
regressions, not evidence of real PCM or audio/haptic synchronization.

See `docs/capability-audit/parallel/media/round21-coordinated/HANDOFF.md` for the
unbuilt ordinary caller, fresh-package acceptance and remaining dependencies.
