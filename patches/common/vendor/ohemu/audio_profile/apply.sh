#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --product) shift 2 ;;
    *) echo "unknown audio-profile argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "${SOURCE_ROOT}" ]; then echo "--source-root is required" >&2; exit 2; fi
bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
  "${COMPONENT_DIR}/0001-move-alsa-arm64-x64-to-board-inheritance.patch"
if [ -f "${SOURCE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full/config.json" ]; then
  bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
    "${COMPONENT_DIR}/0002-move-alsa-arm32-to-board-inheritance.patch"
fi
