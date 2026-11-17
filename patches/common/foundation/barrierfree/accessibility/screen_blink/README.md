# Screen blinking candidate

Fixed project: `c593c7e1a6149a2c13e5931b2114d3c2d0bf20ea`.
Apply after `api26_blink_enums`. The shared phone/2in1 recipe uses this component
for all three ABIs. Full-file hashes reject partial or unknown states; the old
enum component recognizes only the complete successor composition.

The public synchronous `startBlinking` / `stopBlinking` calls use a new appended
IDL method, the real AccessibilityConfig client and AAMS service, and an owned
WM/RS screen window. Both NAPI and service retain system-app and
WRITE_ACCESSIBILITY_CONFIG checks. Only the synchronous server captures Binder
PID/token. There is no caller-supplied identity, RS bypass, permission-table
change, or window-manager skip-check flag.

The worker serializes window operations, reads the actual master setting, uses
pidfd lifetime tracking, and cleans up on stop, account/display change, caller
death, disabled setting, error and shutdown. Low-frequency pulses are 750 ms per
phase. Late cancelled requests are checked after settings IPC and before window
creation/show. An unavailable pidfd/window/provider fails; it is not success.
This implements a screen backend, not a camera flash/torch emulator.

Validation so far: real NAPI/client/service/regenerated proxy/stub compilation
for three ABIs, separate actual screen backend compilation with existing
aams_ext graphics flags, exact patch replay, and ASan/UBSan host lifecycle
doubles. GN/link, actual signed roles, pixels and lifecycle on a newly packaged
guest remain required. No runtime gap may be closed from those compile/double
results. The test HAP/signer are instrumentation, not a completed pixel verifier.
