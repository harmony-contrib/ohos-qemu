#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  make_pc_uefi_disk.sh --source-root ROOT --output FILE [options]

Options:
  --product PRODUCT       Only x86_64_virt is currently supported.
  --disk-size SIZE        Raw disk size passed to truncate, default: 32G.
  --qemu-smoke           Run a short QEMU + OVMF boot smoke after creating disk.
  --smoke-timeout SEC    QEMU smoke timeout, default: 90.
  -h, --help             Show this help.

Required host tools:
  sgdisk losetup partprobe mkfs.vfat grub-mkstandalone dd mount umount

Optional host tools:
  qemu-img qemu-system-x86_64 timeout

The script creates an experimental UEFI/GPT disk image from already-built
OpenHarmony x86_64_virt standard-system artifacts.
USAGE
}

SOURCE_ROOT=
PRODUCT=x86_64_virt
OUTPUT=
DISK_SIZE=32G
QEMU_SMOKE=0
SMOKE_TIMEOUT=90

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
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --disk-size)
      DISK_SIZE="${2:-}"
      shift 2
      ;;
    --qemu-smoke)
      QEMU_SMOKE=1
      shift
      ;;
    --smoke-timeout)
      SMOKE_TIMEOUT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${SOURCE_ROOT}" ] || [ -z "${OUTPUT}" ]; then
  usage >&2
  exit 2
fi

if [ "${PRODUCT}" != "x86_64_virt" ]; then
  echo "unsupported product: ${PRODUCT}; only x86_64_virt is supported" >&2
  exit 2
fi

if [ "$(uname -s)" != "Linux" ]; then
  echo "this script must run on Linux" >&2
  exit 1
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

for cmd in sgdisk losetup partprobe mkfs.vfat grub-mkstandalone dd mount umount stat truncate findmnt; do
  require_cmd "${cmd}"
done

SUDO=
if [ "$(id -u)" != "0" ]; then
  require_cmd sudo
  SUDO=sudo
fi

SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd)"
OUTPUT_DIR="$(dirname "${OUTPUT}")"
mkdir -p "${OUTPUT_DIR}"
OUTPUT="$(cd "${OUTPUT_DIR}" && pwd)/$(basename "${OUTPUT}")"

IMAGE_DIR="${SOURCE_ROOT}/out/x86_64_virt/packages/phone/images"
REQUIRED_IMAGES=(
  bzImage
  ramdisk.img
  updater.img
  chip_prod.img
  sys_prod.img
  system.img
  vendor.img
  userdata.img
)

for image in "${REQUIRED_IMAGES[@]}"; do
  if [ ! -f "${IMAGE_DIR}/${image}" ]; then
    echo "missing required image: ${IMAGE_DIR}/${image}" >&2
    exit 1
  fi
done

file_mib() {
  local file="$1"
  local margin_mib="$2"
  local bytes
  bytes="$(stat -c '%s' "${file}")"
  echo $(( (bytes + 1048575) / 1048576 + margin_mib ))
}

ESP_MIB=512
UPDATER_MIB="$(file_mib "${IMAGE_DIR}/updater.img" 64)"
CHIP_PROD_MIB="$(file_mib "${IMAGE_DIR}/chip_prod.img" 64)"
SYS_PROD_MIB="$(file_mib "${IMAGE_DIR}/sys_prod.img" 64)"
SYSTEM_MIB="$(file_mib "${IMAGE_DIR}/system.img" 256)"
VENDOR_MIB="$(file_mib "${IMAGE_DIR}/vendor.img" 128)"
USERDATA_MIN_MIB="$(file_mib "${IMAGE_DIR}/userdata.img" 512)"

mkdir -p "$(dirname "${OUTPUT}")"
rm -f "${OUTPUT}" "${OUTPUT}.qcow2" "${OUTPUT}.manifest.json" "${OUTPUT}.qemu-smoke.log"
truncate -s "${DISK_SIZE}" "${OUTPUT}"

disk_bytes="$(stat -c '%s' "${OUTPUT}")"
disk_mib="$(( disk_bytes / 1048576 ))"
reserved_mib=64
needed_mib="$(( ESP_MIB + UPDATER_MIB + CHIP_PROD_MIB + SYS_PROD_MIB + SYSTEM_MIB + VENDOR_MIB + USERDATA_MIN_MIB + reserved_mib ))"
if [ "${disk_mib}" -lt "${needed_mib}" ]; then
  echo "disk too small: ${DISK_SIZE} gives ${disk_mib} MiB, need at least ${needed_mib} MiB" >&2
  exit 1
fi

start_mib=4
next_end() {
  local size_mib="$1"
  echo $(( start_mib + size_mib ))
}

make_part() {
  local num="$1"
  local name="$2"
  local size_mib="$3"
  local typecode="$4"
  local end_mib
  end_mib="$(next_end "${size_mib}")"
  sgdisk -n "${num}:${start_mib}MiB:${end_mib}MiB" -c "${num}:${name}" -t "${num}:${typecode}" "${OUTPUT}" >/dev/null
  start_mib="${end_mib}"
}

sgdisk --zap-all "${OUTPUT}" >/dev/null
sgdisk -o "${OUTPUT}" >/dev/null
make_part 1 "EFI-SYSTEM" "${ESP_MIB}" "EF00"
make_part 2 "updater" "${UPDATER_MIB}" "8300"
make_part 3 "chip_prod" "${CHIP_PROD_MIB}" "8300"
make_part 4 "sys_prod" "${SYS_PROD_MIB}" "8300"
make_part 5 "system" "${SYSTEM_MIB}" "8300"
make_part 6 "vendor" "${VENDOR_MIB}" "8300"
sgdisk -n "7:${start_mib}MiB:-34" -c "7:userdata" -t "7:8300" "${OUTPUT}" >/dev/null

LOOP=
MNT=
cleanup() {
  set +e
  if [ -n "${MNT}" ] && findmnt -rn "${MNT}" >/dev/null 2>&1; then
    ${SUDO} umount "${MNT}"
  fi
  if [ -n "${MNT}" ] && [ -d "${MNT}" ]; then
    rmdir "${MNT}" 2>/dev/null || true
  fi
  if [ -n "${LOOP}" ]; then
    ${SUDO} losetup -d "${LOOP}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

LOOP="$(${SUDO} losetup --find --show --partscan "${OUTPUT}")"
${SUDO} partprobe "${LOOP}" || true
sleep 1

part_path() {
  local num="$1"
  if [ -e "${LOOP}p${num}" ]; then
    echo "${LOOP}p${num}"
  elif [ -e "${LOOP}${num}" ]; then
    echo "${LOOP}${num}"
  else
    echo "partition ${num} not found for ${LOOP}" >&2
    exit 1
  fi
}

P1="$(part_path 1)"
P2="$(part_path 2)"
P3="$(part_path 3)"
P4="$(part_path 4)"
P5="$(part_path 5)"
P6="$(part_path 6)"
P7="$(part_path 7)"

${SUDO} mkfs.vfat -F 32 -n OHOS_EFI "${P1}" >/dev/null
${SUDO} dd if="${IMAGE_DIR}/updater.img" of="${P2}" bs=16M conv=fsync,status=none
${SUDO} dd if="${IMAGE_DIR}/chip_prod.img" of="${P3}" bs=16M conv=fsync,status=none
${SUDO} dd if="${IMAGE_DIR}/sys_prod.img" of="${P4}" bs=16M conv=fsync,status=none
${SUDO} dd if="${IMAGE_DIR}/system.img" of="${P5}" bs=16M conv=fsync,status=none
${SUDO} dd if="${IMAGE_DIR}/vendor.img" of="${P6}" bs=16M conv=fsync,status=none
${SUDO} dd if="${IMAGE_DIR}/userdata.img" of="${P7}" bs=16M conv=fsync,status=none

WORK_DIR="$(mktemp -d)"
GRUB_CFG="${WORK_DIR}/grub.cfg"
BOOT_EFI="${WORK_DIR}/BOOTX64.EFI"
cat > "${GRUB_CFG}" <<'EOF'
set timeout=3
set default=0

menuentry "OpenHarmony x86_64 PC experimental" {
    linux /EFI/openharmony/bzImage console=ttyS0,115200 console=tty0 sn=0023456789 init=/init hardware=pc root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=pc ohos.required_mount.updater=/dev/block/vda2@/updater@ext4@ro,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vda3@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vda4@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.system=/dev/block/vda5@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vda6@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.data=/dev/block/vda7@/data@ext4@nosuid,nodev,noatime,barrier=1,data=ordered,noauto_da_alloc@wait,reservedsize=104857600
    initrd /EFI/openharmony/ramdisk.img
}
EOF

grub-mkstandalone \
  -O x86_64-efi \
  -o "${BOOT_EFI}" \
  "boot/grub/grub.cfg=${GRUB_CFG}" \
  >/dev/null

MNT="$(mktemp -d)"
${SUDO} mount "${P1}" "${MNT}"
${SUDO} mkdir -p "${MNT}/EFI/BOOT" "${MNT}/EFI/openharmony"
${SUDO} cp "${BOOT_EFI}" "${MNT}/EFI/BOOT/BOOTX64.EFI"
${SUDO} cp "${GRUB_CFG}" "${MNT}/EFI/openharmony/grub.cfg"
${SUDO} cp "${IMAGE_DIR}/bzImage" "${MNT}/EFI/openharmony/bzImage"
${SUDO} cp "${IMAGE_DIR}/ramdisk.img" "${MNT}/EFI/openharmony/ramdisk.img"
sync
${SUDO} umount "${MNT}"
rmdir "${MNT}"
MNT=
rm -rf "${WORK_DIR}"

${SUDO} losetup -d "${LOOP}"
LOOP=

if command -v qemu-img >/dev/null 2>&1; then
  qemu-img convert -f raw -O qcow2 "${OUTPUT}" "${OUTPUT}.qcow2"
fi

cat > "${OUTPUT}.manifest.json" <<EOF
{
  "product": "x86_64_virt",
  "format": "pc-uefi-gpt-experimental",
  "disk": "$(basename "${OUTPUT}")",
  "disk_size": "${DISK_SIZE}",
  "partitions": [
    { "number": 1, "name": "EFI-SYSTEM", "mount": "ESP", "source": "generated FAT32" },
    { "number": 2, "name": "updater", "source": "updater.img" },
    { "number": 3, "name": "chip_prod", "source": "chip_prod.img" },
    { "number": 4, "name": "sys_prod", "source": "sys_prod.img" },
    { "number": 5, "name": "system", "source": "system.img" },
    { "number": 6, "name": "vendor", "source": "vendor.img" },
    { "number": 7, "name": "userdata", "source": "userdata.img" }
  ],
  "bootloader": "GRUB standalone x86_64-efi",
  "qemu_smoke_command": "qemu-system-x86_64 -machine q35 -m 4096 -bios /usr/share/OVMF/OVMF_CODE.fd -drive if=virtio,file=$(basename "${OUTPUT}"),format=raw -vnc :21 -serial stdio"
}
EOF

if [ "${QEMU_SMOKE}" = "1" ]; then
  require_cmd qemu-system-x86_64
  require_cmd timeout
  OVMF_CODE=
  for candidate in \
    /usr/share/OVMF/OVMF_CODE.fd \
    /usr/share/ovmf/OVMF.fd \
    /usr/share/edk2/ovmf/OVMF_CODE.fd; do
    if [ -f "${candidate}" ]; then
      OVMF_CODE="${candidate}"
      break
    fi
  done
  if [ -z "${OVMF_CODE}" ]; then
    echo "OVMF firmware not found; install ovmf or pass smoke manually" >&2
    exit 1
  fi
  set +e
  timeout "${SMOKE_TIMEOUT}" qemu-system-x86_64 \
    -machine q35 \
    -m 4096 \
    -bios "${OVMF_CODE}" \
    -drive "if=virtio,file=${OUTPUT},format=raw" \
    -display none \
    -serial stdio \
    >"${OUTPUT}.qemu-smoke.log" 2>&1
  rc=$?
  set -e
  if [ "${rc}" != "124" ] && [ "${rc}" != "0" ]; then
    echo "QEMU smoke failed with exit code ${rc}; see ${OUTPUT}.qemu-smoke.log" >&2
    exit "${rc}"
  fi
fi

echo "${OUTPUT}"
if [ -f "${OUTPUT}.qcow2" ]; then
  echo "${OUTPUT}.qcow2"
fi
echo "${OUTPUT}.manifest.json"
