# GNSS measurement fidelity and configuration repair

Base: `6096a405356c538006c284b894af058e2be7e240`. Fixed location project:
`5a0c49c2adb0623fdac73f76e4f98f2e57674c00`, read only from
`ohos-qemu-parallel-source-20261016-02`. This batch changes exactly three new
upstream files, all under `base/location/location/services/location_gnss/gnss`:
`source/gnss_event_callback.cpp`, `include/gnss_event_callback.h`, and
`source/gnss_ability.cpp`. No driver, vendor, shared build, ledger or main-worktree
file is changed. All 22 assigned requirements remain open; this batch closes 0.

The production callback previously saved a satellite report and added five
hardcoded satellites when a subsequent location arrived with at most three GPS
satellites marked used in fix. The patch removes the call, constructors, helper
methods, global cached report/flags, and mutex that supported that behavior.
Device-reported zero satellites remain a genuine zero report; absence of a
satellite report remains absence. Real IDs, constellation, CN0, elevation,
azimuth, frequency and additional flags are preserved. Every input vector is
checked against the active count before indexing. Unreported vector tails are
excluded from the hook's CN0 list. A malformed report fails without publishing
partial or synthetic measurements.

The fixed IDL and actual generated `gnss_types.h` define plain aggregates with
**no default member initialization**. `GnssConfigPara` contains only
`gnssBasic { minInterval, gnssMode }` and
`gnssCaching { interval, fifoFullNotify }`. There is no HDI `size` or `startType`
field. Both normal and cache configurations are now value initialized.
Normal configurations explicitly set the interval in milliseconds and the
configured standalone/MS-based/MS-assisted mode (values 1/2/3); cache fields
remain zero. Cache mode retains the existing bridge discriminator of basic mode
zero and explicitly sets its cache fields. The existing cache caller already
passes milliseconds despite its `reportingPeriodSec` parameter name; this batch
does not add another seconds conversion there.

The full WorkRecord carries per-request intervals in seconds. The normal path
now chooses the fastest active interval, multiplies in int64, preserves explicit
zero, rejects negative input, and saturates at the HDI uint32 maximum without
integer overflow. The handler routes through `SendLocationRequest` so this code
runs on the actual event path. A changed interval during an active session must
successfully configure before replacing the request set; a failed reconfigure
restores the previous interval and returns an error. Provider rejection is not
silently relaxed or replaced with a success. A first request reports failure if
it cannot reach the started state.

Unknown configured modes and failed HDI configuration return a service error.
Both normal and cache starts stop immediately when configuration fails and do
not advance the session state. Successful start commands still use the actual
separate `GnssStartType` enum: normal=1, cache=2. A returned start error also
leaves the existing state unchanged. The legacy `SendMessage` IPC reply denotes
event-queue acceptance; it is not changed into a synchronous device result.
The event handler now diagnoses the returned request/configuration error.
Working-status and capability callbacks retain their existing empty business
handlers; the current implementation updates local state from HDI operation
results and does not require a fabricated status/capability event to accept fixes.

System's separately owned external provider accepts normal standalone mode and
interval 0..3600000 ms, consumes external data, and rejects unsupported modes or
intervals. This business patch does not expand that provider's supported range.
The driver bridge must supply actual vendor struct sizes, copy the interval,
map normal/cache configuration, and stop/join before unloading; those files are
owned by system, not included here. Product SUPL configuration must select a
mode the installed provider really supports. No standalone fallback is invented
for an invalid or missing configuration.

Validation:

- 27 location-prefixed tests passed in 37.870 s. GNSS actual function execution
  uses ASan/UBSan and frozen actual generated POD declarations plus production
  SatelliteStatus class/methods, with explicit HDI/IPC/request-dispatch/hook host
  boundaries. LeakSanitizer is unavailable on this macOS host; detect_leaks=0.
- The original fixed callback is actually compiled/executed and reliably fails
  the satellite count assertion after a location; the patched callback passes.
  Cases include no report, genuine 0/1/3/4/64/128 satellites, every measurement
  field, all seven short-vector cases, huge count, unused tails, and mock-mode
  suppression. This is a regression reproduction, not a real receiver result.
- Actual normal/cache configuration/start/request/handler functions cover POD
  zero fields, modes 1/2/3, unknown mode, 0/1000/90000/UINT32_MAX interval,
  invalid bounds, no interface, HDI configure/start errors, repeated starts,
  second-to-millisecond conversion, minimum interval, active reconfiguration,
  rollback, empty records, and failed first start.
- The production guard pins all 27 complete source targets and accepts exact
  original/prefix1/prefix2/prefix3/prefix4/final states. Complete fixed originals
  matched live read-only hashes/HEAD, and actual five-patch application matched
  every full-file state. Separate guard tests reject mixed/unknown bytes, wrong
  HEAD, changed patch, missing target and symlink paths before mutation.

Parent must compile the two complete platform TUs and link the real GNSS module
with the actual generated headers, then validate the external provider/bridge
and public API through a newly packaged representative artifact. Host execution
and source guards are not vendor/HDI/QEMU/package proof. All provider, behavior,
telephony and six-package delivery gates remain with the root agent.
