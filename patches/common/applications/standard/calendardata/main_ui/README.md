# CalendarData business UI and reminder successor

Patch 0003 extends the complete shared-storage reminder viewer with the retained
calendar browser and ordinary-event create/update/delete UI. The reminder Reader,
URI producer, native/editor sources and notification owner remain guarded by their
existing exact hashes. This is a source candidate until the combined new-package
runtime gate passes.

MainAbility keeps its own LocalStorage, route and revision. Empty routes open
browsing; reminder Wants open the original read-only details branch. Save/delete
require explicit user controls and the real WRITE permission request. Browsing
requests READ. The module adds MainAbility only to the existing in-use WRITE scene;
permission names, authority/proxy boundaries, profile identity/ACLs and signer stay
unchanged. A denied/cancelled/revoked permission or API error is visible. Submitted
provider writes can outlive UI destruction; the UI re-reads persisted data when
still active and never claims to undo a submitted operation.

The installer upgrades complete original, E-prefix and current F-prefix2 states to
one exact business final, pins the state manifest, rejects mixed/drift/symlink input,
and retains staged publication/rollback. Old calendar_main stays disabled. The
provider build guard must use --require-editor --require-reminder-ui
--require-filter-async --require-business-ui together; the original read-only mode
still rejects MainAbility WRITE. User-source keyof is avoided through contextual
field array literals at the SDK calls. Genuine SDK ArkTS compilation remains required.

Portable host checks reuse existing source fixtures and execute installed bodies:

```sh
python3 -m unittest -v test_batch_system_calendar_business \
  test_batch_system_calendar_main test_batch_system_calendar375_composition \
  test_batch_system_calendar_filter_async_lifetime test_calendar_provider
```

Run from ci/capability-audit with the same Node runtime as the existing Calendar
harnesses. Host models do not establish ArkUI rendering, real permissions/IPC,
SDK/signing/BMS, native lifecycle, notification clicking or reboot behavior.

The original viewer layers (0001/0002) and their contracts are described below.

# CalendarData reminder viewer

Apply after the complete `source_provider`, `event_editor` and
`editor_callback_dispatch` stack at CalendarData revision
`f922427ca0dc20895a0e254ae41382e5b03299a4`.

The fixed source's MainAbility loaded an empty page and ReminderAgentHelper
targeted the absent `com.ohos.calendar`. This component keeps the actual signed
`com.ohos.calendardata` app and makes its MainAbility show a reminder's persisted
event through the real CalendarManager `getAllCalendars` / `getEvents` APIs.
Both ordinary and important reminder wants target this installed bundle. The
existing `calendar://com.ohos.calendar?event_id=...&start=...&end=...` URI is kept
for persisted reminders; the viewer validates its exact form, uses only the ID
for the query, and displays database contents. The URI cannot supply a title,
note or trusted occurrence time. This is a reminder details viewer; general
calendar browsing and recurrence occurrence expansion remain outside this batch.

The existing READ_WHOLE_CALENDAR permission scene adds MainAbility. The viewer
requests that permission from the user before querying, handles denial and
errors, and sends no calendar data or privileged result to its caller. The
WRITE scene, authority permissions, reminder service UPDATE_CALENDAR_RRULE,
proxy scopes, system-core identity, signer and ACLs stay unchanged. Every Ability
has its own LocalStorage. A revision counter refreshes the same URI on another
want or foreground transition. Superseded and destroyed reads cannot populate
the active page.

The installer checks the complete editor/native dispatch predecessor and app
identity, stages all changes before writing, rejects unknown/partial/symlink
states, and restores published targets if a later publication fails. The
editor's verifier accepts only this complete exact successor on a replay.

Root must also apply
`patches/common/base/notification/distributed_notification_service/calendar_owner`
and add the strict shared provider guard before preparing/building the source
HAP. The native consumer must use the same installed reminder owner, otherwise
it replaces the producer want and clears its URI. Root owns these integration
scripts and the package/runtime gate.

Host regression:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 -m unittest discover \
  -s ci/capability-audit -p test_batch_system_calendar_main.py -v
```

The eight tests execute the actual viewer/Ability functions, both producer
branches, and four native consumer/cleanup functions with host service doubles.
They also test full provider/editor/dispatch replays, permissions, drift,
symlinks and publication rollback. They do not establish SDK compilation, BMS
registration, real user consent, notification clicking, recurrence or reboot
behavior. Those must pass on the first newly packaged representative artifact.

F shared LocalStorage successor
-----------------------------
The actual E MainAbility passes its own LocalStorage to loadContent, while its
page retained a bare @Entry. Patch 0002 explicitly selects that shared instance
with @Entry({ useSharedStorage: true }). No module-level storage is introduced.
The complete E state is an accepted upgrade prefix, not the final repaired state;
base and prefix1 both upgrade transactionally and the final state is idempotent.
source_states.json pins every whole-source state and both patch byte hashes.
Cold/hot Wants, revision refresh and separate Ability storage stay unchanged.
Actual SDK and newly packaged reminder/UI runtime validation remain required.
