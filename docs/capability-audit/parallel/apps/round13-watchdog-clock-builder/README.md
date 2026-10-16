# Isolated SDK39 watchdog clock CLI builder

This batch adds only `ci/capability-audit/build_watchdog_clock_probe.py`, its
dedicated host test and these docs. Media owns the actual C/clock result parser.
Root owns SDK execution, guest observations before/after suspension, cleanup,
package and first-artifact gates. No product source, product library, HAP,
shared suite or SDK directory is changed. No real compiler or CLI was executed
in this agent batch.

The required C is Media commit `0f1f4eef8789f74cc07d3b249dabb17673b1ec98`,
`ci/capability-audit/watchdog_clock_probe.c`, SHA256
`c5c027cf3bc2c70476b1293d4f60789f5f8bf45080d1685f3d8efc289c32aa6c`.
It must be present beside the builder when root executes the actual build.
The C uses only libc and has no fallback for `CLOCK_BOOTTIME`. The builder
does not modify that source or infer runtime clock values from host time.

## Fixed build interface

```text
python3 ci/capability-audit/build_watchdog_clock_probe.py
  --sdk <actual SDK39 native directory>
  --source <immutable host-absolute frozen watchdog_clock_probe.c>
  --output <new, nonexistent host-absolute output directory>
```

`--sdk` contains `llvm/bin/clang`, `llvm/bin/ld.lld`,
`llvm/bin/llvm-readelf`, `sysroot`, `oh-uni-package.json` and
`build/cmake/ohos.toolchain.cmake`. The input mount must actually be read-only.
The original native metadata must declare path `native`, API `26`, version
`26.0.0.39` and platform `26.0.0`. The host SDK105 was only read as a reference;
it is rejected as an SDK39 substitute. SDK39 has not yet been inspected or
compiled by this agent.

Both the provided frozen C and the current repository C beside the builder
are hashed before/after and must match. Root must bind the frozen C at its
actual host absolute path, as well as the output parent, so the original
recorded source path remains independently readable on the host. Do not pass
a source path existing only under container `/work` or `/ohos`. There is no
path-map substitution. The builder does not copy/relabel arbitrary source as
the approved clock probe.

The builder always processes `arm64`, `armv7a`, `x86_64` sequentially. The
triples are `aarch64-linux-ohos`, `arm-linux-ohos`, `x86_64-linux-ohos`. ARMv7
adds `-march=armv7-a -mfloat-abi=softfp -mfpu=neon`, matching the existing native
SDK callers' base/softfp convention; it also requires the actual SDK toolchain
to contain the ARM target and equivalent `-march=armv7a`/`armv7-a` setting.
The original SDK toolchain bytes/hash are retained. No SDK or product flags are
modified, and this standalone C helper neither requires business CFI nor
replaces a product DSO.

Each ABI gets its own object, dependency file, PIE executable and three logs:

```text
<output>/<arch>/watchdog_clock_probe.o
<output>/<arch>/dependencies.d
<output>/<arch>/watchdog_clock_probe
<output>/<arch>/compile.log
<output>/<arch>/link.log
<output>/<arch>/readelf.log
```

Compile and link are separate actual clang invocations with `-v`. Compile uses
`-MD -MF -MT`, `-std=c11 -O2 -g -Wall -Wextra -Werror -fPIE`; link uses the
actual SDK lld, PIE, RELRO/NOW and no undefined symbols. Header dependencies
must include `time.h`, `stdio.h`, `stdint.h`, `inttypes.h`, reside in the actual
SDK, and retain original plus canonical paths, size and SHA256. Headers and
source/tool inputs must remain identical after compilation/linking. The
compiler, linker, readelf, native metadata, toolchain, builder and C hashes are
recorded before and after the batch.

The actual SDK `llvm-readelf -h -l -d -W <binary>` is invoked without resolving
its argv[0] symlink to `llvm-readobj`. The raw exit/log hash is retained. The
Python ELF reader independently parses the full ELF32/64 header and all program
headers, requires a file-backed executable entry, correct ABI/EABI calling
convention, exactly one proper `/lib/ld-musl-{aarch64,arm,x86_64}.so.1`
interpreter, real loaded PT_DYNAMIC/string table and exactly `DT_NEEDED libc.so`.
RPATH/RUNPATH/TEXTREL, missing/ambiguous loaded ranges, truncated headers,
incorrect entry or host loader are failures. Actual readelf class, machine,
interpreter and NEEDED output must agree with the bytes.

Each command has a bounded 120-second timeout; a timed-out command's process
group is terminated/killed and the failure log remains. A failed ABI does not
prevent the remaining ABIs from being attempted. A dependent link/readelf is
not invented if compile/link failed. Invalid global SDK/source input produces
a failed receipt with three explicitly blocked rows. No old output directory
is overwritten, and no previous failed receipt is changed to a pass.

## `build.json` receipt and independent host verification

Top-level `schema_version=1`, `scope`, `sdk`, `source`, `output`,
`inputs_before/inputs_after`, current C records, frozen SDK metadata/toolchain
descriptors, `architectures`, `errors`, `runtime_validated=false` and
`first_artifact_behavior_gate_passed=false` are recorded. Every ABI row contains
its `commands` (compile/link/readelf argv, cwd, exit, timeout, start/end and log
descriptor), dependency file, original SDK header records, object/binary
descriptors and complete parsed ELF metadata. Only three successful ABI rows,
all actual commands exit0, valid ELF/header evidence and stable inputs produce
`status="pass_build_ONLY"`. Any failure leaves top-level status `fail` and
retains each ABI's real error/log/exit. No guest behavior is claimed.

The root boot observer can use this public, read-only API:

```python
import build_watchdog_clock_probe
verified = build_watchdog_clock_probe.verify_build(
    binary=<output>/<actual_arch>/watchdog_clock_probe,
    receipt=<output>/build.json,
    arch='arm64',  # or armv7a / x86_64
)
```

It independently re-reads the original frozen C path, current repository C,
current builder, entire receipt, all three ABI original command logs, object
and binary bytes, dependency files and the local frozen SDK metadata/toolchain
copies. It reconstructs exact command plans and reparses the local ELF files.
It rejects a self-reported pass without complete successful raw evidence,
changed/missing source/log/output, different argv[0], another ABI, incomplete
batch, foreign headers or inconsistent metadata. The root observer should save
the complete returned dictionary and require exact equality on re-verification.

The return value contains `binary` and `receipt` descriptors (`path`, `sha256`,
`size`), `source_sha256`, `arch`, `scope`, `verified_build_arches`,
`runtime_validated=false`, `first_artifact_behavior_gate_passed=false`,
`SDK_tools_and_headers_re_read_on_host=false` and
`original_Linux_SDK_inputs_SHA_bound_to_receipt=true`. The original Linux SDK
paths and hashes are preserved. The host adapter does **not** open or pretend
to re-read an inaccessible `/ohos` compiler/header. It checks the original
Linux builder's fixed-source/command/hash receipt and local frozen metadata.
Root must separately retain the genuine container build invocation and its
outer log; JSON assertions alone do not authenticate an arbitrary producer.

## Host checks and outstanding real work

Twenty-one dedicated lightweight tests pass. All compiler subprocesses are mocked
and all ELF data is explicitly synthetic; no test is SDK or C runtime proof.
They cover serial execution and LLVM argv[0], three ELF classes, dependency
escaping/target binding, single-ABI failure collection, metadata39/source
pinning, changed compiler/log/current C, arbitrary empty logs, foreign headers,
wrong ABI/loader/entry/dynamic mapping, host SDK absence, immutable output and
bounded process-group termination. The exact command, exit, tool/test hashes
and raw output are in `host-checks.json/log`.

Still required: root's real read-only Linux SDK39 three-ABI compile/link/ELF
batch, current-boot helper deployment and actual nonce-bound clock samples
before/after the real suspend/power operation, cleanup, independent Media
comparison and full first-package runtime gate. These host checks release no
remaining artifact matrix and close no capability row.
