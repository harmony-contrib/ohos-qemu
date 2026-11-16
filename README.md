# OpenHarmony QEMU Images

Prebuilt OpenHarmony standard-system QEMU images for Linux, macOS, and Windows.

Source repository migration to [openharmony-qemu](https://github.com/openharmony-qemu) is complete.
See [repository migration status](docs/repository-migration.md) for the manifest,
component ownership and verification evidence. Package builds and runtime
validation for the migrated source graph are deferred.

## Requirements

- QEMU installed and available in `PATH` (`8.1+` for accessibility QMP
  multitouch events).
- Bash, `curl` or `wget`, and `tar`.
- Windows installation must be run from Git Bash, MSYS2, or Cygwin.
- Linux x86_64 should provide readable and writable `/dev/kvm`. TCG is too slow
  for a reliable standard-system boot.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash -s -- --release v20261114
```

Every named option in `scripts/install.sh` also accepts a matching `OHOS_QEMU_*`
environment variable (CLI options override environment variables), so CI jobs can
install without `bash -s --`:

```bash
OHOS_QEMU_RELEASE=v20261114 \
OHOS_QEMU_DEVICE_TYPE=2in1 \
OHOS_QEMU_WITHOUT_HAP_SIGNER=1 \
OHOS_QEMU_FORCE=1 \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh)"
```

| Installer option | Environment variable | Default |
| --- | --- | --- |
| `--prefix DIR` | `OHOS_QEMU_PREFIX` | `$HOME/.ohos-qemu` |
| `--platform NAME` | `OHOS_QEMU_PLATFORM` | `auto` (`linux` / `macos` / `windows`) |
| `--arch ARCH` | `OHOS_QEMU_ARCH` | `auto` (`arm64` / `armv7a` / `x86_64`) |
| `--device-type TYPE` | `OHOS_QEMU_DEVICE_TYPE` | `phone` (`phone` / `2in1`) |
| `--repo URL` | `OHOS_QEMU_REPO` / `OHOS_QEMU_REPO_URL` | `https://github.com/harmony-contrib/ohos-qemu` |
| `--release TAG` | `OHOS_QEMU_RELEASE` / `OHOS_QEMU_RELEASE_TAG` / `OHOS_QEMU_REF` | `v20261114` |
| `--download-base-url URL` | `OHOS_QEMU_DOWNLOAD_BASE_URL` | unset |
| `--github-token TOKEN` | `OHOS_QEMU_GITHUB_TOKEN` / `GITHUB_TOKEN` | unset |
| `--force` / `--no-force` | `OHOS_QEMU_FORCE` | `0` (`0`/`1`/`true`/`false`) |
| `--keep-archive` | `OHOS_QEMU_KEEP_ARCHIVE` | `0` (`0`/`1`/`true`/`false`) |
| `--with-hap-signer` / `--without-hap-signer` | `OHOS_QEMU_WITH_HAP_SIGNER` / `OHOS_QEMU_WITHOUT_HAP_SIGNER` / `OHOS_QEMU_INSTALL_HAP_SIGNER` | `1` |
| `--hap-signer-version TAG` | `OHOS_QEMU_HAP_SIGNER_VERSION` / `OHOS_QEMU_HAPSIGNER_VERSION` | `v0.1.0` |
| `--hap-signer-download-base-url URL` | `OHOS_QEMU_HAP_SIGNER_DOWNLOAD_BASE_URL` / `OHOS_QEMU_HAPSIGNER_DOWNLOAD_BASE_URL` | unset |

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
# English UI + resolution / resources (guest GPU + QEMU -m/-smp)
./launch/linux.sh --lang en -r 1280x800 -m 8G -s 8

# Pure environment-variable CI launch (every CLI flag has a matching QEMU_* / OHOS_QEMU_* env var)
QEMU_LANG=en QEMU_RESOLUTION=1280x800 QEMU_HEADLESS=1 QEMU_HDC_PORT=5556 ./launch/linux.sh

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
powershell.exe -ExecutionPolicy Bypass -File ./launch/windows.ps1 -Lang en -Cpu EPYC-v5 -Accel whpx
```

| Option | Env | Default |
| --- | --- | --- |
| `-r, --resolution WxH` | `QEMU_RESOLUTION` (`QEMU_XRES` / `QEMU_YRES`) | `800x500` |
| `--width` / `--height` | `QEMU_WIDTH` / `QEMU_HEIGHT` (`QEMU_XRES` / `QEMU_YRES`) | same |
| `-l, --lang, --locale TAG` | `QEMU_LANG` / `QEMU_LOCALE` | `zh-Hans-CN` (`en`, `en-US`, `en-GB`, `zh-Hant`, `ja`, `ko`, `fr`, `de`, `es`, `it`, `pt`, `ru`, `ar`, `vi`, `bo`, `ug`, …) |
| `--region REGION` | `QEMU_REGION` | `CN` (`US`, `GB`, `TW`, `HK`, `JP`, `KR`, `FR`, `DE`, …) |
| `-m, --memory SIZE` | `QEMU_MEMORY` | `4096` (armv7a: `3072`) |
| `--userdata-size SIZE` | `QEMU_USERDATA_SIZE` | `2G` (`images/userdata.img`, online-resized on boot) |
| `--reset` | `QEMU_RESET` | `0` (`1`/`true` resets active `userdata.img` to a clean factory F2FS image before boot, preserving any custom `userdata.img` size unless `--userdata-size` is also set) |
| `-s, --smp N` | `QEMU_SMP` | `4` |
| `--cpu MODEL` | `QEMU_CPU` | `max` (arm64: `cortex-a57`, armv7a: `cortex-a7`) |
| `-d, --display` / `--headless` | `QEMU_DISPLAY` / `QEMU_HEADLESS` | product default (`sdl` / `cocoa` / `none`) |
| `-c, --connect` / `--hdc-port` | `QEMU_CONNECT` / `QEMU_HDC_PORT` / `QEMU_HDC_HOST_PORT` | `5555` |
| `--vnc-display N` | `QEMU_VNC_DISPLAY` | `21` (TCP 5921) |
| `--serial-port PORT` | `QEMU_SERIAL_PORT` | unset |
| `--a11y` | `QEMU_A11Y` / `QEMU_ACCESSIBILITY` | `0` |
| `--qmp-socket PATH` | `QEMU_QMP_SOCKET` | `/tmp/openharmony-qemu-a11y-<HDC_PORT>.sock` with `--a11y` |
| Windows `-QmpPort PORT` | `QEMU_QMP_PORT` | `4445` with `-A11y` |
| `--audio MODE` | `QEMU_AUDIO` / `QEMU_AUDIO_BACKEND` | `auto` (`auto\|none\|coreaudio\|pa\|pipewire\|alsa\|sdl\|dsound\|wav[:PATH]`) |
| `--shared-dir DIR[:TAG]` | `QEMU_SHARED_DIR` | unset (mounts VirtFS 9p at `/mnt/share` and `/data/share`) |
| `--usb` | `QEMU_USB` | `0` (attaches `qemu-xhci`) |
| `--usb-disk FILE[:SIZE]` | `QEMU_USB_DISK` | unset (attaches USB mass storage on `xhci0.0` -> `/mnt/data/external/usb`, `/data/usb`; auto-creates/formats if `:SIZE` is given) |
| `--usb-host VID:PID` | `QEMU_USB_HOST` | unset (USB host device passthrough by hex `VID:PID`) |
| `--usb-serial MODE` | `QEMU_USB_SERIAL` | `off` (`off\|auto\|on\|loopback\|pty\|unix:PATH\|tcp:HOST:PORT`, attaches FTDI USB serial -> `/dev/ttyUSB0` without colliding with RIL `/dev/ttyRIL0`) |
| `--bt-usb VID:PID` | `QEMU_BT_USB` | unset (USB Bluetooth adapter passthrough by hex `VID:PID`) |
| `--balloon` | `QEMU_BALLOON` | `0` (attaches `virtio-balloon-pci`) |
| `--rng MODE` | `QEMU_RNG` | `on` (`auto\|on\|off`, attaches `virtio-rng-pci` hardware entropy source) |
| `--port-forward SPEC` | `QEMU_PORT_FORWARD` / `QEMU_HOSTFWD` | unset (`[tcp\|udp:]HOST_PORT:GUEST_PORT`, comma-separated or repeated SLIRP `hostfwd` rules) |
| `--ril-modem MODE` | `QEMU_RIL_MODEM` | `auto` (`auto\|on\|off`, virtual AT modem over `virtio-serial` `/dev/ttyRIL0`) |
| `--wifi MODE` | `QEMU_WIFI` / `QEMU_WIFI_MODE` | `auto` (`auto\|hwsim\|virt_wifi\|off`) |
| `--gps COORDS` | `QEMU_GPS` | unset (`LAT,LON[,ALT[,SPEED[,BEARING[,HACC[,VACC]]]]]`, streams to `/dev/unix/socket/qemu_gnss/input`) |
| `--sensor VALUES` | `QEMU_SENSOR` | unset (`AX,AY,AZ[:RX,RY,RZ,RW]`, streams to `/dev/unix/socket/qemu_sensor/{input,rotation,headposture}`) |
| `--battery SPEC` | `QEMU_BATTERY` | `100:charging` (`LEVEL[:charging\|discharging\|full\|not_charging]`, updates `/data/service/el0/battery` & status bar) |
| `--thermal TEMP_C` | `QEMU_THERMAL` | `25.0` (temperature in Celsius, updates `/data/service/el0/thermal/sensor/*/temp`) |
| `--sdcard FILE[:SIZE]` | `QEMU_SDCARD` | unset (attaches external SD card -> `/dev/mmcblk0`, `/mnt/data/external/sdcard`, `/data/sdcard`) |
| `--nvme-disk FILE[:SIZE]` | `QEMU_NVME` / `QEMU_NVME_DISK` | unset (attaches NVMe / high-speed disk -> `/dev/nvme0n1`, `/mnt/data/external/nvme`, `/data/nvme`) |
| `--instance ID` | `QEMU_INSTANCE` / `QEMU_INSTANCE_ID` | unset (`1..999`; auto-isolates `userdata.img`/`sys_prod.img`/`chip_prod.img`, MACs, UUID, serial, HDC port, VNC display) |
| `--peer MODE` | `QEMU_PEER` / `QEMU_PEER_MODE` | `off` (`off\|listen[:PORT]\|connect[:PORT]`, attaches `virtio-net-pci` over loopback `stream` for DSoftBus LAN) |
| `--userdata-file PATH` | `QEMU_USERDATA_FILE` | `images/userdata.img` |
| `--rtc MODE` | `QEMU_RTC` | `utc` (`utc\|localtime\|host`, plus guest epoch sync via `/vendor/bin/qemu-hw-bridge`) |
| `--watchdog MODEL` | `QEMU_WATCHDOG` | `none` (`none\|i6300esb[:reset\|shutdown\|poweroff\|pause\|none]`) |
| `--tpm PATH` | `QEMU_TPM` | unset (`swtpm` UNIX control socket or state directory -> `tpm-crb` / `tpm-tis-device`) |
| `--clipboard MODE` | `QEMU_CLIPBOARD` | `auto` (`auto\|on\|off\|text:...`, host-guest clipboard bridge -> `/data/service/el1/public/qemu_clipboard.txt`) |
| `--camera-feed PATTERN` | `QEMU_CAMERA` / `QEMU_CAMERA_FEED` | `bars` (`bars\|smpte\|squares\|checkers\|cross\|ramp\|noise\|moving`, live-switchable via `/data/vendor/camera_scene.cfg`) |
| `--hw-bridge MODE` | `QEMU_HW_BRIDGE` | `auto` (`auto\|on\|off`, host-guest `ohos.hw.bridge0` control channel) |
| `-a, --accel` | `QEMU_ACCEL` | `auto` (`hvf`/`kvm`/`tcg`/`whpx`) |
| `-q, --qemu PATH` | `QEMU_BIN` / `QEMU_PATH` | product `qemu-system-*` |
| `-- ...` | `QEMU_EXTRA_ARGS` | empty |

On Windows PowerShell (`launch/windows.ps1`, included across `x86_64_virt`,
`arm64_virt`, and `armv7a_virt` packages) the same knobs are available as
parameters (`-Resolution`, `-Lang`, `-Locale`, `-Region`, `-Memory`,
`-UserdataSize`, `-Reset`, `-Smp`, `-Cpu`, `-Display`, `-Headless`, `-UsbSerial`,
`-PortForward`, `-Rng`, `-Sdcard`, `-NvmeDisk`, `-Gps`, `-Sensor`, `-Battery`,
`-Thermal`, `-Instance`, `-Peer`, `-Rtc`, `-Watchdog`, `-CameraFeed`,
`-Clipboard`, `-HwBridge`, …) or via the `QEMU_*` / `OHOS_QEMU_*` environment
variables above.

### Multi-language & English UI (`--lang en` / `QEMU_LANG=en`)

All six `phone` and `2in1` images include built-in multi-language support (`SA 1602`
`i18n_service`, ICU 72 locale data, and 18 whitelisted UI languages in
`/system/etc/xml/i18n_param_config.xml`: `zh-Hans`, `en-Latn-US`, `zh-Hant`,
`zh-Hant-HK`, `ja`, `ko`, `fr`, `de`, `es-ES`, `es-US`, `it`, `pt`, `pt-PT`,
`ru`, `ar`, `vi`, `bo`, `ug`):

- **At boot**: pass `--lang en` (or `QEMU_LANG=en`, `--locale en-GB`, `--lang ja`,
  etc.) to boot directly into the selected language and persist it across reboots.
- **At runtime without rebooting**: run `python3 ./tools/qemu_hw_controller.py locale en`
  from the host, `hdc shell qemu-i18n-ctl en` from HDC, or switch interactively
  under **Settings → System → Language & region → Add language**.

### Live runtime hardware & locale control (`tools/qemu_hw_controller.py`)

While QEMU is running, `tools/qemu_hw_controller.py` exposes a host UNIX control
socket (`/tmp/openharmony-qemu-hw-<HDC_PORT>.ctrl.sock`, honoring `QEMU_HDC_PORT`
/ `QEMU_HDC_HOST_PORT` automatically) connected to `/vendor/bin/qemu-hw-bridge`
inside the guest over `virtio-serial` (`ohos.hw.bridge0`) so system UI
language/locale (`locale`, `region`), GPS fixes, 3-axis
accelerometer/rotation/head-posture and extended environmental sensors (`gyro`,
`light`, `proximity`, `barometer`, `magnetic`), battery level/charging state,
thermal zones, hardware key events (`power`, `volup`, `voldown`, `back`, `home`,
…), network state (`online`, `offline`, `latency:MS`), camera test pattern,
clipboard text, and USB serial data can be updated dynamically at runtime without
rebooting:

```bash
python3 ./tools/qemu_hw_controller.py --port 5555 status
python3 ./tools/qemu_hw_controller.py --port 5555 locale en
python3 ./tools/qemu_hw_controller.py --port 5555 locale zh-Hans
python3 ./tools/qemu_hw_controller.py --port 5555 locale list
python3 ./tools/qemu_hw_controller.py --port 5555 region US
python3 ./tools/qemu_hw_controller.py --port 5555 gps 31.2304,121.4737,15.0,3.5,90.0
python3 ./tools/qemu_hw_controller.py --port 5555 accel 0.0,9.81,0.0
python3 ./tools/qemu_hw_controller.py --port 5555 rotation 0.0,0.0,0.7071,0.7071
python3 ./tools/qemu_hw_controller.py --port 5555 headposture 1.0,0.0,0.0,0.0
python3 ./tools/qemu_hw_controller.py --port 5555 gyro 0.05,-0.02,0.12
python3 ./tools/qemu_hw_controller.py --port 5555 light 650.0
python3 ./tools/qemu_hw_controller.py --port 5555 proximity 0.0
python3 ./tools/qemu_hw_controller.py --port 5555 barometer 1013.25
python3 ./tools/qemu_hw_controller.py --port 5555 magnetic 25.0,-10.0,42.0
python3 ./tools/qemu_hw_controller.py --port 5555 battery 75:discharging
python3 ./tools/qemu_hw_controller.py --port 5555 thermal 38.5
python3 ./tools/qemu_hw_controller.py --port 5555 key volup
python3 ./tools/qemu_hw_controller.py --port 5555 network offline
python3 ./tools/qemu_hw_controller.py --port 5555 network online
python3 ./tools/qemu_hw_controller.py --port 5555 camera smpte
python3 ./tools/qemu_hw_controller.py --port 5555 clipboard-set "Hello OpenHarmony"
python3 ./tools/qemu_hw_controller.py --port 5555 clipboard-get
python3 ./tools/qemu_hw_controller.py --port 5555 usb-serial-send "AT+TEST"
python3 ./tools/qemu_hw_controller.py --port 5555 usb-serial-read
```

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

The following commands document the historical source-preparation interface.
These recipes and helpers now belong to their component repositories; the
compatibility tree is generated from the complete manifest lock.
Follow [repository migration status](docs/repository-migration.md) before using
these commands. Their transfer does not validate the legacy builder against the
new QEMU branches. Phone and 2in1 remain separate historical entry points:

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

Development HAPs require a signing block. A truly unsigned package is rejected
with bundle-manager error `9568320` (`no signature file`). The default installer
also installs the Java-free `hap-sign` CLI under `~/.ohos-qemu/bin`; use
`--without-hap-signer` when only the image is wanted.

Read the target guest's UDID before signing. The `v20261107` ARM64 2in1 image
rejects the signer's default `--device-id '*'` with error `9568423` (device
unauthorized), even when developer mode and `oemmode=rd` are enabled:

```bash
export PATH="$HOME/.ohos-qemu/bin:$PATH"

hdc tconn 127.0.0.1:5555
hdc -t 127.0.0.1:5555 shell bm get --udid

# Replace QEMU_UDID with the 64-character value printed above.
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --device-id QEMU_UDID \
  --output entry-default-signed.hap

hdc -t 127.0.0.1:5555 install entry-default-signed.hap
```

The bundle name must match `app.bundleName` inside the HAP. Keep code signing
enabled. For permissions requiring a profile ACL, add `--acl`; it may be
repeated for multiple permissions:

```bash
hap-sign sign entry-default-unsigned.hap \
  --bundle-name com.example.application \
  --device-id QEMU_UDID \
  --acl ohos.permission.READ_PASTEBOARD \
  --acl ohos.permission.MANAGE_VPN \
  --output entry-default-signed.hap
```

Include only the ACLs needed by the application's declared permissions. On
`v20261107` ARM64 2in1, a normal-APL app declaring `READ_PASTEBOARD` failed with
`9568289` until its signed profile included that ACL. Runtime permission grants
remain a separate step. See [Development HAP signing](docs/development-hap-signing.md)
for the verified commands, error reference, and why the older image accepted
the default device ID.

From a source checkout, `scripts/sign-hap.sh` is the equivalent wrapper and
`scripts/install-hap-signer.sh` installs the signer. Release packages carry the
same scripts under `tools/`. `sign-hap.sh` also accepts environment variables
(`OHOS_HAP_INPUT`, `OHOS_HAP_OUTPUT`, `OHOS_HAP_BUNDLE_NAME`,
`OHOS_HAP_DEVICE_ID` / `OHOS_QEMU_UDID`, `OHOS_HAP_ACLS`, `OHOS_HAP_APL`,
`OHOS_HAP_FORCE`) for CI pipelines, with explicit CLI flags taking precedence.
The signer is implemented in the separate
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
- QEMU RD/developer-device boot mode. Include the actual guest UDID in debug
  signing profiles; RD boot settings alone do not guarantee a UDID exemption
  in every release's verifier path.

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
The 2in1 profile enables SceneBoard and the PC freeform window layout, installs
`/etc/sceneboard.config` as `ENABLED`, and sets
`const.window.multiWindowUIType=FreeFormMultiWindow`,
`const.window.support_window_pcmode_switch=true`,
`persist.sceneboard.ispcmode=false`, and
`const.window.device.default_screen_rotation=0` alongside a `6x3` landscape
desktop grid (`/system/etc/desktop/grid_layout_config.json` and
`/system/etc/hw_launcher_default_workspace.json`) and floating window support in
`/system/etc/window/resources/window_manager_config.xml`. It automatically reconstructs and stages the
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
