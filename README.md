# OpenHarmony QEMU Images

Prebuilt OpenHarmony standard-system QEMU images for Linux, macOS, and Windows.

## Requirements

- QEMU installed and available in `PATH`.
- Bash, `curl` or `wget`, and `tar`.
- Windows installation must be run from Git Bash, MSYS2, or Cygwin.
- Linux x86_64 should provide readable and writable `/dev/kvm`. TCG is too slow
  for a reliable standard-system boot.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash -s -- --release v20260809
```

The installer downloads the selected Release and installs the package under
`~/.ohos-qemu`. It selects `arm64` on Apple Silicon and `x86_64` on x64 hosts.
Set `OHOS_QEMU_ARCH` to `arm64`, `armv7a`, or `x86_64` before installation to
override the detected guest architecture.

The installer defaults to `phone`. Select the device type explicitly when
needed:

```bash
bash scripts/install.sh --release RELEASE_TAG --device-type phone
bash scripts/install.sh --release RELEASE_TAG --device-type 2in1
```

`OHOS_QEMU_DEVICE_TYPE=phone` and `OHOS_QEMU_DEVICE_TYPE=2in1` provide the same
selection through the environment. CLI options override environment values.
For `phone`, the installer first tries the current `-phone.tar.gz` asset and
falls back to the legacy archive without a device-type suffix when necessary.
It fails only when neither phone asset exists. A `2in1` selection requires the
`-2in1.tar.gz` asset. The installed directory matches the selected archive, for
example `openharmony-qemu-arm64-arm64_virt-2in1`.

## Run

Linux x86_64:

```bash
~/.ohos-qemu/openharmony-qemu-x86_64-x86_64_virt/launch/linux.sh
```

macOS Apple Silicon:

```bash
~/.ohos-qemu/openharmony-qemu-arm64-arm64_virt/launch/macos.command
```

Windows x86_64, from PowerShell:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "$HOME\.ohos-qemu\openharmony-qemu-x86_64-x86_64_virt\launch\windows.ps1"
```

Stop QEMU with `Ctrl+C`.

### Launch options

CLI flags override environment variables, which override package defaults:

```bash
# Resolution / resources (guest GPU + QEMU -m/-smp)
./launch/linux.sh -r 1280x720 -m 8G -s 8

# Headless / VNC
./launch/linux.sh --headless
./launch/linux.sh --display vnc --vnc-display 21   # TCP 5921

# HDC port when 5555 is busy
./launch/linux.sh --hdc-port 5556
# or: ./launch/linux.sh -c 127.0.0.1:5556

# Acceleration and extra QEMU args
./launch/linux.sh --accel tcg -- -serial mon:stdio

# Override the CPU model on an AMD host using Windows WHPX
powershell.exe -ExecutionPolicy Bypass -File ./launch/windows.ps1 -Cpu EPYC-v5 -Accel whpx
```

| Option | Env | Default |
| --- | --- | --- |
| `-r, --resolution WxH` | `QEMU_XRES` / `QEMU_YRES` | `800x500` |
| `--width` / `--height` | `QEMU_XRES` / `QEMU_YRES` | same |
| `-m, --memory SIZE` | `QEMU_MEMORY` | `4096` (armv7a: `3072`) |
| `-s, --smp N` | `QEMU_SMP` | `4` |
| `--cpu MODEL` | `QEMU_CPU` | `max` (arm64: `cortex-a57`, armv7a: `cortex-a7`) |
| `-d, --display` / `--headless` | `QEMU_DISPLAY` | product default (`sdl` / `none`) |
| `-c, --connect` / `--hdc-port` | `QEMU_HDC_HOST_PORT` | `5555` |
| `--vnc-display N` | `QEMU_VNC_DISPLAY` | `21` (TCP 5921) |
| `--serial-port PORT` | `QEMU_SERIAL_PORT` | unset |
| `-a, --accel` | `QEMU_ACCEL` | `auto` (`hvf`/`kvm`/`tcg`/`whpx`) |
| `-q, --qemu PATH` | `QEMU_BIN` | product `qemu-system-*` |
| `-- ...` | `QEMU_EXTRA_ARGS` | empty |

On Windows PowerShell the same knobs are available as parameters
(`-Resolution`, `-Memory`, `-Smp`, `-Cpu`, `-Display`, `-Headless`, …) or via the
environment variables above.

The ARM64 launcher defaults to `QEMU_ACCEL=auto`, probes whether HVF is usable,
and falls back to TCG when necessary. Set `QEMU_ACCEL=hvf` or
`QEMU_ACCEL=tcg` to force either mode.
## HDC

The launchers forward guest HDC to host TCP port `5555`. With `hdc` from the
OpenHarmony SDK toolchains installed:

```bash
hdc tconn 127.0.0.1:5555
hdc list targets
```

## Sign and install development HAPs

The `v20260809` image requires a HAP signing block. A truly unsigned package is
rejected with bundle-manager error `9568320` (`no signature file`). The default
installer also installs the Java-free `hap-sign` CLI under
`~/.ohos-qemu/bin`; use `--without-hap-signer` when only the image is wanted.

```bash
export PATH="$HOME/.ohos-qemu/bin:$PATH"

hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --output entry-default-signed.hap

hdc install entry-default-signed.hap
```

VPN applications commonly need an ACL in the debug profile:

```bash
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.vpn \
  --acl ohos.permission.FILE_ACCESS_PERSIST \
  --output entry-default-signed.hap
```

From a source checkout, `scripts/sign-hap.sh` is the equivalent wrapper and
`scripts/install-hap-signer.sh` installs the signer. Release packages carry the
same scripts under `tools/`. The signer is implemented in the separate
[`ohos-rs/hapsigner-rs`](https://github.com/ohos-rs/hapsigner-rs) repository
with RustCrypto CMS, X.509, P-256 ECDSA, and SHA-256 crates. `rustls` is not used
because the on-disk format is CMS/PKCS#7 rather than TLS.

The embedded OpenHarmony development key is public test material and is only
appropriate for QEMU/RD development images.

## Standard VPN capability

The full `armv7a_virt`, `arm64_virt`, and `x86_64_virt` packages are built with
OpenHarmony's standard VpnExtension stack:

- built-in guest TUN plus IPv4/IPv6 policy routing;
- fs-verity in the guest kernel and writable F2FS `userdata.img`, including
  OpenHarmony's `FS_IOC_ENABLE_CODE_SIGN` path for signed HAP installation;
- native `asm-x86` UAPI headers in the x86_64 musl sysroot, plus
  target-architecture `statx`, `add_key`, and `keyctl` selection in the
  code-sign services;
- deterministic HCK JIT-hook fallback when the optional JIT-memory hook is
  absent, preventing x86_64 appspawn from rejecting valid `mprotect` calls;
- VPN manager System Ability and VpnExtension runtime;
- SettingsData and the system `VpnDialog`, signed with a currently valid
  OpenHarmony system profile containing the dialog's required ACLs.
- QEMU RD/developer-device boot mode, so normal DevEco debug HAPs can be
  installed without manually changing guest authorization state.

No application is pre-authorized. The first VPN request must show the system
authorization dialog, and the user's decision is stored in the guest
`userdata.img`.

The build applies
[`overlays/standard_qemu_vpn`](./overlays/standard_qemu_vpn) before compiling.
Packaging then checks the final kernel configuration, the F2FS verity feature
of `userdata.img`, and the exact signed `VpnDialog.hap` inside `system.img`; a
package is marked with `"standard_vpn": true` only after those checks pass.
The guest VPN uses `/dev/tun` inside OpenHarmony and does not require a host
TAP device when the default QEMU user-mode network is used.

## Standard QEMU GPU rendering

All three architectures keep RenderService on its normal OpenGL/EGLImage
lifecycle. QEMU exposes a plain `virtio-gpu` DRM device; the guest Mesa stack
tries the virtio path and falls back to `kms_swrast` when host 3D is absent.
The 64-bit Mesa libraries are built from the same OHOS Mesa 21.3.3 baseline as
armv7a with the upstream `ohos_logger` `va_list` fix, instead of packaging the
older QEMU GPU binaries. Both `virtio_gpu_dri.so` and `swrast_dri.so` resolve to
the verified multi-driver `kms_swrast_dri.so` ELF.

Package validation checks the DRI ELF architecture and aliases. QEMU smoke CI
then opens Settings and Photos three times and fails if `render_service`
changes PID or emits a new fault log.

## Phone and 2in1 deviceType package matrix

The matrix entry point builds both full source profiles for all three supported
standard QEMU architectures and emits exactly six suffixed packages:

```bash
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/device-matrix \
BUILD_JOBS=12 KERNEL_BUILD_JOBS=6 \
scripts/run_device_type_matrix_build_docker.sh
```

The matrix is `phone,2in1` × `armv7a_virt,arm64_virt,x86_64_virt`. It is
restartable (`MATRIX_SKIP_EXISTING=1` by default), strictly verifies every
package, and writes `SHA256SUMS` plus `matrix-manifest.json`. It uses one native
Linux source/out volume and defaults to pruning `out/<product>` immediately
after its package is archived, while retaining ccache and kernel objects. This
keeps the six-package build usable on hosts that cannot hold six complete Ninja
trees at once. Set `PRUNE_PRODUCT_OUT_AFTER_PACKAGE=0` only when enough Docker
disk space is available.

Complete phone packages inherit a current-tree-compatible profile derived from
`productdefine/common/inherit/phone.json`; complete 2in1 packages use the same
strategy with `2in1.json`. Both retain the QEMU `rich.json` base and board
display adaptations, and both carry auditable resolved-part evidence.

## 2in1 deviceType packages

Complete **deviceType=2in1** QEMU packages are source-built. The QEMU product
keeps its existing `rich.json` base (applications, SDK, code signing, and VPN)
and then inherits a current-tree-compatible profile derived from
`productdefine/common/inherit/2in1.json`. Shared parts use the 2in1 feature
selection, while QEMU-specific board/display requirements remain enabled.

```bash
# macOS/Apple Silicon host with Docker or OrbStack. OpenHarmony's host
# prebuilts require the default linux/amd64 container.
PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/2in1-full \
scripts/run_2in1_full_build_docker.sh
```

The runner mounts the checkout and `out/` on the case-sensitive Docker volumes
`ohos-qemu-2in1-source` and `ohos-qemu-2in1-out`. The source volume is seeded
once from the host checkout (excluding its `out/`), while the output volume is
reused incrementally. This is required on macOS: Taihe generates case-distinct
paths such as `SourceType` and `sourceType`, and a full compile can exhaust
VirtioFS file handles while reading the checkout. Ccache and its temporary
files also live in the output volume.

Set `DOCKER_SOURCE_REFRESH=1` for one invocation after intentionally updating
the host OpenHarmony checkout. The refresh preserves the separate output
volume, so valid Ninja objects remain reusable when their inputs are unchanged.

Each complete package contains `device-profile.json`, including the upstream
2in1 profile hash, effective inherit chain, resolved part list, compatibility
adaptations, and validated 2in1/QEMU feature flags. Packaging also requires the
DLP manager/service, UI appearance service, Wukong, HNP, Launcher, and SystemUI
runtime artifacts. The source overlay also installs
`const.bms.supportAppTypes=2in1,phone,default,tablet` in the QEMU product parameters:
the current signed Launcher/SystemUI HAPs advertise `default/tablet`, and BMS
needs this compatibility list to register them and complete first-user account
activation when the runtime device type is `2in1`.

Offline verification:

```bash
scripts/verify_device_type_package.sh \
  --package /path/to/openharmony-qemu-arm64-arm64_virt-2in1 \
  --expect-device-type 2in1 \
  --require-full-2in1

scripts/verify_device_type_package.sh \
  --package /path/to/openharmony-qemu-arm64-arm64_virt-phone \
  --expect-device-type phone \
  --require-full-phone
```

`scripts/repackage_device_type.sh` remains available for compatibility testing,
but it only injects system parameters into an existing image and marks the
result `device_type_profile=param_only`. Such a package is not considered a
complete 2in1 build and fails `--require-full-2in1`. CI coverage for both paths
is in `ci/device-type/test.sh`.

## License

[MIT](./LICENSE)
