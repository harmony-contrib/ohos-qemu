# New-package external input to ordinary public API validation

This is a prepared runtime test, not executed guest evidence. It contains five
new Python tools and four caller fixtures. No coordinates, acceleration trace or
expected public states are compiled into the HAP. The caller invokes actual
`geoLocationManager.locationChange`, `sensor.ACCELEROMETER` and public
`stationary.on('still', ...)`. A native NAPI module only records real guest
CLOCK_BOOTTIME and tries both dedicated Unix sockets under the actual app UID; it
cannot send input or change permissions/identity.

The root controller supplies fresh explicit measurement/replay traces after each
`ready-N.json`. It drives real UI buttons and ordinary permission consent, sends
raw authenticated provider frames through HDC Unix forwarding, and preserves all
callback rows, provider handshakes, sent bytes, process maps, actual library hashes
and command logs. Capture alone returns `captured_NOT_verified`. The separate
verifier recomputes results from those raw records and the independent trace.

## Tools and actual boundaries

- `batch_system_build_live_hap.py` generates a fresh caller/SDK source contract.
  Only `--build` invokes the actual SDK native compiler and existing `arkdown build`
  framework. It never signs. Root owns SDK builds, real normal-profile signing and
  the resource lease. Keep absolute project/SDK paths accessible during the later
  verification, including when using a private SDK container.
- `batch_system_run_live_inputs.py` needs a live, already accepted fresh ARM64
  phone boot managed by root (`QemuGuest` context or `boot_package.py --hold`). It
  does not boot/restart system services. It installs only its signed normal HAP,
  uses actual trusted permission UI and invokes its own observer on/off twice.
- `batch_system_verify_live_inputs.py` requires the exact archive and acceptance
  boot, source-built unsigned/signed HAP payload match, actual signature/profile,
  BMS ordinary UID, raw callbacks, fresh independent traces, raw provider nonce
  sessions and source-bound actual mapped DSOs. Missing input, errors, callbacks,
  feature/source/GN/ELF provenance or signature proof fail closed.
- `batch_system_live_inputs.py` contains strict schema/float32/source guards.
- `batch_system_test_live_inputs.py` runs host validator boundary tests using
  explicitly constructed test data. These are never recorded as guest execution.

For each generation, wrong nonce, zero sequence, wrong protocol version and
nonfinite measurement must cause actual server EOF/reset and no public callback
in the app-clock attack interval. The second generation also replays the first
valid session nonce. Every provider nonce must be unique/nonzero. Valid raw frames
must match the external trace byte for byte and the recorded send schedule.
GNSS observes each deliberately spaced independent coordinate/UTC/accuracy fix
with explicit nonmock source GNSS and valid guest boot time. Sensor observes each
float32 m/s² sample with increasing actual guest timestamp, preserving axes.

Public `still` separately requires the source-fixed independent TYPE_STILL
algorithm and service in one native process, no mock DSO, actual package/guest
DSO hash match, and real ENTER/EXIT/ENTER callbacks aligned with the external
in/out/in acceleration phases and real Sensor API timestamps. This proves the
API → genuine input → existing five-event magnitude heuristic path. It does not
prove physical immobility accuracy or implement `relativeStill`.

Each generation's actual off calls must be followed by provider stream EOF/reset. Every raw
callback after `stopped` through the next start is rejected, including the first
four seconds before the measured four-second quiet window. Callback closure
generations prevent an old subscription's callback from being relabeled. The
ordinary app must actually receive EACCES/EPERM for both dedicated sockets at
initial and active generations; ENOENT/ECONNREFUSED does not prove UID isolation.

These two generations exercise real provider Stop/Start through observer
subscription lifetimes. They **do not** constitute native system-service process
restart, crash recovery or guest reboot tests; those remain root-owned first
package cases. Public still's other missing motion capabilities remain open.

## Root execution contract

First integrate the source batch, including manager cleanup and bounded drain;
retain current 13-case native host PASS and finish actual product CFI compilation
and linking. Build one representative ARM64 phone package. Root-owned image guards
must package `gnss-source`, `runtime-assets-source` and `msdp-source` provenance
bound by the acceptance boot. The verifier calls the real shared GNSS/Sensor/MSDP
inventory guards and additionally checks every final public_still source hash.
MSDP uses the actual `libdevicestatus_algo.z.so` and
`libdevicestatus_service.z.so` names and requires product cross-DSO CFI on both.

Generate/build using the same actual SDK that will be passed to verification:

```sh
python3 ci/capability-audit/batch_system_build_live_hap.py \
  --output /absolute/private/live-caller --sdk /absolute/actual/api26/sdk \
  --run-id FRESH_32_LOWERCASE_HEX --arch arm64 --build --arkdown /actual/arkdown
```

Root then signs the resulting unsigned HAP using a legitimate `normal` /
`hos_normal_app` profile with no ACL/restricted grants. Keep real signer output,
key/certificate provenance according to the existing framework; do not invent a
profile or relax platform privileges. The tool verifies actual code/profile CMS
signatures and that signing preserved the unsigned payload.

```sh
/actual/python-with-repository-dependencies ci/capability-audit/batch_system_run_live_inputs.py \
  --archive /absolute/new-arm64-phone.tar.gz --boot /absolute/acceptance/boot.json \
  --project /absolute/private/live-caller --sdk /absolute/actual/api26/sdk \
  --signed-hap /absolute/private/live-caller-signed.hap --signer-jar /actual/hap-sign-tool.jar \
  --hdc /actual/hdc --target ACTUAL_ACCEPTANCE_TARGET --run-id FRESH_32_LOWERCASE_HEX \
  --input-directory /absolute/private/root-traces --output /absolute/private/live-capture
```

The input directory must not contain `generation1.json` or `generation2.json`
before start. When `live-capture/ready-N.json` appears, root publishes that
generation's manifest and actual traces. The manifest requires `run_id`, integer
`generation` (1/2), nonempty actual measurement/replay `source`, `gnss_file` and
`sensor_file` (private simple filenames). GNSS trace uses the existing controller's
`at_ms`, source `utc_ms`, WGS84 coordinates and horizontal accuracy, with optional
actual altitude/speed/bearing/vertical accuracy. UTC is preserved, never rewritten;
the actual provider rejects stale/future source fixes. Provide at least three
distinct GNSS positions, spaced ≥1000ms. Sensor trace contains only `at_ms,x,y,z`
in m/s². Use varied independent samples, ≥10 per phase, in/out/in of the original
7..11m/s² magnitude discriminator; space samples ≥150ms, avoid the threshold by
≥0.1m/s². Keep either trace within45 seconds, below2000 samples and <4-second gaps.
Do not reuse either trace between generations. No tool produces these traces.

```sh
/actual/python-with-repository-dependencies ci/capability-audit/batch_system_verify_live_inputs.py \
  --capture-directory /absolute/private/live-capture \
  --archive /absolute/new-arm64-phone.tar.gz --boot /absolute/acceptance/boot.json \
  --sdk /absolute/actual/api26/sdk --output /absolute/private/live-verified.json
```

Root owns suite/closure integration. Even verifier PASS covers only these input
paths and boundaries, not all MSDP capabilities or the full first-artifact gate.
Do not build the other five packages until that entire first-artifact gate passes.

## Completed evidence

`live-host-tests.log`: 14 pure host validator tests passed. They reject absent
callbacks, wrong generation/axes/units/time, mock/unknown location source, reused
nonce/raw wire mutations, invalid quiet markers, wrong UID/replaced mappings,
missing MSDP provenance and premature/missing public still transitions.
`hap-generation-guards.json` and `actual-sdk-source-contract.json`: actual installed
API26 metadata/declarations were read; source-only generation and two tamper
rejections passed. No native library, HAP, signature or guest test was built/run
in this tool delivery. Native source repair evidence is under `public-still/`.
