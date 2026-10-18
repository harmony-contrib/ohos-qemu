# AudioHaptic public NAPI boundaries

This six-file component uses actual E source export
`r58-E-postcycle-native-readonly-export-14-01/public-source/exports.json`, SHA256
`fb7357c1823163f12e1eb5ce295b6e85777103bd411797bb92cb9117a0bf34ba`.
It requires the coordinated F `audio_haptic_lifecycle` private Session/sink
contract, while public AudioHapticPlayer/AudioHapticPlayerCallback headers and
vtables remain unchanged. Existing GN include directories already contain the
native audio_haptic private directory and existing GN dependencies already
contain accesstoken/ipc. No RTTI, relaxed CFI or security compiler flags are used.

The actual E common async completion created Error(message) without a code
property. It now attaches the existing API numeric BusinessError code, retaining
the actual native failure. In particular MSERR_INVALID_OPERATION after Release
maps to 5400102. The common PromiseReject overload also attaches a numeric code.
The SDK105 public createPlayer contract declares VIBRATE and 201, but actual E
did not check it at this entry. This component queries the actual current token
through AccessTokenKit before queuing native creation/preload, including muted
players. It does not infer permission from the QA caller's arguments. Existing
system-only method checks remain separate and still return 202. Wrapper creation
failure also remains an error rather than resolving an undefined object.

Normal EOS/interrupt notifications retain the actual producer Session into each
NAPI event context. The queued task checks that captured Session at publication
admission, so events queued before Stop/Release/replacement cannot be relabeled
as the next playback. The native normal handler chooses either this private sink
or the existing public callback, never both. The actual factory unconditionally
constructs AudioHapticPlayerImpl for both latency modes, proving the NAPI concrete
static cast without RTTI. Fast/legacy callbacks use the original path and are
explicitly unidentified; their generation behavior is not closed by this change.
Normal loop EOS remains a legitimate per-period notification of the same live
backend. Errors admitted during prepare retain their original native delivery;
there is no new public JS error event or blanket error-generation claim.

HILOG diagnostics beginning `AHPublication` record the real wrapper/player/
callback association and the Session/backend object addresses captured at source
creation. The context strongly retains Session until the task finishes. These
are object identity diagnostics, not JS player_epoch ordinals or globally unique
IDs: addresses can be reused after all owners retire, and the existing JS API
does not expose a native identity join. See the lifecycle HANDOFF-F.md for the
exact fields and remaining attribution limits. No JS journal schema is changed.

The strict component installer accepts only the exact complete E six-file
preimage and new state, verifies project revision, stages complete payloads,
rejects mixed/foreign/symlink states and rolls back checked writes. Install
lifecycle first, then this component, and rebuild both native and NAPI DSOs.

```sh
bash patches/common/foundation/multimedia/player_framework/audio_haptic_public_errors/apply.sh \
  --source-root /absolute/ohos --product arm64_virt
python3 patches/common/foundation/multimedia/player_framework/audio_haptic_public_errors/verify_source.py \
  --source-root /absolute/ohos --require-patched
OHOS_QA_CXX=/absolute/host/compiler python3 -B ci/capability-audit/test_batch_media_audio_haptic_fixes.py
```

The host test executes the complete actual NAPI callback class/CPP and selected
actual common class methods against controlled external NAPI/AccessToken APIs.
It checks numeric rejection, permission denial, queue retirement and reentrant
callback-reference removal. Complete real native class tests separately prove
the backend-generated Session chain. These checks do not establish target NAPI
ABI/CFI, ordinary HAP permissions, actual callback timing, SDK, signing, PCM/VDI
or guest success. Root must execute those gates on the fresh representative.
