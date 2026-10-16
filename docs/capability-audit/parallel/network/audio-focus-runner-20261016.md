# Two ordinary HAP audio focus runner

Entry point: `ci/capability-audit/run_audio_focus_probe.py`. It accepts the same
archive/boot/SDK/guest arguments as the enclosing suite:

```text
python3 ci/capability-audit/run_audio_focus_probe.py \
  --archive NEW_ARCHIVE --boot ACCEPTANCE_BOOT_JSON --boot-id ACTUAL_KERNEL_UUID \
  --sdk API26_RELEASE_SDK --udid ACTUAL_64_HEX_UDID --arch arm64 --device phone \
  --target OWNED_HDC_TARGET --hdc HDC_BINARY --source-volume SOURCE_VOLUME \
  --out-volume OUT_VOLUME --docker-image BUILD_IMAGE --output NEW_PRIVATE_DIRECTORY
```

This batch adds an independent entry point and runtime. It does not modify the
shared normal runner, builder, verifier, media caller, producer, or policy. It
requires the parent's current `audio_focus_observation.py`, current shared
CaptureRuntime/tools/token helpers, media's final fresh snapshot/last_callback
implementation, and the parent's independent `verify_audio_focus_results.py`.
Those dependencies are already maintained separately. The first new package's
complete runtime gate remains necessary; this runner cannot attest that gate.

No SDK, Docker, HAP build, HDC, guest, or producer execution was performed in
this development batch. The host guard regression below is not runtime proof.

## Fixed order and actual boundaries

The entry point first binds the supplied archive, acceptance boot, architecture,
device, HDC target, actual kernel boot UUID and live QEMU process. Missing
independent verifier or failed initial binding does not start guest cleanup or
other commands against an unowned guest. It generates one fresh 32-hex run ID
and sequentially builds/signs two HAPs from current API26 Release input bytes:

- owner: mode 1, `org.harmonycontrib.capabilityaudit`;
- contender: mode 2, `org.harmonycontrib.capabilityauditfocus`.

Both retain the existing normal signer and real code/digest/permission signature
verification. The exported verified P7B and its decoded actual profile are kept;
the runner requires `apl=normal`, `hos_normal_app`, empty allowed ACLs and
restricted permissions, the matching bundle, and the actual device ID. Both
compiled media input contracts and signed HAP native bytes/permissions are
checked using the current shared media contract. After installation, independent
bundle-manager identities must be non-system, account 100, ordinary and have
distinct UIDs. Previous applications are drained only for those two fixed test
bundles before replacement. The fresh run's app files must be absent.

The runtime composes the unchanged `CaptureRuntime.prepare()`: it builds the
actual root tools, compares their linked code with actual guest libraries,
records ALSA hardware, validates real MIC dialog source resources and creates
one independent random stereo challenge in its private root directory. It also
reads the fixed background/notification source contract through the parent's
observation module. Only one producer starts, with fixed rate 48000, channels 2,
repeat 60, timeout 90000 ms and expected 2,880,000 frames. A successful run waits
for the actual producer `played` result and normal exit; it does not terminate
playback and call that success.

Each ordinary actor must independently observe MIC `before-launch=-1`, operate
its actual Start button and trusted MIC Allow control, then observe committed
`after-MIC=0`. If the actual journal reports notification initially disabled,
the runner uses the actual trusted dialog selector; otherwise notification_action
is null. The HAP's own `notification_authorized` readback must be true. The
actual `background_started` IDs, query-background token GRANTED=0, UID/all
unsuspended background task, and ANS OwnerUid/Id/Label join are required. No root
permission grant or fake notification is used.

The owner receives its first active service observation before contender launch.
After the contender's actual MIC primer reaches `contender_start` readiness,
both roles receive another actual UID/all/ANS active snapshot. Only then does
the runner request a new 0.5-second native PCM snapshot for each actor. It checks
the actual nonce/UID/getters/clocks/progress/offset/size, matches the reply file
to the actual native log and independently correlates both samples with the
private challenge before acknowledging contender_start.

After the contender's real VOIP Start interval is printed, the owner must have
a current stopped-state Snapshot and its actual `last_callback` must be
kind 1 / code 0 / hint 3, timestamped no earlier than Start.before_ns and no
later than Start.after_ns + 500 ms. STOPPED/MIC/S16LE enum values are read from
the actual bound public SDK header. This is a control-thread snapshot of native
callback metadata, not callback synthesis. Only that actual condition permits
the owner focus_begin ACK. The final independent verifier still attributes the
actual persisted event_callback and full native/PCM evidence.

The contender_stop ACK permits the real Stop/Release/Destroy. Its actual native
success, native_finished/background_stopped/observer-removal journal, background
service exit and notification exit precede the owner's focus_end ACK. Only
then may the native owner perform its real MIC restart and resumed PCM. Both
roles retain the same actual PID/starttime/UID and have final MIC=0 and
final-background=0 observations. No application force-stop serves as a focus,
revocation, native release, or background-cleanup signal.

## Files, clocks and failure evidence

The stable schema document is `audio-focus-runner-schema.json`. Actual primary
evidence is `OUTPUT/focus/runtime.json`. Actor directories are `OUTPUT/owner`
and `OUTPUT/contender`, with identities, HAPs, profiles, build input manifests,
private files, live native log snapshots and UI trees. Native/private PCM,
ready, request, ACK and snapshot files require actual app UID and mode 0600;
ArkTS permission/journal files retain their actual SDK-created mode. Remote
SHA256 and length are checked against received bytes. Native data files are
never chmodded by the runner.

New root control files are created with exclusive random backing filenames,
mode 0600 and final app UID before atomic hardlink publication to the expected
request/ACK name. The immutable backing hardlink remains as private evidence;
immediate unlink would change ctime during native's before/read/after identity
check. Existing control paths are rejected. The final independent verifier
checks the actual control nonce bytes. No native sample or readiness file is
written by the runner.

Every service snapshot, readiness receipt, fresh request and ACK carries real
guest CLOCK_MONOTONIC bounds from independent read-only token queries around
the operation. Their original JSON is retained in the actor token list. The
runtime rejects expired native readiness before publishing a request or ACK;
native still enforces its own unchanged 15-second handshake deadline. HAP/native
timeouts and callback capacity are not extended or hidden by this runner.

Common producer/tool/library/hardware/boot evidence stays in
`OUTPUT/capture/runtime.json`, generated using the actual shared CaptureRuntime.
The focus runtime references it and all common challenge/boot/notification
contracts by absolute path and SHA256. Command stdout/stderr are preserved as
raw bytes with hashes and actual exit/clock records in `OUTPUT/result.json`.

On failure the runner retains raw native logs, all available nonce-scoped files,
UI snapshots, service and hilog diagnostics before owned cleanup. It stops only
its validated producer and the two fixed test bundles. Cleanup never changes a
failure into success. Runtime status is only `captured_NOT_independently_verified`
after successful collection; the outer result can become pass only after the
parent's independent verifier succeeds with `--runtime --archive --boot-id
--arch --output`. Actual boot UUID and QEMU ownership are checked again.

## Light host checks

```text
LC_ALL=C LC_CTYPE=C LANG=C python3 \
  docs/capability-audit/parallel/network/audio-focus-runner-host-regression.py \
  --dependency-root PARENT_CHECKOUT_WITH_CURRENT_SHARED_HELPERS
```

Nine pure host regressions cover valid/invalid readiness, stale/replayed/foreign
fresh replies, strict integer result fields, actual forced-STOP metadata and
Start causality, expired ACK/request refusing before control mutation, private
native mode rejection before transfer, ordinary identity boundaries, duplicate
JSON rejection and preflight failure without any subprocess/guest cleanup.
The retained transcript is `audio-focus-runner-host-tests-20261016.txt`.
