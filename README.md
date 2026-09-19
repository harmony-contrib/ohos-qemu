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
  --artifact-root /path/to/jsvm-m144 \
  --lfs-asset-root /path/to/openharmony-7.0-lfs \
  --product arm64_virt

bash patches/2in1/apply.sh \
  --source-root /path/to/openharmony \
  --artifact-root /path/to/jsvm-m144 \
  --lfs-asset-root /path/to/openharmony-7.0-lfs \
  --product arm64_virt
```

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

Build the M144 engine artifacts for all supported guest architectures first:

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
standard QEMU architectures and emits exactly six suffixed packages. The
source baseline is the `OpenHarmony-7.0-Release` manifest pinned at
`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`; `master` is not used:

```bash
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/device-matrix \
BUILD_JOBS=12 KERNEL_BUILD_JOBS=6 \
scripts/run_device_type_matrix_build_docker.sh
```

The matrix is `phone,2in1` × `armv7a_virt,arm64_virt,x86_64_virt`. It is
restartable (`MATRIX_SKIP_EXISTING=1` by default), strictly verifies every
package, and writes `SHA256SUMS` plus `matrix-manifest.json`. Before traversing
the six builds it initializes the pinned source, applies the complete patch set
for all selected products, validates the prepared product configurations, and
records a resolved revision manifest. It uses one native Linux source/out
volume and defaults to pruning `out/<product>` immediately
after its package is archived, while retaining ccache and kernel objects. The
matrix caps ccache at 4 GiB by default so image assembly retains disk headroom;
set `CCACHE_MAXSIZE` explicitly on hosts with more space. This
keeps the six-package build usable on hosts that cannot hold six complete Ninja
trees at once. `PACKAGE_ROOT` may be placed outside `CACHE_ROOT`; the Docker
runner bind-mounts it separately, which is useful for temporary package staging
when the build cache disk is nearly full. Set
`PRUNE_PRODUCT_OUT_AFTER_PACKAGE=0` only when enough Docker disk space is
available. When switching between phone and 2in1 profiles, the builder writes
the profile stamp atomically and retries while Docker-backed storage makes
newly reclaimed blocks visible. The retry window can be adjusted with
`PROFILE_STAMP_WRITE_RETRIES` and `PROFILE_STAMP_WRITE_RETRY_DELAY`.

Complete phone packages inherit a current-tree-compatible profile derived from
`productdefine/common/inherit/phone.json`; complete 2in1 packages use the same
strategy with `2in1.json`. Both retain the QEMU `rich.json` base and board
display adaptations, and both carry auditable resolved-part evidence.

## 2in1 deviceType packages

Multi-package changes must pass runtime validation on the first newly packaged
artifact before the remaining packages are built; see [AGENTS.md](AGENTS.md).
The shared system patches fix Native child-process argument queries and the
150 KiB parameter boundary. The [direct C API regression](ci/native-child-process/README.md)
provides the corresponding package validation.
The [six-package release record](ci/native-child-process/RELEASE-20260917.md)
lists archive hashes, runtime evidence, and ARMv7a validation limits.
The [enabled six-package record](ci/native-child-process/RELEASE-20260917-enabled.md)
tracks archives with Native child processes available at first boot; all six
passed the direct C API regression.

Complete **deviceType=2in1** QEMU packages are source-built. The QEMU product
keeps its existing `rich.json` base (applications, SDK, code signing, and VPN)
and then inherits a current-tree-compatible profile derived from
`productdefine/common/inherit/2in1.json`. Shared parts use the 2in1 feature
selection, while QEMU-specific board/display requirements remain enabled.
The 2in1 profile enables SceneBoard and the PC window layout, installs
`/etc/sceneboard.config` as `ENABLED`, and sets
`const.window.multiWindowUIType=FreeFormMultiWindow` plus
`persist.sceneboard.ispcmode=true`. It stages four signed SceneBoard HAPs from
`SCENEBOARD_RUNTIME_ASSET_ROOT`; see
[the asset checksums and provisioning requirements](patches/2in1/sceneboard_runtime/README.md).
The SceneBoard HAPs are checked for privileged-extension authorization,
signature validity, ABI coverage, and exact packaged hashes. These additions
apply only to 2in1 builds; existing phone packages do not require rebuilding.
The 7.0 AbilityManager removes its first-boot UI-ability interceptor only after
it has received both `usual.event.USER_UNLOCKED` and
`usual.event.SCREEN_UNLOCKED` for the same user. The upstream SceneBoard
prebuilt publishes the older `common.event.UNLOCK_SCREEN`; the 2in1 runtime
asset corrects that event name. For headless QEMU boots, a 2in1-only init
configuration publishes both required events after
`bootevent.boot.completed=true`, when AbilityManager has subscribed and user
100 is ready. `USER_UNLOCKED` carries 100 in the common-event code, while
`SCREEN_UNLOCKED` carries it as the Want `userId` parameter. The CEM change
adds that Want parameter and uses the current-user route so the native process
does not hit CES's system-HAP-only special-user check. Phone images do not
install these services and the existing phone archives remain unchanged.
Applications calling the snapshot and main-window enumeration APIs must request
and receive `ohos.permission.CUSTOM_SCREEN_CAPTURE`. Privacy-mode and cursor-lock
APIs also require `ohos.permission.PRIVACY_WINDOW` and
`ohos.permission.LOCK_WINDOW_CURSOR`, respectively.
The 2in1 source component also adds `/system/app/SceneBoard` to BMS's
`install_list.json` and adds the signing certificate and privileged-extension
authorization to `install_list_capability.json`. Without these first-boot
entries the HAP files remain on disk but SceneBoard is not installed, and the
first user cannot finish starting. The package verifier checks both entries.

```bash
# macOS/Apple Silicon host with Docker or OrbStack. OpenHarmony's host
# prebuilts require the default linux/amd64 container.
PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/2in1-full \
scripts/run_2in1_full_build_docker.sh
```

The runner mounts the checkout and `out/` on the case-sensitive Docker volumes
`ohos-qemu-7_0-release-source` and `ohos-qemu-7_0-release-out`. By default the
source volume is initialized directly from the pinned 7.0 Release manifest;
the host checkout is not copied into it. The output volume is reused
incrementally. This is required on macOS: Taihe generates case-distinct
paths such as `SourceType` and `sourceType`, and a full compile can exhaust
VirtioFS file handles while reading the checkout. Ccache and its temporary
files also live in the output volume. The QEMU runner builds the pinned SDK by
default because ArkWeb M144 consumes its generated NDK libraries. A component
patch makes musl's Cortex-M porting script POSIX-safe so Ubuntu's dash shell
reliably installs the intended empty `crtplus.c` and the SDK no longer fails on
`__aeabi_unwind_cpp_pr0`. Set `NO_PREBUILT_SDK=1` only for products that do not
consume the generated SDK.

Although the immutable upstream manifest declares GitCode project remotes,
the runner rewrites those URLs to the official `github.com/openharmony`
mirrors by default. Because the GitHub organization is a read-only mirror and
does not expose the 7.0 branch for every project, the checked-in fallback map
pins affected repositories to their immutable `OpenHarmony-v7.0-Release`
commit. All 35 fallback repositories are fetched once on the host as shallow
bare caches in `$CACHE_ROOT/git-mirrors/openharmony-7.0-release`; 25 come from
GitHub and only the 10 repositories without a usable GitHub release tag come
directly from GitCode. Docker reads their exact peeled commits through a local
remote, avoiding both moving branches and annotated-tag checkout ambiguity.
Some 7.0 GitHub mirrors also expose former Git LFS files as explanatory text
stubs that `git lfs pull` cannot discover. A second pinned map caches the 77
affected objects (about 724 MiB) concurrently on the host, verifies their
OID/size, and restores them before source-profile or architecture traversal.
This includes release HAPs, ArkWebCore, Arkoala packages, ICU, and phone-number
data; archive formats are checked before the build starts. The cache defaults
to `$CACHE_ROOT/artifacts/openharmony-7.0-lfs`, with 10 download jobs controlled
by `LFS_JOBS`.
The QEMU GPU source build additionally needs historical Mesa 21.3.3 commit
`995d2506d18924b48db0cf40e6ad7de04fc4e558`, which is no longer present in a
fresh 7.0 GitHub-mirror checkout. The host runner fetches that exact commit
from GitHub into `$CACHE_ROOT/git-mirrors/qemu-mesa`, validates its `VERSION`,
and the Mesa component imports it before build-graph traversal. Ninja therefore
never performs an unpinned network fetch.
Set `OHOS_PROJECT_MIRROR` to a path-compatible
mirror, or to an empty value to disable rewriting and the fallback manifest.
Source synchronization defaults to 16 network jobs and 4 checkout jobs; tune
them with `REPO_JOBS` and `REPO_CHECKOUT_JOBS`. The host fallback cache uses 10
parallel jobs by default (`FALLBACK_JOBS`).
The documentation-only `docs` project is explicitly omitted from this build
manifest because it is not an input to any of the six QEMU images and its
multi-gigabyte Git history is not needed for product compilation.
GitHub domains are also added to the build container's `NO_PROXY` list by
default so multi-gigabyte Git packs do not traverse a local HTTP proxy; adjust
that list with `OHOS_GITHUB_NO_PROXY` when required by the host network.

Set `DOCKER_SOURCE_SEED=1 DOCKER_SOURCE_REFRESH=1` only when intentionally
seeding from a compatible host OpenHarmony checkout. A reused source volume is
rejected when its manifest commit differs from the pinned revision.

Each complete package contains `device-profile.json`, including the upstream
2in1 profile hash, effective inherit chain, resolved part list, compatibility
adaptations, and validated 2in1/QEMU feature flags. Packaging also requires the
DLP manager/service, UI appearance service, Wukong, HNP, Launcher, and SystemUI
runtime artifacts. The source component also installs
`const.bms.supportAppTypes=2in1,phone,default,tablet` in the QEMU product parameters:
the current signed Launcher/SystemUI HAPs advertise `default/tablet`, and BMS
needs this compatibility list to register them and complete first-user account
activation when the runtime device type is `2in1`.

Offline verification:

```bash
scripts/verify_device_type_package.sh \
  --package /path/to/openharmony-qemu-arm64-arm64_virt-2in1 \
  --expect-device-type 2in1 \
  --require-full-2in1 \
  --require-scene-window

scripts/verify_device_type_package.sh \
  --package /path/to/openharmony-qemu-arm64-arm64_virt-phone \
  --expect-device-type phone \
  --require-full-phone
```

For a freshly archived 2in1 package, the runtime check boots a private QEMU
guest, runs the PR #156 WindowManager tests, and checks all 21 Native child
regression cases. Set `QEMU_SMOKE_ACCEL=hvf` for arm64 on Apple Silicon; use
`tcg` for x86_64 and armv7a on that host.

```bash
BINDINGS_EXAMPLES=/path/to/ohos-native-bindings/examples-ui \
QEMU_SMOKE_ACCEL=hvf \
ci/window-manager/validate-package.sh arm64 \
  /path/to/openharmony-qemu-arm64-arm64_virt-2in1.tar.gz \
  /path/to/validation/arm64-2in1
```

`scripts/repackage_device_type.sh` remains available for compatibility testing,
but it only injects system parameters into an existing image and marks the
result `device_type_profile=param_only`. Such a package is not considered a
complete 2in1 build and fails `--require-full-2in1`. CI coverage for both paths
is in `ci/device-type/test.sh`.

## License

[MIT](./LICENSE)
