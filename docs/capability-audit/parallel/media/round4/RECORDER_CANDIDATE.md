# Public AVRecorder candidate

Base e0d1137035d1283aa6a5b7849b86e262256fe272. All 7 requirements stay open.
A new approved actual upstream target is
foundation/multimedia/player_framework/frameworks/native/capi/recorder/native_avrecorder.cpp.
Apply player_framework/recorder_configuration before final source collection.
It stops Prepare after real Configure failure and checks SetMaxDuration failure.
Root must compile the full TU and actual library with unchanged product options.
Its exact manifest records the full fixed-source preimage/revision and output.

Compile batch_media_recorder_probe.cpp + batch_media_recorder_hap.cpp into
libbatchmediarecorder.so using official API26 NDK, C++17/pthread/shared/PIC and
-lavrecorder -lnative_window -lnative_buffer -lace_napi.z. Actual installed header
names are multimedia/player_framework/avrecorder.h and avrecorder_base.h (without
native_ prefix). Use batch_media_recorder_probe.ets with declaration
run(runId:string, expectedDenied:boolean):boolean; replace
__BATCH_MEDIA_RECORDER_RUN_ID__ (32 lowercase hex) and
__BATCH_MEDIA_RECORDER_EXPECT_DENIED__ (literal boolean). Normal foreground HAP,
ordinary MICROPHONE user grant, awaited real dialog and token evidence only.
The template persists actual authorization answers before invoking native code.
Native two-source full host syntax checks use installed actual API26 headers;
Round5 actual NDK three-ABI compilation/link with --no-undefined passed;
ArkTS/HAP compile and product/runtime validation are still pending.

Before launch generate independent new input:

    python3 ci/capability-audit/batch_media_recorder_challenge.py generate \
      --directory FRESH_DIR --run-id RUN

The root ALSA D1p producer receives only challenge.pcm (48k S16LE stereo, one-second
independent NRZ64 symbols, repeat at least20). Audio samples/oracle are never put
inside the HAP. The HAP receives only recorder-RUN-video.bin, exact7680 bytes of
fresh independent grayscale tile values for two cycles, 60 frames per cycle,
64 tiles of8x8 pixels per64x64 frame. Parent root sets this regular private input
file to the actual BMS application uid/mode0600 at
/data/storage/el2/base/files/recorder-RUN-video.bin. Ordinary HAP code can read its
own video input but never the root audio challenge. Also supply video input for
the denied run, so missing input cannot masquerade as permission denial.

Real public AVRecorder MIC AAC/48k/stereo/192kbit + surface AVC/64x64/30fps/1Mbit
writes app-created MP4. Each of two independent instances does prepare/surface/
start/30 genuine frames/pause300ms/resume/30 frames/stop/reset/release. Surface
uses actual native-buffer map, byte stride/capacity checks, RGBA writes, unmap
and flush/abort with fence waits. Fixed source SurfaceEncoderAdapter uses
monotonic nanosecond input and converts output to microseconds; caller passes
nanoseconds (direct AVC codec probe has a different timestamp convention).
Native callbacks retain actual states/reasons/error codes and monotonic times.
Failed Release retains callback storage instead of freeing in-use memory.
No fixed audio samples, synthesized callbacks or metadata-only success is used.
Private outputs (O_EXCL/NOFOLLOW,0600) are recorder-RUN-results.log and
recorder-RUN-cycle1.mp4 / cycle2.mp4; a collision preserves old evidence.

Extract files after native summary and run the independent media diagnostic:

    python3 ci/capability-audit/batch_media_recorder_challenge.py verify \
      --results EXTRACTED/recorder-RUN-results.log --directory EXTRACTED \
      --challenge FRESH_DIR --identity BMS_APP_INFO --run-id RUN \
      --ffmpeg REAL_FFMPEG --ffprobe REAL_FFPROBE --evidence NEW_DECODE_DIR \
      --output NEW_RESULT.json

Actual external ffprobe/ffmpeg are required, not installed or replaced by this
agent. They must provide actual AAC/H.264 decoders; no ffmpeg executable was found
in this media host PATH/known validation tree, so actual decoder invocation remains
pending parent integration. The diagnostic preserves every exact command/stdout/
stderr and both decoded raw outputs. It checks two real AAC/AVC tracks, 60 decoded
frames in sequence, fresh input tiles, byte limits, real packets/DTS and video PTS
against the actual surface clock after pause removal, track duration/sync, and
48k stereo decoded audio in two disjoint windows per phase using the external
fresh root challenge (Pearson>=0.94, source continuity and channel separation).
It also checks the external source advanced during pause. Silence/mono/stale
challenge/replayed frames/truncation/rate or clock mismatches fail. This media
candidate diagnostic does not replace root's shared final verifier or close IDs.
Denied native failures are logged with zero output; root must pair actual denied
MIC token state and same-image positive playback to distinguish permissions from
an unavailable backend. No self-declared candidate_ok overrides external checks.

Host evidence recorder-host-02.log: 8 tests pass. Actual six configuration function
bodies reproduce old failure and test all 17 returns with controlled inner calls;
actual SDK caller syntax and surface copy/stride/tail/abort/unmap/private-file
functions execute under ASan/UBSan. Pixel, PCM and PTS oracle tests are explicitly
synthetic unit inputs, not an actual decoded recorder file or real AAC algorithm
acceptance. Preserve that distinction in final build/runtime evidence.

Parent integration: freeze component/caller/test bytes; compile full product TU
and two public callers (all deliverable ABIs), build/sign ordinary HAP, wire only
parent-owned runner/UI/token/extraction/verifier. Run fresh root PCM + actual HAP
on the new representative image; collect complete failures before next package.
Remaining audio mode/focus/haptic and active revocation candidates are separate;
real AudioVivid plugin dependency and all dependent pipelines remain open.

This batch also fixes the two Knowledge full-TU compile findings: replace the
nonexistent medialibrary_log.h with the actual media_log.h and add direct
access_token:libaccesstoken_sdk / ipc:ipc_core dependencies to the actual
photoaccesshelpernative GN target. Its13-source guard now permits the exact
previous complete e0d1137 overlay to upgrade and rejects mixed versions. Root
keeps the four already-passed objects and retries the two failed TUs using GN's
real dependency exports. No compiler -I workaround or permission-check removal.
