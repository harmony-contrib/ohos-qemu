> Integration 2026-10-19: retained CRUD candidate; not wired into the current
> product build. The active reminder viewer is `../main_ui`. Both modify the
> same upstream UI files, so compose a reviewed successor before enabling this
> installer. See `docs/capability-audit/integration-20261019/remaining-gaps.md`.

# Calendar MainAbility candidate

This component supplies the missing CalendarData main page and reminder URI
destination. It is a source candidate; no SDK compilation, signed HAP/BMS
installation, guest UI, notification delivery or device comparison is proved.

Apply **after** `source_provider`, `event_editor`, and
`editor_callback_dispatch`:

```sh
bash patches/common/applications/standard/calendardata/calendar_main/apply.sh \
  --source-root /path/to/private/full-source
python3 patches/common/applications/standard/calendardata/calendar_main/verify_source.py \
  --source-root /path/to/private/full-source --require-patched
```

Root must integrate this order and the exact known module successor into the
existing editor/provider validators before applying it to a product. This
component does not edit or weaken those validators. In particular, the provider
validator's permission-scene contract currently stops at
`EditorUIExtensionAbility`; this successor appends `MainAbility` to the same two
existing whole-calendar permissions. APL, ACLs, permission names, lower/whole
DataShare authorities, proxy definitions, original `standard` launch type and
the Editor UI remain unchanged. `main_pages.json` already registers
`pages/index`, so it is not rewritten.

`manifest.json` pins six complete before/after states and seven unchanged
installed editor/native-dispatch dependencies. Optional project Git metadata
must match the fixed upstream revision. Unknown, partial, symlinked and mixed
inputs fail before installation. The installer stages and validates all six
postimages, preserves original file modes, then replaces the six files under
one component lock. A caught commit/verification failure restores every
changed predecessor byte and removes newly created files/directories. A
forced process kill or power loss is not a multi-file atomic filesystem
transaction: its partial state fails closed on replay and requires inspection;
the installer does not discard unknown source edits.

The supplied main page uses `getCalendarManager(UIAbilityContext)`,
`getAllCalendars`, the actual default calendar when the returned list is empty,
and bounded daily `queryEventInstances`. Context and existing provider token
checks determine the accessible current OS user's calendars. No user/account
identifier is accepted from a Want. Calendar selection and day navigation
perform reads; new/save/delete require explicit user controls. Failed reads
show an error rather than an empty-calendar success. Writes use actual
`addEvent`, `updateEvent` and `deleteEvent`, then read persisted data again.
Editable timed, normal, non-lunar, non-recurring events with at most one reminder
preserve untouched public fields. Other event kinds remain viewable and are
explicitly read-only in this small UI. It does not implement a full recurring
series editor or change calendar notification settings.

Each ability owns its own `LocalStorage` and controller. Foreground reloads;
background/destroy invalidates stale reads and queued pre-write work. Once a
provider mutation has been submitted, UI destruction does not claim to cancel
it. A new Want arriving during a mutation is read after that operation settles.
An old window-load callback cannot affect a replacement controller.

The accepted read-only route is:

```text
calendar://com.ohos.calendardata?event_id=POSITIVE_INT32&start=UTC_MS&end=UTC_MS
```

The old `com.ohos.calendar` URI host is also accepted. Both the existing normal
and important reminder requests now target the real
`com.ohos.calendardata/MainAbility` bundle/ability. The URI's exact event ID and
instance bounds must match a real instance returned through a currently
accessible calendar. URI parameters cannot trigger writes. Extra/duplicate
parameters, malformed encodings, invalid ranges, non-canonical IDs, unrelated
hosts and durations above 366 days fail visibly without a mutation.

The fixed provider already constructs and publishes CalendarAlerts data-change
notifications. Its legacy scheduling path uses a process-local timer and a
common event. This project contains no direct `publishReminder`/`cancelReminder`
calls. The actual product reminder-agent subscriber, delivery, cancellation,
and cross-process/reboot recovery must be established separately; correcting
the notification Want does not prove that producer chain exists.

Host checks execute the actual delivered route, controller and ability with
explicit dependency doubles; they do not simulate a passing guest:

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 \
  python3 ci/capability-audit/test_batch_system_calendar_crud_candidate.py -v
```
