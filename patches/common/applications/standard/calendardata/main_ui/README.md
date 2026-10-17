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
