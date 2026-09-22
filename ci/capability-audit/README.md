# OpenHarmony capability audit

This audit keeps four questions separate for every phone and 2in1 API:

1. Is the API documented for the device?
2. Does the image declare the SysCap and register every required permission?
3. Is the ArkTS or Native surface present?
4. Does a real call reach a working service, kernel, or virtual-hardware backend?

`canIUse()`, a packaged library, and a registered System Ability are evidence
for different layers. None of them alone proves an API is usable.

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

## Runtime and ABI stages

Build and run the HAP probe with the same latest JS declarations:

```bash
python3 ci/capability-audit/build_hap_probe.py \
  --arch arm64 \
  --udid DEVICE_UDID \
  --syscap-registry docs/capability-audit/all-capability-matrix.json \
  --api-dir /path/to/interface-sdk-js/api \
  --kits-dir /path/to/interface-sdk-js/kits \
  --output /tmp/ohos-capability-hap
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

The verifier proves that the surface inventory and classifications are
complete. Its success status is deliberately
`complete_surface_inventory_behavior_pending`; it does not turn uncalled APIs
into verified behavior.

For a multi-package change, build and boot one ARM64 representative artifact
first. Validate every changed behavior and device boundary before building the
remaining architectures and products. Keep per-package logs and checksums.
