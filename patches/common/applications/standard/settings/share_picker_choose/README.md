# Legacy native select dialog candidate

This component adds a private `PickerDialog` UIAbility to the existing Settings
phone/default module and a native dialogSession bridge. It preserves all existing
Settings abilities, permissions, modal share extension, wallpaper UI and pages.
It is a source/host candidate only; no SDK/native build, active source
application, package, guest execution or finding closure was performed here.

The round375 successor uses the complete CURRENT Share lifetime plus Wallpaper
source vector. `historical-v1.json` and `tests/predecessor-v1.json` preserve the
old candidate verbatim; its old modal hashes are not accepted as the current
predecessor. The original two patches remain unchanged. The third patch is an
exact successor to their full native postimage.

The fixed native `ACTION_CHOOSE` constant is **`ohos.want.action.select`**. The
deprecated SDK `ACTION_CHOOSE = ohos.want.action.choose` is a different value and
is not intercepted by this revision's `ShowPickerDialog`. This component does
not fabricate a handler or silently rewrite that deprecated action into select,
sendData or viewData. The existing modal `startAbilityByType('share', ...)`
implementation remains separate and unchanged.

Previously, ShowPickerDialog cleared the action and inserted an unconsumed remote
token into the Want. Its StartAbility(want,-1,userId) call actually bound userId=-1
and requestCode=the original userId, because that overload takes userId before
requestCode. It discarded the real original requestCode. The new native bridge
keeps the actual original Want, native caller token and original requestCode in
AMS. Its matching convention is the actual legacy URI/type/entities with the
outer select action cleared. It obtains real enabled/exported UIAbility handlers
from BundleManager, excludes private targets and clones, and bounds the snapshot.
After an explicit user choice it checks both the original snapshot and a fresh
query of the original Want before committing the exact component.

The UI receives only a server-created session ID. After native token/self-call
checks, AMS AttachAbilityThread binds the actual UIAbility token and IPC PID
before the UI can run onCreate. getDialogSessionInfo verifies that existing
binding before page loading. Session access requires the BMS-resolved system
provider UID/access token, attached IPC PID and live owned UIAbility token. Caller-provided IDs cannot create a native
session. The private UI declares exported=false and has no action skill. Actual rejection
of an ordinary app's direct explicit launch remains a required guest negative. Only a committed, authenticated session can supply
caller information to native StartAbilityAsCaller; arbitrary Want parameters
cannot claim that identity. See the handoff for the required source/private-start
chain and the still mandatory ordinary-caller guest positive test.

No original URI, remote token, requestCode, flags, entities or caller identity is
accepted back from the UI. AMS reconstructs the target from its stored original
Want. URI flags remain those supplied by the real original caller and are checked
by the existing permission/grant path. Settings neither opens/copies the content
nor grants it with Settings' token. A file being listed or a target being started
does not prove that the target consumed that file; owner/foreign URI access and
READ/WRITE boundaries must be observed independently in a newly packaged image.

Before selection commits, Cancel, verified UI close, original-caller/provider
death and the native ten-minute idle deadline remove the session once. An
outstanding result uses the stored native requestCode and the original caller's
`SendResultByBackToCaller`, with resultCode=-1 and an empty Want. A normal
startAbility call has requestCode=-1 and receives no invented result. After
selection commits, the existing native StartAbilityAsCallerDetails uses the
original caller token/requestCode. The actual chosen ability supplies its own
result. Picker launch success is never reported as that ability's returned
result. Start failure cancels the outstanding original result and returns the
actual native error to the UI. Picker termination uses `terminateSelf`, with no
fabricated `terminateSelfWithResult` delivery to the original caller.

The native owner map is capped at 64 sessions and handler snapshots at 512.
Each session owns/cancels its own TaskHandle and original caller scheduler death
recipient. The recipient holds only the session ID and is detached on every
terminal path. Cancellation can win during target
revalidation; commitment is the linearization point after which an accepted
launch is not raced with a false cancellation. Subsequent UI-close retries never
dispatch the selection twice. Each standard UIAbility instance owns its own
controller and LocalStorage. Destruction immediately invalidates late JS work.
An untrusted new Want cannot replace an existing controller's native session.

`apply.sh --source-root ROOT` requires the two pinned Git project revisions and
the complete current Share lifetime and Wallpaper predecessor plus exact native
API headers. Both projects must be entirely before or entirely after
this component. Unknown bytes, mixed states, missing dependencies, source/project
symlinks and unexpected patch/payload bytes fail. The installer prepares three
patches and three new ETS files in private scratch, checks every final hash,
then publishes files atomically with original modes. An installation failure
restores changed originals and removes new files; failed rollback retains the
original bytes and recovery manifest and reports its path. Complete replay is
idempotent and does not reapply any earlier Settings/framework patch.

Root owns component order, exact predecessor/successor guards, the two
`const.system.sharePicker.*` parameter values, official SDK/system signature,
the two existing native compilation units and the fresh normal-caller runtime
acceptance. Apply only after the currently running representative attempt has
completed and its evidence has been preserved. The new root parameters should
resolve `com.ohos.settings / PickerDialog`; this component changes neither system
configuration nor the original Settings bundle/profile.

## Request-scoped private startup

The actual fixed `SupportSystemAbilityPermission` header excludes foundation UID
5523. `IN_PROCESS_CALL` alone therefore does not establish private PAGE startup.
The third patch admits only a synchronous AMS-owned request, without changing
that whitelist or exporting the private ability. A stack RAII object holds the
original native `AbilityRequest` and opaque session ID in thread-local storage.
It requires the actual self PID/UID/token and native process token named
`foundation`. Reentry is refused; every scope exit restores the previous pointer.

The dialog manager checks the complete stored caller token/request code/user/
access token against the still-live original ability. It checks the exact
BMS-resolved provider bundle/module/name/UID/token, PAGE/private/system/enabled
state and target user. Only an unbound, uncommitted, unexpired, not-busy session
can consume admission once. UI attachment also requires that admission. No
external Want flag, known SID, same UID alone, direct explicit launch, or another
thread can create the stack capability. Ordinary permission checks and the
original caller's target/URI/result/cancel/death/deadline paths remain in place.

The ordinary native start wrapper passes its validated requested user explicitly
through the PAGE permission helpers. At that point the real producer has not yet
assigned `AbilityRequest.userId`; it remains -1. Admission compares the explicit
native user to the stored original caller and session, rather than mistaking that
unset field or a singleton provider's account UID for the requested user. Other
entry paths retain a default -1 and cannot consume this admission.

This is not native concurrency or packaged permission proof. Root must compile
the real TUs/CFI, SDK-build the actual Settings HAP and challenge normal caller,
forged SID/caller/provider/user, direct private launch, reentry, result and URI
boundaries on the first newly packaged guest before declaring it working.

The installer captures every target/dependency's bytes, mode and inode/link/parent
identity, rechecks all of them before each publication and restores only files
it actually wrote and still owns. External changes remain intact and conflicts
retain a recovery manifest. Complete current replay is a no-op; partial, old
modal, unknown source, symlink and hardlink states fail. Component scratch uses
an explicit Git discovery ceiling, so a TMPDIR inside a repository cannot make
`git apply` silently filter upstream paths.

Root has added complete-vector successor checks to the Share and Wallpaper
guards. The review-only `batch_apps_select375_guard_plan.py` emits the remaining
external-input guard delta. It never edits shared guards. The external-input guard must
still verify its unique ETS files after recognizing the complete successor.
Root also owns build invocation, system parameter values and the exact compiled
private-ability/image check. Until those land this component is not activated.
