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
    OFFICIAL_QEMU_RUN="${SOURCE_ROOT}/vendor/ohemu/qemu_x86_64_linux_full/qemu_run.sh"
    ;;
  arm64_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/arm64_virt/packages/phone/images"
    GUEST_ARCH="arm64"
    KERNEL_FILE="Image"
    QEMU_BIN_UNIX="qemu-system-aarch64"
    QEMU_BIN_WIN="qemu-system-aarch64.exe"
    OFFICIAL_QEMU_RUN="${SOURCE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/qemu_run.sh"
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

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ]; then
  if [ ! -f "${OFFICIAL_QEMU_RUN}" ]; then
    echo "missing official qemu_run.sh: ${OFFICIAL_QEMU_RUN}" >&2
    exit 1
  fi
  cp "${OFFICIAL_QEMU_RUN}" "${LAUNCH_OUT}/qemu_run.sh"
  sed -i -E 's|^OHOS_IMG="(out/[^"]+)"$|OHOS_IMG="${OHOS_IMG:-\1}"|' "${LAUNCH_OUT}/qemu_run.sh"
  chmod +x "${LAUNCH_OUT}/qemu_run.sh"
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
export OHOS_IMG="${IMG}"
exec "${HERE}/launch/qemu_run.sh"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"
elif [ "${PRODUCT}" = "qemu-arm64-linux-min" ]; then
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
