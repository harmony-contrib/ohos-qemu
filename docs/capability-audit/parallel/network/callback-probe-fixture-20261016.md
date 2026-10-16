# Native callback probe: single-VPN exclusion precondition

The parent's real API26/ARM64/libffrt probe compiled successfully and aborted at
the final `closing.owner` disconnected assertion. Its immutable failure evidence
is `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-vpn-broker-callback-and-health-real-FFRT-01/artifacts/callback/evidence.json`;
the original probe SHA256 is
`ea7bfb2fe839f184c71aaee1054069f4993a1fa6b16b78e2fd37ccd99e6fc399`.
The accompanying `runtime.stderr` and failed probe remain unchanged.

The generated native main still assigns its earlier non-system `nextObject` to
`service->vpnObj_`. The deterministic host main removes its equivalent single
VPN through the preceding remote-death regression. Injecting the same later
multi-owner test into these different states caused the discrepancy.

The actual product function
`foundation/communication/netmanager_ext/services/vpnmanager/src/networkvpn_service.cpp::IsNeedNotify`
returns false for `DISCONNECTED`, nonempty `vpnId`, and an existing non-system
single VPN. The original native main satisfies all three conditions. Its callback
is correctly suppressed before listener delivery. This failure does not establish
an FFRT scheduling defect, and changing the product filter would violate the
existing single-VPN exclusion rule.

The shared injected test now explicitly establishes that single-VPN boundary in
both mains. It asserts that the real filter returns false and the actual queued
disconnected callback remains silent. Under the service mutex it then calls the
actual `DestroyOwnedConnection` function, requires success and exactly one
backend-double destroy, clears the previous single object, and requires the
filter to admit the later multi-owner event. The original lock-blocked publish,
stopping-generation CONNECTED suppression, and final exact disconnected count,
state, and `closing.owner` assertions remain intact. Product patches, account and
permission checks, compiler warnings, sanitizers, and test assertions were not
relaxed.

Previously the native-only main was emitted without being executed by host
tests. The existing callback regression now additionally compiles and executes
that same main with an explicit asynchronous serial-worker FFRT double. It uses
real host threads, mutexes, futures, and the extracted product functions; it is
not target FFRT proof. The double does not model delayed health scheduling,
which retains its separate health regression and real target probe.

Before correcting the fixture precondition, this new host path reproduced the
same original final assertion. The retained reproduction is
`callback-fixture-before-fix-host-reproduction-20261016.txt`. After repair, the
callback/broker/health modules collect 10 tests: 8 pass and 2 Linux-only process
tests skip on macOS. Evidence is `callback-fixture-host-tests-20261016.txt`.
The native emitter's two generator regressions also pass.

Regenerate with `batch_network_emit_vpn_broker_native.py --output-dir PRIVATE_DIR`.
The repaired callback probe SHA256 is
`da52abb3f26a2db4187b763fd743f18add45ecbe02c8e9b3f3be5461607841f7`.
The health probe remains byte-identical at
`c791f7560e366bee21569d14c8f494f2574ac60a9d8450465efc2b6656e1e9f2`.
The parent must repeat target compilation and real libffrt execution of the
repaired callback probe. No new upstream target or product source change is
introduced. All nine assigned capability gaps and the first-package runtime
gate remain open.
