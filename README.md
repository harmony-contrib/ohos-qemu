# OpenHarmony QEMU Images

This repository packages reusable OpenHarmony standard-system QEMU images for
local development and CI smoke testing.

## Packages

Image archives are stored in Git LFS under `artifacts/`:

- `openharmony-qemu-arm64-arm64_virt.tar.gz`: arm64 guest image, suitable for
  arm64 macOS hosts through QEMU.
- `openharmony-qemu-x86_64-x86_64_virt.tar.gz`: x86_64 guest image, suitable for
  x86_64 Linux and Windows hosts through QEMU.

Each package contains image files, launch scripts, a package manifest, and
checksums.

## CI

The `QEMU Smoke Tests` workflow downloads the LFS package, starts QEMU, waits
for HDC on `127.0.0.1:5555`, and runs two smoke checks:

- a static Rust executable transferred and executed through HDC;
- a Cargo test built for `*-unknown-linux-ohos` and executed with
  `openharmony-rs/ohos-test-runner`.

The workflow uses `openharmony-rs/setup-ohos-sdk` to install the OpenHarmony SDK
and HDC.

## Local Use

Network install:

```bash
curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash
```

Install QEMU and extract one of the packages from `artifacts/`, then run the
matching launcher in the package:

- Linux: `launch/linux.sh`
- macOS: `launch/macos.command`
- Windows: `launch/windows.ps1`

HDC is forwarded through host TCP port `5555` when the guest is running.

## License

[MIT](./LICENSE)
