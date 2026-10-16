# Runtime tool repair 02

The original LinuxSDK39 live build failed00304029 because an `externalNativeOptions`
object containing only `abiFilters` still selected the CMake task. The native SDK
compile had already succeeded. The generator now uses the plain stage entry
profile and packages that actual precompiled library from
`entry/libs/<actual ABI>/libliveinputaudit.so`. Its source contract separately
checks the ABI/triple/prebuilt library path. No CMake placeholder or check bypass
is added. ETS and permissions are unchanged. The original failure log is untouched;
`original-SDK02-cmake-failure.json` binds its SHA and exact relevant lines.

All three product helpers actually compiled and linked in root batch01. That
original report remains **fail**. Its ELF reader executed as `llvm-readobj`
because the builder resolved the `llvm-readelf` symlink before selecting argv0.
The existing parser only understood GNU symbol rows and parenthesized NEEDED
tags. Both formats now require an actual defined CFI symbol and actual dynamic
dependency rows. `original-receipt.json` binds the original report/logs and
verbatim selected LLVM output. `actual-log-parser-replay.json` shows the original
function rejecting and the new function accepting those same recorded rows.

The 25 helper tests and20 live tests pass. These are Python metadata/parser/control
flow tests. They neither execute a guest nor establish that the linked product
DSOs passed the new reader. Actual SDK metadata was read for source-only project
generation; its contract and plain entry profile are saved here.

## Root's read-only artifact recheck

Use the frozen repaired repository at `/work`, the same stable `/ohos` and
`/ohos/out` **read-only**, and the original helpers directory **read-only** at
`/evidence/helpers`. A fresh sibling output is required. Under root's lease:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 /work/ci/capability-audit/batch_system_build_runtime_helpers.py \
  --source-root /ohos --product arm64_virt \
  --verify-existing /evidence/helpers/build.json \
  --existing-report-sha256 b2d5d610217aa173d7b8e2837f0bd9208cda59fe273fbd44c94df4d1276194ba \
  --output /evidence/helpers-recheck-02
```

This mode never invokes Ninja, clang, a linker or a guest executable. It verifies
the old full command/log receipts, all recorded source/header/DSO hashes, and
the old binary/source/guard/dependency-file hashes. Input mount/path identity
must match the old receipt; it fails rather than rebasing a changed source/out.
It captures object hashes and explicitly records that the old report contained
no object hash. The independently captured object hashes are in
`original-receipt.json`; they are new observations, not compile-time witnesses.

Only the actual ELF reader can run in this mode. It checks the three immutable
PIEs, required DT_NEEDED bindings, and the direct product libraries previously
not reached after the parser rejection. AccessToken must still define its actual
cross-DSO CFI symbol. All helpers are collected before returning failure. Logs,
all current input hashes, prior failure status, old command receipts, new symbol
checks, and unchanged-input checks go into the **new** `build.json`.

A recheck pass means compile/link receipt and ELF contract validation only.
No original failure report is rewritten. SDK retry, legitimate normal signing,
same new archive/boot callbacks, and the representative package behavior gate
remain root's pending integration checks. No requirement is closed by this batch.
