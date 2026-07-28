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
curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash -s -- --release v20260717
```

The installer downloads the selected Release and installs the package under
`~/.ohos-qemu`. It selects `arm64` on Apple Silicon and `x86_64` on x64 hosts.
Set `OHOS_QEMU_ARCH` to `arm64`, `armv7a`, or `x86_64` before installation to
override the detected guest architecture.

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

Stop QEMU with `Ctrl+C`. Use `QEMU_DISPLAY=none` on Unix or
`$env:QEMU_DISPLAY="none"` in PowerShell for headless mode. Set the value to
`vnc` to connect a VNC client to `127.0.0.1:5921`.

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

## Standard VPN capability

The full `armv7a_virt`, `arm64_virt`, and `x86_64_virt` packages are built with
OpenHarmony's standard VpnExtension stack:

- built-in guest TUN plus IPv4/IPv6 policy routing;
- fs-verity verification for installed HAPs;
- VPN manager System Ability and VpnExtension runtime;
- SettingsData and the system `VpnDialog`.

No application is pre-authorized. The first VPN request must show the system
authorization dialog, and the user's decision is stored in the guest
`userdata.img`.

The build applies
[`overlays/standard_qemu_vpn`](./overlays/standard_qemu_vpn) before compiling.
Packaging then checks the final kernel configuration and `system.img`; a
package is marked with `"standard_vpn": true` only after those checks pass.
The guest VPN uses `/dev/tun` inside OpenHarmony and does not require a host
TAP device when the default QEMU user-mode network is used.

## License

[MIT](./LICENSE)
