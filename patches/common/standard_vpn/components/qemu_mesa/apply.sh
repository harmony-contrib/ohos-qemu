#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
ARGV=("$@")
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --product) shift 2 ;;
    *) echo "unknown QEMU Mesa argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" "${ARGV[@]}"
install -m 0755 "${COMPONENT_DIR}/files/build_qemu_mesa.py" \
  "${SOURCE_ROOT}/device/qemu/common/virt_full/hardware/gpu/build_qemu_mesa.py"
echo "installed QEMU Mesa component builder"
