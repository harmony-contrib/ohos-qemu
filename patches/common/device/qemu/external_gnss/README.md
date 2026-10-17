# External QEMU GNSS vendor and compatible HDI bridge

This component implements the existing vendor ABI using explicit external GNSS
measurements, and repairs the existing HDI bridge's sizes, configuration and
callback/unload lifetime. It generates no location without an input frame, no
satellites, NMEA, cached fixes, assistance data or artificial capability reports.
Only normal standalone positioning is implemented. Root owns product build,
init/SELinux/HDC wiring and new-package public API validation.

The manifest pins drivers/peripheral at
`69094b77aa2200160207b1b06b3c0b586ae2157c` and device/qemu at
`b017aee8e2dfc97e45aeb508facc1527c3d06f4b`. The actual complete
`location_vendor_lib.h` is a hashed read-only dependency. The installer verifies
all three original bridge files and five new device files before replacing
anything; unknown/mixed edits, symlinks, wrong revisions, changed ABI headers or
foreign overlays are refused. Failed replacements roll back all touched files.

```sh
bash patches/common/device/qemu/external_gnss/apply.sh --source-root /path/to/ohos
```

## Actual ABI and function contracts

`drivers/peripheral/location/gnss/hdi_service/location_vendor_interface.cpp`
loads `vendorGnssAdapter.so`, then `dlsym`s a **data** symbol named
`GnssVendorInterface`: `GnssVendorDevice {size, getGnssInterface}`. The getter
returns the actual namespaced `GnssVendorInterface` structure, consisting of
`size` and these eleven functions, in source order:

| Function | Implemented behavior |
| --- | --- |
| enableGnss | Validate full/basic callback sizes and mandatory location callback; copy its function pointer, open the private endpoint; 0 on successful resource initialization, -EINVAL/-EBUSY/-EIO on failure |
| disableGnss | Invalidate session, stop input, clear callbacks; external caller joins worker; reentrant worker call schedules its own termination without self-join |
| startGnss | Normal category 1 only; enable real input delivery; other categories return -ENOTSUP, uninitialized input returns failure |
| stopGnss | Normal category 1 only; invalidate/close old connection, wait for in-flight delivery from another thread; later normal start is allowed |
| injectsGnssReferenceInfo | -ENOTSUP; reference information is never promoted into a measured fix |
| setGnssConfigPara | Strict structure sizes, normal category, standalone mode 1, interval 0..3600000 ms; invalid/unsupported configurations fail |
| removeAuxiliaryData | No-op void operation because this implementation maintains no assistance cache |
| injectExtendedEphemeris | -ENOTSUP |
| getCachedLocationsSize | null, unsupported |
| flushCachedGnssLocations | null, unsupported |
| getGnssModuleIface | null for every optional module, unsupported |

`GnssLocation` is the actual complete vendor type. Legacy QGN1 mandatory validity bits are
latitude/longitude/horizontal accuracy/UTC/boot time. Optional altitude, speed,
bearing and vertical accuracy bits are set only when supplied. Unmarked fields
remain zero; no accuracy or motion measurement is invented. UTC comes unchanged
from the source measurement; boot time is guest CLOCK_BOOTTIME nanoseconds
(including suspend), with a host-only CLOCK_MONOTONIC fallback on platforms
without CLOCK_BOOTTIME. Callback data is borrowed synchronously; provider never
retains the caller's callback structure. The input worker holds its own shared
state; callbacks execute outside locks and do not capture the Provider object.

The bridge now supplies the correct basic callback size, fully initializes each
vendor configuration on the stack and preserves actual minInterval. It snapshots
strong HDI callback references under the map mutex, then invokes callbacks after
unlocking. Enable no longer calls the vendor while holding the callback mutex.

The loader returns stable proxy tables and retains each in-flight API call.
It copies callbacks into session-owned storage and forwards through permanent
trampolines. Cleanup removes the active generation before allowing any new
callbacks. A non-provider reaper waits for outstanding API calls, calls the real
vendor disable (which joins its worker), then waits for callback completion and
only then calls dlclose. Callback-initiated cleanup queues that work and returns;
callback counts alone are not treated as proof the provider has returned from
its callback or that its code can be unmapped. Invalid device/table sizes or
missing mandatory functions close the failed load handle. Repeated cleanup is
idempotent. Unsupported cache functions retain null pointers through the proxy.

The old ABI exposes unscoped optional module pointers. If a nonnull module is
borrowed, or disable/cleanup fails, the loader retains that mapping and blocks
replacement instead of unmapping potentially active code. This provider returns
no such modules. This conservative behavior needs broader product review for
other vendor backends; no successful unload is claimed for an unscoped module.

## External protocol

Endpoint: `/dev/unix/socket/qemu_gnss/input`, mode 0600, writer peer UID **0** via
SO_PEERCRED (getpeereid in host tests). There is no product environment override.
The server's 32-byte hello is `QGN1`, LE u32 version 1, fresh random nonce16,
LE u32 frame size 88, reserved u32 zero. Each frame is:

| Offset | Representation |
| --- | --- |
| 0 | `QGF1` |
| 4 | LE u32 version 1 |
| 8 | nonce16 from this connection |
| 24 | nonzero strictly increasing LE u64 sequence |
| 32 | LE u64 source UTC milliseconds |
| 40, 48, 56 | LE float64 WGS84 latitude degrees, longitude degrees, altitude metres |
| 64, 68, 72, 76 | LE float32 horizontal accuracy metres, vertical accuracy metres, speed m/s, bearing degrees |
| 80 | LE u32 optional validity mask: altitude4/speed8/bearing16/verticalAccuracy64 |
| 84 | reserved u32 zero |

Latitude is [-90,90], longitude [-180,180], altitude [-12000,100000], positive
horizontal accuracy <=100000, optional positive vertical accuracy <=100000,
speed [0,1500], bearing [0,360). All numbers must be finite. Unknown flags,
malformed/partial frames, wrong version/nonce and replayed sequence/UTC fail.
UTC must be an actual epoch from 2020..2100, no more than 10 seconds old or
1 second in the future relative to guest wall time, and strictly increase in
that connection. A historical trace is not relabeled with fresh UTC: replay
outside the live window is unsupported and must fail.

There is one active controller, listen backlog 1, requested kernel receive buffer
4096 and no userspace fix FIFO. Transfers are bounded and idle/incomplete input
expires after 5 seconds. Stop, callback changes and cleanup invalidate the old
session and close its connection; reconnect uses a new nonce. Buffered events
from an old session cannot be dispatched after stop returns. External stop waits
for an active callback; callback reentry never waits on itself.

The controller consumes a JSON array of explicit source measurements, each with
`at_ms`, `utc_ms`, `latitude`, `longitude`, `horizontal_accuracy`; optional keys
are `altitude`, `vertical_accuracy`, `speed`, `bearing`. at_ms is increasing
relative send time, with transfer gaps below 4 seconds. It preserves source UTC
and records wire frames; successful send alone proves no public API delivery.

```sh
python3 ci/capability-audit/batch_system_gnss_controller.py --tcp-port OWNED_FORWARDED_PORT --input /absolute/live-measurements.json --output /absolute/unique-sent.json
```

The root can forward an owned root HDC localfilesystem endpoint to the socket.
No HDC/VM, external endpoint, SDK build or package operation was performed by
this component batch.

## Integration and evidence

The actual HCS host is `location_host`: vendor/ohemu/virt/hdf_config/uhdf/
`device_info.hcs:557..589`, uid/gid location_host, GNSS module
`liblocation_gnss_hdi_driver.z.so`, service `gnss_interface_service`, preload 2
(existing on-demand device loading). init passwd:22/group:23 map UID/GID1022;
SELinux drivers/adapter/public/type.te:56 declares domain location_host. Existing
location_host policy only grants search on dev_unix_socket. Root must create
`/dev/unix/socket/qemu_gnss` 0700 location_host:location_host before host start,
with exact directory/socket types and narrow location_host creation and root su
connection rules. The root-owned parent directory remains 0755.

Root adds a dependency on
`//device/qemu/common/virt_full/external_gnss:qemu_external_gnss` and checks
installation as **vendorGnssAdapter.so**, without lib prefix or .z suffix.
The new BUILD explicitly requests output_name, empty output_prefix,
output_prefix_override=true and output_extension=so; the actual OHOS template
supports the prefix override and explicit extension. Official GN generation,
product TU/link/CFI checks are still required. Check actual loaded mappings and
symbol binding, not just compilation or archive presence.

Location agent's separate base fix initializes its actual IDL config, forwards
the fastest real request interval, handles HDI errors before Start, and removes
the previous dummy satellite construction. Normal sequence is Enable→Config→
Start(category1). Root must select legitimate standalone mode1 and verify
optional AGNSS/GEOFENCE compile requirements. Working status/capability callbacks
are not needed to advance the current base state machine; no artificial reports
are added. Genuine fixes flow through HDI ReportLocation→GnssEventCallback→
SubAbility→Locator ReportManager and the real GNSS/fusion fence consumers.

Completed host results: 35 actual provider/Unix/ABI scenarios, 24 bridge scenarios
(6 actual-function boundaries and 6 actual loader/DSO cases, each before/after),
and 10 strict installer tests. The bridge suite reproduced six original function
failures (including callback reentry deadlock), three bad-loader failures and two
premature DSO cleanup failures; repaired cases passed ASan/UBSan. Full source
fixtures, commands and logs are in docs/capability-audit/parallel/system/
round4-gnss. Platform logging/remote/IDL scaffolding limitations are explicit.

An additional same-process unload/reload attempt failed Darwin ASan global ODR
registration in the test DSO. That uncompleted extension is not counted as a
pass, no sanitizer was relaxed, and its complete log is retained. Root must
validate actual Linux/ARM64 reload/CFI and new-package end-to-end behavior.
No capability requirement or first-artifact gate is closed by these host tests.


## Explicit raw-precision V2 extension (requires a newly built guest)

The existing UID0/0600 endpoint and unchanged `QGN1` hello remain. V1 senders
continue sending QGF1 with all original constraints. That hello does **not**
advertise V2. A V2 controller must explicitly select `--protocol qgn2-precision`,
send an 88-byte QGP2 probe (version2, current nonce16, remaining64 bytes zero),
and receive the exact 32-byte QGA2 ACK: version2, same nonce16, frame size88,
capability word1. No ACK, wrong nonce/version/capability or an old guest closes
or fails the operation. The controller never silently falls back to V1.

After an ACK the connection accepts only QGF2/version2 data frames. A V2 frame
before the probe, a V1 frame after the ACK, repeated/late probes, or mixed/wrong
versions terminate the connection. A connection that first sends QGF1 is V1
until it closes. Negotiation consumes no measurement sequence/UTC. Restart,
stop, session invalidation and reconnect still require a new random nonce.

QGF2 retains the88-byte layout: offsets0/4 are QGF2/version2; offsets8..63 and
68..83 retain V1 meaning. Offset64 is the raw little-endian uint32 bit word of
horizontal accuracy. Offset84 is an exact0/1 validity word (all other bits are
invalid); it controls only the existing HDI horizontal-accuracy bit32. Mandatory
LAT/LONG/UTC/guest boot-time bits and all other optional fields remain unchanged.
The protocol decodes accuracy as uint32 and the vendor uses memcpy into its
actual float32 field, without evaluating/normalizing NaN, Inf, signed zero,
subnormal or negative encodings. Both validity states are permitted for every
accuracy bit word so the real HDI/business validators, rather than the input
codec, can be challenged. This explicit root-only mode is raw boundary/fault
input, not a claim of physically measured accuracy or successful public delivery.

Only horizontal-accuracy validation differs from V1. Latitude/longitude,
altitude, vertical accuracy, speed, bearing, UTC epoch/window, strictly increasing
sequence/UTC, nonce, five-second transfer deadlines, peer UID and session
lifetime protections are retained. QGN1 still rejects zero/nonfinite/negative
accuracy exactly as before. V2 JSON requires `horizontal_accuracy_bits` as eight
lowercase hexadecimal digits and `horizontal_accuracy_valid` as a JSON boolean;
it does not accept a numeric `horizontal_accuracy` field. Hex is the numerical
IEEE binary32 word, e.g. `7fc01234` becomes wire bytes3412c07f. No input UTC is
created or refreshed by the controller.

Python wire/transcript/static checks are in
`ci/capability-audit/test_batch_system_gnss_precision_protocol.py`. They do not
execute native provider/HDI code. The dedicated native precision harness must be
compiled and run by root, in addition to the unchanged V1 suite, before a new
package. Full compiler/ABI, actual new-package HDI mask/raw-bit observation and
ordinary callback/precision-consumer acceptance remain required. Sending bytes
or receiving an ACK proves no capability ID closure.
