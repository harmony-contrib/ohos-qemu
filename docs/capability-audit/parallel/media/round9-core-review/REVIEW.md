# Round 9 core media protocol review

Read-only review of the main checkout at `/Volumes/PSSD/code/ohos-rs/ohos-qemu`, observed HEAD `f89b9c743f90b4fdaa7b737451b1a4cdff57f02e`. Individual bytes are bound in `review-inputs.json`; the main branch may advance independently. Child baseline is `54f1ae07a4a6096a6334c67a5ccbb3ca997e312f`.

Only this documentation directory was changed. No runner, verifier, native/ArkTS protocol, frozen product source, network file, or package was modified. No Docker, SDK compilation, HDC, QEMU, or guest test ran. The host checks below are synthetic oracle diagnostics, not runtime acceptance. Closed requirements: **0**. Representative artifact / full guest behavior gate: **not passed by this review**. Earlier statements that mode0 active revocation had passed a real guest gate were corrected by root; its formal orchestration and host mutation checks were implemented, but the guest gate has not run.

## Confirmed defects for the next combined repair batch

### R9-1 — ArkTS microphone readiness can abort on a file still being written

References: `batch_media_audio_event_probe.ets:121-147`; `batch_media_audio_event_probe.cpp:70-74,216-227`; compare the corrected root-side completion handling in `audio_focus_runtime.py:394-420`.

Native `WritePrivate` exposes the new ready inode at `open(O_CREAT|O_EXCL)`, then writes, fsyncs and closes it. Only afterwards does native append `event_ready`. The ArkTS 20 ms `waitForMicrophone` loop checks `accessSync` and immediately parses `readTextSync`. It does not wait for native's completion marker or retry a partial file. An empty/short read throws through its outer catch, records `startup_failed`, and aborts the otherwise valid native session. This is a definite protocol race; its occurrence frequency on a real guest is unmeasured.

Minimal regression: make the ready inode visible with empty/partial JSON, complete the same nonce-scoped file on the next poll, and require startup to continue only once the complete current-run ready record is available. Retain the actual worker status, 8 second timeout, RUNNING/frame checks, and fatal treatment of a completed wrong-run/malformed record. Use an explicit completion signal or a bounded completion protocol; arbitrary parse-error suppression would hide corrupt completed files. Root's HDC-side ready handling is already completion-aware; that does not protect the in-app reader.

### R9-2 — Main-stream error callbacks are not rejected by the event oracle

References: `batch_media_audio_event_probe.cpp:43-49,56-68`; `batch_media_audio_event_challenge.py:81-100`; callers `verify_audio_focus_results.py:243-247` and `verify_audio_revoke_results.py:65-68`. The primer correctly checks errors at event oracle line 34.

Actual `Error` only appends `{kind:2,code,hint:0,monotonic_ns}` to the context. It does not set `invalid`, so a transient error does not necessarily fail the native summary. The event oracle collects main `event_callback` rows, requires the owner's forced STOP callback, and returns the callbacks without rejecting kind2. The outer focus verifier also does not reject them. Thus an error followed by otherwise valid data/state can be accepted. The ready/fresh protocol itself still requires real PCM; this finding is about an ignored actual error, not a claim that callbacks alone pass positive capture.

Host reproduction: insert `event_callback(kind=2,code=2,hint=0)` into each existing mode0/1/2 fixture. All three mutated logs still return `candidate_audio_event_PCM_diagnostic_pass`. Add rejection tests for each main actor; any intentionally tolerated error needs a precise API/state/phase rule rather than blanket acceptance. Callback errors in the deliberate denied restart should be considered separately if the public contract documents them, but the demonstrated injected error occurs in the active baseline before the external action.

### R9-3 — Event timestamps can use a wrong absolute clock while passing validation

References: `batch_media_audio_event_challenge.py:15-17,70-73`; `audio_focus_runtime.py:62-110` (`validate_fresh`); `verify_audio_focus_results.py:346-360`. The ordinary Capturer oracle already checks absolute query bounds at `batch_media_audio_capture_challenge.py:125-145`.

The event baseline/primer oracle requires successful timestamp calls and a 48 kHz delta, but never compares returned `timestamp_ns` with that getter's actual `before_ns/after_ns`. Fresh snapshot validation compares timestamp progress between request and reply, but also lacks the returned timestamp's relation to the actual query clock. Adding one hour to all baseline/primer returned timestamps preserves the delta and passes in modes0/1/2. It would accept a wrong clock domain or constant clock offset even though native explicitly asks for `CLOCK_MONOTONIC`.

Minimal regression: shift only returned timestamp values (keep callback/query monotonic clocks unchanged) forward/backward by a large amount and require rejection. Apply explicit documented query/latency bounds, frame/position checks and result/type checks in active running phases, following the existing ordinary Capturer oracle. Preserve appropriate stopped-state handling rather than requiring a stopped timestamp to progress.

## Timing / runtime risks that are not proven failures

- Owner `focus_begin` is created before `launch(contender)` (`audio_focus_runtime.py:708-743`). Its immutable 15 second deadline must include the second app's actual start button/MIC and optional notification UI, normal background task startup, multiple UID/ANS service dumps, ready-file transfers, both 0.5 second fresh PCM observations/correlations, process checks, VOIP Start, live forced STOP observation, and owner ACK. Each generic root wait has its own 12 second allowance rather than a propagated owner deadline. `ack`/fresh-request checks correctly reject expired operations; they do not establish the full sequence fits on the new guest. Many sequential HDC round trips make this a material liveness risk, but no real latency measurement was collected here. Preserve command and guest monotonic timing, test a controlled slow transport/UI, batch read-only observations where safe, and fail explicitly before the remaining budget is exhausted. Do not extend native's frozen handshake or treat an old guest / host fixture as evidence that this route fits.
- The native loop continues 50 ms snapshots and cancellation/deadline checks while waiting for new PCM; no timer-only success was found. Two fresh observations consume at least 1 second of genuinely new PCM in sequence. Maximum valid native owner/contender phase durations stay below each context's 40 second PCM storage bound; wall-clock control overhead may still exhaust handshakes.
- The service may suspend/cancel a real background audio task, and this ETS helper intentionally aborts on unexpected actual cancellation/suspension. The read source here does not prove that a legitimate focus forced STOP will necessarily cancel `audioRecording`. A new-guest observation is required. Keep raw service/task/notification dumps and cancellation details; do not mark this as a confirmed product defect or bypass it with fabricated foreground/system identity.
- Producer starts before permission UI. Focus uses an exact 60 seconds of challenge (`repeat=60`, 2,880,000 stereo frames), native producer deadline 90 seconds, and completion wait 95 seconds. Waiting for full producer completion after both streams stop is intentional; it is not a native handshake. Early producer exit is fail-closed during waits. If UI/control setup consumes challenge time, fresh correlation must reject missing/stale/silent input. Measure remaining source coverage on the new guest. Revoke intentionally uses the common 20 second producer and its matching 35 second collection wait/verifier; do not silently compare it with the focus-only 60 second contract.

## Source-level agreements checked

- Actual API26 `native_audiostream_base.h` declares MIC=0, VOICE_COMMUNICATION=7, S16LE=1, STOPPED=3. Native uses these real enums; fresh observations must be actual MIC in mode1 owner / mode2 primer, while mode2 subsequently creates VOICE_COMMUNICATION. Existing renderer-only code is not used as capture evidence.
- Root ready/fresh readers wait for the matching native completion row after checked file writes, then compare copied JSON with the row. The fresh PCM is exactly 96,000 bytes (48,000 Hz × 2 channels × 2 bytes × 0.5 seconds), from callbacks later than request acceptance; full PCM callback offsets and private file content are replayed independently. One request per handshake; same ready nonce; early ACK after an uncompleted requested snapshot fails.
- Root creates nonce control files exclusively through a private backing inode, assigns ordinary UID/0600, then hardlinks the final path. Retaining the backing link avoids a ctime change during native's fstat-before/after snapshot request validation. Root checks PID/starttime/UID; no app-level grant or privilege escalation substitutes for actual UI/token observations.
- Permission action uses actual UI hierarchy nodes. Native worker starts only after the actual permission request result. Background focus start waits for actual MIC RUNNING data, normal `KEEP_BACKGROUND_RUNNING` token, and real task/ANS joins. Mode0 stays foreground. Normal permission `availableLevel=normal` needs no additional ACL/profile exception; installation and independent token observations still must prove the real grant.
- Contender Stop/Release/native completion/public background stop/observer cleanup/service exit precede owner's `focus_end` ACK and restart. Final owned force-stop is cleanup after collection, not focus evidence. Mode0 verifies the same live process around actual RevokePermission, denied token, nonce ACK, quiet stopped state, and denied restart through its independent oracle.

## Host check and evidence limit

Command, from the private media worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C LC_CTYPE=C LANG=C python3 docs/capability-audit/parallel/media/round9-core-review/reproduce_oracle_gaps.py --root /Volumes/PSSD/code/ohos-rs/ohos-qemu --output docs/capability-audit/parallel/media/round9-core-review/host-observations.json
```

Result: six mutations unexpectedly accepted, comprising R9-2 and R9-3 in each mode0/1/2. The generator creates independent random challenge data using the existing fixture helper; it is only a deterministic test of current verifier logic, not actual captured PCM, installed HAP permission proof, or guest execution. Temporary inputs were removed; only the small result and reproduction script are retained. R9-1 is established from actual file publication/reader ordering; the empty-JSON host control is not an ArkTS engine test. Root owns the unified repair and new-guest validation.
