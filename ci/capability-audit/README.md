# OpenHarmony capability audit

This audit treats the complete capability list as the work queue. It does not
infer runtime support from `syscap.json`, a library, a System Ability profile,
or an XTS source file.

Generate the index from the exact `syscap.json` files extracted from the two
representative ARM64 images. Always pass fresh `OpenHarmony-7.0-Release`
documentation and interface-sdk-js worktrees; the main OpenHarmony checkout may
lag those repositories:

```bash
python3 ci/capability-audit/build_matrix.py \
  --ohos-root /Volumes/PSSD/qemu/openharmony \
  --docs-root /path/to/latest/openharmony-docs \
  --sdk-js-root /path/to/latest/interface-sdk-js \
  --phone-syscap /path/to/phone-syscap.json \
  --two-in-one-syscap /path/to/2in1-syscap.json \
  --findings ci/capability-audit/known-findings.json \
  --output-dir docs/capability-audit
```

The generated artifacts have separate purposes:

- `all-capability-matrix.csv/json`: every public SysCap found in the OHOS 7
  SDK, docs, API annotations, XTS metadata, bundles, or runtime images;
- `advertised-capability-matrix.csv/json`: every capability declared by either
  image or required by the official phone/2in1 SDK profile;
- `ohos-public-syscap-registry.json`: the union of SDK profiles, API
  annotations, bundle declarations, XTS metadata, and image declarations;
- `method-device-boundaries.csv/json`: every OHOS 7 reference-document entry
  containing an explicit device behavior difference;
- `summary.json`: completeness counts. A capability remains
  `runtime_validation_required` until a real application or native API probe
  supplies behavioral evidence.

Build the HAP from the same latest interface API directory. The probe calls
`canIUse` for every row in `all-capability-matrix.json`, probes every public
module entry (`@ohos.*`, legacy `@system.*`, and `@kit.*`), and performs
targeted behavior checks. `permissions.d.ts` and the ArkTS language builtins
are declarations rather than OHOS module entry points, so they are kept out of
the runtime module count:

The compiler SDK must contain the same `api/@ohos*.d.ts`, `api/@system*.d.ts`,
and `kits/@kit*.d.ts` revision passed below. A nominally API 26 DevEco SDK may
still lag the current `OpenHarmony-7.0-Release` declarations; using that older
copy would make the audit HAP fail to compile newer API 26 probes.

```bash
python3 ci/capability-audit/build_hap_probe.py \
  --arch arm64 \
  --udid DEVICE_UDID \
  --syscap-registry docs/capability-audit/all-capability-matrix.json \
  --api-dir /path/to/latest/interface-sdk-js/api \
  --kits-dir /path/to/latest/interface-sdk-js/kits \
  --output /tmp/ohos-capability-hap
```

Analyze each device independently, then build the one-row-per-SysCap ledger:

```bash
python3 ci/capability-audit/analyze_syscap_runtime.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --device phone --probe-log /path/to/phone-results.log \
  --output docs/capability-audit/runtime/arm64-phone/syscap-runtime.json

python3 ci/capability-audit/analyze_arkts_modules.py \
  --sdk /Applications/DevEco-Studio.app/Contents/sdk/default/openharmony \
  --api-dir /path/to/latest/interface-sdk-js/api \
  --profile phone --probe-log /path/to/phone-results.log \
  --output docs/capability-audit/runtime/arm64-phone/arkts-module-load-latest.json

node ci/capability-audit/analyze_arkts_exports.js \
  --typescript /path/to/typescript/lib/typescript.js \
  --api-dir /path/to/latest/interface-sdk-js/api \
  --kits-dir /path/to/latest/interface-sdk-js/kits \
  --runtime docs/capability-audit/runtime/arm64-phone/arkts-module-load-latest.json \
  --output docs/capability-audit/runtime/arm64-phone/arkts-export-surface-latest.json

python3 ci/capability-audit/build_coverage_ledger.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --output docs/capability-audit/capability-coverage-ledger.json

python3 ci/capability-audit/verify_results.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --ledger docs/capability-audit/capability-coverage-ledger.json \
  --api-dir /path/to/latest/interface-sdk-js/api \
  --kits-dir /path/to/latest/interface-sdk-js/kits
```

The inventory and surface scan are complete only when the strict verifier
passes. That does not mean every API behavior has been proven. A behavioral
audit is complete only when:

1. no declared or officially expected capability remains
   `runtime_validation_required`;
2. every `review_required` method/device boundary has been classified;
3. successful probes validate observable behavior, not only return values;
4. phone and 2in1 results are recorded separately;
5. architecture-sensitive backends are checked on arm64, armv7a, and x86_64.

For a multi-package change, build and boot one ARM64 representative artifact
first. Validate every changed behavior and its device boundary before building
the remaining architectures and device packages. Keep the per-package logs and
checksums with the audit evidence.
