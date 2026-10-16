# CalendarData public event editor

Apply `source_provider` before this component, using the fixed `calendar_data`
project at `f922427ca0dc20895a0e254ae41382e5b03299a4`. This component adds the
actual `com.ohos.calendardata/EditorUIExtensionAbility` requested by the public
CalendarManager `editEvent` API. It creates a per-session editable title/time/note
form, preserves the event's supported location/reminder/repeat values, and calls
the real CalendarManager/DataShare `getCalendar` and `addEvent` only on Save.
Cancel returns `eventId=-1` without opening the database. Success returns the
positive ID produced by the real provider. A failed result delivery can retry
without inserting twice. Invalid IDs, important events, malformed timestamps and
fields explicitly unsupported by editEvent are rejected.

The API26 SDK documents editEvent as a user-mediated new-event flow without a
READ/WRITE_CALENDAR permission requirement. Opening the extension never saves an
event. It accepts no receive-data command that could authorize a save, and ignores
the untrusted caller display string for authorization. It cannot update an
incoming event ID or return existing calendar contents. The existing lower and
whole-calendar DataShare URIs, read/write permissions and proxy scopes are kept
exactly. The existing system-core CalendarData signature/ACLs and preinstall
certificate binding remain required; no new permission names or ACLs are added.
The two existing whole-calendar usedScene lists add this actual UIExtension.

NAPI no longer retains a `napi_value` across callback scopes. It keeps a numeric
event ID, initializes cancellation, rejects invalid context/session creation and
provider errors, and settles once for result/release/error/destroy callbacks.
It marks a session closed before calling CloseModalUIExtension to guard reentry,
and never dereferences the host UIContent after onDestroy. Destruction before a
write starts prevents the write. If the host dies during a user-confirmed commit,
the user-created event may remain, while no result goes to the destroyed session.

The separate full Calendar launcher UI, Cangjie callback implementation and
expanded text-menu date/time routing are not implemented by this component.
They remain explicit integration/remaining work.

Host check:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/test_batch_apps_calendar_editor.py
```

Four host tests execute the exact patched controller and native callback bodies,
including 11 controller and 13 native scenarios, patch replay/drift rejection,
and unchanged DataShare contracts. They use explicit host service doubles and do
not prove guest CRUD, permissions or UI behavior.

Actual official SDK26 Release assembleHap passed with all five local HARs. Its
unsigned artifact, inputs, SDK/tools, failed attempts and SHA256 records are in
`docs/capability-audit/parallel/apps/calendar-editor-sdk-20261016.json`.
The successful HAP contains the real extension and compiled `ets/modules.abc`.
No system signing, BMS registration or new-image runtime acceptance is claimed.

The parent agent must:

1. Wire this component after source_provider and before compiling CalendarData.
2. Update the shared calendar-provider guard to accept only the exact new
   extension dictionary, retaining every URI/permission/signer/ACL check.
3. Compile the full native target
   `//applications/standard/calendardata/calendarmanager:calendarmanager`, including
   `napi/src/calendar_manager_napi.cpp` and the changed
   `napi/include/calendar_manager_napi.h` with the actual platform headers.
4. Use the normal GN `calendardata_hap`/app_sign chain and existing vendor signer
   binding, then perform the first-package gate before the other five packages.

New-package UI acceptance must start with an ordinary caller without calendar
read/write grants: show the proposed event, cancel and confirm no row; edit and
save, require a positive returned ID, and use a separately authorized whole-
calendar reader to find the changed values and delete the test row. Its direct
read/write calls must still be denied. Include repeat/reminder preservation,
malformed/forbidden fields, failed provider writes/results, caller exit,
simultaneous sessions, repeated save, Back/Cancel, service restart and duplicate
native callbacks. The editor's stable `calendar-editor-*` node IDs support real
input/node/pixel checks. Do not treat an app launch or a positive mock ID as proof.
