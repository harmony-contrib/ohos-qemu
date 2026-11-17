# Peer-bound OOB service/GAP candidate

Pinned `foundation/communication/bluetooth_service` revision:
`c489d0aabf77624a4f5ca80ab8b5adefd2d5cfbf`. Apply with
`apply.sh --source-root OPENHARMONY_ROOT`; exactly 12 approved upstream files
change. The existing ordinary pairing IPC and permission dispatch remain intact.
OOB calls additionally verify the real system-API/ACCESS permission item inside
`BluetoothHostServer::StartPair`, so an ordinary pairing permission cannot grant
access to the system OOB path. The SDK selects one curve (P256 when both inputs
are supplied); see the separate framework `api26_oob_validation` component.

The service validates the parcel flags, address/type, 16-byte C/R, curve, role,
name and exact peer binding. Its fixed virtual-to-raw API is unimplemented, so
mismatched identifiers reject explicitly instead of authenticating another peer.
Classic P192 advertises P192 and consumes the one-time C/R using the real
`GAPIF_RemoteOobRsp`. P256 advertises P256 and uses the new blocking GAP task to
the already implemented `HCI_RemoteOOBExtendedDataRequestReply`; omitted P192
command fields are zero, and actual HCI/task/allocation errors propagate.
LE P256 advertises SC OOB and consumes C/R through `GAPIF_LePairScOobRsp`.
LE legacy requests receive an actual negative response: its 16-byte Temporary
Key is not a P192 confirmation hash. LE P192 therefore returns 801.

Each adapter keeps one bounded peer/type-bound slot. Consumption erases C/R;
replays, mismatched type, expiration and cancellation cannot consume them again.
A weakly captured timer erases expired data after 60 seconds, and every access
also checks its monotonic deadline. Cancel/expire retains the in-flight slot
until a real terminal GAP event, preventing reuse by a delayed request; missing
terminal events may keep that adapter's OOB slot reserved until power-off.
Disable immediately wipes and disables the slot; actual successful enable
reinitializes it. Timer creation/start or real pairing-start failure rejects
and releases the unused slot. HCI response failure cancels pairing and publishes
the existing failure event, never an invented paired state. Local OOB generation
has no actual controller/observer path and now returns 801, or the actual
parameter/off error, rather than empty success.

Remaining limits are explicit: optional SDK randomizer omission returns 801
because this backend cannot validate C without its matching R; virtual alias
mapping, LE legacy TK API, actual local generation and controller/vendor setup
remain unavailable. Delayed GAP callbacks carry only an address (no session
identifier); reservation until terminal events protects the current in-flight
request but does not prove arbitrary firmware duplicate-event behavior across
a new completed session or service restart. This requires actual controller and
peer challenges before acceptance.

`test_batch_network_bluetooth_service.py` runs exact source guards plus actual
storage, service, classic/LE handler and C GAP/HCI function bodies with explicit
platform/clock/controller doubles. It covers concurrent single-use consumption,
wrong peer/type, curve selection, P192/P256 command data, SC negotiation failure,
permission/off/parameter errors, expired/cancelled/replayed requests, weak timer
teardown, real return-code propagation and unknown-source preservation under
ASan/UBSan and `-Werror`. These are host regressions, not a product translation
unit build or a successful Bluetooth pairing. Parent integration must compile
and link all affected service/stack TUs, supply a real controller/vendor/peer,
then validate the newly packaged first artifact before the other five packages.
No audit requirement is closed by this source candidate.
