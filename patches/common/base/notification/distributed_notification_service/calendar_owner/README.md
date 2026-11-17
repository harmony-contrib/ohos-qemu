# Use the installed CalendarData reminder owner and schema

This exact component pins notification-service revision
`08a878a934511503bca88d3d69c686cc283c198c`. Apply only together with the complete
CalendarData `main_ui` component. Root's shared integration guard must require
that viewer before accepting this owner.

`ReminderCalendarShareTable::NAME` previously selected absent
`com.ohos.calendar`. Binding it to the actual `com.ohos.calendardata` bundle
aligns the consumer's UID lookup, notification owner, uninstall reset and
CheckWantAgent target with the producer. A correctly targeted reminder retains
its real URI. An unrelated bundle still follows the original rejection path.
The data proxy, creator name, callback extension, MainAbility and authorization
boundaries are unchanged.

The actual provider declares `ohos.calendardata.reminderDbVersion=2`; the
consumer previously accepted only the `hmos` prefix and left its version at 0,
skipping BuildReminderV1's extra fields. Accept both exact known key names while
keeping the existing version values 1 and 2. Unknown versions are not promoted
to success. No schema or reminder values are synthesized.

The system Calendar host test compiles and executes actual InitNormalInfo,
CheckWantAgent, UpdateCalendarUid and CancelAllReminders bodies with explicit
BMS/service doubles, against old and patched source. This proves the narrow
source defect and correction, not native platform linking or real guest
notification delivery/deletion. Root must rebuild the real service and source
HAP together, then validate the new archive's reminder lifecycle.
