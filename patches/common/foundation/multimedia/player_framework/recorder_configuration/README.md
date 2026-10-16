# Propagate real recorder configuration failures

The fixed public C OH_AVRecorder_Prepare called Configure and then overwrote its
result with the inner Recorder::Prepare result. An audio source/profile/URL
configuration failure could therefore call Prepare and emit a false prepared
callback if that later call returned success. Configure also ignored the real
SetMaxDuration return value. This exact full-source component checks both errors
before advancing. SetLocation and SetOrientationHint are actually void; no fake
return checking or replacement backend is added.

Apply `apply.sh OHOS_ROOT` to the exact manifest revision and whole TU preimage.
The installer preflights before mutation, rejects unknown edits and symlinks,
preserves original CRLF, and repeats only the exact installed state. The review
patch is LF; the actual payload preserves original source bytes outside the two
local replacements. No ABI, public struct, permission or service backend changes.

Host ASan/UBSan executes the six actual GetVideoOrientation/IsLocationValid/
SetProfile/ConfigureUrl/Configure/OH_AVRecorder_Prepare function bodies, using
actual installed public SDK config types and controlled inner Recorder callouts.
It reproduces old false prepared success, injects each of 17 configuration call
failures, verifies no subsequent Prepare/prepared callback, and covers successful
audio-only/video-only/audio-video, invalid config/URL/location/orientation and
inner Prepare failure. Exact full-source installer/review diff tests also pass.
These dependency callouts are not an actual Recorder backend or runtime proof.
The parent must compile this full TU with real product flags and link/validate
actual public recording on the new representative image.
