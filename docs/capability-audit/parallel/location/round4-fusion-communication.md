# Batch 4: fusion fences and explicit modem communication state

Base: `c77dddccc28c8e9f1fb67a380646fb875eac4a9d` in the location-only worktree.
No root checkout, driver project, shared helper, ledger, source volume or out
volume was modified. Runtime closures remain **0 of 22**.

## Fusion fence business path

API 26 dynamic add/remove/support exports call native locator RPCs 72/73/74;
private lifecycle RPC75 releases only the original owner and callback object.
The complete old 1..71 mapping is preserved. The new bounded parcelable does not
append fields to any old wire payload. RequestConfig's internal precise-consumer
flag defaults false, is copied/equality-checked, resets on legacy IPC input and
never changes the old ten serialized fields.

GNSS fences create real owner Request/WorkRecord subscriptions and fine
PrivacyKit use; GNSS/RTK callbacks supply coordinates. Circles and spherical
polygons cover the antimeridian and reject degenerate edge geometry. Accuracy
bounds suppress uncertain boundary decisions; mock, stale, future and wrong
provider reports are discarded. WLAN fingerprints use actual complete scans,
MAC groups and measured RSSI/deviation. Scanning must start successfully; failed
or empty results never manufacture a negative transition. Actual scan completion
and sample ages are preserved, including rejection of stale still-state caches.
CELL uses CoreServiceClient's real per-slot cell list; empty/error/unsupported,
future and >30s data are rejected. Its boot-millisecond timestamps are converted
to boot nanoseconds without relabeling cache age. LTE/NR TAC and NR 36-bit NCI are
preserved. Required GN support and conditional `tel_core_service_api` wiring are
in the owned locator BUILD.gn.

Fresh positive evidence from any selected modality puts a fence inside; an exit
requires fresh negative evidence for every selected modality. Missing evidence
is unknown, not outside. Motion events use changing real GNSS signed distance;
near-wander needs observed direction changes. Dwell requires uninterrupted fresh
inside evidence. Expiring a shape resets evidence and does not synthesize EXIT.
BLE bitmap8 remains an explicit device-boundary801: this fixed SDK supplies no
BLE fence/fingerprint field, so no new hidden input or constant match is invented.

Records are isolated by uid/token/firstToken/identifier. Duplicate and capacity
checks are owner-scoped; remove and cleanup cannot delete another owner or later
same-id callback. Native queued NAPI work owns its exact callback generation and
becomes silent after removal/env cleanup. Promise creation/queue/cancellation
failures reject and release references. Periodic maintenance is independent of
provider reports and stops on expiry, permission revocation, account or switch
changes. It retains failed PrivacyKit stop ownership for retry; frozen callers
receive no event and lose dwell continuity. Radio-only fine permission use also
feeds the real location-icon query. No service/request lock is held across owner
permission/account/RDB checks or remote callback dispatch.

The district locale guard now uses the same 100-byte bound as this fixed source's
napi_util locale parser, with explicit100/101-byte tests and no borrowed undeclared
MAX_BUF_LEN. Parent found the original full-TU compile error; host harnesses no
longer inject that identifier into this parser's scope.

## 5A producer, registry and observers

The reference AT vendor consumes only an independently received strict
`+OHOS5A: 0` or `+OHOS5A: 1` unsolicited line. Invalid/partial/extra-field lines
cannot create a state. That real vendor-report path uses notification1412 with
an aligned-independent int32 payload restricted to0/1, HRilNetwork, the parent's
new RIL V1_5 one-way callback162, TelRilNetwork, state-registry IPC14 and observer
callback13/mask0x2000. Existing network/NR registration is never interpreted as5A.

The registry accepts publication only from the actual native `telephony` process
with SET_TELEPHONY_STATE, verifies real slots, keeps unknown until the first
explicit update, deduplicates repeated reports and rechecks GET_NETWORK_INFO
for each subscriber/delivery. On/off take mandatory callback and optional slot
options. Dynamic unregister is env/slot/event/function scoped; old queued work
cannot call a newer generation and env teardown can release an owned subscription
after permission revocation. ANI/Rust/ETS bindings carry the same real bool/slot
producer; Rust parsing passed, but actual ANI generation/compilation/lifecycle
runtime remains a parent gate.

The parent's actual inherited RIL generation already proved old command mappings
unchanged, new162, true bool/oneway wire, and full generated proxy/stub TUs. It does
not prove this business code or a running modem. A peer must first bring up the
real reference vendor radio/AT connection; radio-unavailable state rejects URCs.
The peer must report transitions to false when its actual 5A state ends, including
radio shutdown/reset. IMS/RTT still needs a genuine controlled IMS service/peer.

## Exact source and validation boundaries

Cumulative actual targets: location24, communication42 and previous RTT4 =70.
This batch changes location17 plus communication42 =59 actual source targets.
Original raw hashes/explicit new-header absence match the live read-only fixed
source. Only one target is CRLF: state_registry_ipc_interface_code.h; its binary
Git diff preserves those39 original CRLF lines. All other changed files use the
fixed LF source format.

The location guard accepts only complete original/prefix1/prefix2/prefix3/final
states at the pinned project HEAD. Its explicit absent-header state rejects an
unexpected existing header, dangling symlink or mixed predecessor. Communication
pins all three project HEADs and complete original/final states. Both preflight
remaining patches privately, require exact final hashes, recheck the original
snapshot, then atomically replace owned targets under their component lock.
Unknown bytes, mixed files, wrong HEADs, changed patch data and symlink ancestors
fail before source writes. No public helper was changed.

24 location-prefixed host tests pass, including actual patched wire/service,
geometry, cell-query, NAPI Promise/callback, vendor-parser/HRil/registry and 5A
listener queue functions under ASan/UBSan. Dependency doubles expose external
provider/framework boundaries. macOS LeakSanitizer is unsupported; reference
ownership is separately asserted in the harnesses. This is not a modem, GNSS,
WLAN, HDI, ANI or packaged-runtime proof. The two existing public-enum tests and
exact full-source hash checks are recorded separately in the log.

The complete26-TU list, generated sources, build graph and disabled-feature
checks are in round4-platform-build-request.json. The parent alone regenerates,
compiles, links, packages and validates the new ARM64 phone representative
artifact. All failures must be batched before rebuilding it. Only a passing new
representative runtime gate allows the other five packages.
