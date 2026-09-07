#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: apply.sh --source-root ROOT" >&2
}

SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
if [ -z "${SOURCE_ROOT}" ]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0001-add-virtual-vibrator-target.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0002-declare-vibrator-device-dependencies.patch"
if [ -f "${SOURCE_ROOT}/device/qemu/arm_virt/linux_full_armv7a/bundle.json" ]; then
  bash "${PATCH_ROOT}/lib/apply_patch.sh" \
    "${SOURCE_ROOT}" "${SCRIPT_DIR}/0003-declare-armv7a-vibrator-dependencies.patch"
fi

TARGET_DIR="${SOURCE_ROOT}/vendor/ohemu/virt/hals/vibrator"
mkdir -p "${TARGET_DIR}"
install -m 0644 "${SCRIPT_DIR}/files/BUILD.gn" "${TARGET_DIR}/BUILD.gn"
install -m 0644 "${SCRIPT_DIR}/files/qemu_virtual_vibrator.cpp" \
  "${TARGET_DIR}/qemu_virtual_vibrator.cpp"

echo "QEMU virtual vibrator component configured"
