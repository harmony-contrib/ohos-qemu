Unexecuted source candidate, original ID `behavior:accessibility-caption-provider-missing`.
No parser, syntax checks, host tests/ASR, SDK/build, signing, Docker, QEMU, HDC,
QMP, downloads of binary/model/audio, resource starts or cleanup were executed by
this author. Hashing/copying/diffs below describe source bytes, never acceptance.

The canonical new sources are candidate/ci/capability-audit/livecaptions579*.py,
its livecaptions579 fixture directory and livecaptions579_provider product tree.
Existing source deltas are candidate/product and candidate/patches/lib. Exact
actual before/after bytes and repository HEADs are PRODUCT-STATES.json; existing
source preimages are before/product. FILES.json records the finite full delivery.
The root agent alone composes product guards/hooks, copies canonical files and
builds a new representative artifact. Do not apply old whole files over other
agents' work. Reject unknown/mixed source states; root's product component must
stage the complete reviewed vector in scratch before guarded atomic commit.

Product

- Register/preinstall the real OS endpoint com.ohos.vassistant /
  AiCaptionServiceExtAbility, SERVICE, system_basic / hos_system_app, OS signed.
  Exactly MANAGE_SETTINGS, SYSTEM_FLOAT_WINDOW, WRITE_ACCESSIBILITY_CONFIG; entry
  requires WRITE_ACCESSIBILITY_CONFIG. No INTERNET, MANAGE_AUDIO_CONFIG or static
  capture bypass permission. Actual definitions admit all three at system_basic.
- livecaptions579_provider_project.py is the explicit original caller-builder
  adapter: family livecaptions579_provider, case english, role provider, fresh
  run token, parameters={}. Root must overlay all returned sources, attach only
  product_assets() from livecaptions579_inputs.py BEFORE compile/sign, preserve
  actual build/sign/verify receipts, and include the resulting HAP in the image.
  The template's entry/build-profile.json5 registers the actual ThreadWorker.
- The GN entry is //applications/standard/hap:vassistant_livecaptions579, source
  applications/standard/hap/vassistant_livecaptions579.hap, install app/VAssistant,
  part prebuilt_hap, subsystem applications. The provided BUILD.gn is the finite
  entry body. Root adds its exact target to the selected actual HAP graph and
  existing product/preinstall selection using the original signer/preparer.
  A data-installed normal demo HAP is explicitly rejected at runtime.
- Actual captured 16k mono S16LE -> bounded private worker -> actual native VAD,
  OfflineRecognizer.decode/getResult -> visible English-only captions. No text
  in worker input, no injected PCM/API test RPC, no fixed transcript/fallback.
  One fixed Whisper tiny.en CPU profile, one thread. No SenseVoice dependency.
  User-visible title and Settings menu explicitly say English. Full original
  notices are an admitted raw asset and visible through the product license UI.
- Cancellation invalidates callbacks synchronously, releases native capturer,
  observes actual worker exit, destroys overlay, removes style listener, writes
  its own user state false and uses the separately integrated conditional-startId
  native SERVICE stop. Old callbacks cannot close a replacement generation.

Actual OS consent/security deltas

- AudioServer's int32 permission denial now returns ERR_PERMISSION_DENIED rather
  than false/zero. NAPI's real mapping then produces 201 for valid unprivileged
  report parameters. No permission policy override.
- The pending native stream binds real owner UID + own modern capture SID, one
  request at a time, deadline60s, atomic consumed grant, released/completing state,
  and actual held SystemUI connection. Release cancels and disconnects. Late,
  duplicate or expired reports cannot grant. Missing actual listener propagates
  failure. No native global mutex is held while waiting for a user choice.
- Client waits only in RequestUserPrivacyAuthority for60s, resets old notification
  before sending, handles real request/release failure and snapshots result under
  mutex. Other native operation deadlines are unchanged. This is not just a
  delay extension: UI expiry50s, release, stale grant and connection cancellation
  are part of the same source vector.
- SystemUI product/default/dialog gains a nonexported sys/commonUI extension and
  true visible Allow/Cancel UI, binding actual prepared playback SID/UID/source
  and BMS UID->bundle. Back, UI destruction, lost stream and50s expiry deny.
  Duplicate click/destruction is idempotent. Real AudioManager report is called;
  the source-local interface declares that actual exported NAPI method only.
- Existing START_SYSTEM_DIALOG host gets private cancel opcode3 scoped to the
  same real caller PID/token + SID/UID. Audio windows have distinct compound keys
  and guarded async window generations. Incoming synchronous user-report call
  does not synchronously RPC back to its blocked JS thread; its own content
  session closes after native reply. Provider release uses the real close RPC.
- SystemUI requestPermissions and desired signed ACL add only MANAGE_AUDIO_CONFIG
  and GET_BUNDLE_INFO_PRIVILEGED. Both actual permission definitions are
  system_grant/system_basic/provisionEnable=true. Original signed profile's
  exact five ACL guard remains; desired ACL7 is separate, original system_basic
  APL, signer and vendor policies remain. Root must integrate signer delta with
  the real SystemUI source preparation and verify the final installed profile.
- Settings nine-file finite delta exposes CAPTIONS_ASSISTANT, correct state/URI,
  actual registered UIExtensionContext.startAbility, English labels and a stable
  id on its two mutually exclusive real first-use confirmation button layouts.

Dependencies (root prepares actual bytes, not this child)

DEPENDENCIES.json freezes exact Whisper encoder/decoder/tokens, HAR, OHOS32 ORT,
VAD and official original LibriSpeech archive digests. Existing HAR has true
arm64-v8a/x86_64 only. Root is obtaining original Silero v4 object and requires
strict equality with fixed SIG LFS SHA+size; git LFS pointer text is never a model.
OpenAI v20250625 explicitly licenses code and weights MIT; retain that full notice
and k2 conversion/source notice plus actual runtime third-party notices. Silero
MIT, ORT MIT+ThirdPartyNotices and actual SDK libc++ notice must be present in the
complete user-visible notices asset. No SenseVoice model is selected/copied.

livecaptions579_native.py returns the finite official OHOS32 C API + real NAPI
recipe. Keep official TTS/diarization feature exports because the unchanged HAR
NAPI target references them. Use the exact official node-addon-api commit and
my-patch.diff once in a fresh private copy; supply its patched directory through
FetchContent source override, never reset a shared checkout. Root admits every
transitive source/download and license into its original dependency cache, then
records real commands/SDK/ELF/dependency/output receipts. Add real armeabi-v7a
abiFilter and four actual OHOS32 library bytes to the HAR; no ABI alias or GNU/
Android SO substitution. This is a source recipe, not a successful build or ABI
claim. Remaining five packages stay behind the first new package's full VM gate.

Prepare two different speakers from the pinned original OpenSLR12 test-clean
archive before recognition. Retain archive LICENSE.TXT plus full original
attribution, exact original FLAC/member hash, original transcript and selected
utterance ID, actual ffmpeg argv/exit/raw and mono16k S16LE WAV hash. Use no HF
unprovenance test_wavs, synthesized fixed transcript, host ASR, or output-derived
oracle. Fixture HAPs include both actual WAVs and both attribution/license assets.

Root runtime seam

- Explicit call: livecaptions579_runtime.run(root_io). Original OwnedIO only:
  existing held guest, shell/command real stdout/exit/footer receipts, original
  ui/QMP/frame, prepare_callers, register_cleanup. No new resource owner/process.
- package_inputs.livecaptions579 = {archive_sha256, language:'en',
  model:'whisper-tiny.en', abi, admission:Ref, provider_hap:Ref,
  libraries:{libsherpa_onnx.so:Ref, libsherpa-onnx-c-api.so:Ref,
             libonnxruntime.so:Ref, libc++_shared.so:Ref},
  speech:{a:{audio:Ref,license:Ref,groundtruth:Ref,utterance_id:'speaker-chapter-id',
             contains:[independent original transcript fragment length>=12]},
          b:{same, different speaker/audio}}}.
  Every Ref is an absolute real immutable {path,sha256} artifact. groundtruth is
  the unchanged original transcript text containing the exact utterance ID line;
  contains is independently chosen before ASR and must occur in that real line.
- Root original caller registry family livecaptions579, case end-to-end,
  roles control/media/private/ordinary, parameters={}; use its *_project adapter.
  prepare_callers returns existing actual {case,run_id,boot_id,callers:{role:row}}
  with each real project/unsigned/signed/profile/signing/build/sign/verify receipt,
  plus audio_fixtures={a:Ref,b:Ref} and license_fixtures={a:Ref,b:Ref}. Fixed
  asset_destinations maps a/b WAV and license_a/license_b raw-file paths. No JSON
  source selector. Control is system_basic with exactly READ/WRITE accessibility
  config; other three are normal with no permissions and independent real UIDs.
- Fresh new-image inactive provider required. Stage saves actual shortcut config,
  configures the true CAPTIONS_ASSISTANT target, drives genuine QMP physical volume
  chord -> actual first-use Settings UI when present -> AAMS -> actual provider.
  It restores original shortcut settings and removes only its four fixture HAPs.
- Seven fixed cases: provider start permission; native valid live-SID report201
  plus user Cancel; cancel pending through actual AAMS close; real Back denial;
  UI expiry denial; actual public speech A to visible independent groundtruth
  plus private speech B excluded while actual capture/worker progresses; abrupt
  provider death, true AAMS close recovery and new record/process/stream/session
  with public speech B recognized. Each independent failure remains in evidence;
  later cases run after actual recovery, and cleanup always runs. No skip flag.
- Runtime binds actual signed preinstalled HAP, native library bytes/ABI and live
  provider maps, complete UID process scanner, start ticks, genuine service record,
  actual per-PID fsynced raw fixture journal/inode/nonce/UID, native API callback,
  actual user UI hierarchy + framebuffer, model PCM/result counters, native AMS
  conditional-stop record decision and repeated process/capture/UI absence.
  Recognized text is not logged by product; actual visible UI is sampled only by
  authorized test evidence. Cleanup never kills audio_server/SystemUI to fake
  release. Abrupt death recovery uses real AAMS close Want, never writes provider
  key from fixture/shell. Any raw mismatch/failure is a real stage failure.
- Evidence output is root_io.output/evidence.json schema
  actual-livecaptions579-runtime/v1. Full commands, raw Refs, UI, fixture journals,
  process scans, native maps, all cases and cleanup remain on failure. Root joins
  the original Owner report/boot/package receipts as for other fixed stages.

Remaining acceptance limits

This batch has NOT built or run. Root must verify actual installed permission
profile, native Connect path (including START_SYSTEM_DIALOG service enforcement),
modern capture feature/policy/mixer, genuine runtime native loading and inference,
modal action/Back/expiry/cancel, memory/worker/UID/stream/window release and rebuilt
session behavior in the newly packaged representative image. The full SystemUI
controller still has its old general termination policy; these new-image cases
must expose any remaining concurrency/lifecycle issue rather than claiming this
source is a pass. Expiry case proves user-facing expiry plus actual client/native
result and cleanup; it does not claim a separate privileged direct malformed or
post-deadline IPC fixture was executed. English-only profile is the delivered
scope, never a claim of Chinese speech recognition.
