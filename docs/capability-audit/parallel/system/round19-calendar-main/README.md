# Calendar MainAbility / URI candidate handoff

The fixed SDK01 CalendarData export has a MainAbility that only loads
`pages/index`, whose `build()` is empty. Its reminder request generator targets
`com.ohos.calendar/MainAbility`, while the exported app is
`com.ohos.calendardata`. The new, separate `calendar_main` component replaces
that empty main flow, uses actual CalendarManager APIs, validates read-only
reminder links against real accessible instances, and fixes both notification
Want targets. Existing Editor UI and native dispatch files are unchanged.

`source-evidence.json` records 20 complete input-file hashes plus line-numbered
excerpts. The source export is from the prior Calendar SDK01 candidate; it has
no `.git`. Its hashes are cross-checked against the installed editor contract,
while the required upstream revision comes from the existing exact component
guards. The SDK declarations read here are **26.0.0.105**, not the actual
LinuxSDK39 compiler used by newer root batches. There was no source/out,
inspector, Docker, build, native compiler, SDK, VM or HDC access in this round.

The original empty page, missing URI handling and foreign reminder bundle are
checked directly from retained predecessor bytes. Eight Python tests, including
19 scenarios executing the exact new ETS route/controller/ability in Node,
pass in `host-tests-03.log`. No native/SDK compilation runs inside those tests.
The tests cover URI bounds and no writes, token/read errors, explicit CRUD and
cancel, field preservation, unsupported rich event kinds, failed mutations,
duplicate saves, delayed read/write destruction, new Wants during both stages
of a save, independent controllers, recreation, and old window callbacks.
Fault injection after four file replacements restores the whole predecessor,
including removal of both newly introduced files. Unknown/partial inputs,
editor/native drift and symlinks are rejected without replacing source.

The earlier failed `host-tests-01-failed.log.gz` (verbatim compressed output) is preserved. Passing `[]` is the
real NAPI representation of an unrestricted instance-ID set; the host dependency
double initially treated it as matching no IDs. That test-engineering defect
caused seven scenario failures. `host-tests-02.log` passed after fixing the
double. The final batch also adds the pre-write new-Want refresh case and the
visible initialization-error case; no failed log was overwritten.

One fixed native API limitation was found in the allowed source export:
`CalendarNapi::GetEvents` deletes its `napi_ref` just after queuing AsyncWork,
while worker execution retains a raw `EventFilterNapi*`. The new main controller
strongly owns its actual filter wrapper through promise settlement, including
background/dispose. This protects this caller; it does not repair or prove the
general native lifetime contract for unrelated CalendarManager callers. Root
should assign a separate precise native fix/test if that broader boundary is
needed. This component does not change the frozen dispatch implementation.

Root integration still needs:

1. Install `calendar_main` after the complete native dispatch successor. Teach
   the existing editor guard and Calendar provider permission-scene validator
   to accept **only** this complete known six-target successor plus the seven
   exact unchanged dependencies; do not permit arbitrary new module hashes.
2. Use the actual official SDK to compile this changed HAP, preserve its
   source/metadata/compiler evidence, sign through the original system-core
   OS profile and three ACLs, then prove the actual preinstall and BMS entry.
3. On the next representative new package, use the real main page to create,
   cancel, read, edit and explicitly delete a challenged event. Read back
   persisted IDs and all retained fields with an independently authorized
   caller. Verify denied normal-app direct access separately. Test actual
   activity/process restart, valid/invalid URI launch, stale/deleted instance
   links, rapid repeated actions, and background before/during provider writes.
4. Resolve the actual reminder-agent consumer for the provider's CalendarAlerts
   proxy notifications. The inspected project has real request construction,
   alert rows and notifyChange, plus a legacy process-local common-event timer,
   but no direct publishReminder/cancelReminder calls. Identify its real
   external subscriber/permissions, then prove publication, notification tap,
   cancellation and reboot recovery. No timer, reminder callback or success
   receipt is fabricated here.

`behavior:calendar-lifecycle-device-difference` remains open. Phone/tablet
behavior, a complete recurring/lunar/important editor, real reminder delivery
and device comparison are not proved by host function execution. The ledger
and currently running representative build remain unchanged.
