# F media source-only batch

All changes are confined to the assigned F tree, base c14e803. MAIN, E, previous
executed private drivers and original runtime evidence are unchanged. No test,
syntax check, compiler, SDK, signing, Docker, native runtime, verifier replay or
guest operation was run by this agent. All guest/capability closure claims remain
false. delivery-f.json lists changed repository files and exact pre/post SHA256.

Authoritative actual E source is export14 exports.json SHA256
`fb7357c1823163f12e1eb5ce295b6e85777103bd411797bb92cb9117a0bf34ba`.
All 149 exported members were independently hash-read before editing. The
source causal facts below use that export, not a host mirror or old F09 source.

| Actual E failure | Source cause and F change |
| --- | --- |
| MIC 704 zero frames before revoke | HPAE ReadDataFromSource returns on empty read, then DoProcessMicInner pads an incomplete 256-frame history to 960. New ordinary-MIC real assembler waits for full frames and preserves actual short reads. |
| Real cable data availability/XRUN risk | QemuCapture performed a pre-read wait and implicitly recovered EPIPE/ESTRPIPE. Read now occurs first and real cable XRUN fails without recover/start. Other cards retain old recovery. |
| Normal Stop/Release waits about the remaining 3 seconds | StartVibrate held waitStartVibrateMutex_ across the blocking normal external pattern, preventing RetireNormalPlayback from admitting cancellation. Only normal mode unlocks around that external call; stopped state and worker join remain. |
| post-release-start reported fallback -1 | Actual NAPI CommonAsyncCallbackComp omitted Error.code. It now maps the actual native error to numeric 5400102/5400103/5400105/5400106 using existing local constants; no new media-client DSO dependency. |
| denied-create returned a player | Actual NAPI createPlayer omitted its SDK-declared VIBRATE check. It now rejects 201 from the real token query before creation/preload. |
| bad-file branches used normal resources | project.phases nested add() intercepted `audio`/`haptic` as observation-mode formals. Explicit resources now populate options while preserving actual negative paths and failed-create/rebuild cases. |
| queued normal callback can outlive Stop/rearm | The real backend Session now survives the native worker through an optional private publication sink and the actual NAPI task. Native fallback remains one callback. Retirement is checked at task admission. |

Source locations are in the review diffs and exact payloads:

- capture_loopback/files/alsa_snd_capture.c: CapturePcmReadi, CaptureReadImpl.
- capturer_frame_assembly/files/hpae_source_input_node.cpp: DoProcess,
  ProcessAssembledMic and lifecycle invalidation; new real assembler header.
- audio_haptic_lifecycle/0003: StartVibrate, PlaybackCreated, Start,
  HandlePlaybackEndOfStream/Interrupt; private publication/session headers.
- audio_haptic_public_errors/files: common PromiseReject/permission helper,
  manager CreatePlayer, player CommonAsyncCallbackComp/Constructor,
  complete callback NAPI queue and actual task execution.

Installation and product integration requirements:

1. capture_loopback accepts exact full six-file E state `e`, plus historical full
   before/previous, and complete after. New frame_assembly installs exact E CPP/H
   plus absent new header. Their source members do not overlap.
2. lifecycle accepts historical complete vectors and preserved `incarnation_e`,
   upgrades six whole files including the new publication header, and rejects
   every mixed state. Canonical name remains incarnation. Original historical
   provenance is retained; new E-to-F review delta is 0003.
3. Install lifecycle then public_errors. Both component states are mandatory
   together. public_errors owns six distinct NAPI source/header files.
4. Root must add both new component apply/verify calls to its existing build
   integration, and require their final states. No global installer/recipe was
   edited here. Rebuild actual hpae node and dependents, native audio_haptic,
   audiohaptic_napi and lower ALSA capture DSO. Preserve official GN headers,
   CFI/LTO, security flags and -fno-rtti. No new public header/vtable or GN deps.

The actual E OutputPort default publication only updates a local vector and
does not call a consumer. Assembly holds only its private queue mutex over
conversion/publication; HDI is outside it. Manager graph lifecycle is serialized
on its process thread. A leased read is rejected after invalidation, so cached
bytes and delayed appends cannot cross Stop/Flush/Reset/reopen. EC/MICREF methods
and legacy non-Qemu recovery are retained. An XRUN is an actual error and must
stay visible to the runtime acceptance; no recovery/padding/clock replacement
is used to obtain success.

Root batch checks proposed (not executed here):

```sh
OHOS_QA_CC=/absolute/host/cc OHOS_QA_CXX=/absolute/host/cxx \
python3 -B -m unittest discover -s ci/capability-audit -p 'test_batch_media_alsa_capture.py'
OHOS_QA_CXX=/absolute/host/cxx python3 -B ci/capability-audit/test_batch_media_capturer_frame_assembly.py
python3 -B ci/capability-audit/test_batch_media_audio_haptic_lifecycle.py
OHOS_QA_CXX=/absolute/host/cxx python3 -B ci/capability-audit/test_batch_media_audio_haptic_fixes.py
python3 -B ci/capability-audit/batch_media_audio_haptic_reviewfix_checks.py
python3 -B ci/capability-audit/batch_media_audio_haptic_generation_native.py \
  --compiler /absolute/host/cxx --work-root /absolute/owned/evidence --sanitize address,undefined
```

Existing capturer_read_lifecycle, policy and media-integrity regressions should
also run with the batch. Sanitizers remain enabled. The native runner compiles
the complete actual normal/player CPPs and actual class headers, checks the
fresh-IDLE Reset counterexample, retained source FD after close/unlink,
Stop/Start/retry/loop/error/worker generations, concurrent time snapshots and
new blocked-pattern cancellation. Its controlled transport sink retains the
real backend-generated Session and checks both delayed delivery and exclusive
legacy/sink dispatch. The NAPI test separately executes the actual full callback
CPP with external transport controlled. These complement actual target object,
full DSO ABI/CFI, SDK and new-package runtime gates; none substitutes for them.

HILOG diagnostic contract (no journal fields added):

- prefix AHPublication; `stage=napi-bind` records actual `wrapper`, concrete
  `player` and `callback` addresses. The actual factory always constructs
  AudioHapticPlayerImpl, proving the static cast.
- native `stage=created|start-confirmed|native-sink`, scope=normal records actual
  player, captured Session address and `backend` address retained immutably at
  actual backend construction. Native sink also names EndOfStream/Interrupt.
- NAPI `stage=queue-attempt|enqueue|enqueue-failed|task-admitted|task-dropped`, event=eos|interrupt records
  captured callback/Session/backend, `end_observed`, `confirmed`, loop and
  accepted. `end_observed` is a diagnostic atomic read after the admission test,
  not a second acceptance oracle; concurrent retirement may advance it.
- scope=legacy-fast-unidentified means no source Session is available. Its
  missing identity cannot satisfy normal coverage.
- End enum values: LIVE0, STOPPED1, RELEASED2, REPLACED3, PREPARE_FAILED4,
  START_FAILED5, ERROR6, ENDED7, INTERRUPTED8. Enqueue means actual napi_send_event returned napi_ok; queue-attempt alone does
  not establish that. A task may execute before the enqueue-success log; source
  snapshots keep diagnostics safe without reading a destroyed task context.
  Backend identity is diagnostic only,
  never used to admit an event in place of its strong captured Session.

Pending events strongly retain Session, so its object address cannot be reused
while they remain pending. The backend itself is weakly held by Session and its
address may be reused sooner; never use backend address alone as a unique key.
Session addresses may be reused after complete destruction.
Boot/PID, actual operation intervals and native-bind records are still required;
the existing JS API exposes no exact native identity-to-player_epoch join. Do
not infer that join from matching ordinals. The final guard linearizes admission
at its atomic retirement read; public JS callbacks run outside internal locks,
so a simultaneous Stop after admission is not claimed to be atomically excluded.
Fast/legacy generation and every already-admitted native error race remain gaps.

Runtime/verifier guidance to root: keep actual bad paths and numeric errors,
including denied-create201 and post-release5400102. Loop EOS is a legitimate
period event while the same backend stays LIVE; it must not alone imply quiet
PCM/VDI before an explicit Stop. Nonloop EOS remains ENDED and later Start uses
a distinct backend. Do not skip the retained PCM, independent output decoder,
clock, VDI, callback or cleanup checks after repairing the shared footer parser.
Continuous QMP whole-clock observations and MIC producer protocol repairs stay
root-owned. New representative behavior remains unverified.
