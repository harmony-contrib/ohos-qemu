#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
python3 "${COMPONENT_DIR}/check.py" "$@"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --product) shift 2 ;;
    *) echo "unknown camera-profile argument: $1" >&2; exit 2 ;;
  esac
done
bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
  "${COMPONENT_DIR}/0001-inherit-camera-arm64-x64-from-board.patch"
if [ -f "${SOURCE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full/config.json" ]; then
  bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
    "${COMPONENT_DIR}/0002-inherit-camera-arm32-from-board.patch"
fi
python3 "${COMPONENT_DIR}/check.py" --source-root "${SOURCE_ROOT}" --require-patched
