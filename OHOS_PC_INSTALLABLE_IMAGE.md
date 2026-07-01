# OpenHarmony for PC Installable Image Exploration

## Goal

Explore whether we can build an OpenHarmony image that can be installed directly
onto an x86_64 PC, instead of only running OpenHarmony through QEMU `-kernel`
boot parameters.

## Short Answer

It is possible as an engineering project, but it is not just a packaging change
on top of the current `x86_64_virt` QEMU artifacts.

The current `x86_64_virt` product is a QEMU virtual hardware product. It builds
Linux kernel and OpenHarmony partition images, and the provided runner boots
them by passing `bzImage`, `ramdisk.img`, and partition images directly to QEMU.

A PC-installable image needs a different boot and deployment model:

- UEFI boot path, probably GRUB/systemd-boot or direct EFI stub boot.
- GPT disk image layout with an EFI System Partition.
- Installed OpenHarmony partitions on the same target disk.
- Bootloader config that supplies the OpenHarmony kernel command line.
- Hardware support beyond QEMU virtio devices.
- An installer or image flasher workflow.

## What We Already Have

### x86_64 standard-system product

`vendor/ohemu/qemu_x86_64_linux_full/config.json` defines:

- `product_name`: `x86_64_virt`
- `target_cpu`: `x86_64`
- `device_build_path`: `device/qemu/x86_64_virt/linux_full`

Build output:

```text
out/x86_64_virt/packages/phone/images/
  bzImage
  ramdisk.img
  updater.img
  system.img
  vendor.img
  sys_prod.img
  chip_prod.img
  userdata.img
```

### Kernel config has useful PC boot signals

The `device/qemu/common/virt_full/kernel/x86_64_virt_defconfig` includes useful
options for a PC-like boot path:

- `CONFIG_EFI=y`
- `CONFIG_EFI_STUB=y`
- `CONFIG_EFI_PARTITION=y`
- `CONFIG_FB_EFI=y`
- `CONFIG_EFIVAR_FS=y`
- `CONFIG_NVME_CORE=y`
- `CONFIG_ATA=y`
- `CONFIG_SATA_AHCI=y`
- `CONFIG_USB_XHCI_HCD=y`
- `CONFIG_DRM_I915=y`
- `CONFIG_DRM_VIRTIO_GPU=y`
- `CONFIG_VIRTIO_BLK=y`
- `CONFIG_VIRTIO_NET=y`

This means the kernel is not obviously blocked from UEFI/GPT/NVMe/SATA boot
experiments, but it is not proof that arbitrary PCs will boot successfully.

### Product component templates mention PC

`productdefine_common/README_zh.md` documents an `inherit/pc.json` template as
"PC部件集合，个人PC解决方案". However, the currently inspected repository snapshot
does not contain a mature PC hardware product or ISO installer target. Treat the
PC template as a component selection hint, not as a complete installable PC
distribution.

### Installer components exist

Standard/rich product configurations include updater/installer components such
as:

- `updater`
- `sys_installer`

These are useful, but they do not by themselves generate a bootable PC ISO or a
generic bare-metal install disk.

## Main Gap From QEMU Image to PC Installable Image

Current QEMU launcher:

```text
qemu-system-x86_64 \
  -kernel images/bzImage \
  -initrd images/ramdisk.img \
  -drive file=system.img ...
```

PC installable boot target:

```text
UEFI firmware
  -> EFI System Partition
  -> bootloader or EFI stub
  -> bzImage + initrd
  -> root=/dev/ram0 plus ohos.required_mount.* entries
  -> mounted OpenHarmony partitions from GPT disk
```

So the missing artifact is a real disk image, for example:

```text
openharmony-pc-x86_64.img
  p1 EFI System Partition, FAT32
     /EFI/BOOT/BOOTX64.EFI
     /EFI/openharmony/grub.cfg
     /EFI/openharmony/bzImage
     /EFI/openharmony/ramdisk.img
  p2 updater
  p3 chip_prod
  p4 sys_prod
  p5 system
  p6 vendor
  p7 userdata
```

An ISO can be a delivery format, but the first technically simpler target should
be a raw or qcow2 disk image that boots under OVMF. If that works, we can add an
ISO installer later.

## Proposed Phases

### Phase 1: UEFI disk image that boots in QEMU

Build `x86_64_virt`, then assemble a GPT disk image:

1. Create a sparse raw disk.
2. Partition it with GPT.
3. Create an EFI System Partition.
4. Copy `bzImage` and `ramdisk.img` to the EFI partition.
5. Copy OpenHarmony raw images into their GPT partitions.
6. Generate bootloader config with the current kernel bootargs.
7. Boot with QEMU + OVMF:

```sh
qemu-system-x86_64 \
  -machine q35 \
  -m 4096 \
  -bios /usr/share/OVMF/OVMF_CODE.fd \
  -drive if=virtio,file=openharmony-pc-x86_64.img,format=raw \
  -vnc :21 \
  -serial stdio
```

Success criteria:

- UEFI loads the bootloader.
- Bootloader loads `bzImage` and `ramdisk.img`.
- Kernel reaches OpenHarmony init.
- Required partitions mount from the GPT disk.

Implemented prototype script:

```sh
scripts/make_pc_uefi_disk.sh \
  --source-root <openharmony-root> \
  --product x86_64_virt \
  --output out/openharmony-pc-x86_64.img \
  --disk-size 32G
```

It creates:

- `openharmony-pc-x86_64.img`
- `openharmony-pc-x86_64.img.qcow2` when `qemu-img` is available
- `openharmony-pc-x86_64.img.manifest.json`

The disk currently uses a standalone GRUB `BOOTX64.EFI` and a GPT layout:

```text
p1 EFI-SYSTEM  FAT32
p2 updater     raw ext image copied from updater.img
p3 chip_prod   raw ext image copied from chip_prod.img
p4 sys_prod    raw ext image copied from sys_prod.img
p5 system      raw ext image copied from system.img
p6 vendor      raw ext image copied from vendor.img
p7 userdata    raw ext image copied from userdata.img
```

This is still experimental. The initial bootargs assume the disk appears as
`/dev/block/vda*`, which is correct for QEMU virtio disk smoke tests, but not
generic enough for arbitrary real PCs.

### Phase 2: Generic PC image smoke on virtual hardware

Broaden virtual hardware coverage:

- QEMU q35 + virtio disk/network
- QEMU q35 + SATA/AHCI disk
- QEMU q35 + NVMe disk
- VNC display and serial logs

This catches bootloader, root device naming, and partition discovery issues
before testing real PCs.

### Phase 3: Physical PC bring-up

Start with a narrow hardware profile:

- x86_64 UEFI-only machine
- Intel integrated graphics preferred
- SATA or NVMe storage
- USB keyboard/mouse
- Ethernet preferred over Wi-Fi
- Secure Boot disabled

## Physical PC Hardware Requirements

### Minimum to attempt boot

Use a spare machine where wiping the disk is acceptable.

| Area | Minimum |
| --- | --- |
| CPU | x86_64 CPU, preferably Intel Core-class. AMD x86_64 may boot, but is not the first target. |
| Firmware | UEFI boot support. Legacy BIOS/CSM is out of scope for the first prototype. |
| Secure Boot | Disabled. The generated `BOOTX64.EFI` is not Secure Boot signed. |
| RAM | 8 GB minimum, 16 GB recommended. |
| Storage | Dedicated SATA SSD or NVMe SSD, 64 GB minimum, 128 GB recommended. The prototype image overwrites the target disk. |
| Storage mode | AHCI or plain NVMe. Disable Intel RST/RAID/VMD for first bring-up. |
| Graphics | Intel integrated GPU is the first supported target. |
| Input | USB keyboard and mouse. Built-in laptop touchpads are not a first target. |
| Network | Wired Ethernet preferred. Intel e1000/e1000e and Realtek r8169 have kernel config coverage. |
| Wi-Fi | Not required for first boot. Intel Wi-Fi has `iwlwifi` as a module, but firmware/userspace readiness still needs validation. |

### Recommended first test machine

- Intel NUC or small desktop
- Intel integrated graphics
- SATA SSD in AHCI mode, or simple NVMe SSD
- USB keyboard/mouse
- Intel or Realtek wired Ethernet
- UEFI-only boot with Secure Boot off
- No dual boot on the same disk

### High-risk hardware for the first prototype

- NVIDIA dGPU-only machines
- AMD dGPU-only machines
- New laptops requiring vendor-specific ACPI/platform drivers
- Storage behind Intel RST/RAID/VMD
- Wi-Fi-only devices
- Secure Boot-only locked devices

The inspected `x86_64_virt_defconfig` has `CONFIG_DRM_I915=y`, but
`CONFIG_DRM_AMDGPU` and `CONFIG_DRM_NOUVEAU` are not enabled. That makes Intel
integrated graphics the pragmatic first target.

Expected first-boot gaps:

- Graphics stack may not match arbitrary GPUs.
- Wi-Fi and Bluetooth device support will be limited.
- Touchpad, suspend/resume, audio, battery, brightness, and hotkeys may need
  platform-specific work.
- Partition mount paths must be stable across SATA/NVMe.

### Phase 4: Installer ISO

After the raw disk image works:

- Build a small Linux or OpenHarmony-based installer environment.
- Include `system.img`, `vendor.img`, `sys_prod.img`, `chip_prod.img`, and
  default `userdata.img`.
- Partition the target disk.
- Copy partitions.
- Install EFI boot files.
- Generate machine-specific boot config.

## Product Direction

We should not rename the current `x86_64_virt` package as "OpenHarmony for PC".
It is a useful base, but the PC installable product should be explicit, for
example:

- `openharmony-pc-x86_64-uefi`
- `product_name`: eventually `x86_64_pc` or `pc_x86_64`
- inherit set: likely `rich.json` plus a PC-specific template if available
- device path: new `device/pc/x86_64` or similar, not `device/qemu/x86_64_virt`

## Recommended Next Work

1. Add a new packer script:

```text
scripts/make_pc_uefi_disk.sh
```

Inputs:

- `--source-root`
- `--product x86_64_virt`
- `--output openharmony-pc-x86_64.img`
- `--disk-size 32G`

Outputs:

- `openharmony-pc-x86_64.img`
- `openharmony-pc-x86_64.qcow2`
- `BOOTX64.EFI`/GRUB config logs
- partition manifest

2. Add a CI job that builds `x86_64_virt`, creates the UEFI disk image, and
   boots it with OVMF in QEMU.

3. Only after QEMU/OVMF disk boot passes, test a real PC.

## Risk Assessment

| Area | Risk |
| --- | --- |
| Bootloader | Medium. Kernel has EFI stub, but the current flow bypasses UEFI. |
| Partition mounting | Medium. Existing bootargs use fixed `/dev/block/vd*` mappings from QEMU. PC storage may produce different device names. |
| Display | High. QEMU uses virtual GPU paths; real PCs need i915/amdgpu/nouveau paths and userspace compatibility. |
| Input | Medium. USB HID likely works; laptop touchpads may not. |
| Network | Medium. Ethernet is more realistic than Wi-Fi initially. |
| Installer UX | High. No mature PC ISO installer was found in the current official QEMU/product snapshot. |

## Current Decision

Proceed with a staged prototype:

1. Keep current QEMU packages.
2. Add an experimental UEFI disk packer based on `x86_64_virt`.
3. Validate with QEMU + OVMF.
4. Treat real PC installability as a later hardware enablement milestone.
