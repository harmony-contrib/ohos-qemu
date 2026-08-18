#!/usr/bin/env bash
# Host-side launcher for a full OpenHarmony QEMU phone or 2in1 source-profile
# build inside Ubuntu 22.04 Docker (OrbStack / Docker Desktop).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
OHOS_ROOT="${OHOS_ROOT:-${CACHE_ROOT}/openharmony}"
DEVICE_TYPE="${DEVICE_TYPE:-2in1}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages/${DEVICE_TYPE}-source-$(date -u +%Y%m%d)}"
CONTAINER_HOME="${CONTAINER_HOME:-${CACHE_ROOT}/home}"
CCACHE_DIR="${CCACHE_DIR:-${CACHE_ROOT}/ccache}"
LOG_DIR="${LOG_DIR:-${CACHE_ROOT}/logs}"
DOCKER_IMAGE="${DOCKER_IMAGE:-}"
SKIP_APT="${SKIP_APT:-}"
# OpenHarmony host prebuilts (python/node/toolchains under prebuilts/*) are
# primarily linux-x86_64. Default to amd64 containers so those binaries run.
# Override with DOCKER_PLATFORM=linux/arm64 only if the checkout has a full
# aarch64 host toolchain set.
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
# Keep generated output on a native Linux, case-sensitive filesystem. Taihe
# emits identifiers that differ only by case (for example SourceType and
# sourceType); placing out/ on macOS VirtioFS corrupts those generated files.
DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME:-ohos-qemu-2in1-out}"
# A full standard-system build eventually exhausts the macOS VirtioFS file
# server even with a high container nofile limit. Keep the checkout itself on
# a native Linux volume as well. The one-time seed excludes out/ because that
# has its own persistent volume below.
DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME:-ohos-qemu-2in1-source}"
DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH:-0}"
BUILD_JOBS="${BUILD_JOBS:-2}"
KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS:-${BUILD_JOBS}}"
SKIP_REPO_SYNC="${SKIP_REPO_SYNC:-1}"
SKIP_PREBUILTS="${SKIP_PREBUILTS:-1}"
SKIP_GIT_LFS="${SKIP_GIT_LFS:-0}"
BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD:-0}"
PRODUCTS="${PRODUCTS:-arm64_virt x86_64_virt armv7a_virt}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-0}"

case "${DEVICE_TYPE}" in
  2in1)
    DEVICE_TYPE_BUILD_PROFILE=qemu_2in1_full_source
    QEMU_2IN1_FULL_OVERLAY=1
    QEMU_PHONE_FULL_OVERLAY=0
    ;;
  phone)
    DEVICE_TYPE_BUILD_PROFILE=qemu_phone_full_source
    QEMU_2IN1_FULL_OVERLAY=0
    QEMU_PHONE_FULL_OVERLAY=1
    ;;
  *)
    echo "DEVICE_TYPE must be phone or 2in1 for a full source-profile build" >&2
    exit 2
    ;;
esac

mkdir -p "${PACKAGE_ROOT}" "${CONTAINER_HOME}" "${CCACHE_DIR}" "${LOG_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found in PATH" >&2
  exit 1
fi

# Reuse the repository's prepared dependency image when it is already local.
# A clean host still falls back to Ubuntu and lets the inner build script
# install the exact package set.
if [ -z "${DOCKER_IMAGE}" ]; then
  if docker image inspect ohos-qemu-build-env:deps >/dev/null 2>&1; then
    DOCKER_IMAGE=ohos-qemu-build-env:deps
    SKIP_APT="${SKIP_APT:-1}"
  else
    DOCKER_IMAGE=ubuntu:22.04
    SKIP_APT="${SKIP_APT:-0}"
  fi
elif [ -z "${SKIP_APT}" ]; then
  SKIP_APT=0
fi

# The armv7 Linux 6.6 kernel builds a host GCC plugin which includes gmp.h.
# Detect stale prepared images before the multi-hour OHOS build starts and
# let the inner build script repair their package set.
if [ "${SKIP_APT}" = "1" ]; then
  for requested_product in ${PRODUCTS}; do
    if [ "${requested_product}" = "armv7a_virt" ] && \
       ! docker run --rm --platform "${DOCKER_PLATFORM}" \
         "${DOCKER_IMAGE}" bash -lc \
         "printf '#include <gmp.h>\\n' | c++ -E -x c++ - >/dev/null 2>&1"; then
      echo "${DOCKER_IMAGE} lacks libgmp-dev required by armv7a_virt; enabling apt dependency repair"
      SKIP_APT=0
      break
    fi
  done
fi

if [ ! -x "${OHOS_ROOT}/build.sh" ]; then
  echo "OpenHarmony checkout missing build.sh: ${OHOS_ROOT}" >&2
  exit 1
fi

for volume_name in "${DOCKER_SOURCE_VOLUME}" "${DOCKER_OUT_VOLUME}"; do
  if [[ ! "${volume_name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then
    echo "invalid Docker volume name: ${volume_name}" >&2
    exit 2
  fi
done

if [ "${DOCKER_SOURCE_REFRESH}" != "0" ] && [ "${DOCKER_SOURCE_REFRESH}" != "1" ]; then
  echo "DOCKER_SOURCE_REFRESH must be 0 or 1" >&2
  exit 2
fi

seed_source_volume() {
  local seed_marker=/target/.ohos-qemu-source-volume-seeded
  local refresh_arg=
  if [ "${DOCKER_SOURCE_REFRESH}" = "1" ]; then
    refresh_arg=refresh
  fi

  docker volume create "${DOCKER_SOURCE_VOLUME}" >/dev/null
  docker run --rm \
    --platform "${DOCKER_PLATFORM}" \
    -v "${OHOS_ROOT}:/source:ro" \
    --mount "type=volume,src=${DOCKER_SOURCE_VOLUME},dst=/target" \
    "${DOCKER_IMAGE}" \
    bash -lc '
      set -euo pipefail
      marker=$1
      refresh=${2:-}
      if [ ! -f "${marker}" ] || [ "${refresh}" = refresh ]; then
        echo "seed native Linux source volume from /source (excluding out/)"
        command -v rsync >/dev/null
        rsync -a --delete \
          --exclude=/.ohos-qemu-source-volume-seeded \
          --exclude=/out \
          /source/ /target/
        touch "${marker}"
        echo "native Linux source volume seed complete"
      else
        echo "reuse native Linux source volume"
      fi
    ' bash "${seed_marker}" "${refresh_arg}"
}

LOG_FILE="${LOG_DIR}/${DEVICE_TYPE}_full_build_$(date -u +%Y%m%dT%H%M%SZ).log"

echo "=== ${DEVICE_TYPE} full source build ==="
echo "CACHE_ROOT=${CACHE_ROOT}"
echo "OHOS_ROOT=${OHOS_ROOT}"
echo "PACKAGE_ROOT=${PACKAGE_ROOT}"
echo "DEVICE_TYPE=${DEVICE_TYPE}"
echo "PRODUCTS=${PRODUCTS}"
echo "DOCKER_PLATFORM=${DOCKER_PLATFORM}"
echo "DOCKER_IMAGE=${DOCKER_IMAGE} SKIP_APT=${SKIP_APT}"
echo "DOCKER_SOURCE_VOLUME=${DOCKER_SOURCE_VOLUME} (mounted at ${OHOS_ROOT})"
echo "DOCKER_OUT_VOLUME=${DOCKER_OUT_VOLUME} (mounted at ${OHOS_ROOT}/out)"
echo "BUILD_JOBS=${BUILD_JOBS}"
echo "SKIP_REPO_SYNC=${SKIP_REPO_SYNC} SKIP_PREBUILTS=${SKIP_PREBUILTS}"
echo "BUILD_ONLY_LOAD=${BUILD_ONLY_LOAD}"
echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE=${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}"
echo "LOG_FILE=${LOG_FILE}"
echo
echo "Full ${DEVICE_TYPE} QEMU capability stack:"
echo "  - QEMU rootfs /system compat symlinks"
echo "  - access_tokenid kernel ABI"
echo "  - case-insensitive host FS fixes (when source on macOS volume)"
echo "  - VirtioFS node/kernel copy fixes"
echo "  - standard_qemu_vpn overlay"
echo "  - qemu_absolute_pointer overlay + virtio-tablet launcher"
echo "  - armv7a_virt full overlay (when armv7a selected)"
echo "  - rich + effective productdefine/common/inherit/${DEVICE_TYPE}.json profile"
echo "  - package_standard_qemu.sh --device-type ${DEVICE_TYPE}"
echo "  - auditable resolved parts and profile metadata in each package"
echo

seed_source_volume

# shellcheck disable=SC2086
set -- ${PRODUCTS}

exec > >(tee -a "${LOG_FILE}") 2>&1

docker run --rm \
  --platform "${DOCKER_PLATFORM}" \
  --name "ohos-qemu-${DEVICE_TYPE}-build" \
  --ulimit nofile=1048576:1048576 \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e NOFILE_LIMIT=1048576 \
  -e CACHE_ROOT="${CACHE_ROOT}" \
  -e OHOS_ROOT="${OHOS_ROOT}" \
  -e PACKAGE_ROOT="${PACKAGE_ROOT}" \
  -e CONTAINER_HOME="${CONTAINER_HOME}" \
  -e CCACHE_DIR="${CCACHE_DIR}" \
  -e DEVICE_TYPE="${DEVICE_TYPE}" \
  -e DEVICE_TYPE_BUILD_PROFILE="${DEVICE_TYPE_BUILD_PROFILE}" \
  -e QEMU_2IN1_FULL_OVERLAY="${QEMU_2IN1_FULL_OVERLAY}" \
  -e QEMU_PHONE_FULL_OVERLAY="${QEMU_PHONE_FULL_OVERLAY}" \
  -e BUILD_JOBS="${BUILD_JOBS}" \
  -e KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS}" \
  -e SKIP_REPO_SYNC="${SKIP_REPO_SYNC}" \
  -e SKIP_PREBUILTS="${SKIP_PREBUILTS}" \
  -e SKIP_GIT_LFS="${SKIP_GIT_LFS}" \
  -e BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD}" \
  -e PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" \
  -e SKIP_APT="${SKIP_APT}" \
  -e STANDARD_VPN_OVERLAY=1 \
  -e QEMU_ABSOLUTE_POINTER_OVERLAY=1 \
  -e ARMV7A_FULL_OVERLAY=1 \
  -e QEMU_FIX_ACCESS_TOKENID_ABI=1 \
  -e QEMU_FIX_SYSTEM_COMPAT_SYMLINKS=1 \
  -e QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION=1 \
  -e QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN=1 \
  -e QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK=1 \
  -e QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY=1 \
  -e QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR=1 \
  -e QEMU_FIX_VIRTIOFS_KERNEL_COPY=1 \
  -e QEMU_CCACHE_ON_OUT_VOLUME=1 \
  -e OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE="${OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE:-0}" \
  -v "${CACHE_ROOT}:${CACHE_ROOT}" \
  --mount "type=volume,src=${DOCKER_SOURCE_VOLUME},dst=${OHOS_ROOT}" \
  --mount "type=volume,src=${DOCKER_OUT_VOLUME},dst=${OHOS_ROOT}/out" \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  --tmpfs /tmp:exec,mode=1777,size=32g \
  "${DOCKER_IMAGE}" \
  bash -lc "ulimit -n ${NOFILE_LIMIT:-1048576} 2>/dev/null || true; ulimit -n; exec bash /work/scripts/build_standard_qemu_in_docker.sh $(printf '%q ' "$@")"
