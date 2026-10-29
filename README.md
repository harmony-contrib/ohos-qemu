# OpenHarmony QEMU Images

Prebuilt OpenHarmony standard-system QEMU images for Linux, macOS, and Windows.

## Requirements

- QEMU installed and available in `PATH` (`8.1+` for accessibility QMP
  multitouch events).
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

# Accessibility testing: virtio multitouch + QMP control socket
./launch/linux.sh --headless --a11y --qmp-socket /tmp/ohos-a11y.sock

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
| `--a11y` | `QEMU_ACCESSIBILITY` | `0` |
| `--qmp-socket PATH` | `QEMU_QMP_SOCKET` | `/tmp/openharmony-qemu-a11y-<HDC_PORT>.sock` with `--a11y` |
| Windows `-QmpPort PORT` | `QEMU_QMP_PORT` | `4445` with `-A11y` |
| `-a, --accel` | `QEMU_ACCEL` | `auto` (`hvf`/`kvm`/`tcg`/`whpx`) |
| `-q, --qemu PATH` | `QEMU_BIN` | product `qemu-system-*` |
| `-- ...` | `QEMU_EXTRA_ARGS` | empty |

On Windows PowerShell the same knobs are available as parameters
(`-Resolution`, `-Memory`, `-Smp`, `-Cpu`, `-Display`, `-Headless`, …) or via the
environment variables above.

Current full packages pair `virtio-tablet` with a guest MMI absolute-coordinate
mapping. The mapping uses the active framebuffer dimensions, so pointer clicks
remain aligned after changing `--resolution`, resizing the host window, or
using HiDPI scaling. The package manifest records this as
`capabilities.absolute_pointer_sync=true`; older relative-mouse packages do not
gain this capability merely by rewriting their launch scripts.

The ARM64 launcher defaults to `QEMU_ACCEL=auto`, probes whether HVF is usable,
and falls back to TCG when necessary. Set `QEMU_ACCEL=hvf` or
`QEMU_ACCEL=tcg` to force either mode.

For accessibility tests, `--a11y` adds `virtio-multitouch-pci` and enables a
QMP server. After installing a HAP containing an `AccessibilityExtensionAbility`,
switch HDC to root mode and enable it through the guest's built-in QEMU CLI:

```bash
hdc smode
hdc tconn 127.0.0.1:5555
hdc shell /system/bin/cli_tool/executable/ohos-a11yManager ability-enable \
  --name com.example.app/AccessibilityExtAbility \
  --capabilities 7
```

The capability mask must be a subset of the extension's
`accessibilityCapabilities` metadata. The value `7` matches an extension that
declares `retrieve`, `touchGuide`, and `gesture`.

The package manifest reports this complete host/guest path as
`capabilities.accessibility_test=true` only when the generic CLI is present in
`system.img`.

For the `ohos-native-bindings` accessibility E2E, the packaged launcher and
system CLI replace the manual `QEMU_EXTRA_ARGS` and uploaded
`accessibility-enable` helper from
[PR #13](https://github.com/harmony-contrib/ohos-qemu/pull/13):

```bash
export QEMU_QMP_SOCKET=/tmp/ohos-a11y.sock
export ACCESSIBILITY_E2E_ENABLE_COMMAND=\
'/system/bin/cli_tool/executable/ohos-a11yManager ability-enable '\
'--name com.richerfu.ohos_example/AccessibilityE2ETestExtension --capabilities 7'
pnpm run test:ui:accessibility -- --arch x64  # use arm64 for an ARM64 guest
```

The extension still has to be enabled after its HAP is installed: its bundle
and ability do not exist when QEMU starts. The E2E runner performs that step by
executing `ACCESSIBILITY_E2E_ENABLE_COMMAND` after installation.

## Source capability components

Source builds use a component-owned patch tree under [`patches`](./patches).
Phone and 2in1 are independent top-level entries; the removed `overlays/`
commands are not retained as compatibility wrappers:

```bash
bash patches/phone/apply.sh \
  --source-root /path/to/openharmony \
  --v8-artifact-root /path/to/jsvm-m144 \
  --core-artifact-root /path/to/source-arkweb-core \
  --vulkan-artifact-root /path/to/swiftshader-m144 \
  --avc-artifact-root /path/to/avc-m144 \
  --lfs-asset-root /path/to/openharmony-7.0-lfs \
  --product arm64_virt

bash patches/2in1/apply.sh \
  --source-root /path/to/openharmony \
  --v8-artifact-root /path/to/jsvm-m144 \
  --core-artifact-root /path/to/source-arkweb-core \
  --vulkan-artifact-root /path/to/swiftshader-m144 \
  --avc-artifact-root /path/to/avc-m144 \
  --lfs-asset-root /path/to/openharmony-7.0-lfs \
  --product arm64_virt
```

Run these source-only entries inside the prepared local Ubuntu 22.04 Docker
environment. Both invoke the exact ordered `apply_qemu_capability_patch_plan`
used by the full builder, including graphics, providers, audio, camera,
kernel and the profile-specific Serial integration. They do not sync, build,
package or assert runtime success. All four dependency roots are required;
the old ambiguous `--artifact-root` option is not retained.

Every leaf component has its own `apply.sh`, and each stable source change is
an independently reviewable numbered patch. The aggregate entries apply, in
dependency order:

- pinned former-LFS asset restoration for GitHub mirror checkouts;
- the generated phone or 2in1 product profile;
- QoS authority kernel support and `qos_auth` integration;
- a stateful QEMU vibrator product VDI;
- a generic `ohos-a11yManager` entry for enabling an installed test
  `AccessibilityExtensionAbility` without pushing a helper binary;
- release-HAP dependency handling that skips registry access only when no
  runtime package dependency is declared;
- absolute-pointer synchronization and the standard VPN/GPU stack;
- JSVM linked to the pinned ArkWeb/Chromium M144 `v8_shared` artifact;
- the armv7a product components when `armv7a_virt` is selected.

For standalone V8 artifacts (not the complete ArkWeb core HAP):

```bash
scripts/build_m144_v8.sh arm arm64 x86_64
```

The builder pins Chromium, V8, ArkWeb, CEF, depot_tools, and the OpenHarmony
7.0 WebView interface revisions. It records per-file SHA-256 values in
`manifest.json`; the JSVM component rejects a wrong milestone, revision,
architecture, checksum, SDK link stub, or non-OpenHarmony libc++ ABI
namespace/version before modifying the OpenHarmony checkout. Image packaging
also verifies that the vibrator VDI exports `hdfVdiDesc` and that
`libv8_shared.so` satisfies every V8 C++ symbol required by `libjsvm.so`.

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
[`patches/common/standard_vpn`](./patches/common/standard_vpn) before compiling.
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
standard QEMU architectures and emits all six suffixed packages (`phone,2in1` ×
`arm64_virt,x86_64_virt,armv7a_virt`). The source baseline is the
`OpenHarmony-7.0-Release` manifest pinned at
`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549` paired with the pinned Chromium/ArkWeb
M144 source lock ([`scripts/m144_release_source_lock.json`](scripts/m144_release_source_lock.json)):

```bash
export CACHE_ROOT=/Volumes/PSSD/qemu
export PACKAGE_ROOT="${CACHE_ROOT}/packages/device-matrix"

DOCKER_BUILD_CPUS=10 \
DOCKER_BUILD_MEMORY=20g \
DOCKER_BUILD_MEMORY_SWAP=24g \
BUILD_JOBS=8 \
KERNEL_BUILD_JOBS=8 \
CCACHE_MAXSIZE=80G \
bash scripts/run_device_type_matrix_build_docker.sh
```

For detailed architecture, source baseline locks, from-zero build instructions
on a new machine, and subsystem adaptation references, see:

- [**Adaptation Documentation Index**](docs/README.md)
- [**Architecture and Source Baseline**](docs/architecture-and-baseline.md)
- [**From-Zero Build and Packaging Guide**](docs/build-and-packaging-guide.md)
- [**Subsystem Adaptations and Technical Reference**](docs/subsystem-adaptations.md)

## 2in1 deviceType packages

Complete **deviceType=2in1** QEMU packages are source-built. The QEMU product
keeps its existing `rich.json` base (applications, SDK, code signing, and VPN)
and then inherits a current-tree-compatible profile derived from
`productdefine/common/inherit/2in1.json`. Shared parts use the 2in1 feature
selection, while QEMU-specific board/display requirements remain enabled.
The 2in1 profile enables SceneBoard and the PC window layout, installs
`/etc/sceneboard.config` as `ENABLED`, and sets
`const.window.multiWindowUIType=FreeFormMultiWindow` plus
`persist.sceneboard.ispcmode=true`. It automatically reconstructs and stages the
five signed SceneBoard runtime HAPs (`SceneBoard.hap`, `NotificationManagement.hap`,
`ThemeService.hap`, `ThemeComponent.hap`, `SecurityPrivacyCenter.hap`) via
[`scripts/prepare_sceneboard_runtime_assets.py`](scripts/prepare_sceneboard_runtime_assets.py)
using `${OHOS_LFS_ASSET_ROOT}` and [`patches/assets/sceneboard-runtime-delta.tar.gz`](patches/assets/sceneboard-runtime-delta.tar.gz).

To build a single package (`phone` or `2in1`) directly in Docker:

```bash
DEVICE_TYPE=2in1 \
PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/2in1-full \
bash scripts/run_2in1_full_build_docker.sh
```

## License

[MIT](./LICENSE)
