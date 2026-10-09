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
