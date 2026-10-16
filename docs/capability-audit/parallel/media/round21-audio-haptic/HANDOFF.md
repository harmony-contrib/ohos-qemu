# AudioHaptic TIME candidate and acceptance design

This is a source/data/protocol candidate, not a compiled or guest result. It does
not close `behavior:audio-interrupt-haptic-renderer-dependency`. Root confirmed
the old finding specifically reports renderer Start=2/no callback data, rather
than a requirement for physical vibration or HD waveform support. The proposed
runtime scope is actual public AudioHapticPlayer playback/interrupt/lifecycle,
fresh virtual audio data and the existing virtual TIME vibrator's observable
start/stop/deadline. No VDI or product source was modified.

## Confirmed sources and APIs

Actual host SDK is `provider-sdk-26-full/26.0.0`, ETS26.0.0.105.
`ets/api/@ohos.multimedia.audioHaptic.d.ts` declares:

| Lines | Actual API/constraint |
| --- | --- |
| 24 | Devices without a vibration component produce no vibration effect. |
| 37/125/142 | getAudioHapticManager/registerSource/unregisterSource |
| 155/169 | setAudioLatencyMode/setStreamUsage |
| 174–188 | createPlayer; VIBRATE needed when haptics is requested; real201/401/5400102/5400103/5400106 errors |
| 288 | isMuted(AudioHapticType), the available relevant getter |
| 299/309/318 | start/stop/release; no public prepare, state or playback-position getter |
| 329/350 | actual endOfStream/audioInterrupt callbacks |
| 388/458 | setVolume/setLoop, public; separate future boundary cases |

The fixed16-file root export is
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-audio-haptic-source-inputs-01/evidence.json`.
`verify_export` checks all recorded file SHA values before generating data.
Relevant actual paths under its `source/` preserve upstream relative names:

- `foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_player_impl.cpp`:
  Prepare191–207 prepares real sound and haptic source; Start211–237 starts the
  real sound. NotifyStartVibrate687–698 wakes the haptic thread from the real
  first-frame event. StartVibrate529–558 waits for that event, applies latency
  delay and calls the vibrator. Line558 ignores the asynchronous vibrator return
  code; line563 still logs a success event. Therefore neither a resolved start
  nor this log proves vibration. Stop240–254 and interrupt663–668 stop vibration.
- `audio_haptic_sound_normal_impl.cpp:493–504` receives the actual native
  first-frame event and its latency. This private pipeline observation can be
  an independent timing witness if its PID/stream/clock mapping is established.
- `audio_haptic_vibrator_impl.cpp:274–319` really opens/decodes the file via
  Sensors::PreProcess. Normal mode486–487 goes to the AVPlayer path; lines698–706
  reach Sensors::PlayPattern. Essential branches require SUPPORT_VIBRATOR.
- `base/sensors/miscdevice/services/miscdevice_service/src/vibrator_thread.cpp:226–256`
  has the real COMPOSITE_TIME→TransformTime→EnableCompositeEffect branch.
  `haptic_matcher/src/custom_vibration_matcher.cpp:127–156` emits relative event
  starts and a final zero-duration stop marker.
- The exported `utils/tools/haptic_format_converter/converter/schemas/oh_schema.json`
  and `tests/test_data/oh_no_curve_sample.json` define the actual MetaData /
  Channels / Pattern / Event / StartTime format. Generated JSON uses one
  continuous event at0, one channel, no curve or invented pulse capability.

The existing virtual VDI is
`patches/common/drivers/peripheral/vibrator/files/qemu_virtual_vibrator.cpp`.
Lines110–144 validate TIME composites and retain their aggregate deadline;
154–159 return actual running state. Lines162–176 reject HD patterns/startup
time. It does not expose or simulate physical output or per-pulse intensity.
Using a single zero-start continuous event avoids claiming gap-waveform support.

Root's retained actual selected-GN evidence is
`r52-selected-GN-suspend-and-haptic-01/evidence.json`; the selected audio_haptic
graph includes SUPPORT_VIBRATOR. This is GN selection only. Actual compilation,
linking, current-image DSO and guest mapping must still be proved. The real
player selects DSP using `const.multimedia.audio.support_hadware_audio_haptic_sync`
(the source spells **hadware**), player_impl72–90. Record its actual guest value;
do not override true or assume default=false was what ran.

## New candidate interfaces

`ci/capability-audit/batch_media_audio_haptic.py` prepares real external inputs:

```sh
python ci/capability-audit/batch_media_audio_haptic.py prepare \
  --sdk /absolute/provider-sdk-26-full/26.0.0 \
  --source-export /absolute/r52-audio-haptic-source-inputs-01/evidence.json \
  --output /absolute/fresh/challenge
python ci/capability-audit/batch_media_audio_haptic.py project \
  --sdk /absolute/provider-sdk-26-full/26.0.0 \
  --challenge /absolute/fresh/challenge/challenge.json --output /absolute/new/project
```

`project --denied` creates a distinct normal zero-permission caller. Positive
bundle is `org.harmonycontrib.audiohaptic`, requested permission only VIBRATE;
negative is `org.harmonycontrib.audiohapticdenied`, no requested permission. Both
are normal/hos_normal_app, empty ACL/restricted sets, actual guest-UDID signing
and actual BMS/token checks required. The source projects use the real SDK105
default profile, module `entry`, ability `EntryAbility`. No signer was added.

The challenge contains a fresh run nonce, random stereo48kHz/16bit WAVs and
real-format JSON. `expiry` audio is3000ms and its TIME event600–1100ms, permitting
natural expiry while audio continues. `stop` audio is6000ms with TIME4000ms,
permitting a real early stop. Independent random phase chips differ per channel
and case. These are test inputs, not fabricated output. Root must read back
private staged inputs and match their original SHA before accepting output.

The public page is `batch_media_audio_haptic_probe.ets`. UI IDs:
`audio_haptic_run`, `audio_haptic_status`. Root publishes a fresh owned0600
`filesDir/audio-haptic-request.json` then performs the real UITest click:

```text
schema_version:1, run_id:challenge nonce, boot_id:actual UUID,
operation_id:fresh32lowerhex, action, case_id:expiry|stop,
mute_audio:bool, mute_haptics:bool, fast:bool
actions: init | start | snapshot | stop | release | start-after-release
```

Init reads only `filesDir/RUN-CASE.wav` and `RUN-CASE.json`, uses the actual public
manager/latency/stream-usage/createPlayer APIs and subscribes real EOS/interrupt.
Start/stop/release/unregister results and BusinessError fields are recorded
without substituting expected results. Source objects remain owned for cleanup
if creation fails. A released real object is retained for the explicit negative
start; a subsequent init may create a new generation. Callback generations are
captured separately, overflow is explicit, old/late callbacks are not relabeled
as a new player. No guessed state/first-frame callback is exposed.

Raw `filesDir/audio-haptic-RUN.jsonl` rows contain schema/run/boot/operation/
sequence/UID, actual ACTIVE-uptime before/after ns, API/event, raw value JSON and
original error fields. `systemDateTime.getUptime(ACTIVE,true)` is actual SDK105
line294; unsafe numeric precision fails. Callback handlers store at most128
records in memory; the control thread writes snapshots, with overflow and real
eventType/forceType/hintType/timestamp/generation. Root must independently bind
UID/token/installed HAP, source/SDK/signature and actual VIBRATE grant. Self-token
rows alone are not independent identity proof.

The new passive product helper is `batch_media_audio_haptic_hdi_observer.cpp`:

```text
batch_media_audio_haptic_hdi_observer RUN DURATION_MS PERIOD_MS
RUN=32lowerhex, duration=100..60000ms, period=5..100ms and less than duration
```

It only gets the actual HDI proxy, GetHapticCapacity and IsVibratorRunning for
device0/vibrator0. It never calls Start/Stop/Cancel/EnableCompositeEffect, including
on exit. It reads actual boot_id and brackets each IPC with CLOCK_MONOTONIC.
RPC failure reports null, nonzero result/exit and no fabricated idle state.
Clock failure is fatal, without fallback. Output is complete newline JSONL
begin/sample/complete with run/boot/sequence/clock brackets. Root must build it
using the actual product HDI2.0 proxy/libutils/system-libc++ ABI and preserve
compiler/header/ELF/DSO/CFI/source/current-image provenance. The old mutating
`probes/vibrator_hdi.cpp` must not run concurrently: it creates effects and its
destructor stops them.

## Concrete same-guest acceptance design

1. Bind a single fresh unchanged acceptance archive/boot. Independently verify
   both real HAP source/SDK/signature/profile/installed bytes/BMS identities and
   normal VIBRATE grant/denial. Bind current product DSOs and passive observer.
   Save actual DSP parameter and TIME capacity; establish idle before playback.
2. Start the passive observer and fresh QMP wavcapture before the real HAP call.
   Root proved local QEMU11.0.3 syntax only: `wavcapture ABS_PATH ohos_audio 48000
   16 2`, `info capture`, `stopcapture INDEX`. Retain actual commands/errors,
   active capture index, current owned QMP socket, nonce path, before/after boot
   and nonempty real PCM. Do not change the product `-audiodev none` or pause the
   acceptance guest. Root's empty44-byte smoke WAV proves no guest playback.
3. For normal both-enabled expiry, correlate actual WAV samples/channels with
   the original independent challenge; silence, another case, constant tone,
   channel collapse, old bytes or absent frames fail. Require one actual TIME
   episode of the specified duration, independent expiry before audio EOS,
   actual EOS callback and idle afterward. Repeat with the distinct stop case;
   stop only after actual fresh audio and TIME activity, then require cessation
   in the declared measured bounds and no replay from the previous resource.
4. Audio-only must retain actual PCM with no TIME episode; haptic-only must have
   the actual TIME episode and no corresponding audio waveform. Unmuted/negative
   no-VIBRATE caller must preserve actual201 if applicable, never convert a
   failed create/start into output. Test release→actual invalid start, resource
   unregister/recreate, final idle and cleanup of only owned inputs/apps/capture.
5. For real synchronization, bind the native first-frame/latency event to the
   same actual owner PID/stream and a verified MONOTONIC mapping; corroborate
   actual output with nonce-WAV correlation. Alternatively provide a measured
   QEMU sample-clock mapping with a real write-buffer/error bound. Capture-start
   time, file growth, source duration and start-promise completion are not audio
   onset timestamps. Without that anchor, report playback/TIME behavior only,
   and leave synchronization unverified.
6. Double-UID renderer focus is a separate required composition. Owner uses the
   long unmuted case; contender plays independent fresh audio with haptics muted,
   so it cannot manufacture HDI activity. Before contender Start, prove owner
   still emits new real PCM and TIME activity after the second app's UI setup.
   A legal normal audioPlayback continuous task/notification may be needed;
   use actual KEEP_BACKGROUND_RUNNING definition and source-bound notification
   UI, rather than reusing audioRecording or adding system APL. Bind actual
   policy-selected eventType/forceType/hintType, contender actual start and
   owner cessation/restart/cleanup. The initial foreground page does not yet
   implement this background/focus coordinator; that boundary remains pending.

`parse_hdi` / `time_episodes` / `alignment_bounds` use conservative intervals.
An edge is `[previous.before_ns,current.after_ns]`; using previous.after or
current.before incorrectly tightens an IPC observation. Duration and audio-
haptic difference are intervals, including both uncertainties. Any eventual
tolerance must contain the full difference interval and have a bounded measured
uncertainty; a mere intersection or wider uncertainty cannot create a pass.
`parse_hap` checks raw framing/identity/clocks/callback overflow, not real output.
Neither parser emits a full runtime pass or closes the ledger.

## Failures and potential source ownership

If actual public normal playback still fails, the exact candidate locations are
the exported audio_haptic player/sound/vibrator TUs and miscdevice matcher/thread
above, plus root-owned audio render/HDI routes. Distinguish native sound Start
failure, missing SUPPORT_VIBRATOR branch, decode/preload failure, unsupported DSP
selection, missing TIME mode selection and asynchronous haptic-start failure by
actual error/raw output. The supplied export proves that the TIME branch exists,
not that service capability selection reached it. No product change is proposed
solely because physical or HD waveform output is absent.

Actual SDK compilation, native compilation/linking, signing, QMP/guest commands,
output timing anchor, dual-UID background/focus driver and complete new-package
acceptance remain root work. No SDK/native compilation, Docker, live source/out,
VM, signing or host-emulated haptic output was executed in this batch.

## Retained light host check

`host-evidence.json` preserves the exact Python discovery command, locale, elapsed
time, exit0, four candidate/test source SHA values, actual SDK metadata SHA and
the four original root source/GN/QEMU receipt SHA values. `host-tests.log` records
14 tests passing in0.938s (outer subprocess1.0406s), without skipped tests.
The SDK105/default profile and all16 actual exported files were read during the
source-project preparation test. The generated projects and passive C++ helper
were not compiled, signed or run. These parser/data/source checks are not a
representative-package gate and do not change any requirement's closure state.
