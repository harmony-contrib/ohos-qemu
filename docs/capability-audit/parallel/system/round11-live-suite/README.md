# External-inputs family for a newly packaged ARM64 phone

`batch_system_live_inputs_suite.py` supplies the fixed parent family interface:

```sh
/actual/python-with-repository-dependencies ci/capability-audit/batch_system_live_inputs_suite.py \
  --boot /ABS/work/boot/external-inputs-boot.json \
  --archive /ABS/new-arm64-phone.tar.gz --hdc /ABS/hdc \
  --artifacts /ABS/filled-actual-artifacts.json --output /ABS/work/external-inputs
```

The boot is root's exclusive byte copy of the acceptance boot, in the same
directory as its actual qemu.log. It stays stable when the parent records later
wake operations. This wrapper never builds/boots, restarts a shared service,
changes IDs or permissions, or decides the full first-artifact gate.

The artifacts template is deliberately invalid until root fills actual paths and
SHA values. It is not evidence or a generated result. The ordinary caller's run
ID comes from its already compiled source contract; the wrapper does not rewrite
ETS or embed expected positions, acceleration, or still transitions. Root must
supply the successful actual LinuxSDK39 project and native build receipts.
Contacts/Wallpaper successful HAPs need not be rebuilt.

## Actual SDK/signature/source contract

The wrapper lazily uses Apps' real `batch_apps_contact_picker_coordinator.py`
`verify_sdk_project`, `sign_normal_hap`, and `verify_signed_hap_artifacts` (delivered
by Apps in a3e0347). Missing integration fails. It neither copies nor replaces
that adapter. The source manifest is `live-inputs-contract.json`; its direct
fixture hashes and actual compiled source inventory must match the frozen live
fixture. Actual project compile/log/HAP proof is checked even if some other
project in that original multi-project SDK batch failed.

The original SDK report also needs the root-agreed `native_builds` array with one
row for `sdk_project`:

```json
{
  "project": "live-inputs",
  "command_label": "compile-native",
  "source": {"path": "/ABS/live-inputs/socket_probe.cpp", "sha256": "ACTUAL_SHA"},
  "binary": {"path": "/ABS/live-inputs/entry/libs/arm64-v8a/libliveinputaudit.so", "sha256": "ACTUAL_SHA"},
  "compiler": {"path": "/ORIGINAL/LinuxSDK39/native/llvm/bin/clang++", "sha256": "ACTUAL_TOOL_SHA"},
  "headers": {"/ORIGINAL/LinuxSDK39/native/sysroot/usr/include/napi/native_api.h": "ACTUAL_HEADER_SHA"},
  "sdk_native_metadata_sha256": "ACTUAL_NATIVE_METADATA_SHA"
}
```

`headers` must contain the complete actual SDK compiler dependency hashes, not
only the example NAPI header. The native command must be the recorded successful
actual `compile-native` command with the real source, ARM64 target, shared/PIC
output and warnings gate. Actual ELF64/AArch64/type and the exact DSO bytes in the
compiled HAP are checked. Compiler/header hashes are explicitly the original
Linux SDK runner's actual-read receipts; the host wrapper does not claim it
reread Linux-only tools. Root owns retaining raw dependency/tool/ELF evidence.

`sdk` may be root's exact export of the three complete public d.ts files and
ets/native oh-uni-package metadata consumed by `sdk_contract`. Such an export is
only a declaration/metadata contract directory, not a host SDK or compiler. Its
hashes must match the actual SDK39-generated source contract and native metadata
receipt. No105/39 metadata substitution, namespace replacement or SDK compile
claim is made by this wrapper.

The SDK project/report are unchanged. The capture receives a new private copy of
every SDK-hash-checked source input and real native DSO. A clearly labeled derived
receipt contains the original actual SDK commands/logs/HAP, without claiming a
new compile. Parent re-verification reconstructs this binding independently.

Signing and re-verification use the fixed real public signer chain, actual Java
code/profile verification, fixed leaf CMS verification, exact ordinary normal
bundle/permissions, current guest UDID and no ACL/restricted grant. Signed HAP
payload must equal the actual SDK output. Only real BMS/UI/public API operations
can produce the runtime capture.

## Independent controlled protocol source

Default `input_source.mode` is explicit `controlled_virtual_protocol_vectors`.
Root chooses the vectors in a separate SHA-bound file. Schema:

- top-level exactly `schema_version:1`, `source_id` equal to the artifacts value,
  and `generations`, containing exactly generation1 and2;
- each generation exactly `generation`, `gnss`, `sensor`;
- `gnss`: explicit integer `at_ms`, latitude/longitude/horizontal_accuracy,
  optional altitude/speed/bearing/vertical_accuracy, no prefilled UTC;
- `sensor`: explicit integer `at_ms`, x/y/z in m/s².

The existing strict trace validators require at least three distinct GNSS fixes
at least1s apart, at least10 samples per in/out/in phase of the original7..11m/s²
heuristic, at least12 distinct float32 samples, at least150ms spacing, finite
ranges, distance from thresholds, at most2000 samples and45 seconds, and gaps
below4 seconds. Both generations must differ. No built-in coordinates or motion
trace exists in the wrapper/HAP.

A separate fixed publisher subprocess only reads that root-selected file. After
the actual capture creates ready-N, it rechecks the source SHA, records current
host UTC and monotonic time, assigns UTC+at_ms **only to these declared virtual
protocol vectors**, and atomically publishes complete traces and the manifest.
Its receipt does not claim physical measurements or guest success. It never
connects to a provider or public API. The existing capture sends the raw bytes,
and the existing independent verifier compares those bytes with ordinary public
GNSS/Sensor/still callbacks. Guest BOOTTIME comes exclusively from the real
provider/API/NAPI; it is not supplied by the publisher. Provider stale/future
limits are enforced by the actual backend.

For independently managed real replay, root can explicitly select
`{"mode":"external_publisher_directory","directory":"/ABS/fresh-private-traces"}`.
No manifest may exist before ready-N. Root publishes fresh complete generation
manifests/traces under the existing capture contract, preserving original UTC.
This mode does not start or claim ownership of the external publisher process.
No arbitrary executable/argv is accepted in artifacts.

## Runtime, cleanup and independent parent verification

The current true capture/strict verifier require the actual new archive and boot,
raw normal BMS UID and socket EACCES/EPERM, fresh provider handshakes/nonces,
wrong nonce/zero sequence/version/nonfinite rejection, old generation replay
rejection, exact wire frames, genuine mapped provider/bridge/business/Sensor/real
MSDP DSOs and root-owned source/GN/CFI package inventories. Stop/start uses real
ordinary observer lifetimes; no direct ABI callback injection is accepted.

This batch also repairs a confirmed capture omission: its process-map grep now
includes `libdevicestatus_service.z.so`, which the existing strict MSDP checker
requires alongside the actual algorithm DSO. It also records a private forward
before creation, so a command that fails after creation still enters cleanup.
Neither change weakens verification.

Finally always closes the owned streams, joins/terminates only its publisher,
force-stops/uninstalls only its own ordinary app, and records actual BMS absence,
two proc process/ordinary-UID absence observations, and the actual forward list.
All script/target/guest exits/stdout/stderr/log/raw bytes and hashes are retained.
Remaining app/process/forward/socket/publisher or an unquiesced owned command
group makes `cleanup_complete:false`, with `cleanup_errors`. A functional failure
with verified cleanup remains fail but permits root to collect other family
failures safely. A failure before guest mutation reports that separate no-mutation
state. System-owned provider sockets/services remain with the suite.

The top-level `evidence.json` has `status`, `archive_sha256`, `boot_id`,
`cleanup_complete` and `cleanup_errors`. Parent calls
`verify_evidence(evidence_path, archive_path, boot_path)` to recompute SDK/native
source binding, real signer verification, cleanup, root-selected post-ready
publication, raw callbacks/wire, actual source/DSO inventories, and all three
component results. A stored pass flag or UI text cannot replace these checks.

No runtime was executed in this delivery. Process restart/crash recovery, physical
GNSS accuracy, physical immobility accuracy, relativeStill, other system service
requirements and the full representative artifact gate remain unverified. The
other five packages must still wait for root's complete first-package gate.
