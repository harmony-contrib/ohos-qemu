# OpenHarmony capability audit

This audit keeps seven questions separate for every phone and 2in1 API:

1. Is the API documented for the device?
2. Does the image declare the SysCap and register every required permission?
3. Is the ArkTS or Native surface present?
4. Does a real call reach a working service, kernel, or virtual-hardware backend?
5. If the service delegates to a system HAP, is its payload listed, accepted by
   the signature policy, registered by BMS, and exposing the exact ability or
   extension name that the framework targets?
6. If resolution is implicit, does an enabled HAP skill match the action while
   retaining its entity, URI/UTD, and domain-verification constraints? An
   action-only source reference cannot prove a constraint-bound route; the
   audit leaves that state explicitly unresolved.
7. If the framework loads a product plug-in at runtime, is the exact shared
   library present in the image, or does execution fall back to a no-op or
   unsupported implementation?

`canIUse()`, a packaged library, and a registered System Ability are evidence
for different layers. None of them alone proves an API is usable.

The default new-package suite also runs the ordinary Camera persona. It declares
only CAMERA and clicks the actual trusted PermissionManager Allow control for
the dedicated audit app, using localized labels from the fixed source. It never
substitutes a root permission grant. Both live preview generations require real
UITest-selected rectangles, same-phase app log prefixes and independently
checked compositor pixels. NDK callbacks/boundaries, ArkTS lifecycle recreation
and four decoded JPEGs are separate requirements. Source/SDK hashes and fresh
nonces remain bound to the evidence. SDK compilation and parser fixtures are
not guest success; this closes only the missing capture backend finding, not
advanced camera/video APIs. Selected node rectangles are JSON-stable lists for
independent evidence comparison after serialization.

The ordinary test signer also normalizes the one observed ArkDown native staging
path into canonical `libs/<ABI>/lib*.so` entries before actual code-signing. This
fixes x86_64 test HAPs that compiled successfully but placed their libraries under
intermediates subdirectories. It preserves all library/application/resource and
permission bytes and the original unsigned HAP. Unknown nesting, duplicate
canonical paths, symlinks or wrong ELF ABIs fail closed. This is shared by the
audit and native-bindings test signing paths; it is not a production ArkWeb HAP
format change or evidence of application loading.

`run_library_exit_probes.py` normally clears loader overrides and tests the
installed system libraries. Its explicit `--candidate-surface`,
`--candidate-fence`, and `--candidate-mapping-probe` diagnostic mode instead
stages only that verified pair in a fresh private guest directory. It requires
actual process mappings to prove both candidates were loaded, and rejects
namespace fallback, duplicated/deleted mappings and early loader failure.
It never replaces a system library or attests a new package. In particular,
an old image's NDK namespace may select the old provider despite an application
`LD_LIBRARY_PATH`; that is a failed diagnosis, not evidence for or against a
coherently rebuilt image. Do not force it through by weakening namespace policy.

The QEMU 7.0 realtime-audio candidate has a separate exact XML/map check:

```bash
python3 ci/capability-audit/check_qemu_audio_policy_7.py \
  --source-root /path/to/read-only/openharmony \
  --work /tmp/audio-policy-7-validation-UNIQUE
python3 scripts/verify_qemu_audio_policy_image.py \
  --chip-prod-image /path/to/completed-package/images/chip_prod.img
```

The first command uses fixed pristine inputs and an owned scratch ext4 fixture;
the second reads the preferred actual chip_prod configuration. Both fail closed
on missing flags/device maps or unrecognized XML. Neither is Renderer PCM,
Capturer, Bluetooth/distributed hardware, or the first-artifact behavior gate.

## Build the inventory

Use the `syscap.json` extracted from each tested image and the exact OHOS 7
documentation, JS SDK, and C SDK revisions:

```bash
python3 ci/capability-audit/build_matrix.py \
  --ohos-root /path/to/openharmony \
  --docs-root /path/to/openharmony-docs \
  --sdk-js-root /path/to/interface-sdk-js \
  --sdk-c-root /path/to/interface_sdk_c \
  --phone-syscap docs/capability-audit/runtime/arm64-phone/image-syscap.json \
  --two-in-one-syscap docs/capability-audit/runtime/arm64-2in1/image-syscap.json \
  --findings ci/capability-audit/known-findings.json \
  --output-dir docs/capability-audit
```

The documentation parser starts from API headings. It inherits a file or
module SysCap into child methods when the method does not repeat the marker.
This is required for Native reference pages such as Camera, which declare the
SysCap once in the header and then document dozens of functions. Entries with
no document-level or inherited SysCap remain visible with `syscap=null`.

Generated artifacts:

- `all-capability-matrix.json`: every public SysCap found in SDK profiles,
  image declarations, API annotations, docs, bundles, or XTS metadata.
- `capability-coverage-ledger.json/csv`: one result per SysCap and device.
- `public-api-inventory.json/csv`: regenerated full method/type inventory;
  ignored by Git because it is large.
- `api-usability-ledger.json/csv`: one result per documented API and device;
  ignored by Git. `api-usability-summary.json` is the checked-in summary.
- `method-device-boundaries.json/csv`: explicit document device differences.
- `runtime-backend-audit.json`: hardware, service, kernel, and launch-topology
  evidence for critical backend families.
- `runtime/arm64-*/config-bundle-reference-audit.json`: every bundle name
  referenced by packaged JSON configuration, checked against `bm dump -a`.
- `runtime/arm64-*/preinstalled-hap-audit.json`: every `/system/app` HAP,
  module entrypoint, preinstall-list membership, live BMS state, certificate
  fingerprint, signature allow-list result, and path mismatch candidate.
- `system-bundle-provider-audit.json`: every semantically retained provider
  candidate token; exact bundle/entrypoint pairs resolved from C++ and
  same-object ArkTS/TS/JS Wants; implicit actions joined to HAP skills while
  retaining entity, URI/UTD, and domain-verification constraints; DataShare authorities;
  runtime-parameter target pairs; and production `dlopen()` dependencies. The
  scanner preserves absent, nonlocal, and unresolved targets so filtering or a
  hand-written rule list cannot hide a missing provider or product plug-in.
  Provider scans include `applications`, `arkcompiler`, `base`,
  `commonlibrary`, `domains`, `drivers`, and `foundation`; the runtime-library
  pass also includes device-side `developtools`. Test, sample, mock, demo,
  build, and output trees are excluded.

## Runtime and ABI stages

`run_normal_hap_probe.py` builds a fresh API26 Release ordinary test HAP,
signs and actually verifies it in local Docker, installs only the dedicated
audit bundle, rejects stale output and runs the existing strict data/boundary
verifier. Supported personas are Web, user-ID, I18n, Matrix4, compiled const-enum, all-own ArkTS exports,
AudioRenderer, software AVC, AudioSuite effects and Vulkan-window. Vulkan-window uses actual UITest
layout bounds, compositor screenshots and surface destroy/recreate actions;
its pixel verifier does not accept a headless readback as visible presentation.
The test SDK patch version is recorded separately
from the OS build number. Before replacing a HAP the runner stops only its
dedicated audit bundle and requires two real kernel-process/AA-record absence
observations within 30 seconds. An uninstall reply alone is not lifecycle
completion. Unknown stop replies or dump formats fail; no system process is
stopped. Camera reads results and receives photos from its UIAbility module
context (`haps/entry/files`); application-context personas use `files`.
These are test setup corrections, not capability passes.

Example for an already booted newly packaged guest:

```bash
python3 ci/capability-audit/run_normal_hap_probe.py \
  --archive /absolute/path/to/new-package.tar.gz \
  --output /absolute/path/to/fresh-unique-attempt \
  --sdk /absolute/path/to/API26-Release-SDK --udid ACTUAL_64_HEX_DEVICE_UDID \
  --persona audio-stream --arch arm64 --device phone --target 127.0.0.1:5555
```

This does not boot the guest, grant permissions, replace libraries or satisfy
the full first-artifact gate. The enclosing fresh-VM suite must bind its
environment to the archive. The automated runner itself was exercised on the
old R6 I18n diagnostic guest; that eight-case pass is not new-package evidence.

`matrix4` makes actual typed SDK calls, with no native export shim and no
requested permissions. Its 17 ordered observations cover all seven repaired
module-level helpers, matrix multiplication order, copies remaining independent,
inverse/translation/scale/rotation/point arithmetic, three invalid-argument
boundaries, existing factory-object regressions and 64 state-isolation roundtrips.
The strict verifier binds the current page, SDK declaration, fresh challenge,
ordinary account100 identity and raw values. It registers only these seven
helper contracts; it never attests the rest of ArkUI or compositor behavior.
Unsigned HAP compilation and synthetic verifier fixtures are not guest passes.

`factory-objects` covers only ResourceManager `Configuration`/`DeviceCapability`
and TaskPool `TaskInfo`/`ThreadInfo`/`TaskPoolInfo`. The SDK declares these as
factory-returned data classes with no constructor or static member. The actual
ordinary typed caller checks every resource field through sync, promise and
callback APIs, snapshot isolation, and two generations of four real tasks with
matching live IDs/names/states/worker IDs, exact computed results and cleanup.
The verifier retains the original five ledger entries and records the resolution
as a verified factory-return contract, never as an added runtime constructor.
All other resource/TaskPool/ArkUI requirements remain independent. Compilation
or synthetic test fixtures do not satisfy the new-package behavior gate.

The matrix defaults to `scripts/validate_packaged_qemu.sh`, which owns one fresh
extraction/VM and connects all narrow results to its actual kernel boot ID.
Set `QEMU_TEST_SDK_HOME` to a host-compatible API26 Release SDK and
`OHOS_NATIVE_BINDINGS` to the current bindings checkout. The latter is copied
with uncommitted changes into an owned test tree; all 32 current modules must
run, zero skips/empty reports are accepted, and the dependency locks must stay
unchanged. `scripts/sign_qemu_test_hap.py` adapts the source project's supported
`HAP_SIGN` override to official code-sign and actual verification in local
Docker, without adding privileged ACLs or altering the test source.

The isolated bindings main/test `deviceTypes` declarations are adapted to the
actual phone/2in1 target without changing original files, permissions or test
assertions. Before any finite application-test timeout setup, the fresh suite
requires two default-policy s2idle/physical-key wake cycles with actual visible
UITest windows and decoded compositor screenshots. Kernel UUID, RenderService
and Foundation must remain unchanged. Old candidate-kernel diagnostics cannot
satisfy this check. The suite queries actual PowerMgr timeout and backup values
before/setup/after restoration, refuses an existing override owned by another
client, and requires the exact original policy before the final verdict. A
successful shell transport or a cleanup claim alone does not release the gate.

`const-enum` compiles every baseline enum member with the real API26 Release
SDK and checks ordinary-app execution against that SDK compiler's declaration
values (16 contracts/53 members at the current SDK). Declaration/compiler/page
hashes, member order, types, nonce and architecture are independently verified.
This is a compiled-constant contract only, not a NAPI export, service or hardware
backend proof. The complete ledger retains all other requirements.

Module export inventory now includes all own string properties using the
public `napi_get_all_property_names`, not only enumerable keys. `napi_default`
exports are commonly non-enumerable. The collector records its mode; old logs
remain explicitly `unknown_legacy_probe`. This improves triage, not behavior
proof, and does not remove any original ledger requirement or fabricate class
constructors for factory/injected objects.

The default fresh suite also executes complete root bitmap/user-ID/BPF data
and boundary probes, real AudioSuite PCM/state transitions, and the actual
Vibrator HDI timer/timeline/error cases. Public ordinary-app calls and their
permissions are separate checks. BPF map/filter success alone does not close
NetManager or NetFirewall service/policy findings.

The RS object repair adds an independent `rs-objects` package check. Its caller
uses the actual product compiler flags/headers and links only the newly built
RS/IPC/c_utils libraries; only its executable is transferred, without loader
overrides or replacement system DSOs. Eighteen ordered observations cover
ordinary/ashmem payload sizes, null objects, FD 0, cross-thread consumption and
cancellation, repeated lifetimes and four damaged sidecar rejections. A fresh
nonce, exact ABI, actual process exit and the enclosing live archive/boot are
required, and the gate independently rechecks the raw transcript. These are
real-class boundaries, not cross-process Binder or compositor proof; ordinary
Web and independent Vulkan UI tests remain mandatory. The optional completed
TU evidence mode is compile-only and cannot supply guest acceptance.

Full-source packaging first runs `scripts/verify_native_gap_abi_image.py` against
the real final `system.img`, fixed SDK-C source HEAD, NDK manifests and all
headers. Every original Native gap remains in the archive's
`native-gap-abi-image.json`; required or declared libraries need their complete
symbol contract for that ABI. Undeclared optional libraries are explicitly
not implemented, never reported as implemented. The package verifier rechecks
actual image bytes, SysCaps, whole ELF exports and library identities without
needing an SDK source checkout. Runtime `build_native_gap_abi_probe.py` and
`run_root_probe.py --kind native-gap-abi` independently perform real system
`dlopen`/`dlsym`/`dladdr` for every required symbol. This is system-loader ABI
proof only: provider behavior and ordinary-app namespace/permissions remain
separate requirements.

`run_root_probe.py --boot-evidence /absolute/owned/boot.json --boot-id UUID`
can reuse the enclosing live VM's already checked complete archive-member
inventory. It still rehashes the archive, verifies the extracted manifest,
actual private host process/QMP, and real guest boot ID. Native definitions
must be the checked member of that actual package. This avoids decompressing
multi-GiB userdata for every tiny probe, without accepting a stale VM/cache.
Running it against an explicitly diagnostic old image never proves the new
first-artifact gate.

The 2in1 suite additionally uses a private actual QEMU FTDI USB-serial endpoint.
Ordinary apps must be denied raw-node access and the authorization service;
only clicks on the actual trusted system dialog may grant the captured request.
Basic deny/allow/data I/O and real unplug/replug/callback/regrant boundaries are
independently verified. Host socket OPEN/CLOSE attaches/detaches the real QEMU
USB device; a host journal alone is not guest data/permission proof.

`verify_gap_closure.py` additionally requires every focused Native ABI, dynamic
ArkTS export/load, compiled constant, permission and behavior gap. Unregistered
or incomplete behavior stays unresolved; a successful browser, graphics or
bindings subset does not satisfy this gate. Schema2 first-artifact evidence
checks actual child JSON results and the exact current audit baseline, rather
than trusting a generic outer `pass` or command exit status.

Run two HAP personas on each device:

- a normal application for public permission and sandbox behavior;
- a platform-signed system application with both `apl=system_core` and
  `app-feature=system` for system APIs. Setting the APL alone still returns
  error 202 for multiple system APIs.

Build the probe with the same latest JS declarations:

```bash
python3 ci/capability-audit/build_hap_probe.py \
  --arch arm64 \
  --udid DEVICE_UDID \
  --syscap-registry docs/capability-audit/all-capability-matrix.json \
  --api-dir /path/to/interface-sdk-js/api \
  --kits-dir /path/to/interface-sdk-js/kits \
  --output /tmp/ohos-capability-hap
```

Provider-backed UI calls also have a focused persona. It runs before the broad
native probe and avoids a slow emulator consuming the UIAbility lifecycle
deadline before a picker or dialog is reached:

```bash
python3 ci/capability-audit/build_hap_probe.py \
  --provider-only \
  --arch arm64 \
  --udid DEVICE_UDID \
  --syscap-registry docs/capability-audit/all-capability-matrix.json \
  --api-dir /path/to/interface-sdk-js/api \
  --kits-dir /path/to/interface-sdk-js/kits \
  --output /tmp/ohos-provider-probe
```

Then regenerate the SysCap, module, export, permission, C ABI, static ArkTS,
System Ability, and backend reports for each device. Build the two ledgers last:

```bash
python3 ci/capability-audit/build_coverage_ledger.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --output docs/capability-audit/capability-coverage-ledger.json

python3 ci/capability-audit/build_api_usability_ledger.py \
  --inventory docs/capability-audit/public-api-inventory.json \
  --capability-ledger docs/capability-audit/capability-coverage-ledger.json \
  --runtime-root docs/capability-audit/runtime \
  --output docs/capability-audit/api-usability-ledger.json

python3 ci/capability-audit/audit_runtime_backends.py \
  --runtime-root docs/capability-audit/runtime \
  --output docs/capability-audit/runtime-backend-audit.json

python3 ci/capability-audit/audit_system_bundle_providers.py \
  --ohos-root /path/to/openharmony \
  --runtime-root docs/capability-audit/runtime \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --output docs/capability-audit/system-bundle-provider-audit.json
```

## Strict verification

```bash
python3 ci/capability-audit/verify_results.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --ledger docs/capability-audit/capability-coverage-ledger.json \
  --api-ledger docs/capability-audit/api-usability-ledger.json \
  --backend-audit docs/capability-audit/runtime-backend-audit.json \
  --api-dir /path/to/interface-sdk-js/api \
  --kits-dir /path/to/interface-sdk-js/kits \
  --static-sdk /path/to/static-arkts-sdk
```

The verifier proves that the surface inventory is complete, every phone/2in1
contract SysCap has a concrete classification, every C++ and ArkTS/TS/JS
provider target is either resolved or retained as an unresolved record, and
runtime parameter, implicit-Want skill, DataShare provider, and `dlopen()`
library joins are populated. Its success
status is
`complete_capability_classification_method_sampling_full_provider_inventory`.
Method rows still say when a method was not individually executed; a
capability-level sample never turns every method into a verified pass.

## Native and ArkTS 1.1 gap view

To review only the Native C/C++ and dynamic ArkTS 1.1 gaps, excluding ArkTS
Static, regenerate the focused ledger after the main audit artifacts:

```bash
python3 ci/capability-audit/build_native_arkts11_gap_ledger.py \
  --runtime-root docs/capability-audit/runtime \
  --findings ci/capability-audit/known-findings.json \
  --output docs/capability-audit/native-arkts11-gap-ledger.json
```

The focused ledger keeps ABI/export, permission, product declaration, system
provider, kernel, and virtual-hardware failures separate. It does not promote
a module because it loads or because a lifecycle smoke test passes.

The export analyzer keeps ambient `const enum` contracts separate from NAPI
object exports; program compilation may inline their members. See the
[TypeScript enum contract](https://www.typescriptlang.org/docs/handbook/enums.html#const-enums).
Those rows remain `compiled_caller_not_verified`, not passes or erased
requirements. Regenerate against the recorded audit SDK commit, not an older
build SDK that omits newer interfaces. Ordinary enums/classes and missing
functions are not blanket-exempted; data-class APIs need real factory/value
checks. For AST host regressions, set `OHOS_AUDIT_TYPESCRIPT` to an installed
TypeScript compiler directory; fixtures are not guest validation.

For a multi-package change, build and boot one ARM64 representative artifact
first. Validate every changed behavior and device boundary before building the
remaining architectures and products. Keep per-package logs and checksums.

## ArkWeb versus Vulkan graphics probes

Keep these paths separate. The WebView HAP probe's `--web-only` mode records
JavaScript arithmetic, DOM, Canvas 2D pixels, WebGL1/2 shader compilation and
pixel readback independently. It also requires the invalid shader boundary,
caught JavaScript exception/continued execution, actual ArkTS proxy callbacks
and round-trip values, state retained across reload, and renderer termination
followed by restored DOM/proxy/WebGL1/2 draws. An initial draw alone does not
satisfy the renderer recovery check.
`sign_web_probe.py` signs its unsigned HAP with the OpenHarmony test signer in
the Linux/Java 11 build container. `egl_extension_probe.c` compares the public
EGL wrapper's extension advertisement to the Mesa backend.

```bash
python3 ci/capability-audit/build_hap_probe.py --web-only --arch arm64 \
  --udid sign-after-new-boot --output /path/to/web-probe
# Boot the NEW package, obtain its UDID, then sign/install/run the HAP.
python3 ci/capability-audit/verify_web_results.py \
  --log /path/to/new-guest-web-results.log --output /path/to/web-result.json
```

Use a fresh app result file per run. The verifier fails on timeout/late/error
records, missing native-side callbacks, incorrect proxy counts, or claimed
success with incorrect pixels. The caught page exception test does not claim
that arbitrary JavaScript exceptions reject the controller's Promise.

The Native Vulkan probes separately check loader/ICD discovery, physical and
logical device creation, mapped buffer memory, extension advertisements, and
headless surface/swapchain creation. The headless test does **not** prove
`VK_OHOS_surface` or XComponent native-window presentation. See
`docs/OHOS_7_ARKWEB_VULKAN_REPAIR.md` for the architecture matrix and the
first-new-package validation gate. `vulkan_ohos_surface_probe.c` additionally
submits actual Vulkan clear commands to an OHOS NativeWindow, maps the consumer
buffers and checks ten frames/1500 RGBA pixels, then verifies resize rejection
without a false submitted buffer. This CPU consumer queue is NOT a visible
compositor or XComponent screenshot test.

```bash
bash ci/capability-audit/build_graphics_probes.sh --arch arm64 \
  --output /path/to/graphics-probes
python3 ci/capability-audit/test_ohos_present_copy.py
python3 ci/capability-audit/test_vulkan_loader_ohos_surface.py
```

The last two commands compile exact code extracted from the patches with
ASan/UBSan. Pixel stride/overflow and mock multi-ICD allocation/cleanup checks
provide regression coverage, not new-image runtime validation. Likewise,
`compile_patched_vulkan_loader.py` compiles a scratch source copy using actual
product Ninja arguments but explicitly emits `compile_only_not_runtime`.

The `--vulkan-window-only` HAP obtains its NativeWindow from an actual ArkUI
XComponent callback (no static import of the XComponent-bound module). It
presents five clear frames, releases the native resources, and exposes buttons
to destroy and recreate the surface. After booting the new archive, sign for
its UDID, install, and use fresh app data. Capture the initial compositor
screenshot after `vulkan_window.present`, click Destroy then Recreate, capture
the second screenshot, and pull the app's `vulkan-window-results.log`. Obtain
each native surface rectangle in screenshot pixels, not ArkUI density units.

```bash
python3 ci/capability-audit/build_hap_probe.py --vulkan-window-only --arch arm64 \
  --udid sign-after-new-boot --output /path/to/vulkan-window
python3 -m venv /path/to/screenshot-venv
/path/to/screenshot-venv/bin/pip install -r ci/capability-audit/requirements-test.txt
/path/to/screenshot-venv/bin/python ci/capability-audit/verify_vulkan_window.py \
  --archive /path/to/NEW-archive.tar.gz --results /path/to/vulkan-window-results.log \
  --initial-screenshot /path/to/initial.png --recreated-screenshot /path/to/recreated.png \
  --initial-rect x,y,width,height --recreated-rect x,y,width,height \
  --output /path/to/vulkan-window-result.json
```

This verifies ALL interior RGBA pixels in both screenshots and the exact
initial→destroyed→recreated native lifecycle. It records the actual archive
and screenshot hashes. Bad pixels, geometry, timeouts and stale/missing
cleanup records fail; generated fixtures are only verifier regression tests,
not evidence that RenderService displayed the new archive's Vulkan frames.
Background/foreground and compositor resize need separate runtime checks.

## AudioSuite data path

The pinned Linux API 26 native SDK includes `ohaudiosuite` headers that older
DevEco SDKs omit. Build the probe in the source-volume container with that SDK:

```bash
OHOS_SDK=/path/to/26.0.0/native \
  bash ci/capability-audit/build_audio_suite_probe.sh arm64 /path/to/probes
```

`probes/audio_suite.cpp` uses `dlsym` to report missing stub-library exports,
then exercises two complete PCM input→output pipelines. It requires callbacks,
3840 nonzero sample values with correct channel/sign data, clean frame padding,
end-of-input, stop-state boundaries and resource teardown/recreation. It does
not claim algorithm plug-ins, cloud download or realtime hardware nodes work.
An enabled GN feature or a successfully compiled probe is not its pass result.

The AudioSuite library-path component selects `/system/lib/` for ARM32 and
`/system/lib64/` for LP64. Only the default XML directory is remapped; custom
paths remain unchanged and the existing canonical-path allowlist remains in
place. QEMU's `/system` resolves to `/usr/system`; the loader also accepts the
matching ABI's canonical read-only root, never an arbitrary `/data` directory.
`realpath` is still called before the allowlist check, so an escaped symlink
does not become a trusted plug-in path. `test_audio_suite_library_path.py` exercises both ABI branches with
ASan/UBSan plus apply/reverse-check idempotence. It does not provide the missing
DSP plug-ins or certify their execution.

## I18n bundled data and permissions

The QEMU I18n init component removes three unavailable vendor `hmos_cust_*`
mount commands. The upstream implementation uses bundled OpenHarmony city/time
zone data, compiled-in libphonenumber metadata and system taboo resources. The
real `icu72_dat_mount` recovery program and the I18n service are retained; do
not replace them with success-only helper programs.

```bash
python3 ci/capability-audit/build_hap_probe.py --i18n-only --arch arm64 \
  --probe-run-id NEW_32_HEX_RUN_ID --udid sign-after-new-boot --output /path/to/i18n-data
# Sign for the new guest as a NORMAL app without UPDATE_CONFIGURATION.
python3 ci/capability-audit/verify_i18n_data.py --archive /path/to/NEW-archive.tar.gz \
  --results /path/to/i18n-data-NEW_32_HEX_RUN_ID-results.log --run-id NEW_32_HEX_RUN_ID \
  --output /path/to/i18n-result.json
```

The app uses a frozen host challenge in its filename and every record, truncates
its own result log, then checks fixed Shanghai and New York
offsets (including DST), city/catalog data, E164 format and invalid-number
rejection, localized country/ICU year data, and rejection of system-language
updates in a normal app with no language change. The public installed SDK omits
the system setter, so the probe uses an explicit typed bridge for the API in
the pinned sdk-js. A missing method, a string error code or any code other than
numeric 201/202 is a failure. Wrong parameter types and missing arguments must
throw numeric 401 without changing the language. All eight records must be
fresh and complete; failed observations and hashes are retained.
It does not claim every I18n API, custom data updates or all permissions work.

The first ARM64 phone actually denied the operation but returned string `"202"`;
it also silently accepted the wrong argument type. `business_error` delegates
to the existing numeric BusinessError helper and rejects invalid setter type
conversions. Service permissions and legacy non-throwing paths are preserved.
`compile_i18n_error.py --kind helper|setters` checks each product's actual Ninja
compiler arguments in scratch. If a product has not prepared PNG yet, the
script strictly prepares the pinned archive/config/patch inputs in scratch and
records their hashes, not another architecture's generated output. Compilation
does not satisfy the new-package behavior gate.

The default ordinary-app suite also runs `contact-sync-mode`. It independently
checks both members of `contact.ContactSyncMode` and `audio.DeviceBlockStatus`,
plus the existing member of `photoAccessHelper.FusionAssetType`, using API26
typed values and actual public NAPI own-member reads, with zero
requested permissions, a fresh challenge and a normal account-100 identity.
The SDK declaration/compiler, native collector and generated caller are bound
to their actual hashes. An object or function of the right name alone cannot
close an enum finding. This probe does not call cloud sync, write contacts or
exercise microphone blocking or fusion providers; provider/storage, audio backends and permission
behavior require their own evidence. Its three ABI unsigned HAP builds are not
a new-image behavior pass.

Run the host regression suite in a task-specific venv with the pinned screenshot
dependency:

```bash
/path/to/screenshot-venv/bin/python -m unittest discover \
  -s ci/capability-audit -p 'test_*.py'
```

The bindings workspace now has an ARM32 E2E driver path on branch
`audit/ohos7-qemu-e2e-arm32`. Sync the selected Rust demos for the requested
architecture BEFORE invoking `test:ui`. The driver rejects missing, duplicate
or wrong-ELF native payloads before installing main/test HAPs. `ohrs build -a
arm` has compiled the actual JSVM/QoS/Vibrator demos, but compilation and the
driver's nine fixture tests do not replace a run on a new ARM32 package. The
Hypium driver requires every source-declared case in order, matching successful
summary counts, no ignored cases, and a successful runner completion; zero-case,
partial and stale reports fail. Checks against older JSVM/QoS/Vibrator logs only
establish parser compatibility, not new-package E2E results.

The profile policy records all protected official SysCaps as
`required_official_syscaps`, explicit QEMU requirements, and any required
positive SysCap overrides. Packaging and `verify_device_contract.py` require
positive declarations, not just absence of the excluded caps. A consistent
JSON/parameter pair that omits a required cap still fails. These are policy and
declaration gates only; API behavior must still pass on the newly packaged guest.

## AccessToken kernel bitmap ABI and authorization

`common/kernel/linux/linux_6_6/access_token_abi` patches the real switch
dispatcher, not only ioctl numbers. It snapshots the bitmap under the read
lock and fixes the single-query use-after-unlock race. Exact old-header
migration is SHA-bound; idempotence is also reverse-checked, not inferred from
a marker. `kernel_spm_handshake` selects SPM only after a successful v1
handshake; unimplemented enhanced SPM/refcount commands are not success stubs.

```sh
python3 ci/capability-audit/test_access_token_kernel.py
python3 ci/capability-audit/test_access_token_probe.py
python3 ci/capability-audit/test_verify_access_token_results.py
bash ci/capability-audit/build_access_token_probe.sh --arch arm64 --output /path/to/probe
# On the NEW guest as root; reserved invalid token only, with cleanup:
access_token_kernel --privileged NEW_32_HEX_RUN_ID
# Separately under a real ordinary-app UID (never root or ATM/3020):
access_token_kernel --unprivileged DIFFERENT_32_HEX_RUN_ID
python3 ci/capability-audit/verify_access_token_results.py --archive /path/to/NEW.tar.gz \
  --log /path/to/complete-jsonl.log --arch arm64 --mode privileged \
  --run-id NEW_32_HEX_RUN_ID --probe-exit-code ACTUAL_GUEST_EXIT_CODE \
  --output /path/to/result.json
```

Repeat for `armv7a`/`x86_64` and both profiles as their new packages become
available after the first-package gate. This checks the 260-byte compat ABI,
every bit, grant/revoke, bad pointers/opcodes, removal/re-add concurrency,
ordinary-user authorization and truthful unsupported SPM. Device access
denial is reported separately from ioctl denial. Capture the actual guest
process exit code, not only `hdc`'s exit code. Mock/sanitizer tests and
cross-compiled binaries do not satisfy the runtime or six-package gate, and
these results do not prove all AccessToken APIs or enhanced SPM implemented.

The same kernel component now stores/reads the actual task `user_id`; it does
not synthesize zero or relax the root/ATM mutation check. AppSpawn sets it
before dropping root and propagates failures. Its common implementation calls
the real ioctl even when `appspawn_custom_sandbox=false`; a successful weak
no-op is not accepted. Validate it separately:

```sh
# NEW guest root: the final argument is unused by the root role.
access_token_userid --privileged NEW_32_HEX_RUN_ID 0
python3 ci/capability-audit/verify_userid_results.py --archive /path/to/NEW.tar.gz \
  --log /path/to/root-userid.jsonl --arch arm64 --mode privileged \
  --run-id NEW_32_HEX_RUN_ID --probe-exit-code ACTUAL_PROCESS_EXIT \
  --output /path/to/root-userid-result.json
python3 ci/capability-audit/build_hap_probe.py --userid-only --arch arm64 \
  --probe-run-id DIFFERENT_NEW_32_HEX_RUN_ID --udid sign-after-new-boot \
  --output /path/to/userid-app
# Sign/install as an ordinary app; pull its freshly truncated userid-results.log.
python3 ci/capability-audit/verify_userid_results.py --archive /path/to/NEW.tar.gz \
  --log /path/to/app-userid.jsonl --arch arm64 --mode unprivileged --app-context \
  --run-id DIFFERENT_NEW_32_HEX_RUN_ID --expected-user-id ACTUAL_OS_ACCOUNT_ID \
  --probe-exit-code ACTUAL_NATIVE_RETURN --output /path/to/app-userid-result.json
```

Root covers real roundtrip, fork inheritance/child isolation, input/output and
read-only copyout boundaries, then restores its original task state. The
ordinary HAP independently queries the account service, requires the actual
AppSpawn-assigned ID to match, rejects self-retagging, and records the native
return value (not an assumed process exit) after closing the log. Its host
challenge is frozen into the HAP and recorded in `userid-probe-inputs.json`.
Device-open denial is a failure here, unlike the separate bitmap authorization
test. Neither test proves parent-HAP-token mapping or enhanced SPM support.

## Kernel patch freshness

For the isolated NEW guest's root bitmap, user-ID and real HDI checks, use
`run_root_probe.py` to collect fresh logs and actual guest exit status:

```sh
python3 ci/capability-audit/run_root_probe.py --kind bitmap \
  --archive /path/to/NEW.tar.gz --probe /path/to/access-token-kernel-arm64 \
  --arch arm64 --device phone --target 127.0.0.1:5681 --output /path/to/NEW-root-bitmap-run
# Repeat with --kind userid / --kind vibrator-hdi and their respective executables.
# Use a PRIVATE foreground HDC server; do not reset a shared user's server.
# hdc -s 18710 -m
# For standalone commands only, prefix with OHOS_HDC_SERVER_PORT=18710 if using that server.
# validate_packaged_qemu.sh instead owns an isolated foreground server and TMPDIR,
# records <evidence-output>.hdc/transport.json, and never restarts a shared server.
# Graphics kinds: vulkan-device / vulkan-headless / vulkan-ohos-surface / gles.
python3 ci/capability-audit/run_root_probe.py --kind permission-registry \
  --definitions /path/to/pinned-permission-definitions.json \
  --archive /path/to/NEW.tar.gz --probe /path/to/permission_registry \
  --arch arm64 --device phone --target 127.0.0.1:5681 --output /path/to/NEW-permissions-run
python3 ci/capability-audit/run_root_probe.py --kind audio-suite \
  --archive /path/to/NEW.tar.gz --probe /path/to/audio-suite-arm64 \
  --arch arm64 --device phone --target 127.0.0.1:5681 --output /path/to/NEW-audio-suite-run
```

The output directory must not already exist. The runner checks the selected
package/ELF/guest architecture and profile, transfers only the executable,
compares its guest SHA-256, clears injected library variables and captures an
unambiguous, fresh process-exit envelope rather than relying on HDC's exit.
Timeout/failure evidence is retained; privileged probes are never auto-replayed.
The caller must have booted this selected archive. The runner does not attest
that relationship or mark the complete first-artifact gate passed. Ordinary
HAPs, permission boundaries and UI/data paths still need their separate tests.

Permission input names are source/hash bound and independently checked after
transfer. Compare all source policies, including device-restricted absence;
unknown nonempty `invalid!` is a valid unknown name (12100007), not a validation
error. Empty or over-256-byte names require 12100001. Never accept arbitrary
errors as an absent permission or weaken APL/grant metadata.

Before rebuilding the common sandbox fix, `compile_appspawn_userid.py` can
check it with each product's actual Ninja clang command and system headers:

```sh
python3 ci/capability-audit/compile_appspawn_userid.py \
  --source-root /path/to/openharmony --product arm64_virt \
  --patch patches/common/base/startup/appspawn/kernel_user_id/0002-store-user-id-without-custom-sandbox.patch \
  --output /path/to/appspawn-compile.json
```

It patches only scratch copies and requires a strong `SetUserId` symbol in
the compiled common object. Repeat for `armv7a_virt`/`x86_64_virt`; these checks
do not prove ordinary-app account isolation in a packaged guest.

The upstream GN action depended only on the top-level kernel directory. A
nested driver/config patch did not invalidate its mtime, so even forcing the
inner script's rebuild flag could leave Ninja reusing an old Image. The
`kernel_build_dependencies` component adds a deterministic fingerprint of
eight actual input roots, prepared after all patches and before traversal.
Only an executed successful build can certify Image and the twelve modules.
Packaging verifies the current inputs/artifacts and includes
`kernel-source-inputs.json` / `kernel-inputs.json`; delivery verification checks
the actual packaged Image against those hashes. These are build-provenance
checks, not boot or behavior evidence. A new archive must still pass the
representative-artifact runtime gate before the remaining five builds.

## Device-specific permission policy

`device_type=2in1` alone does not select the AccessToken PC policy: the upstream
generator uses `target_platform`, whose GN default is phone. Managed builds
now explicitly pass phone/pc and packaging records `permission-profile.json`.
`patches/lib/permission_profile.py` requires every generated permission and
original APL, grant mode, ACL/provision, kernel and value flags to match the
pinned source's device restrictions, including the two ATM internal permissions.
No permission levels or global grants are changed. `audit_permissions.py` also
requires `--source-definitions` so a shared SysCap does not misclassify PC-only
permission absence on phone as a missing privilege. API boundary cases remain
unverified until called; legacy Sensor permission names are not automatically
invented or treated as aliases.

Build the read-only registry probe inside the Linux source environment:

```bash
python3 ci/capability-audit/build_permission_probe.py --source-root /path/to/openharmony \
  --arch arm64 --output /path/to/permission-probe
# Transfer executable and permission-names.txt to the NEW guest, then run:
permission_registry /data/local/tmp/permission-names.txt NEW_32_HEX_RUN_ID
python3 ci/capability-audit/verify_permission_results.py --archive /path/to/NEW.tar.gz \
  --definitions /path/to/permission-probe/permission-definitions.json --device phone \
  --results /path/to/actual-guest-results.log --run-id NEW_32_HEX_RUN_ID \
  --probe-exit-code ACTUAL_EXIT_CODE --output /path/to/permission-results.json
```

The innerkit probe uses the actual system toolchain and libc++ ABI, queries
every source definition without creating tokens or granting rights, and checks
absent/invalid/empty-name boundaries. Results require a fresh run ID, complete
footer, exact ordered records and successful process exit. This establishes
registration/metadata only, not caller authorization or all associated APIs.

## Vibrator time backend and application path

The virtual VDI advertises only time-sequence support, not HD effects,
primitive mapping or intensity/frequency modulation. Composite delays are
between event starts, and the upstream transform's final zero-duration stop
marker is valid. Invalid/overflowing input must not change an existing run.

```bash
python3 ci/capability-audit/build_vibrator_hdi_probe.py \
  --source-root /path/to/openharmony --arch arm64 --output /path/to/vibrator-hdi
# Transfer only the executable, not substitute shared libraries, to the NEW guest.
vibrator_hdi NEW_32_HEX_RUN_ID
python3 ci/capability-audit/verify_vibrator_hdi_results.py \
  --archive /path/to/NEW.tar.gz --probe /path/to/vibrator-hdi/vibrator_hdi \
  --log /path/to/actual-hdi.jsonl --arch arm64 --run-id NEW_32_HEX_RUN_ID \
  --probe-exit-code ACTUAL_GUEST_PROCESS_EXIT --output /path/to/hdi-result.json
```

The fourteen ordered cases call the real HDI IPC interface as root. They require
observable running/cancel/expiry state, the final stop marker, no double-counted
timeline, known/unknown preset behavior, wrong-device and malformed-input boundaries, truthful unsupported
modulation, and cleanup. Fresh run IDs, exact records and actual exit status
are required. This is not permission or JSON-decoder evidence: additionally run
the strict `ohos-native-bindings` Vibrator tests as an ordinary application.
An API returning success after merely queuing work is not backend validation.

## Manual permission settings on 2in1

The pinned client requires `com.ohos.permissionmanager.OpenSettingAbility`,
the single-permission request key `ohos.open.setting.permission`, and the
result key `ohos.open.setting.result_code`. The new component preserves the
older array-based PermissionStateSheet protocol rather than aliasing it.
Only the pinned PC/tablet manual-settings permissions are accepted; phone
does not receive extra PC permissions.

Host model/lifecycle tests and the isolated full-system-API compile check do
not establish runtime success. On the newly packaged 2in1 system provider,
verify actual caller identity and declared permission, a parented modal UI,
explicit Allow plus a real grant/status query, Cancel/back without a grant,
already-granted/unsupported/undeclared results, and stale-token, duplicate
click, close/reuse and concurrent-session boundaries. Internal failures must
not return success. Never install the compile-only HAP
`org.harmonycontrib.permissioncompile` as a substitute system provider.

## Real-time OHAudio is separate from AudioSuite

The original 2026-10-05 new ARM64 phone package passed AudioSuite PCM, but a
normal non-system HAP reproduced real AudioRenderer Start=2 in both create/
release cycles. Do not treat builder creation or a queued Start as playback.
HDI reinitialization logs showed `snd_ctl_open("hw:0")` failure: the fixed ALSA
library defaults to an empty global config and the complete vendor config tree
was not packaged. The repair pairs the existing config-enable feature with
all 79 fixed upstream config files in the chipset image. Empty local ALSA
product entries are moved to shared board inheritance, without relaxing the
generic local-shadow guard. This remains pending newly packaged runtime tests.

```bash
python3 scripts/verify_alsa_config_image.py --vendor-image /path/to/NEW/images/vendor.img \
  --machine 183 --output /path/to/NEW-alsa-config.json

python3 ci/capability-audit/build_hap_probe.py --arch arm64 --audio-stream-only \
  --probe-run-id NEW_32_HEX_RUN_ID --udid REAL_GUEST_UDID --output /path/to/audio-hap
# Sign with sign_web_probe.py as a NORMAL, non-system HAP; do not elevate it.
# With a dedicated HDC server/target, install this HAP. Require its unique
# audio-stream-RUN_ID-results.log to be absent BEFORE starting EntryAbility.
# Save the real bm dump applicationInfo (normal, isSystemApp=false, actual UID),
# then receive the completed native JSONL result from the normal app filesDir.
python3 ci/capability-audit/verify_audio_stream_results.py \
  --archive /path/to/NEW.tar.gz --results /path/to/native-results.jsonl \
  --application-identity /path/to/bm-dump.json --run-id NEW_32_HEX_RUN_ID \
  --output /path/to/NEW-audio-result.json
```

Use machine 40/62 and the corresponding armv7a/x86_64 HAP for those packages.
The probe writes actual nonzero stereo S16LE PCM in real callbacks, tracks
atomic counters, checks frame progression in two separate create/release
cycles, and covers pause/flush/resume plus null/invalid-channel/state boundaries.
Every recorded call is evaluated before logging its output. It runs off the UI
lifecycle thread, uses an explicit host challenge and refuses overwriting a
previous native log. The verifier independently checks all 71 ordered rows,
identity, both PCM progress phases and original package checksum; it rejects
incomplete/stale runs and false-success summaries.

None of these results certify Capturer input, algorithm plugins, or physical
host audio. QEMU's default `none` backend is an intentional virtual endpoint;
audible playback and microphone/sample fidelity require separate evidence.
The package checker is offline config/ABI evidence, not audio behavior or the
full first-artifact acceptance gate.

## Real kernel BPF data path

`bpf_syscall.c` calls the real kernel syscall, not a mock service. It validates
map metadata and challenged readback, malformed access, and actual loopback UDP
packets: attach a drop program, observe no payload within a bounded timeout,
replace it with an allow program, and verify the exact fresh challenge bytes.
The probe closes its descriptors and does not pin objects or change service
firewall rules. Build it with the actual NDK for each target ABI:

```bash
bash ci/capability-audit/build_access_token_probe.sh --arch arm64 \
  --output /path/to/kernel-probes
OHOS_HDC_SERVER_PORT=DEDICATED_PORT python3 ci/capability-audit/run_root_probe.py \
  --kind bpf --archive /path/to/NEW.tar.gz \
  --probe /path/to/kernel-probes/bpf_syscall --arch arm64 --device phone \
  --target GUEST_TARGET --output /path/to/bpf-result
```

Require all 23 ordered cases, matching fresh run ID, exact values and native
process exit status. The runner records the archive and probe checksums; the
caller must separately attest that this archive booted the selected guest.
This root-only kernel result does not certify NetManager statistics, 2in1
NetFirewall, System VPN, ordinary-HAP permissions, or the full first-package
behavior gate. Repeat on each newly packaged architecture/profile.

## Real software AVC, not a library-presence pass

Build the pinned M144 OpenH264 wrapper dependency independently of the six
QEMU artifact matrix. This compiles only the real library, not QEMU packages:

```bash
QEMU_AVC_ARTIFACTS=/path/to/avc-m144 bash scripts/build_m144_avc_encoder.sh arm arm64 x86_64
python3 patches/lib/avc_artifacts.py --artifact-root /path/to/avc-m144 --arch arm arm64 x86_64
```

Full build launchers require `QEMU_AVC_ARTIFACTS` (default under CACHE_ROOT),
matching the pinned source/ABI, current adapter, actual ELF and runtime notices.
The AVCodec component installs the backend, provenance and all four notices.
An independent `avc_eos` component first repairs stale EOS buffer size/PTS and
backend error propagation; the backend installer refuses an unknown wrapper
or missing EOS repair. The native HAP's header + four frames exceeds the pinned
four-output-buffer pool before EOS, so it must exercise actual reuse.
`verify_avc_backend_image.py` inspects the actual system image; neither this
check nor the real host OpenH264 encode/decode test establishes guest success.

```bash
python3 scripts/verify_avc_backend_image.py --system-image /path/to/NEW/images/system.img \
  --machine 183 --output /path/to/NEW-avc-dependency.json
python3 ci/capability-audit/build_hap_probe.py --arch arm64 --sdk /path/to/API26-SDK \
  --avc-media-only --apl normal --probe-run-id NEW_32_HEX_RUN_ID \
  --udid REAL_GUEST_UDID --output /path/to/avc-hap
# Sign with sign_web_probe.py, retaining signCode=1, normal non-system identity.
# Use the pinned Linux signer if macOS Java rejects native code-sign ZIP64.
# Require the challenged filesDir log to be absent before EntryAbility starts.
python3 ci/capability-audit/verify_avc_media_results.py --archive /path/to/NEW.tar.gz \
  --results /path/to/avc-media-RUN_ID-results.log --run-id NEW_32_HEX_RUN_ID \
  --application-identity /path/to/actual-bm-dump.json --output /path/to/NEW-avc-media-result.json
```

The HAP calls public software AVCodec APIs, not the backend's private C exports.
It tests Baseline/Main, CBR/VBR/CQ, two independent create/destroy cycles for
each combination, actual parameter sets/profile, dynamic bitrate, requested
IDR, challenged Y-plane pixels/PTS, full decoder drain/EOS and null boundaries.
Callbacks are bounded and retain their storage on failed destruction; a
unique native log is created without overwriting prior runs. The verifier
requires all 437 records and all 48 actual decoded frames plus normal BMS UID.
Transport timeouts, codec creation alone, a host decode, or a root process do
not satisfy this ordinary-app test. This does not certify hardware codecs,
HEVC, mathematical CBR conformance, video effects or Audio Vivid/AudioSuite
plugins, and does not by itself unlock the first-artifact behavior gate.

To check the real debugfs extraction/ABI path before a full image exists:

```bash
python3 ci/capability-audit/check_avc_image_fixture.py --artifact-root /path/to/avc-m144 \
  --mke2fs /path/to/mke2fs --output /path/to/offline-fixture-result.json
```

This uses the actual three-ABI libraries/notices in temporary tiny ext2 fixtures,
and checks that deleting a required notice is rejected. It does not build a
QEMU artifact, boot a system, or establish any guest API behavior.

## Public AudioSuite DSP effects, separate from PCM and real-time audio

The `audio_suite_dsp` component builds a real CPU implementation for the ten-band
equalizer, four sound-field modes and four environment effects. It routes only
these three nodes; it does not replace absent AI/cloud plugins with successful
no-ops. Host sanitizer tests, source flags compilation and XML/library presence
are not ordinary-app pipeline acceptance.

```bash
python3 scripts/verify_audio_suite_dsp_image.py \
  --system-image /path/to/NEW/images/system.img --machine 183 \
  --output /path/to/NEW-dsp-package-check.json
python3 ci/capability-audit/build_hap_probe.py --arch arm64 --sdk /path/to/API26-SDK \
  --audio-suite-effects-only --apl normal --probe-run-id NEW_32_HEX_RUN_ID \
  --udid REAL_GUEST_UDID --output /path/to/dsp-hap
# Sign with sign_web_probe.py; actual code-sign/digest/permission verification
# is mandatory. Install as a normal, non-system HAP on the NEW packaged guest.
# Require audio-suite-effects-RUN_ID-results.log absent before EntryAbility
# starts, and save actual bm dump applicationInfo with UID/isSystemApp/APL.
python3 ci/capability-audit/verify_audio_suite_effects_results.py \
  --archive /path/to/NEW.tar.gz --results /path/to/native-results.jsonl \
  --application-identity /path/to/bm-dump.json --run-id NEW_32_HEX_RUN_ID \
  --output /path/to/NEW-dsp-result.json
```

Use machine 40/62 and matching armv7a/x86_64 HAP for the other ABIs. The public
API-only HAP creates and destroys 36 complete pipelines in two cycles, tests all
ten EQ bands and all eight field/environment modes, and records actual PCM
energy, parameter round trips and rejection/state boundaries. The independent
verifier requires all 1359 ordered records, matching native/app UID and a fresh
challenge, recomputes the challenged input waveform energy and checks actual
output energy/gain. No private DSP export or injected library is used by this HAP.
This validates neither noise reduction, separation, voice/tempo/pitch,
spatial/HOA, download support, nor real-time Renderer/Capturer or physical audio.
It does not itself unlock the full representative-artifact behavior gate.

## Public Camera preview and photos

Phone retains its required Camera capability. The opt-in Vivid kernel producer
provides a real V4L2 capture device; the USB VDI selector accepts its bounded
driver/card/bus identity without pretending that it is USB. Three-ABI Kconfig,
driver objects, HAL/VDI compilation and SDK HAP builds are separate from runtime.

```bash
python3 ci/capability-audit/build_hap_probe.py --arch arm64 --sdk /path/to/API26-SDK \
  --camera-only --apl normal --app-feature normal --probe-run-id NEW_32_HEX_RUN_ID \
  --udid REAL_NEW_GUEST_UDID --output /path/to/camera-hap
# Sign/fully verify as a normal, non-system app with user CAMERA permission only.
# Install on the NEW packaged phone. Require all challenged result/JPEG files
# absent before launching. Approve the actual user permission dialog, not a
# privileged grant. Capture bm dump applicationInfo, both completed JSONL logs,
# and camera-RUN_ID-c{1,2}-p{1,2}.jpg from the application's private filesDir.
python3 ci/capability-audit/verify_camera_results.py \
  --archive /path/to/NEW.tar.gz --native-results /path/to/native-results.log \
  --arkts-results /path/to/arkts-results.log --photo-root /path/to/pulled-files \
  --application-identity /path/to/bm-dump.json --run-id NEW_32_HEX_RUN_ID \
  --arch arm64 --output /path/to/NEW-camera-result.json
```

The public C++ NDK checks invalid/state boundaries and two complete preview
create/start/callback/stop/release cycles. ArkTS 1.1 requests real user consent,
then recreates two photo sessions and captures four timestamped JPEGs. The host
independently decodes those actual files and checks their dimensions and sampled
pixels against the app, rejecting blank, stale, missing or mismatched payloads.
Neither callbacks nor photo pixels prove visible compositor preview: collect
that separately while the preview is active. Video and advanced modes also need
separate tests. Synthetic photos only test the verifier; no first-package gate
is unlocked by this tool alone. 2in1's non-required Camera remains undeclared.

## CertificateManager empty-result regression

The default package suite runs `run_certificate_probe.py` on its exact new
archive/boot ID. A dedicated system HAP requests only the two documented
certificate permissions; the separate normal HAP has no ACLs or permissions.
Actual signed-profile verification and BMS identity checks are mandatory. This
does not alter the image permission table or grant system privileges to normal
apps. The system run checks empty promise/callback/own lists, two own test-PKCS12
import/query/uninstall cycles, invalid format/password/alias/URI errors and 64
repeat empty queries. The normal run must be denied on all four valid calls.
Only this probe's own returned import URI may be deleted, never all credentials.
Unexpected install success is recorded before cleanup, so a cleanup permission
error cannot manufacture a passing denial. A signed or compiled HAP, mock NAPI
test, or old guest result does not close the original audit finding.
