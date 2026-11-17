# Actual QEMU screen refresh modes

The pinned public refresh-rate navigation route exists in native Settings but
has no page registration. A fresh R21 guest returned successfully and opened an
empty destination. Add the missing source Settings page, not a success stub.

The page queries the real main Screen and its supported/active modes, offers
only modes at the current resolution, and reads back a requested mode change.
It never invents 90/120 Hz, changes resolution implicitly, alters a SysCap,
grants permissions, or changes the display backend. Unsupported, ambiguous,
failed and unapplied requests remain errors. A single-mode QEMU display shows
only its actual mode.

Requires source Settings packaging. Host controller tests and HAP compilation
do not establish guest success: validate a newly packaged artifact, real screen
readback, return navigation, invalid modes and ordinary-app permission denial
before accepting this capability. Both profiles and all three ABIs use the same
component; their own packaged behavior gates remain mandatory.

R24 exposed two independent mistakes in the first candidate. The dynamic
page must be listed in the phone build profile's `arkOptions.runtimeOnly.sources`;
a route string and a successful HAP build do not mean the page bytecode exists.
Also, `activeModeIndex` and `setScreenActiveMode()` use array indices, not each
mode's `id`. QEMU actually returns reverse-ordered IDs: index 25 can refer to
ID 0, the real 1280x800/75 Hz mode. Patch 0002 adds the compiler entry and maps
selected IDs to indices only at the public setter boundary. Labels continue to
identify real IDs and post-call readback checks the actual selected mode.

The component accepts a fresh pinned source, the exact completed state, or
migrates its fully hashed previous candidate. Unknown/partially edited files
are never overwritten. This migration is not an old runtime entry point.
