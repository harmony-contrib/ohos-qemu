# AudioHaptic same-guest coordinator candidate

This batch adds only `batch_media_audio_haptic_coordinator.py`, its dedicated
test and this directory. It does not edit the round21 files, shared runners,
VDI, product source, launch policy or the running representative build02.
Nothing here closes `behavior:audio-interrupt-haptic-renderer-dependency`.

The coordinator has executable preparation, collection and independent raw
recheck paths. Synchronization acceptance deliberately remains rejected:
the public AudioHaptic API and the supplied latency-only native log cannot
establish actual audio output onset on CLOCK_MONOTONIC. `run` and `verify`
return1, including a clean partial collection; neither is a full-gate command.
Do not register this candidate as a successful closure or ignore that exit.

## Prepare and actual root prerequisites

```sh
python ci/capability-audit/batch_media_audio_haptic_coordinator.py prepare \
  --sdk /absolute/provider-sdk-26-full/26.0.0 \
  --source-export /absolute/r52-audio-haptic-source-inputs-01/evidence.json \
  --output /absolute/new/audio-haptic-inputs
```

The command reads SDK26.0.0.105 and the already-exported16 real files, writes
`preparation.json`, three complete derived source projects, three distinct random
stereo48k/16bit NRZ WAVs and real-format JSON. Default duration is60s. Each JSON
event is at most5000ms (the actual schema's maximum); adjacent events have no
gaps. Only the virtual TIME aggregate start/deadline/stop is claimed, not pulse
shape or physical vibration. The short1s option exists only as the Python
function's host-test argument; the CLI prepares60s for the real UI sequence.

| Role | Exact bundle | Ordinary requested permissions | Actual use |
| --- | --- | --- | --- |
| owner | org.harmonycontrib.audiohaptic | VIBRATE, KEEP_BACKGROUND_RUNNING | MEDIA playback and real audioPlayback background task |
| contender | org.harmonycontrib.audiohapticcontender | none | VOICE_COMMUNICATION playback, muteHaptics=true |
| denied | org.harmonycontrib.audiohapticdenied | none | actual unmuted createPlayer201 rejection |

All three require normal/hos_normal_app, empty ACL/restricted sets, actual fresh
UDID signatures and installed BMS identities. No system identity or permission
grant operation is implemented. Root must compile/sign/install these projects;
the previous foreground HAPs are not interchangeable with these new sources.
`entry/EntryAbility` uses the SDK105 default profile. The owner's ability has
only `backgroundModes: ['audioPlayback']`. App label is the actual generated
resource `Haptic audit`, used for the real notification dialog selector.

`prepare` also writes `audio_haptic_token_observer.cpp`. Root must compile this
read-only helper and round21's passive HDI observer against actual product ABI
and DSOs. No compilation occurred here. Token CLI is:

```text
TOKEN RUN32hex UID EXACT_BUNDLE ohos.permission.VIBRATE
TOKEN RUN32hex UID EXACT_BUNDLE ohos.permission.KEEP_BACKGROUND_RUNNING
```

It only uses GetHapTokenID/GetHapTokenInfo/VerifyAccessToken and MONOTONIC. The
three fixed bundles and two permissions are the entire accepted surface. It has
no grant/revoke/general bundle mode. One JSON line contains schema_version1,
run_id,user_id100,uid,bundle,token_id,permission,before,after,before_ns,after_ns.
Errors exit nonzero. The independent parser rejects changed UID/bundle/token,
unexpected grant, boolean numeric values, duplicate keys and backwards clocks.

## Actual inputs contract

`run --boot BOOT --archive ARCHIVE --hdc HDC --preparation preparation.json
--inputs actual-inputs.json --output NEWDIR` never boots, builds, signs or
installs. The enclosing suite must already own the healthy new acceptance guest
and install the verified HAPs. `actual-inputs.json` has:

```text
actors.{owner,contender,denied}:
  source_project: absolute prepared role/project path
  sdk_project: actual project key in original SDK report
  sdk_evidence: {path,sha256} of original actual SDK report
  unsigned_hap: {path,sha256} of actual SDK output
  signed_hap: {path,sha256} of actual UDID-signed output
signer_dist: actual fixed public signer distribution
signer_jar: optional actual fixed jar path
helpers.{passive,token}:
  binary: {path,sha256}
  build: {path,sha256} of original real compile/link receipt
  path_map: optional at most2 explicit {from:LinuxBindPrefix,to:hostPrefix}
```

Shared `batch_apps_contact_picker_coordinator` is reused lazily for real SDK
project checks and Java/OpenSSL signature/profile verification. Root must have
that already-integrated helper available. Every prepared code/config/resource
SHA must occur unchanged in the selected original SDK project's inventory;
compiled signed payloads must equal the unsigned SDK payloads. A failed unrelated
project in a batch is not rewritten into a globally successful SDK report.

Each new native build receipt is required to contain:

```text
scope: compile_link_ONLY_NOT_guest
arch: actual arm64|armv7a|x86_64
source: original {path,sha256} of prepared source
binary: original {path,sha256} of actual ELF
commands: [{argv:[actual original argv],exit_code:0,log:{path,sha256}}, ...]
libraries: [{guest_path:actual /system|vendor/lib* DSO path,
             file:{path,sha256} of retained real linked DSO,
             runtime_sha256: actual loadable ELF runtime identity}, ...]
```

Only explicit bind prefixes map retained source/binary/log/DSO artifacts to the
host; original records/argv/report are preserved. No arbitrary `/ohos` header
re-read is asserted. Root must preserve actual compiler/header/input metadata
and original builder report as part of its build gate. This is an interface for
the next real root compilation, not a fabricated build receipt.

Both helpers' linked DSO runtime bytes are read back from this guest and compared.
The actual owner/contender `/proc/PID/maps`, unique `libaudio_haptic.z.so` inode,
current file bytes and runtime identity are also retained. That is not a fresh
source→GN compile→image provenance witness: independent output explicitly keeps
`native_pipeline_source_image_witness_verified:false`. Root must additionally
join those actual bytes to its real build02/current archive source witness.

## Executed protocol when root runs it

1. Validate enclosing archive/boot/QEMU identity, actual active account100,
   helper receipts/current DSOs, all SDK sources/signatures, installed HAP byte
   equality, BMS ordinary UIDs and independent permission tokens.
2. Launch each actual page with GuestUi, verify a single real visible button and
   kernel PID/UID/start generation; stage distinct inputs and UID-owned0600
   private journals/requests. The page's sandbox is the UIAbility directory
   `/data/app/el2/100/base/BUNDLE/haps/entry/files/`; a different actual layout
   fails, rather than silently writing another sandbox.
3. One actual `audio_haptic_run` click arms each control timer. Fresh atomic
   request nonces then control only that app's public calls. Its50ms poll reads
   complete newline-terminated requests, while each host operation retains its
   original15s deadline. Neither poll count nor deadline expiry is a pass.
4. Owner performs real notification authorization. The controller observes the
   source-bound notification dialog title/bundle/Allow node; an already-enabled
   actual getter may complete without a new dialog. Denial fails. Then exercise
   the actual zero-permission201 and both ordinary real init calls.
5. Start the passive HDI observer from real idle, then owner's actual player and
   audioPlayback task. Move the contender UI to foreground. Only now create a
   fresh nonce QMP WAV. Require new independent owner PCM/progression and actual
   unsuspended mode2 background task/ANS/PID/UID/IDs before contender Start.
6. Start a second fresh WAV, issue contender's real public Start, read owner and
   contender journals, and retain actual eventType/forceType/hintType/ACTIVE
   timestamps. The current candidate requires an observed forced BEGIN PAUSE or
   STOP and real TIME cessation. It does not assume the MIC/VOIP capture policy
   proves this renderer policy. If current product policy differs, preserve raw
   failure and inspect the real renderer row; do not relabel DUCK or shared
   hints into forced STOP.
7. Independently correlate disjoint real PCM windows and progression. The focus
   WAV deliberately has an owner prefix; only its final independent half-second
   is tested as contender. Correlation≥.99999 rejects appreciable mixed audio;
   it is not an assertion of mathematically zero residual or physical silence.
   Empty44-byte WAV, silence, collapsed channels, unrelated input and replay fail.
8. Release players/resources, publicly stop owner background task, unsubscribe
   and close controls, verify both actual task/notification absence, passive
   final idle, own observer exit, own caller PID absence, capture cessation and
   owned input/root-temp removal. The suite still owns installed HAP removal;
   private raw journals remain until its uninstall. `cleanup_complete` means
   those active test resources were actually reclaimed, not app uninstall.

Owned QMP operations are only real `info capture`, `wavcapture PATH ohos_audio
48000 16 2` and `stopcapture OWN_INDEX`, via the existing owned socket. Exact
command/reply nonce/path bindings are rechecked. A lost start reply is tracked
before the call and cannot create an unowned capture or a false cleanup flag.
No pause/continue, backend change, manual vibration Start/Stop, timer-generated
success or power/screen policy override exists. Run the old mutating vibrator
probe separately, never concurrently.

## Independent recheck and unimplemented anchor

```sh
python ci/capability-audit/batch_media_audio_haptic_coordinator.py verify \
  --evidence NEWDIR/evidence.json --archive SAME_ARCHIVE --boot SAME_BOOT \
  --output /absolute/new-verification.json
```

`verify_observations(...)` re-reads actual raw logs, helper/SDK/signature/HAP bytes,
token/PID identity, current account, real PCM, HDI samples, service dumps, request
nonce/terminal rows, clock brackets and forced callback. It reruns Java/OpenSSL
verification in a new directory; a receipt `pass` field is insufficient.
The Python entry requires `signature_output` and `signature_command`; the CLI
supplies real subprocess implementations and saves their original logs/argv.
No actual signing or verifier command was executed during this host-only batch.

Observed app ACTIVE clocks must fit the enclosing actual helper MONOTONIC
control brackets. These brackets bound control actions only. Conservative HDI
edge intervals retain IPC uncertainty. Host QMP timestamps order actions only.
Source duration, capture creation, file growth, a resolved Start, recording
start, the timer or a latency-only hilog line are not an audio onset clock.
`no_onset_anchor` accepts no purported anchor timestamp/JSON; unsupported claims
raise. Recheck returns `accepted:false`, synchronization false, ledger false and
first-artifact gate false even if all available observations pass.

The newest root `r52-Audio-first-frame-source-01` export resolves the callback
producer, not the output clock. `renderer_in_client_public.cpp:64,758–774` uses
the120ms constant for normal first-frame callbacks; its507–510 fast latency is
also a20ms debug constant. The older fast path reaches
`AudioProcessInClientInner::GetLatency:525–528`, another20ms debug constant.
`renderer_in_client.cpp:881` triggers first-frame processing at first write.
`HiPlayerImpl::NotifyAudioFirstFrame:3757–3763` forwards the latency unchanged.
AudioHaptic then adds `max(audioLatency-hapticDelay,0)` milliseconds before its
async haptic start. None of these values is a measured speaker onset.

`FastAudioStream::GetAudioTime:338–350` requires Timestamp::MONOTONIC, but its
actual frame/time pair comes from shared-buffer GetHandleInfo in
`AudioProcessInClientInner::GetAudioTime:487–510`. The handle producer is not
proved by that client code. Normal `GetAudioTimestampInfo:2220+` obtains
readIdx/timestamp/latency through IPC GetAudioPosition and subtracts buffering,
speed and Sonic frame latency. The server/HDI clock lineage remains to be
established. Client session/PID/UID association is available through
GetSwitchInfo/GetStreamSwitchInfo:1846–1884, but AudioHaptic's public object does
not expose that underlying renderer. A newly inserted MONOTONIC log at the
first-write callback would merely timestamp an estimate.

The narrowed remaining read-only source request is in `source-export-request.json`.
A valid next implementation must bind the *same actual AudioHaptic
renderer* and first presented frame (or a measured QEMU sample-clock mapping)
to MONOTONIC with an independently established uncertainty, corroborated by the
fresh captured waveform. Only after that implementation and its source/image
binding may a separately reviewed synchronization verifier accept a tolerance.

`source-basis.json` records the exact already-frozen source/SDK/contracts read.
Final `host-evidence-03.json` / `host-tests-03.log` record37 passing light host
checks (23 new plus14 frozen round21,1.201s; outer subprocess1.3402s). Original
attempt01 caught a cleanup-block indentation error; attempt02 caught the host
fixture's `/var` versus canonical `/private/var` QMP path. Their original reports
and logs remain unchanged as `host-evidence.json`/`host-tests-01.log` and
`host-evidence-02.json`/`host-tests-02.log`; the exact QMP path check was retained.
These are source/protocol/explicitly named host-PCM-fixture tests, not real guest
behavior. No SDK/native compile, signing, Docker, source/out access, VM or
capability closure took place.
