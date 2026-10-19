These two small Node fixtures execute installed business controller/page method
bodies with explicit service and plain-state doubles. They contain no upstream
CalendarData source copies and no private-directory or SDK path. The Python test
builds its input through the real installer using the existing exact Calendar
provider/editor/dispatch/native-filter/viewer fixtures.

controller.cjs uses a fixed clock and America/New_York to cover public call
routing, READ/WRITE consent and denial, CRUD persistence doubles, field projection
and preservation, lifecycle races, provider errors, and 23/25-hour DST days.
page_lifecycle.cjs executes actual page method bodies and Ability methods, using
plain host state instead of ArkUI decorators/window services. Real ArkTS parsing,
rendering, provider IPC, consent UI, signing/BMS and new-package runtime remain
separate required gates. Existing reminder Reader/Ability/producer/native consumer
fixtures and tests remain the regression authority; they are not replaced here.
