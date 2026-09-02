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
for patch_file in \
  0001-declare-qos-config.patch \
  0002-merge-qos-config.patch \
  0003-wire-qos-authority.patch; do
  bash "${PATCH_ROOT}/lib/apply_patch.sh" \
    "${SOURCE_ROOT}" "${SCRIPT_DIR}/${patch_file}"
done
install -m 0644 "${SCRIPT_DIR}/qos.config" \
  "${SOURCE_ROOT}/device/qemu/common/virt_full/kernel/qos.config"
install -m 0644 "${SCRIPT_DIR}/files/qos_auth.patch" \
  "${SOURCE_ROOT}/device/qemu/common/virt_full/kernel/patch/qos_auth.patch"

echo "QEMU QoS kernel component configured"
