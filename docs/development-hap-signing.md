# Development HAP signing and installation

Use the Java-free [`hap-sign`](https://github.com/harmony-contrib/hapsigner-rs)
CLI with the actual target guest's UDID. On the official `v20261107` ARM64
2in1 image, the default `device-ids=["*"]` profile fails installation with
`9568423`, although developer mode and RD boot settings are enabled.

The commands below use the public OpenHarmony development identity embedded
in `hap-sign`, for local QEMU development.

## Sign for the target guest

Connect to the guest's HDC forwarding port and read its identity:

```bash
export PATH="$HOME/.ohos-qemu/bin:$PATH"

hdc tconn 127.0.0.1:5555
hdc -t 127.0.0.1:5555 shell bm get --udid
```

`bm get --udid` prints a label followed by a 64-character hexadecimal UDID.
Replace `QEMU_UDID` below with that value, and replace the bundle name with
`app.bundleName` from the HAP's `module.json`:

```bash
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --device-id QEMU_UDID \
  --output entry-default-signed.hap

hdc -t 127.0.0.1:5555 install entry-default-signed.hap
```

Use the same explicit HDC target when more than one device is connected, and
change the port if the launcher uses `--hdc-port`. Keep code signing enabled;
the validation below used the default normal APL, normal application feature,
and compatible version 9 (V3 signing block).

`scripts/sign-hap.sh` wraps `hap-sign sign` in a source checkout; release
packages include the same wrapper as `tools/sign-hap.sh`.

Signing preserves the HAP's application payload. It does not convert SDK/API
metadata, ABC bytecode, or native ABIs. Check that these match the guest if an
installation or launch fails after signing. The `v20261107` ARM64 2in1 guest
reports `const.bms.supportAppTypes=2in1,phone,default,tablet`; the tested HAPs
declared `deviceTypes=["default","tablet"]` and needed no device-type rewrite.

## Provisioning-profile ACLs

A permission declaration in `module.requestPermissions` and an ACL in the
signed provisioning profile serve different purposes. When a declared
permission requires profile authorization, pass its name with `--acl`:

```bash
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --device-id QEMU_UDID \
  --acl ohos.permission.READ_PASTEBOARD \
  --output entry-default-signed.hap
```

The signer includes the name in `acls.allowed-acls`, signs the profile, and
embeds it in the signed HAP. Repeat `--acl` to include multiple names, for
example when the application declares both permissions:

```bash
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --device-id QEMU_UDID \
  --acl ohos.permission.READ_PASTEBOARD \
  --acl ohos.permission.MANAGE_VPN \
  --output entry-default-signed.hap
```

The CLI takes these ACLs explicitly; it does not infer them from the HAP.
Select the required permissions using the target guest's
`/system/etc/access_token/permission_definitions.json` and the application's
APL. Keep the application at normal APL when a permitted profile ACL is
sufficient.

On the tested `v20261107` ARM64 2in1 guest, `READ_PASTEBOARD` has
`availableLevel=system_basic`, `provisionEnable=true`, and
`grantMode=user_grant`. Adding only this permission declaration to a normal-APL
control HAP reproduced `9568289`; signing the same HAP with
`--acl ohos.permission.READ_PASTEBOARD` installed successfully. This verifies
installation acceptance. Handle runtime user authorization separately.

## Installation error reference

| Code | Observed message | Action |
| --- | --- | --- |
| `9568320` | `no signature file` | Sign the HAP before installing it. |
| `9568423` | Device unauthorized; configure the device UDID in the signing profile | Read the intended guest's UDID and re-sign with `--device-id`. |
| `9568289` | `grant request permissions failed. PermissionName: ...` | Check that permission's definition, the application's APL, and required profile ACL; re-sign with the needed `--acl`. |

## Why the older release accepted `*`

The verifier compares UDIDs as exact strings. `*` is not a wildcard. Debug
profiles can bypass this comparison when the verifier's process-local
`g_isRdDevice` is set to `true`.

The two releases use different installation paths:

| Release | Observed path | RD initialization and result |
| --- | --- | --- |
| `v20260809` | BMS → AccessToken/SPM `CheckHapSignInfo` | `HapSignVerifyManager` recognizes RD mode from `/proc/cmdline` and calls `SetDevMode(DEV)` and `SetRdDevice(true)`; the default-marker debug profile installs. |
| `v20261107` | BMS → `BundleVerifyMgr::HapVerify` → `Security::Verify::HapVerify` | The BMS signature extension is absent, so the direct fallback runs without initializing the verifier's RD flag; the same profile fails UDID matching. |

The new image pins `bundlemanager_bundle_framework` to
`537bdea9ae5634a847db774fe00ba4d190cbcc65`. Upstream
[`d9f0042`, Revert SPM and fake decompression](https://github.com/openharmony/bundlemanager_bundle_framework/commit/d9f0042cc6b277ea39a0135f3a2a299dabb989ff)
removes `CheckHapsSignInfoAndInitSession` and restores
`CheckMultipleHapsSignInfo`/`BundleVerifyMgr`. The AccessToken
[`e999a7b`, revert spm code](https://github.com/openharmony/security_access_token/commit/e999a7b0cad0c4a87492979c47406a82b9f94892)
also removes the manager constructor's RD initialization. These changes explain
the runtime-path difference observed in the released images.

Source references:

- [AccessToken RD initialization before the revert](https://github.com/openharmony/security_access_token/blob/60b8a052627174a962a60a76c48f5715eb9d60f4/services/accesstokenmanager/main/cpp/src/permission/hap_sign_verify_manager.cpp)
- [BMS direct fallback in the new baseline](https://github.com/openharmony/bundlemanager_bundle_framework/blob/537bdea9ae5634a847db774fe00ba4d190cbcc65/services/bundlemgr/src/bundle_verify_mgr.cpp)
- [Verifier RD flag, exact UDID match, and debug-profile conditions](https://github.com/openharmony/security_appverify/blob/23c525515452ffe1e9dfd10c1de934ba010ed4aa/interfaces/innerkits/appverify/src/provision/provision_verify.cpp)

The kernel's `oemmode=rd` and the parameter
`const.security.developermode.state=true` do not automatically initialize
`g_isRdDevice` in the BMS process. Setting it in another service process does
not change BMS's copy. Explicitly including the real UDID works with the
observed verifier path. Restoring RD-based UDID exemption requires image-side
verifier initialization work; no such change is included in this documentation
update.

## Historical release validation, 2026-11-12

These are runtime results from the official released images, rather than a
newly built artifact from the current development branch. Both archives were
checked against their release's official `SHA256SUMS`:

| Release / archive | Guest | Archive SHA-256 |
| --- | --- | --- |
| [`v20260809`](https://github.com/harmony-contrib/ohos-qemu/releases/tag/v20260809), `openharmony-qemu-arm64-arm64_virt-2in1.tar.gz` | `OpenHarmony 7.0.0.32`, 2in1 | `dfce47fcf37e83d71a3cbe153381b78599116b7780f0a1f29a11ee80c4eeb88c` |
| [`v20261107`](https://github.com/harmony-contrib/ohos-qemu/releases/tag/v20261107), `openharmony-qemu-arm64-arm64_virt-2in1.tar.gz` | `OpenHarmony 7.0.0.39`, API 26, 2in1 | `437c720e913cb690c1e25253d00ebbda0ee58c9e5de9b21802d0dfea8863b2d5` |

Environment: macOS ARM64, QEMU 11.0.2, HVF, 4 virtual CPUs, 4096 MiB RAM,
headless. Each archive was extracted into its own temporary directory. The
new guest used HDC port `5557`, and the old guest used `5558`. Both guests
reported developer mode enabled; both launchers included `oemmode=rd`.

```bash
# Run the packaged launcher in each extracted release, using separate ports.
./launch/macos.command --headless --hdc-port 5557 \
  --accel hvf --memory 4096 --smp 4
```

The signer was `hap-sign` 0.2.0 built from
[`193e101`](https://github.com/harmony-contrib/hapsigner-rs/commit/193e1010729754161c701d35d794297aa93662a5).
The OpenHarmony
[`security_code_signature` fixtures](https://github.com/openharmony/security_code_signature/tree/f41e32b1beca7913bd2c5d888a6ec74dfb5ffe20/test/unittest/resources)
supplied these inputs:

| Input | Bundle name | Input SHA-256 |
| --- | --- | --- |
| `demo_without_lib/demo_without_lib.hap` | `com.example.myapplicationwithoutso` | `c51d5580ee39f911a0faecffd5832de4ef5e5e2384420c3414faf27a1088ca8b` |
| `demo_with_multi_lib/demo_with_multi_lib.hap` | `com.example.myapplicationwithso1953` | `cec30c0e2a336c2c08e91d8ac26aa7fc363a6c4a63bce39c27b597fc45dec046` |

Both declare OpenHarmony SDK type, minimum/target API 10, and
`deviceTypes=["default","tablet"]`. Existing fixture signing blocks were
replaced; ZIP entry payloads remained byte-identical after signing. The
unsigned control was repacked from the same payload without a signing block.

| Case | `v20260809` ARM64 2in1 | `v20261107` ARM64 2in1 |
| --- | --- | --- |
| Unsigned control | Rejected, `9568320` | Rejected, `9568320` |
| Same ABC-only HAP, default `device-ids=["*"]` | Installed | Rejected, `9568423` |
| ABC-only HAP, actual new guest UDID | Not tested | Installed; Ability started; process alive |
| Native-library HAP, actual new guest UDID | Not tested | Installed; Ability started; process alive and foreground |
| Normal-APL control declaring `READ_PASTEBOARD`, actual UDID, no ACL | Not tested | Rejected, `9568289` |
| Same permission control with `--acl ohos.permission.READ_PASTEBOARD` | Not tested | Installed |

The exact default-profile signed HAP used for the old/new comparison had
SHA-256 `f8b1852c865fb6b1417ab2ccbe7561bff7e266e0510683d448fc2905a0bff88e`.
Local `verify-app` passed for both fixture HAPs with either the default profile
or the actual new guest UDID. The permission control was an installation test;
clipboard access at runtime was not exercised.

Relevant guest log excerpts from installing that same default-profile HAP:

```text
v20260809:
  ATM CheckHapSignInfo: Result 0, sessionId 76
  BMSInstaller CheckHapsSignInfoAndInitSession: CheckHapSignInfo success, sessionId=76
  BMS FinishHapInstall sessionId:76 success:1

v20261107:
  BMS bms_extension_data_mgr.cpp(HapVerify:125): access bms-extension failed
  HapVerify provision_verify.cpp(CheckDeviceID:319): current device is not authorized
  BMS bundle_verify_mgr.cpp(HapVerify:80): HapVerify result -15
  BMSTool: on finished result is 9568423
```

The old guest's `libaccesstoken_manager_service.z.so` also imports
`SetRdDevice(bool)` and contains the RD-initialization log string
`Detected RD device, enabling dev mode.` This supports the source/runtime
comparison above. Both test instances were stopped after validation. Other
architectures and device profiles were not part of this comparison.
