# Native select picker source candidate

The current batch addresses part of
`behavior:ability-share-picker-system-provider-missing`. It does not close that
finding. No active OpenHarmony source/out, Docker, SDK compiler, product compiler,
GN/Ninja, HDC or VM was accessed by this agent. Source evidence came from the
frozen actual Settings SDK06 project and narrow host exports made by root.
Formal fullbuild02 was not changed by this candidate. Root reported that attempt
finished exit1 after 2114.37s at the unrelated Mesa script mode failure, before
any new package or guest existed. This candidate belongs to the next batch.

The actual AMS source constant named ACTION_CHOOSE is
`ohos.want.action.select` (fixed source line 363). Its three ordinary start
branches call ShowPickerDialog at lines 1521, 1956 and 2337. The SDK's deprecated
`ohos.want.action.choose` literal is not that route. Before this candidate,
ShowPickerDialog at 12367–12379 cleared the action, inserted
`ohos.ability.params.token` and called StartAbility(newWant,-1,userId). The real
overload at AMS.cpp:702 and header:190–192 takes (want,userId,requestCode,token),
so this actually passed userId=-1 and requestCode=the original userId. The early
description of requestCode=-1 was incorrect and is corrected here. The original
requestCode was still lost. The candidate calls StartAbility(dialog,userId,-1)
for the private UI while storing the actual caller requestCode separately. The
UIAbility context's native StartAbilityAsCaller at 210–218 and 244–254 passes
nullptr as the source token. The original remote token therefore cannot be
assumed to establish delegation. UpdateAsCallerInfoFromDialog at 263–300 uses
DialogSessionManager, which supplies the legal existing route reused here.

The candidate's nine precise upstream targets and complete original/final hashes
are in `manifest.json` and `result.json`. Four native targets modify the existing
ability_manager_service.cpp and dialog_session_manager.cpp units and their
headers; no new GN source/ABI entry is introduced. The five Settings targets are
module.json5, main_pages.json and three new ChoosePicker ETS files. The existing
SharePicker Controller/Extension/Page keep their exact original final hashes.

Before any IN_PROCESS_CALL, Show requires an existing live UIAbility token,
correct native user and IsAppSelfCalled(caller) access-token match. The existing
VerificationAllToken function alone only establishes that a token is known; it
is not evidence that this IPC caller owns it. SA/other-app delegation is outside
this bounded candidate's accepted input.

The server stores the flat original Want rather than inventing a nested-Want
protocol. It clears only the native select action and private/reserved session
authority before rebuilding real caller information from the verified native
token. URI, MIME, entities, flags and ordinary application parameters remain in
the stored Want. A fresh BundleManager QueryAbilityInfos of that original Want
must still contain the selected visible/enabled component. The UI can send only
bundle/module/ability identity; the server constructs an empty selection Want
and supplies the stored full payload to the existing native startup chain.
All native session access is bound to the configured provider's actual BMS UID,
access token and attached IPC PID. A known session ID alone is insufficient.
AMS token/self-call validation precedes AttachAbilityThread binding of the actual
native provider record, UID/token/PID and UIAbility token. JS does not establish
that binding. Getter verifies the live owned window; cleanup closes only that
stored token, rechecking SID/provider identity. The original caller's real
scheduler has a per-session death recipient; it retains only SID and unregisters
only itself. A death during creation cannot leave a late-added recipient behind.
The IPC API identifies a trusted Settings process and opaque session; it does not
claim to isolate malicious code already running inside the same OS application.

The provider is a private standard UIAbility with no action skill or extra
permissions. This identity design must be challenged in a real ordinary-caller
positive and forged-session negative test; host doubles are not that proof.

Cancel/close/death/deadline use the real original caller scheduler result entry
and the original native requestCode, never a caller-provided number. Cancellation
returns resultCode=-1; a requestCode=-1 normal start receives no result. A chosen
target receives the original requestCode, and only the target's eventual actual
result satisfies the caller's startAbilityForResult result. `accepted=true` in
the private controller means only that the native target start returned success.
It does not assert file access, content consumption or result delivery.

Private-provider startup is a mandatory integration check. The candidate retains
the pre-existing ShowPickerDialog IN_PROCESS_CALL(StartAbility(...)) boundary;
it does not add a generic permission or an arbitrary ResetCallingIdentity call.
The actual macro and permission-check callers are retained with SHA/line ranges
in private-start-chain.json. One exact conditional remains unresolved: the body
of SupportSystemAbilityPermission::IsSupportSaCallPermission and its production
header were requested as a narrow sixth host export, which was not available
at handoff. Both IsCallFromBackground and JudgeInvisibleAndBackground depend on
it. The native TOKEN_NATIVE/static-permission evidence alone does not prove that
this helper admits AMS's own identity. Do not mark private startup source proof
complete, change export policy or invent a permission bypass to cover that gap.
Root must inspect those exact production bytes and pin the accepted dependency
before integration, followed by the real normal-caller positive/negative. Independently of source reasoning, root must exercise a real normal
non-system caller using select and observe the private Settings provider, actual
target and original result/cancel callbacks in the fresh image. Do not accept an
explicit shell start of PickerDialog or a successful modal share test as that
positive test.

Root integration requests:

- Apply the new component after the complete existing Settings share_picker and
  wallpaper_settings SDK06 state. The custom installer requires both fixed Git
  revisions. It is transactional across all nine files, refuses unknown/partial
  source and retains a recovery copy if rollback itself fails.
- Teach the old Settings exact guards to recognize only this complete successor:
  new module/page hashes, all three new ETS hashes, all four native final hashes
  and all exact predecessor/API/permission-chain dependencies in manifest.json. A changed module alone must
  not authorize a skip or replay of older overlapping patches.
- Configure the existing const.system.sharePicker.bundleName as
  com.ohos.settings and const.system.sharePicker.abilityName as PickerDialog.
  Keep the original Settings identity/profile/signing and existing permissions.
- Batch the official actual product SDK build and the two existing complete
  native TUs, with real headers/CFI/link/source-to-image binding, after the
  currently running representative attempt finishes. No diagnostic/old HAP can
  stand in for this candidate's changed module and new ETS.
- Fresh ordinary caller tests must cover select with URI/type/entities/flags,
  true current-handler enumeration/revalidation, original target result with
  distinct non-default resultCode/data, Cancel/Back, requestCode=-1 normal start,
  malformed/foreign/owner URI and READ/WRITE boundaries, forged/foreign/expired
  session IDs, direct private-provider start rejection, target disable/removal,
  process/window exit, reentrant choices and the real idle deadline.

Remaining scope: the deprecated choose literal, cloned/remote/SA-without-UI-token
requests and newer request-start callbacks are not newly claimed by this batch.
Existing modal share, sendData receiver behavior, HMS/Bluetooth backends, other
device profiles and all fresh-runtime evidence remain independently unclosed.

Final host validation: 18 methods PASS in 5.674s (process 5.767s), including 22
actual-controller and five actual-ability scenarios. host-final-03.json pins
every tested installer/patch/payload/fixture/test SHA and complete raw logs;
host-final-01/02 and validation-history preserve earlier results and limitations.
The final rerun verifies that blank unified-diff context-line normalization still
reconstructs every exact original/final source hash with actual git apply.
Only the simple native owner expression was executed with unchanged operators
in a host JS harness. Native concurrency, native IPC identity/permissions, actual
SDK/HAP compilation and fresh guest behavior have not been executed here.
