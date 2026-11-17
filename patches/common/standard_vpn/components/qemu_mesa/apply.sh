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

QEMU_MESA_COMMIT="995d2506d18924b48db0cf40e6ad7de04fc4e558"
QEMU_MESA_VERSION="21.3.3"
QEMU_MESA_REF="refs/ohos-qemu/mesa-${QEMU_MESA_VERSION}"
MESA_REPOSITORY="${SOURCE_ROOT}/third_party/mesa3d"
if [ -n "${QEMU_MESA_REVISION_CACHE:-}" ]; then
  if [ ! -d "${QEMU_MESA_REVISION_CACHE}" ]; then
    echo "missing QEMU Mesa revision cache: ${QEMU_MESA_REVISION_CACHE}" >&2
    exit 1
  fi
  cached_commit="$(git --git-dir="${QEMU_MESA_REVISION_CACHE}" \
    rev-parse "${QEMU_MESA_REF}^{commit}" 2>/dev/null)" || {
      echo "QEMU Mesa revision cache is missing ${QEMU_MESA_REF}" >&2
      exit 1
    }
  cached_version="$(git --git-dir="${QEMU_MESA_REVISION_CACHE}" \
    show "${QEMU_MESA_COMMIT}:VERSION" 2>/dev/null)" || {
      echo "QEMU Mesa revision cache is missing ${QEMU_MESA_COMMIT}:VERSION" >&2
      exit 1
    }
  if [ "${cached_commit}" != "${QEMU_MESA_COMMIT}" ] || \
     [ "${cached_version}" != "${QEMU_MESA_VERSION}" ]; then
    echo "invalid QEMU Mesa revision cache: commit=${cached_commit} version=${cached_version}" >&2
    exit 1
  fi
  if ! git -C "${MESA_REPOSITORY}" cat-file -e \
    "${QEMU_MESA_COMMIT}^{commit}" 2>/dev/null; then
    git -C "${MESA_REPOSITORY}" fetch --quiet --no-tags --depth=1 \
      "file://${QEMU_MESA_REVISION_CACHE}" "${QEMU_MESA_REF}"
  fi
  actual_version="$(git -C "${MESA_REPOSITORY}" \
    show "${QEMU_MESA_COMMIT}:VERSION")"
  if [ "${actual_version}" != "${QEMU_MESA_VERSION}" ]; then
    echo "QEMU Mesa ${QEMU_MESA_COMMIT} has version ${actual_version}; expected ${QEMU_MESA_VERSION}" >&2
    exit 1
  fi
  echo "verified QEMU Mesa source revision: ${QEMU_MESA_COMMIT} (${QEMU_MESA_VERSION})"
fi
echo "installed QEMU Mesa component builder"
