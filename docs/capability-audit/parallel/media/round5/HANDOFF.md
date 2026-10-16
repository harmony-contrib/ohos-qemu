# Media round 5 handoff

Base caeaf60ba125eb06cdece16735aa89886003cf8e. All 7 requirements remain open.
No Docker, product build, QEMU, HDC or package was started. Cumulative actual
upstream ownership remains the same 25 files in result.json.

## Public SDK and background recording

Official installed API26 compiler/sysroot compiled and linked Recorder and audio
events for aarch64, armv7a and x86_64, with -Wall -Wextra -Werror and
-Wl,--no-undefined. ELF machine, actual expected public DT_NEEDED libraries and
exported C entrypoints were checked. native-sdk-01.json records all six original
successes. A final cancellation-boundary change affected only audio_event;
native-sdk-02-audio-event.json records its final three successes. Recorder source
hashes are unchanged. Full frozen sources, libraries, command logs, dynamic
sections, imports and exports are preserved under /tmp/media-audio-review/
r5-sdk-01 and r5-sdk-02-audio-event; committed JSON binds each output and source
hash. These are actual public SDK links, not full product or runtime acceptance.

The actual ETS AudioRecordingSession helper is compiled against official API26
SDK types in test_batch_media_audio_background.py. It uses the public
@ohos.wantAgent module consistent with the background API, and the real
ContinuousTaskSuspendInfo.continuousTaskId/suspendState fields. Original type
errors/warnings are preserved in background-sdk-types-01..04.log; types-05 and
background-host-02 show successful checks. Full UI ArkTS/HAP build remains root's
gate. The five helper lifecycle scenarios use controlled SDK services; they are
not real task/notification/MIC permission proof.

Root builder changes required for both distinct ordinary focus bundles:

- Request normal ohos.permission.KEEP_BACKGROUND_RUNNING; retain the normal
  signer with ACL[], ordinary APL, actual unique UIDs and MIC user grant. Root
  verified actual IsAclSatisfied: equal normal APL/availableLevel requires no
  extra ACL/profile exception. Independently query the real installed grant.
  The permission is system_grant/normal/NORMAL, provisionEnable=true, since8;
  no privileged SYSTEM or SPECIAL_SCENARIO permission is needed.
- Set EntryAbility backgroundModes to ["audioRecording"]. Preserve actual
  normal UIAbility Context; the WantAgent targets that context's actual bundle,
  ability and module. No APL elevation, system identity, foreground override or
  special-scenario RequestAuthFromUser is used.
- Extend libbatchmediaaudioevent.so's real declaration with
  run(runId:string,mode:number):boolean, status(runId:string):number and
  abort(runId:string):boolean. status is -1 for unknown,0 for actual active
  worker,1 for finished native return0,2 for finished failure. status0 alone
  does not assert stream RUNNING. abort only requests cancellation of the actual
  active matching run and never claims Release succeeded.
- Tap the real "Start audio audit" button after the page is displayed. Await
  the actual MIC dialog. If notifications are disabled, the public
  requestEnableNotification(Context) dialog must also be answered by the real
  permission controller/user; disabled/denied remains failure. This additional
  real notification consent and actual normal install grant must be verified.

Modes1/2 request a real public audioRecording task only after their actual native
private ready record has stateResult0/RUNNING, positive real frames and copied
PCM bytes. Mode0 revocation remains foreground and requests no background task.
The task's actual returned notification/task id, notification authorization,
cancel/suspend and cleanup results are separate private sequence files named
`audio-event-RUN-modeN-background-000.json`,001,... . Every file write is checked
and fsynced; missing/error evidence cannot pass. Native completion/abort is
polled; actual task stop and each unsubscribe are attempted even if disk writes
fail. Unexpected cancellation or suspend(true) aborts the matching run and is a
failure. Resume notifications and other task ids do not abort it. A 60s guard
records an actually still-running worker; it does not manufacture resource release.

Mode2 now starts a genuine public MIC primer while awaiting contender_start.
It produces its own real callbacks,50 native state/frame/timestamp observations,
`audio-event-RUN-mode2-primer.pcm` checkpoint and `-primer-full.pcm`, then actually
Stop/Release/Destroy after fresh nonce ACK before creating VOICE_COMMUNICATION.
MIC->MIC sharing is the fixed policy; no idle/fake recording task is used.
Primer step/chunk/callback/PCM event types are separately prefixed event_primer_.
The media-owned diagnostic requires their full lifecycle, fresh challenge PCM,
checkpoint-prefix consistency,48k timestamp rate and absence of forced STOP/error;
silence, stopped/counter-only/missing primer fixtures fail. It closes 0 IDs.

Root runner must wait for each actual background_started record and independently
verify its real BGT service task/notification/ordinary token before changing apps.
Keep the current fresh nonce/0600 app-owned ACK protocol (15s timeout). After the
second app is granted/ready, verify owner's latest await_action snapshots remain
RUNNING with advancing frames and fresh challenge PCM before contender_start ACK.
A previous baseline checkpoint or accepted background-task request alone is
insufficient. Bind owner forced STOP to contender's actual VOIP Start interval;
an earlier dialog/background stop must fail. Preserve native task-cancel/error
artifacts if policy suspends a legitimate task. Foreground restoration before
owner resume, if required by the actual service, remains root's real UI action;
a task cancellation or background Start failure is not a successful focus test.
No two-app background behavior has yet been runtime validated.

## Known component integration failures

Recorder apply.sh now transparently forwards the standard --source-root PATH
[--product PRODUCT] [--require-patched] CLI. Regression applies an actual pinned
full TU, verifies idempotence and require-patched, and preserves unknown edits.
The upstream Recorder payload is unchanged.

Knowledge photoaccesshelpernative now directly declares
relational_store:rdb_data_share_adapter for media_asset_rdbstore.h's rdb_utils.h.
The fixed target exports interfaces/inner_api/rdb_data_share_adapter/include via
rdb_data_share_adapter_public_config. No permission checks or header guards were
removed. Holiday medialibrary_data_extension already declares
openssl:libcrypto_shared in this and the previous batch. Its actual fixed
crypto_config_public exports third_party/openssl/include and generated/include;
OpenSSL SHA256 is a real linked dependency. The diagnostic based on old service
flags omitted that newly declared export. Regenerate/derive both new dependencies
from actual GN exports; do not guess include paths or treat the older flag
command as fresh GN proof. gn-dependencies.json records exact fixed source,
public-config facts and SHA hashes. Root's latest full platform batch still has
4 passes and these 2 header failures; actual retry/link is pending.

The thirteen-source exact installer accepts original Knowledge, complete e0d1137,
complete caeaf60 and current states. Full SHA manifests and both prior complete
states are recorded; mixed/unknown/symlink sources remain rejected. Current
round4-to-round5 upgrade and standard CLI pass. Real query/producer semantics and
all account/Visitor/three-role/revocation/calendar-asset runtime gates remain open.
AudioVivid still needs the actual external builder/algorithm; no metadata stub
or fake implementation was added. Screen capture/transcode/haptic remain open.
