#!/usr/bin/env bash
set -euo pipefail

DEVICE_TYPE="${1:-}"
[ "${DEVICE_TYPE}" = phone ] || [ "${DEVICE_TYPE}" = 2in1 ] || {
  echo "internal usage: apply_device_type.sh phone|2in1 ..." >&2
  exit 2
}
shift

SOURCE_ROOT=
ARTIFACT_ROOT=
LFS_ASSET_ROOT=
PRODUCTS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --artifact-root) ARTIFACT_ROOT="${2:-}"; shift 2 ;;
    --lfs-asset-root) LFS_ASSET_ROOT="${2:-}"; shift 2 ;;
    --product) PRODUCTS+=("${2:-}"); shift 2 ;;
    -h|--help)
      echo "usage: apply.sh --source-root ROOT --artifact-root M144_DIR --lfs-asset-root LFS_CACHE [--product PRODUCT ...]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
[ -n "${ARTIFACT_ROOT}" ] || { echo "--artifact-root is required" >&2; exit 2; }
[ -n "${LFS_ASSET_ROOT}" ] || { echo "--lfs-asset-root is required" >&2; exit 2; }
if [ "${#PRODUCTS[@]}" -eq 0 ]; then
  PRODUCTS=(armv7a_virt arm64_virt x86_64_virt)
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt|arm64_virt|x86_64_virt) ;;
    *) echo "unsupported product: ${product}" >&2; exit 2 ;;
  esac
done

if [[ " ${PRODUCTS[*]} " == *" armv7a_virt "* ]]; then
  bash "${PATCH_ROOT}/common/device/qemu/armv7a_product/apply.sh" \
    --source-root "${SOURCE_ROOT}"
fi

PROFILE_ARGS=(--source-root "${SOURCE_ROOT}")
VPN_ARGS=(--source-root "${SOURCE_ROOT}")
for product in "${PRODUCTS[@]}"; do
  PROFILE_ARGS+=(--product "${product}")
  VPN_ARGS+=(--product "${product}")
done
bash "${PATCH_ROOT}/common/build/github_lfs_assets/apply.sh" \
  --source-root "${SOURCE_ROOT}" \
  --asset-root "${LFS_ASSET_ROOT}"
bash "${PATCH_ROOT}/${DEVICE_TYPE}/product_profile/apply.sh" "${PROFILE_ARGS[@]}"
bash "${PATCH_ROOT}/common/foundation/resourceschedule/qos_manager/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/drivers/peripheral/vibrator/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/foundation/barrierfree/accessibility/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/foundation/ability/ability_runtime/native_child_process/apply.sh" \
  --source-root "${SOURCE_ROOT}"
if [[ " ${PRODUCTS[*]} " == *" armv7a_virt "* ]]; then
  bash "${PATCH_ROOT}/common/device/qemu/armv7a_product/components/compact_child_args/apply.sh" \
    --source-root "${SOURCE_ROOT}"
fi
bash "${PATCH_ROOT}/common/build/compile_app/release_dependencies/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/third_party/musl/cortex_m_sdk/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/drivers/peripheral/audio/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/foundation/multimodalinput/input/absolute_pointer/apply.sh" \
  --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/common/standard_vpn/apply.sh" "${VPN_ARGS[@]}"

for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt)
      profile=vendor/ohemu/qemu_armv7a_linux_full/config.json
      arch=arm
      ;;
    arm64_virt)
      profile=vendor/ohemu/qemu_arm64_linux_full/config.json
      arch=arm64
      ;;
    x86_64_virt)
      profile=vendor/ohemu/qemu_x86_64_linux_full/config.json
      arch=x86_64
      ;;
  esac
  bash "${PATCH_ROOT}/common/arkcompiler/jsvm/apply.sh" \
    --source-root "${SOURCE_ROOT}" \
    --artifact-root "${ARTIFACT_ROOT}" \
    --profile "${profile}" \
    --metadata "vendor/ohemu/virt/virt_${DEVICE_TYPE}_full.meta.json" \
    --arch "${arch}"
done

echo "QEMU ${DEVICE_TYPE} component patch set applied"
