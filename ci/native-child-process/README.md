# Native child-process regression

This minimal HAP calls the SDK C API directly; it contains no Rust bindings and
does not access private system symbols or hard-coded addresses.

The 21 cases check the parent getter, both Native startup APIs, empty/small and
99/100/150 KiB arguments, the exact byte boundary, Unicode, 16 named FDs with
20-byte names, and rejection of 150 KiB + 1 followed by a successful launch.
Every successful child compares the complete payload hash/length, checks the
getter in the entry and a second thread, and communicates through every FD.
The ARMv7a TCG guest runs the 21 cases in separate app launches because its
foreground regression process can be terminated while repeatedly starting
native children. The over-limit case still checks a successful launch after
rejection in the same app process. On armv7a/2in1, the probe starts from
`onForeground` and the runner waits 20 seconds after force-stop so the previous
app and Native child can finish cleanup before the next case.

## First-artifact gate

Build and package one artifact (normally arm64/2in1), hash the archive, and boot
that exact package in a private snapshot. Do not proceed to the remaining
packages until its runtime regression passes. Keep the package checksum, launch
command, guest environment, and test logs together as release evidence.

Native child processes require an eligible device profile and a nonzero process
limit. The validator sets these entries in the extracted private 2in1 image
before the first boot, then checks their live values:

```text
persist.sys.abilityms.multi_process_model = true
const.max_native_child_process = 50
```

These test settings must not be written into the distributed base image merely
to make the regression run. Phone images retain their normal eligibility rules
by default. Set `NATIVE_CHILD_TEST_PHONE=1` to apply the same settings to an
extracted private phone image and run the C API regression there. This checks
phone runtime capability without changing the distributed archive.

## Build and run

On macOS, `validate-package.sh PACKAGE.tar.gz EVIDENCE_DIR` runs the archive
through offline checks, boot/account readiness, native executable and UI-switch
smoke checks, and (for 2in1, or an opted-in private phone test) the C API
regression. By default it edits only the extracted test copy. Set
`NATIVE_CHILD_REQUIRE_PACKAGED=1` to require eligibility in the archive and
avoid the private-image edit. It records the archive hash and stops its guest on
exit. Set `ARKDOWN`
and `HAP_SIGN` when those tools are not on PATH. This command validates one
package; it never starts subsequent package builds.
Successful runs remove the extracted test images to conserve build space;
set `KEEP_TEST_IMAGE=1` to retain them. Logs and verification results are kept.

For a fast Linux check before a system image is available, run
`test-singleton.sh OHOS_SOURCE_ROOT WORK_DIR` against the patched source. It
compiles the actual manager into a shared library and verifies communication
between two hidden-symbol DSOs and a second thread. This is supplemental and
does not replace the first-artifact runtime gate.

Requires SDK 7.0, `arkdown`, `hap-sign`, and `hdc`. Paths can be passed explicitly
with `--sdk`, `--arkdown`, and `--hap-sign`; defaults use the macOS DevEco SDK and
tools on PATH. Obtain the UDID with `hdc -t TARGET shell 'bm get --udid'`.

```bash
python3 ci/native-child-process/build.py \
  --arch arm64 --udid UDID --output .tmp/native-child-regression/arm64

python3 ci/native-child-process/run.py \
  --target 127.0.0.1:5566 \
  --hap .tmp/native-child-regression/arm64/entry/build/default/outputs/default/entry-default-signed.hap \
  --evidence .tmp/native-child-regression/results-arm64
```

Use `--arch armv7a` or `--arch x86_64` for the other guests. Pass
`--isolated-cases` to `run.py` for ARMv7a and `--foreground-probe` to `build.py`
for armv7a/2in1; `validate-package.sh` selects both automatically. A successful run
prints `SUMMARY total=21 failures=0` and writes `result.json`, the complete test
log, environment, install/start results, and a system hilog snapshot. Each test
uses a dedicated bundle, `org.harmonycontrib.childprocessregression`.

## Enabled QEMU packages

`scripts/package_native_child_process_enabled.py` creates a separate archive
from one fixed-library archive. It changes only the two eligibility values in
`system.img`, retains the parameter file owner, mode, and SELinux label, records
the source archive and before/after values in
`native-child-process-eligibility.json`, and regenerates package checksums.
The original six fixed-library archives remain available with their default
disabled eligibility settings.

Validate an enabled archive with `NATIVE_CHILD_REQUIRE_PACKAGED=1`. For a phone
archive, also set `NATIVE_CHILD_TEST_PHONE=1`. The enabled release's
[matrix record](RELEASE-20260917-enabled.md) contains six full 21-case passes.

## Same-release phone packages

For a pinned 2in1 base archive, `scripts/repackage_native_child_process_2in1.py`
can update the affected libraries compiled from the patched source target
graph. It verifies the clean original archive, filesystem integrity, file
metadata, ELF symbols and the complete 2in1 device profile, then stores the
base archive hash, source build log hash and binary hashes in the new package.
Boot the resulting archive and pass all 21 Native cases before using it for a
phone package. The Ability fix changes three libraries; the ARMv7a guest also
updates two appspawn libraries to avoid a 32-bit nativespawn crash during child
cleanup. ARMv7a uses UTF-8 for child parameter fields on both sides of its
internal IPC; UTF-16 would put even 99 KiB of ASCII near that guest's IPC
boundary. The original full source profile supplies the other files.

When the changed libraries in the original phone and 2in1 packages for
an architecture are byte-identical, `scripts/repackage_native_child_process_phone.py`
can carry those rebuilt libraries from the newly validated 2in1
archive into the original phone archive. It refuses different pinned source
baselines or differing original libraries, starts from the original compressed
archive (not a previously booted unpacked image), preserves each file's owner,
mode and SELinux label, checks ext4 and all package checksums, and records both
source archive hashes and each library hash in `native-child-process-repack.json`.
Boot and validate each resulting phone archive with `validate-package.sh`; the
phone validation checks boot/UI/static ELF by default. With
`NATIVE_CHILD_TEST_PHONE=1`, it also runs the 21 Native child-process cases in a
private phone test image. This reuse is specific to the verified matching
binary set; do not assume the profiles always share those libraries.
