#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  apply.sh --source-root ROOT [--product PRODUCT ...]

Products:
  armv7a_virt
  arm64_virt
  x86_64_virt

With no --product arguments, all three standard-system QEMU products are
configured.
USAGE
}

SOURCE_ROOT=
PRODUCTS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --product)
      PRODUCTS+=("${2:-}")
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

if [ -z "${SOURCE_ROOT}" ]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=(--source-root "${SOURCE_ROOT}")
for product in "${PRODUCTS[@]}"; do
  ARGS+=(--product "${product}")
done
COMPONENTS=(
  device_qemu_kernel
  code_sign
  musl_uapi
  linux_security
  xpm
  vendor_product
  vpn_dialog
  qemu_mesa
  validate
)
for component in "${COMPONENTS[@]}"; do
  bash "${SCRIPT_DIR}/components/${component}/apply.sh" "${ARGS[@]}"
done
echo "standard VPN support configured"
