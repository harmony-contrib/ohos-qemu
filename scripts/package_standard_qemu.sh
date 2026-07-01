#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  package_standard_qemu.sh --source-root ROOT --product PRODUCT --output-dir DIR

Products:
  x86_64_virt
  arm64_virt
  qemu-arm64-linux-min

This packages already-built OpenHarmony standard-system QEMU images and
generates Linux, macOS, and Windows launchers where applicable.
USAGE
}

SOURCE_ROOT=
PRODUCT=
OUTPUT_DIR=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --product)
      PRODUCT="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "${SOURCE_ROOT}" ] || [ -z "${PRODUCT}" ] || [ -z "${OUTPUT_DIR}" ]; then
  usage >&2
  exit 2
fi

case "${PRODUCT}" in
  x86_64_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/x86_64_virt/packages/phone/images"
    GUEST_ARCH="x86_64"
    KERNEL_FILE="bzImage"
    QEMU_BIN_UNIX="qemu-system-x86_64"
    QEMU_BIN_WIN="qemu-system-x86_64.exe"
    ;;
  arm64_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/arm64_virt/packages/phone/images"
    GUEST_ARCH="arm64"
    KERNEL_FILE="Image"
    QEMU_BIN_UNIX="qemu-system-aarch64"
    QEMU_BIN_WIN="qemu-system-aarch64.exe"
    ;;
  qemu-arm64-linux-min)
    IMAGE_DIR="${SOURCE_ROOT}/out/qemu-arm-linux/packages/phone/images"
    GUEST_ARCH="arm64"
    KERNEL_FILE="Image"
    QEMU_BIN_UNIX="qemu-system-aarch64"
    QEMU_BIN_WIN="qemu-system-aarch64.exe"
    ;;
  *)
    echo "unsupported product: ${PRODUCT}" >&2
    exit 2
    ;;
esac

COMMON_IMAGES=(
  "${KERNEL_FILE}"
  "ramdisk.img"
  "system.img"
  "vendor.img"
  "userdata.img"
  "updater.img"
)

FULL_ONLY_IMAGES=(
  "sys_prod.img"
  "chip_prod.img"
)

for file in "${COMMON_IMAGES[@]}"; do
  if [ ! -f "${IMAGE_DIR}/${file}" ]; then
    echo "missing required image: ${IMAGE_DIR}/${file}" >&2
    exit 1
  fi
done

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ]; then
  for file in "${FULL_ONLY_IMAGES[@]}"; do
    if [ ! -f "${IMAGE_DIR}/${file}" ]; then
      echo "missing required full image: ${IMAGE_DIR}/${file}" >&2
      exit 1
    fi
  done
fi

PACKAGE_NAME="openharmony-qemu-${GUEST_ARCH}-${PRODUCT}"
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"
IMAGES_OUT="${PACKAGE_DIR}/images"
LAUNCH_OUT="${PACKAGE_DIR}/launch"

rm -rf "${PACKAGE_DIR}"
mkdir -p "${IMAGES_OUT}" "${LAUNCH_OUT}"

for file in "${COMMON_IMAGES[@]}"; do
  cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
done

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ]; then
  for file in "${FULL_ONLY_IMAGES[@]}"; do
    cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
  done
fi

cat > "${PACKAGE_DIR}/manifest.json" <<EOF
{
  "product": "${PRODUCT}",
  "guest_arch": "${GUEST_ARCH}",
  "kernel": "${KERNEL_FILE}",
  "qemu_unix": "${QEMU_BIN_UNIX}",
  "qemu_windows": "${QEMU_BIN_WIN}",
  "display_default": "vnc",
  "network_default": "user"
}
EOF

cat > "${PACKAGE_DIR}/README.md" <<EOF
# ${PACKAGE_NAME}

This package contains an OpenHarmony standard-system QEMU image.

Install QEMU on the host first, then run one of:

- Linux: \`launch/linux.sh\`
- macOS: \`launch/macos.command\`
- Windows PowerShell: \`launch/windows.ps1\`

The default display is VNC on port 5921. Connect a VNC client to
\`127.0.0.1:5921\` after launch. HDC/debug forwarding uses host TCP port 5555
where supported by the guest.
EOF

if [ "${PRODUCT}" = "x86_64_virt" ]; then
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
ACCEL_ARGS=(-accel tcg,thread=multi)
if [ -r /dev/kvm ]; then
  ACCEL_ARGS=(-accel kvm)
fi
exec qemu-system-x86_64 \
  -machine q35 \
  "${ACCEL_ARGS[@]}" \
  -cpu max \
  -smp 4 \
  -m 4096 \
  -kernel "${IMG}/bzImage" \
  -initrd "${IMG}/ramdisk.img" \
  -device virtio-gpu-pci,xres=800,yres=500 \
  -vnc :21 \
  -serial stdio \
  -device virtio-mouse-pci \
  -device virtio-keyboard-pci \
  -netdev user,id=net0,hostfwd=tcp::5555-:5555 \
  -device virtio-net-pci,netdev=net0 \
  -drive if=none,file="${IMG}/updater.img",format=raw,id=updater \
  -device virtio-blk-pci,drive=updater,serial=updater \
  -drive if=none,file="${IMG}/system.img",format=raw,id=system \
  -device virtio-blk-pci,drive=system,serial=system \
  -drive if=none,file="${IMG}/vendor.img",format=raw,id=vendor \
  -device virtio-blk-pci,drive=vendor,serial=vendor \
  -drive if=none,file="${IMG}/sys_prod.img",format=raw,id=sys_prod \
  -device virtio-blk-pci,drive=sys_prod,serial=sys_prod \
  -drive if=none,file="${IMG}/chip_prod.img",format=raw,id=chip_prod \
  -device virtio-blk-pci,drive=chip_prod,serial=chip_prod \
  -drive if=none,file="${IMG}/userdata.img",format=raw,id=userdata \
  -device virtio-blk-pci,drive=userdata,serial=userdata \
  -append "console=ttyS0,115200 sn=0023456789 init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@ext4@nosuid,nodev,noatime,barrier=1,data=ordered,noauto_da_alloc@wait,reservedsize=104857600"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"

  cat > "${LAUNCH_OUT}/windows.ps1" <<'EOF'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Img = Join-Path $Root "images"
$AccelArgs = @("-accel", "tcg,thread=multi")
try {
  $AccelHelp = & qemu-system-x86_64.exe -accel help 2>&1 | Out-String
  if ($AccelHelp -match "whpx") {
    $AccelArgs = @("-accel", "whpx,kernel-irqchip=off")
  }
} catch {
  $AccelArgs = @("-accel", "tcg,thread=multi")
}
$Updater = Join-Path $Img "updater.img"
$System = Join-Path $Img "system.img"
$Vendor = Join-Path $Img "vendor.img"
$SysProd = Join-Path $Img "sys_prod.img"
$ChipProd = Join-Path $Img "chip_prod.img"
$Userdata = Join-Path $Img "userdata.img"
& qemu-system-x86_64.exe `
  -machine q35 `
  @AccelArgs `
  -cpu max `
  -smp 4 `
  -m 4096 `
  -kernel (Join-Path $Img "bzImage") `
  -initrd (Join-Path $Img "ramdisk.img") `
  -device virtio-gpu-pci,xres=800,yres=500 `
  -vnc :21 `
  -serial stdio `
  -device virtio-mouse-pci `
  -device virtio-keyboard-pci `
  -netdev user,id=net0,hostfwd=tcp::5555-:5555 `
  -device virtio-net-pci,netdev=net0 `
  -drive "if=none,file=$Updater,format=raw,id=updater" `
  -device virtio-blk-pci,drive=updater,serial=updater `
  -drive "if=none,file=$System,format=raw,id=system" `
  -device virtio-blk-pci,drive=system,serial=system `
  -drive "if=none,file=$Vendor,format=raw,id=vendor" `
  -device virtio-blk-pci,drive=vendor,serial=vendor `
  -drive "if=none,file=$SysProd,format=raw,id=sys_prod" `
  -device virtio-blk-pci,drive=sys_prod,serial=sys_prod `
  -drive "if=none,file=$ChipProd,format=raw,id=chip_prod" `
  -device virtio-blk-pci,drive=chip_prod,serial=chip_prod `
  -drive "if=none,file=$Userdata,format=raw,id=userdata" `
  -device virtio-blk-pci,drive=userdata,serial=userdata `
  -append "console=ttyS0,115200 sn=0023456789 init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@ext4@nosuid,nodev,noatime,barrier=1,data=ordered,noauto_da_alloc@wait,reservedsize=104857600"
EOF
elif [ "${PRODUCT}" = "arm64_virt" ]; then
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
ACCEL_ARGS=(-accel tcg)
if [ -r /dev/kvm ]; then
  ACCEL_ARGS=(-accel kvm)
fi
exec qemu-system-aarch64 \
  "${ACCEL_ARGS[@]}" \
  -M virt \
  -cpu cortex-a57 \
  -smp 4 \
  -m 4096 \
  -kernel "${IMG}/Image" \
  -initrd "${IMG}/ramdisk.img" \
  -device virtio-gpu-pci,xres=800,yres=500 \
  -vnc :21 \
  -serial stdio \
  -device virtio-mouse-pci \
  -device virtio-keyboard-pci \
  -netdev user,id=net0,hostfwd=tcp::5555-:5555 \
  -device virtio-net-device,netdev=net0,mac=12:22:33:44:55:66 \
  -drive if=none,file="${IMG}/updater.img",format=raw,id=updater \
  -device virtio-blk-device,drive=updater,serial=updater \
  -drive if=none,file="${IMG}/system.img",format=raw,id=system \
  -device virtio-blk-device,drive=system,serial=system \
  -drive if=none,file="${IMG}/vendor.img",format=raw,id=vendor \
  -device virtio-blk-device,drive=vendor,serial=vendor \
  -drive if=none,file="${IMG}/sys_prod.img",format=raw,id=sys_prod \
  -device virtio-blk-device,drive=sys_prod,serial=sys_prod \
  -drive if=none,file="${IMG}/chip_prod.img",format=raw,id=chip_prod \
  -device virtio-blk-device,drive=chip_prod,serial=chip_prod \
  -drive if=none,file="${IMG}/userdata.img",format=raw,id=userdata \
  -device virtio-blk-device,drive=userdata,serial=userdata \
  -append "default_boot_device=a003e00.virtio_mmio sn=0023456789 ip=dhcp loglevel=4 console=ttyAMA0,115200 init=/bin/init ohos.boot.hardware=virt root=/dev/ram0 rw ohos.required_mount.system=/dev/block/vde@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdd@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdc@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vdb@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev,noatime,barrier=1,data=ordered,noauto_da_alloc@wait,reservedsize=104857600"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"
  sed -i.bak 's/ACCEL_ARGS=(-accel tcg)/ACCEL_ARGS=(-accel hvf)/' "${LAUNCH_OUT}/macos.command"
  rm -f "${LAUNCH_OUT}/macos.command.bak"
else
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
exec qemu-system-aarch64 \
  -M virt \
  -smp 4 \
  -m 1024 \
  -nographic \
  -cpu cortex-a57 \
  -kernel "${IMG}/Image" \
  -initrd "${IMG}/ramdisk.img" \
  -drive if=none,file="${IMG}/userdata.img",format=raw,id=userdata,index=3 \
  -device virtio-blk-device,drive=userdata \
  -drive if=none,file="${IMG}/vendor.img",format=raw,id=vendor,index=2 \
  -device virtio-blk-device,drive=vendor \
  -drive if=none,file="${IMG}/system.img",format=raw,id=system,index=1 \
  -device virtio-blk-device,drive=system \
  -drive if=none,file="${IMG}/updater.img",format=raw,id=updater,index=0 \
  -device virtio-blk-device,drive=updater \
  -append "console=ttyAMA0 init=/bin/init hardware=qemu.arm.linux root=/dev/ram0 rw sn=0023456789 ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"
fi

cat > "${LAUNCH_OUT}/windows.cmd" <<'EOF'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0windows.ps1"
EOF

if [ ! -f "${LAUNCH_OUT}/windows.ps1" ]; then
  cat > "${LAUNCH_OUT}/windows.ps1" <<EOF
Write-Error "Windows launcher is not enabled for ${PRODUCT} yet. Use x86_64_virt for Windows x86_64."
exit 1
EOF
fi

chmod +x "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"

(
  cd "${PACKAGE_DIR}"
  find images launch -type f -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
)

(
  cd "${OUTPUT_DIR}"
  tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
  if command -v zip >/dev/null 2>&1; then
    zip -qr "${PACKAGE_NAME}.zip" "${PACKAGE_NAME}"
  fi
)

echo "${PACKAGE_DIR}"
