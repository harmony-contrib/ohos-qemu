# Native child-process enabled QEMU packages (2026-09-17)

Archives, `SHA256SUMS`, `matrix-manifest.json`, and validation evidence are in
`/Volumes/PSSD/qemu/packages/device-matrix-child-process-enabled-20260917`.
These six archives start from the fixed-library archives in
`device-matrix-child-process-fix-20260915`; each archive explicitly enables
`persist.sys.abilityms.multi_process_model=true` and
`const.max_native_child_process=50` in `system.img`. The package records its
source archive and parameter change in `native-child-process-eligibility.json`.
The original six archives were not overwritten.

| Guest | Profile | SHA-256 | Native runtime evidence |
| --- | --- | --- | --- |
| arm64 | phone | `eda208b8ae5375e42af0f1ad6756d9e3ba57dd6ee9b13c2c7917c46b4ab14710` | 21/21, `validation/arm64-phone` |
| arm64 | 2in1 | `d30c9504211019c301b75f04b4f49cd8b077044083624506751959566850a902` | 21/21, `validation/arm64-2in1` |
| x86_64 | phone | `08d35399119ec9b87d564cd8bf024e8a189921f5bacf09da889b7b223848a488` | 21/21, `validation/x86_64-phone` |
| x86_64 | 2in1 | `97db8c1323965032fe4979fd30b44370eec4ce3bbefebd0706b71aa5ea8f27f8` | 21/21, `validation/x86_64-2in1` |
| armv7a | phone | `a380cff914f10a9c05b9801d60862e5fb9e0ab8b0ec930b3bdc845e55f6189c4` | 21/21 in isolated app launches, `validation/armv7a-phone` |
| armv7a | 2in1 | `e2592d19f95cba2d9f1afe26d2fffc6efe980b638fac849d811876c7b52e72c8` | 21/21 in isolated app launches, `validation/armv7a-2in1-clean` |

The first package was arm64/phone. Its archive checksum, exact command,
environment, 21/21 Native result, UI switching and 180-second stability were
recorded in `validation/arm64-phone/first-artifact-gate.md` before building the
remaining five packages, as required by `AGENTS.md`. Every later archive passed
package profile, ELF, eligibility, cold boot, Rust executable, UI switching,
and at least 180 seconds of stability. The validator used
`NATIVE_CHILD_REQUIRE_PACKAGED=1`, so it did not change the extracted image.

The armv7a/2in1 regression app initially hit foreground lifecycle timeouts
and exited during rapid force-stop/restart cycles on the TCG guest. The final
test invokes the asynchronous probe from `onForeground` and waits 20 seconds
after each force-stop before the next isolated launch. A fresh, fully automated
run against the unchanged archive passed all 21 cases, UI switching, and
stability through 840 seconds of guest uptime. The result log contains all 21
case markers; the validator did not edit the extracted image. Command:

```sh
NATIVE_CHILD_REQUIRE_PACKAGED=1 \
  ARKDOWN=/Volumes/PSSD/code/ohos-rs/ohos-native-bindings/examples-ui/node_modules/.bin/arkdown \
  HAP_SIGN=/Volumes/PSSD/code/ohos-rs/ohos-native-bindings/examples-ui/.tools/hapsigner-0.2.0/bin/hap-sign \
  QEMU_SMOKE_ACCEL=tcg \
  bash ci/native-child-process/validate-package.sh \
    /Volumes/PSSD/qemu/packages/device-matrix-child-process-enabled-20260917/openharmony-qemu-armv7a-armv7a_virt-2in1.tar.gz \
    /Volumes/PSSD/qemu/packages/device-matrix-child-process-enabled-20260917/validation/armv7a-2in1-clean
```

Earlier failed attempts and fault logs remain in the validation directory for
diagnosis. The isolated ARMv7a runs prove each API/boundary case and the
within-process rejection/recovery sequence; they do not establish 21
consecutive successful child launches in one ARMv7a app process.

The six full passes cover both Native startup APIs, empty input, exact 150 KiB
ASCII and Unicode, 16 FDs, over-limit rejection, and recovery. ARMv7a/phone
uses separate app launches for its 21 cases, so that pass does not establish a
long sequence of successful child launches inside one app process.
