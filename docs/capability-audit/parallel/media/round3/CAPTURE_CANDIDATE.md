# Public Capturer candidate — integration request

Base: d4e74c00caa47127906075c57d59500d60844f04. All 7 requirements stay open.
This batch adds only media-owned diagnostic/caller files; no product source,
shared build/runner/verifier, kernel, adapter JSON or device file is changed.

Compile batch_media_audio_capture_hap.cpp and batch_media_audio_capture_probe.cpp
with the actual ordinary HAP NDK target/sysroot, -std=c++17 -pthread -Wall -Wextra
-Werror -fPIC -shared -lace_napi.z -lohaudio, producing libbatchmediacapture.so.
The ArkTS template is batch_media_audio_capture_probe.ets; its generated declaration
must declare run(runId:string, expectedDenied:boolean):boolean. Replace exactly
__BATCH_MEDIA_CAPTURE_RUN_ID__ (fresh 32 lowercase hex) and
__BATCH_MEDIA_CAPTURE_EXPECT_DENIED__ (true/false). Declare MICROPHONE as an ordinary
user grant permission, reason/usedScene EntryAbility/inuse. Keep the application
foreground. The template awaits the public requestPermissionsFromUser call with
the actual UIAbilityContext before invoking native capture. Parent drives the real
grant/deny dialog and independently checks/revokes the application token. Returned
permissions/authResults/dialogShownResults are saved in a fresh private
audio-capture-RUN-permission.json and hilog. Existing permission evidence is preserved.
An answer contrary to expectedDenied still proceeds to the real native call and
must be rejected by actual lifecycle/content/token verification; the template
does not silently grant itself or request a system source.

Native APIs are public OH_AudioStreamBuilder/OH_AudioCapturer, using real MIC,
48kHz S16LE stereo, normal latency and the API20+ read-data/error callbacks.
The callback copies only actual supplied bytes to a bounded 8-second buffer and
records the exact offset/length/phase/monotonic clock. It never reads the challenge
file, produces sample values, uses Renderer or calls ALSA. Two separate capturer
instances each exercise prepared → start → pause → flush → resume → stop → release,
check actual states and paused/stopped/released quiescence. Six GetTimestamp and
GetFramesRead observations are recorded per instance. Private log/PCM files are
created exclusively at mode0600 under /data/storage/el2/base/files:

- audio-capture-RUN-results.log
- audio-capture-RUN-cycle1.pcm
- audio-capture-RUN-cycle2.pcm

Stop/Release errors remain failures. A failed Release retains callback storage
rather than releasing it while a callback could still use it. The native summary
is only candidate_ok and explicitly requires independent PCM verification.

Parent root producer/compiler remains responsible for the actual ALSA tool from
the preceding batch. Generate fresh host data before each run:

    python3 ci/capability-audit/batch_media_audio_capture_challenge.py generate \
      --directory NEW_EVIDENCE_DIR/challenge --run-id RUN

Only root receives challenge.pcm. Run the actual guest producer against loopback
D1p before/during the ordinary HAP capture of D0c. Defaults are one second of fresh
independent random NRZ chip data, 48k S16LE stereo; each chip spans 8 frames and
amplitude is +/-8192. Use --repeat 20 --timeout-ms 30000 for the guest producer.
Keep challenge.json/hash, producer binary/hash/log/status, /proc/asound card/PCM,
package/hash, normal application identity and actual token grant/denial evidence.
Do not ship the challenge or expected samples inside the HAP. Root producer success
alone is not an acceptance oracle. Extract private results only after the native
summary, preserving original permissions/file paths in evidence.

The media-owned independent diagnostic (not the shared formal verifier) runs:

    python3 ci/capability-audit/batch_media_audio_capture_challenge.py verify \
      --results EXTRACTED/audio-capture-RUN-results.log --pcm-directory EXTRACTED \
      --manifest NEW_EVIDENCE_DIR/challenge/challenge.json \
      --challenge NEW_EVIDENCE_DIR/challenge/challenge.pcm \
      --application-identity BM_APPLICATION_INFO --run-id RUN --output NEW_RESULT.json

It independently validates normal UID/system status, exact lifecycle/error/state
sequence, actual public format, quiet intervals, complete PCM/chunk ranges and
file sizes. For each pre/post-pause phase in both instances it finds a fresh
random two-channel sequence and compares every sample in two disjoint 8192-frame
windows. Both Pearson correlations must be >=0.995, cross-channel correlation <=0.25,
and the source displacement must match the captured frame displacement within one
sample. Silence, a stale challenge, mono/duplicated/swapped channels, wrong rate,
repeated short buffers, lost samples, truncated files and self-declared pass values
cannot substitute. Three actual native timestamp/frame/byte observations per phase
must advance in the monotonic clock domain at 48kHz within 2%. No numpy dependency.

Expected-denied mode reports the actual GenerateCapturer/Start error and creates
no accepted PCM. Parent must pair this with independent denied-token evidence and
the granted positive run from the same newly packaged artifact. A generic backend
failure cannot prove permission enforcement. Revocation while active and actual
focus interruption are still separate parent-controlled cases; this candidate logs
a real callback/error/lifecycle failure rather than recasting it as success.

Host evidence capture-host-02.log: 4 tests passed. The full native capture caller
passes local clang syntax checks against 8 exact pinned public SDK C headers;
actual read-callback copy/boundary functions execute with ASan/UBSan. Independent
oracle tests use explicitly synthetic unit fixtures to prove acceptance/rejection
logic, not backend capability. Actual HAP NDK compilation/link/signing and the new
representative image have not been run by this agent. The parent owns SDK compile
scheduling and the formal runtime gate.

Still missing beyond this candidate: public AVRecorder output/decode and PTS tests,
real permission revocation/focus/haptic/dependent pipelines, KnowledgeContent actual product/ACL/runtime acceptance, and actual AudioVivid
builder dependency. NONE/HOLIDAY producer semantics are addressed by the separate
knowledge_holiday_index candidate with no runtime closure. None is closed
by callback counters or these host checks.

Parent validation update: actual official API26 native caller compile/link for all
three ABIs passed (r52-public-capturer-SDK-3ABI-01); actual API26 HAP02 compiled
with WRITE_ONLY. Parent owns native binding checks, signing and runtime gate.
