# OpenHarmony QEMU Image Automation Exploration

## Conclusion

Automating OpenHarmony standard-system QEMU image builds is feasible. The
official OpenHarmony repository set already contains QEMU board support, product
definitions, image packaging rules, and QEMU launch scripts.

The practical automation path is:

1. Fetch OpenHarmony source with `repo` and the `openharmony/manifest` groups.
2. Build selected QEMU standard-system products with `./build.sh`.
3. Collect image artifacts from `out/.../packages/phone/images`.
4. Boot the result with the matching `vendor/ohemu/*/qemu_run.sh`.

This project should not target LiteOS mini/small products unless we explicitly
add a separate embedded-kernel track later.

## Useful OpenHarmony Repositories

| Repository | Role |
| --- | --- |
| `openharmony/manifest` | Source checkout manifest. Defines groups such as `ohos:mini`, `ohos:small`, `ohos:standard`, `ohos:system`, and `ohos:chipset`. |
| `openharmony/build` | GN/Ninja based build framework and `./build.sh` entrypoint. |
| `openharmony/device_qemu` | QEMU device/board support, driver adaptation, image packaging config, and platform HOWTO docs. |
| `openharmony/vendor_ohemu` | Community QEMU product samples and `qemu_run.sh` launch scripts. |
| `openharmony/productdefine_common` | Common product inheritance templates, especially standard/headless/rich product templates. |
| `openharmony/kernel_linux_5.10` and related Linux kernel repos | Kernel source used by standard-system QEMU products, depending on OpenHarmony release branch. |

## Product Targets Found

### Standard System, Linux Kernel

| Product name | CPU | Device build path | Image path | Runner |
| --- | --- | --- | --- | --- |
| `qemu-arm-linux-min` | arm | `device/qemu/arm_virt/linux` | `out/qemu-arm-linux/packages/phone/images` | `vendor/ohemu/qemu_arm_linux_min/qemu_run.sh` |
| `qemu-arm64-linux-min` | arm64 | `device/qemu/arm_virt/linux` | `out/qemu-arm-linux/packages/phone/images` | `vendor/ohemu/qemu_arm64_linux_min/qemu_run.sh` |
| `qemu-arm-linux-headless` | arm | `device/qemu/arm_virt/linux` | `out/qemu-arm-linux/packages/phone/images` | `vendor/ohemu/qemu_arm_linux_headless/qemu_run.sh` |
| `qemu-x86_64-linux-min` | x86_64 | `device/qemu/x86_64_virt/linux` | `out/qemu-x86_64-linux/packages/phone/images` | `vendor/ohemu/qemu_x86_64_linux_min/qemu_run.sh` |
| `qemu-riscv64-linux-min` | riscv64 | `device/qemu/riscv64_virt/linux` | `out/qemu-riscv64-linux/packages/phone/images` | `vendor/ohemu/qemu_riscv64_linux_min/qemu_run.sh` |
| `arm64_virt` | arm64 | `device/qemu/arm_virt/linux_full` | `out/arm64_virt/packages/phone/images` | `vendor/ohemu/qemu_arm64_linux_full/qemu_run.sh` |
| `x86_64_virt` | x86_64 | `device/qemu/x86_64_virt/linux_full` | `out/x86_64_virt/packages/phone/images` | `vendor/ohemu/qemu_x86_64_linux_full/qemu_run.sh` |

Standard build command shape:

```sh
./build.sh --product-name qemu-arm64-linux-min --ccache --jobs 8
```

Required runtime files are typically:

- `ramdisk.img`
- `system.img`
- `vendor.img`
- `userdata.img`
- kernel image: `Image`, `zImage-dtb`, or `bzImage` depending on architecture

## Recommended First Automation Target

Start with two release lanes:

1. `qemu-arm64-linux-min`: small headless smoke-test image for validating the
   build and QEMU boot path.
2. `x86_64_virt` and `arm64_virt`: full standard-system images for public
   desktop QEMU use.

Reasons:

- All three are standard-system targets, so the build can use `./build.sh`.
- The min target gives fast CI feedback and simpler serial diagnostics.
- The full targets are better suited for user-facing Windows/macOS/Linux QEMU
  packages because they include richer standard-system capabilities.
- `x86_64_virt` is the default package for x86_64 Windows/Linux/Intel macOS.
- `arm64_virt` is the default package for Apple Silicon macOS and ARM64 Linux.

Minimal CI flow:

```sh
repo init -u https://gitee.com/openharmony/manifest.git -b master -g ohos:standard
repo sync -c -j8
./build/prebuilts_download.sh
./build.sh --product-name qemu-arm64-linux-min --ccache --jobs 8
test -f out/qemu-arm-linux/packages/phone/images/ramdisk.img
test -f out/qemu-arm-linux/packages/phone/images/system.img
test -f out/qemu-arm-linux/packages/phone/images/vendor.img
test -f out/qemu-arm-linux/packages/phone/images/userdata.img
vendor/ohemu/qemu_arm64_linux_min/qemu_run.sh
```

Full image build flow:

```sh
./build.sh --product-name x86_64_virt --ccache --jobs 8
./build.sh --product-name arm64_virt --ccache --jobs 8
test -f out/x86_64_virt/packages/phone/images/bzImage
test -f out/arm64_virt/packages/phone/images/Image
```

## Cross-Host Release Model

The OpenHarmony images are guest-architecture artifacts. Windows, macOS, and
Linux do not need different image contents for the same guest architecture; they
need different QEMU binaries, acceleration settings, display backends, and
launcher scripts.

Recommended release packages:

| Package | Guest arch | Primary hosts | Product | Display default |
| --- | --- | --- | --- | --- |
| `openharmony-qemu-x86_64-full` | x86_64 | Windows x86_64, Linux x86_64, Intel macOS | `x86_64_virt` | VNC for portability, native SDL/GTK optional |
| `openharmony-qemu-arm64-full` | arm64 | Apple Silicon macOS, Linux ARM64 | `arm64_virt` | macOS Cocoa when available, VNC fallback |
| `openharmony-qemu-arm64-headless` | arm64 | CI, smoke tests, servers | `qemu-arm64-linux-min` | serial console |

Each package should contain:

```text
images/
  Image or bzImage
  ramdisk.img
  updater.img
  system.img
  vendor.img
  sys_prod.img
  chip_prod.img
  userdata.img
launch/
  linux.sh
  macos.command
  windows.ps1
  windows.cmd
manifest.json
README.md
SHA256SUMS
```

Do not bundle QEMU binaries by default. Ask users to install QEMU through their
platform package manager, or provide a separate `with-qemu` distribution only if
we are ready to satisfy QEMU's redistribution and source-offer obligations.

Host-specific launcher defaults:

| Host | Preferred guest | QEMU binary | Acceleration | Notes |
| --- | --- | --- | --- | --- |
| Linux x86_64 | `x86_64_virt` | `qemu-system-x86_64` | KVM if `/dev/kvm` is readable, else TCG | Use user-mode NAT by default; bridge mode requires root setup. |
| Linux ARM64 | `arm64_virt` | `qemu-system-aarch64` | KVM if available, else TCG | Useful for ARM servers and ARM Linux desktops. |
| macOS Apple Silicon | `arm64_virt` | `qemu-system-aarch64` | HVF if QEMU supports it, else TCG | Best macOS performance path. |
| macOS Intel | `x86_64_virt` | `qemu-system-x86_64` | HVF if QEMU supports it, else TCG | Intel Macs are legacy but still supportable. |
| Windows x86_64 | `x86_64_virt` | `qemu-system-x86_64.exe` | WHPX if QEMU supports it, else TCG | Prefer VNC display for fewer GTK/SDL packaging issues. |

## Release Automation Stages

1. Build in Linux CI for each selected product.
2. Validate required artifacts and write `manifest.json` with product,
   OpenHarmony revision, build date, guest architecture, and expected QEMU
   binary.
3. Generate host launchers from templates.
4. Package `.tar.zst` for Unix-like hosts and `.zip` for Windows.
5. Boot-smoke each image in headless or VNC mode:
   - `qemu-arm64-linux-min`: serial console smoke test.
   - `x86_64_virt`: VNC/display process smoke test plus serial init markers.
   - `arm64_virt`: VNC/display process smoke test plus serial init markers.
6. Publish checksums and a compatibility table.

## GitHub Actions CI

The workflow `.github/workflows/build-standard-qemu.yml` provides a manual
`workflow_dispatch` entrypoint. Inputs:

- `product`: `all`, `x86_64_virt`, `arm64_virt`, or `qemu-arm64-linux-min`.
- `manifest_url`: defaults to `https://gitee.com/openharmony/manifest.git`.
- `manifest_branch`: defaults to `master`.
- `repo_jobs` and `build_jobs`: parallelism knobs.
- `runner`: defaults to `ubuntu-22.04`.

For real `x86_64_virt` and `arm64_virt` full image builds, prefer a self-hosted
Linux runner with large disk capacity. GitHub-hosted runners can validate the
workflow shape but may not have enough disk and time for a full OpenHarmony
standard-system checkout and build.

The workflow uploads `.tar.gz` and `.zip` QEMU packages generated by
`scripts/package_standard_qemu.sh`.

## Risk Points

- Full OpenHarmony checkout is large. Do not clone the GitHub organization repo
  by repo manually; use `manifest` and `repo` groups.
- QEMU network mode may require `sudo`, bridge setup, `tun/tap`, and
  `/etc/qemu/bridge.conf`; keep network optional in CI.
- Official QEMU docs mention QEMU 5.1+ for tested `virt` targets, while the
  top-level QEMU install guide references QEMU 6.2.0.
- Some runners assume Linux host commands such as `modprobe`, `ip`, `ifconfig`,
  and bridge networking. macOS should run builds inside Linux VM/container.
- Full UI targets may need display backend and accelerator handling; publish
  VNC launchers as the stable baseline and native display launchers as optional.
- Windows/macOS builds should not compile OpenHarmony locally. Build images in
  Linux CI, then distribute ready-to-run QEMU image packages for each host.

## Next Implementation Shape

Create a small wrapper CLI with these commands:

- `fetch`: initialize and sync OpenHarmony standard-system source by manifest
  group.
- `build <product>`: call `./build.sh` for standard-system targets.
- `artifacts <product>`: validate and package expected image files.
- `launchers <product>`: render Linux/macOS/Windows QEMU launcher scripts.
- `smoke <product>`: boot QEMU headlessly and scan serial output for init-ready
  markers, with a timeout.
