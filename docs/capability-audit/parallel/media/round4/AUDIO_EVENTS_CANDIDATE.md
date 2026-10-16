# Public MIC active revocation and two-caller focus candidate

No requirement is closed. Compile batch_media_audio_event_probe.cpp and
batch_media_audio_event_hap.cpp as libbatchmediaaudioevent.so with actual API26
NDK, C++17/pthread/PIC/shared, -lohaudio -lace_napi.z. ETS template
batch_media_audio_event_probe.ets uses run(runId:string,mode:number):boolean and
__BATCH_MEDIA_AUDIO_EVENT_RUN_ID__ / __BATCH_MEDIA_AUDIO_EVENT_MODE__ placeholders.
Round5 adds status(runId:string):number and abort(runId:string):boolean.
The real ordinary MICROPHONE requestPermissionsFromUser is awaited and actual
answers are saved as audio-event-RUN-modeN-permission.json. Normal APL/UID only;
no system permission, forged foreground or self-grant is added. Mode0 is active
MIC revocation, mode1 MIC focus owner, mode2 VOICE_COMMUNICATION contender.

Each real public Capturer registers actual read/interrupt/error callbacks, 48k
S16LE stereo raw input. Callbacks copy only supplied bytes into bounded40-second
storage, recording every phase/byte range/monotonic time. Native state, frames
read and timestamps are sampled every20ms, including every call result. A200ms
actual warmup precedes the50-point baseline. Failed Release retains callback
storage. Post-action query failures are logged as actual failures; protocol
completion is not a claim that denied queries must succeed or capability passed.

Parent generates a fresh ordinary Capturer NRZ8 challenge with
batch_media_audio_capture_challenge.py generate. Only root ALSA D1p receives
challenge.pcm (repeat at least45); ordinary callers use actual public HDI MIC/D0c.
Before any action, caller writes fresh0600 app-private files:

- audio-event-RUN-modeN-baseline.pcm: actual pre-action data, independently verify fresh two-channel challenge before action.
- audio-event-RUN-modeN-results.log: identity, actual Start call before/after interval, configuration, snapshots, action-ready/ack records.
- audio-event-RUN-ACTION-ready.json: fresh random32hex nonce from real /dev/urandom, actual uid/state/frames/copied bytes/monotonic time.

Parent reads ready, checks real uid/token/state and required preceding PCM, then
performs the real external action. It creates (no reuse/overwrite) the matching
app-private audio-event-RUN-ACTION-ack, exactly nonce plus newline (33bytes), app
uid,0600. Publish the complete ack atomically. Symlink, wrong uid/mode, wrong
length/nonce, missing-after15sec or clock rollback/error fails the handshake.
Read-only ready/ack signals carry no permission/token privilege or expected PCM.
The final audio-event-RUN-modeN.pcm and log contain all actual callbacks/events.
All private evidence uses O_EXCL/NOFOLLOW; previous evidence is preserved.

Mode0 sequence: granted MIC baseline/checkpoint -> ACTION=revoke -> root actual
query/granted evidence, live RevokePermission without killing app, query/denied
evidence -> ack ->1.5sec actual post-revoke state/frame/clock/PCM observation ->
actual Start return recorded ->0.5sec observation -> actual Stop/Release. Require
positive fresh PCM before revocation, app remains alive/ordinary, token really
changes, post-action stream stops/no nonzero samples after200ms, and denied
restart. Failure of an unavailable backend cannot prove permission enforcement.

Mode1 and mode2 must be distinct ordinary bundles/UIDs with real MIC grants.
Round5 supersedes the original idle-contender preparation. See
../round5/HANDOFF.md for actual MIC primer, real ordinary audioRecording task,
normal KEEP_BACKGROUND_RUNNING/profile/backgroundModes and notification consent,
new native status/abort methods, Start button and root service/UI verification.
Root must independently verify owner is still RUNNING with advancing fresh PCM
after second-app authorization and before contender_start ACK. Both actor tasks
and tokens must be real ordinary service state. No runtime claim is made.

After contender Start succeeds, it obtains real baseline PCM and publishes
ACTION=contender_stop ready. Parent verifies contender actual input, grants owner
focus_begin ack, and observes owner stopped with real forced STOP callback.
Owner then publishes ACTION=focus_end. Parent acks contender_stop and waits for
actual contender Stop/Release completion before acking owner focus_end. Owner
calls the actual Start again, records1sec fresh resumed PCM, then Stop/Release.
Bind callback timing to contender's actual before/after Start interval and token/
session/service evidence. Owner stopped before contender Start is failure.
The fixed source XML row is SOURCE_TYPE_MIC -> SOURCE_TYPE_VOICE_COMMUNICATION,
private/forced STOP(existing); fixture records actual upstream file SHA and row.
Parent must verify the newly packaged service actually uses that policy. Two
same-UID instances, a dialog/background stop or self-reported callback count
cannot establish this two-caller focus behavior.

The media-owned independent diagnostic is:

    python3 ci/capability-audit/batch_media_audio_event_challenge.py \
      --results EXTRACTED/audio-event-RUN-modeN-results.log --directory EXTRACTED \
      --manifest CHALLENGE/challenge.json --challenge CHALLENGE/challenge.pcm \
      --identity NORMAL_BMS_INFO --run-id RUN --mode N --output NEW_RESULT.json

It verifies ordinary identity, full public lifecycle/action/nonces, actual complete
PCM/chunk file and checkpoint-prefix consistency, two disjoint fresh stereo
correlation windows, baseline native timestamp/rate, stopped/no-leak/restart
boundaries, real forced STOP and fresh resumed PCM. It deliberately returns
external_token_or_second_app_policy_evidence_required=true and closed_requirements=0.
Root's shared verifier still must bind actual permission/token changes, two UIDs,
actual installed focus policy, cross-app Start/stop/callback timing and foreground
state. The diagnostic alone does not certify them. Host tests use explicit
synthetic oracle fixtures; SDK syntax and actual callback/nonce/file functions
execute under ASan/UBSan. Round5 actual official SDK26 three-ABI native links passed; full UI HAP and
real product/HDI/service runtime remain pending.
