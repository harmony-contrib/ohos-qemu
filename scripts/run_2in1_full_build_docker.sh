#!/usr/bin/env bash
# Host-side launcher for a full OpenHarmony QEMU phone or 2in1 source-profile
# build inside Ubuntu 22.04 Docker (OrbStack / Docker Desktop).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CACHE_PREPARER="${SCRIPT_DIR}/prepare_ohos_7_0_release_cache.sh"
LFS_CACHE_PREPARER="${SCRIPT_DIR}/prepare_ohos_7_0_release_lfs_cache.sh"
MESA_CACHE_PREPARER="${SCRIPT_DIR}/prepare_qemu_mesa_revision_cache.sh"

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
OHOS_ROOT="${OHOS_ROOT:-${CACHE_ROOT}/openharmony}"
OHOS_BRANCH="${OHOS_BRANCH:-OpenHarmony-7.0-Release}"
MANIFEST_REVISION="${MANIFEST_REVISION:-f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549}"
OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR-https://github.com/openharmony/}"
OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK:-1}"
OHOS_GITHUB_NO_PROXY="${OHOS_GITHUB_NO_PROXY:-github.com,.github.com,githubusercontent.com,.githubusercontent.com}"
DEVICE_TYPE="${DEVICE_TYPE:-2in1}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages/${DEVICE_TYPE}-source-$(date -u +%Y%m%d)}"
CONTAINER_HOME="${CONTAINER_HOME:-${CACHE_ROOT}/home}"
CCACHE_DIR="${CCACHE_DIR:-${CACHE_ROOT}/ccache}"
# A full standard-system Ninja tree is substantially larger than its cache.
# Keep the default conservative so the native Docker out volume has enough
# headroom for image assembly; callers on larger disks can still override it.
CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-4G}"
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
DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME:-ohos-qemu-7_0-release-out}"
# A full standard-system build eventually exhausts the macOS VirtioFS file
# server even with a high container nofile limit. Keep the checkout itself on
# a native Linux volume as well. The one-time seed excludes out/ because that
# has its own persistent volume below.
DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source}"
DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH:-0}"
DOCKER_SOURCE_SEED="${DOCKER_SOURCE_SEED:-0}"
BUILD_JOBS="${BUILD_JOBS:-2}"
KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS:-${BUILD_JOBS}}"
REPO_JOBS="${REPO_JOBS:-16}"
REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS:-4}"
FALLBACK_JOBS="${FALLBACK_JOBS:-10}"
FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT:-${CACHE_ROOT}/git-mirrors/openharmony-7.0-release}"
OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT:-${CACHE_ROOT}/artifacts/openharmony-7.0-lfs}"
QEMU_MESA_REVISION_CACHE="${QEMU_MESA_REVISION_CACHE:-${CACHE_ROOT}/git-mirrors/qemu-mesa/third_party_mesa3d.git}"
LFS_JOBS="${LFS_JOBS:-10}"
CONTAINER_NO_PROXY="${NO_PROXY:-${no_proxy:-}}"
if [ -n "${OHOS_GITHUB_NO_PROXY}" ]; then
  CONTAINER_NO_PROXY="${CONTAINER_NO_PROXY:+${CONTAINER_NO_PROXY},}${OHOS_GITHUB_NO_PROXY}"
fi
SKIP_REPO_SYNC="${SKIP_REPO_SYNC:-0}"
SKIP_PREBUILTS="${SKIP_PREBUILTS:-0}"
SKIP_GIT_LFS="${SKIP_GIT_LFS:-0}"
BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD:-0}"
NO_PREBUILT_SDK="${NO_PREBUILT_SDK:-0}"
PREPARE_ONLY="${PREPARE_ONLY:-0}"
PRODUCTS="${PRODUCTS:-arm64_virt x86_64_virt armv7a_virt}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-0}"
QEMU_JSVM_COMPONENT="${QEMU_JSVM_COMPONENT:-1}"
QEMU_ACCESSIBILITY_COMPONENT="${QEMU_ACCESSIBILITY_COMPONENT:-1}"
JSVM_ENGINE_ARTIFACTS="${JSVM_ENGINE_ARTIFACTS:-${CACHE_ROOT}/artifacts/jsvm-m144}"
SDKMANAGER_COMMON_VERSION="${SDKMANAGER_COMMON_VERSION:-2.26.3}"
SDKMANAGER_COMMON_ARTIFACT="${SDKMANAGER_COMMON_ARTIFACT:-${CACHE_ROOT}/artifacts/npm/sdkmanager-common-${SDKMANAGER_COMMON_VERSION}.tgz}"
SDKMANAGER_COMMON_URL="${SDKMANAGER_COMMON_URL:-https://repo.harmonyos.com/npm/@ohos/sdkmanager-common/-/@ohos/sdkmanager-common-${SDKMANAGER_COMMON_VERSION}.tgz}"
SDKMANAGER_COMMON_SHA512="${SDKMANAGER_COMMON_SHA512:-1f20b632c759085d79321f3b95425b4ee7608fdd1911c1c9965ab16d49f96c3384657f92dd16cda5710fdaa95215908a323cb1d629b9eede1edb500664170533}"

case "${DEVICE_TYPE}" in
  2in1)
    DEVICE_TYPE_BUILD_PROFILE=qemu_2in1_full_source
    QEMU_2IN1_PROFILE_COMPONENT=1
    QEMU_PHONE_PROFILE_COMPONENT=0
    ;;
  phone)
    DEVICE_TYPE_BUILD_PROFILE=qemu_phone_full_source
    QEMU_2IN1_PROFILE_COMPONENT=0
    QEMU_PHONE_PROFILE_COMPONENT=1
    ;;
  *)
    echo "DEVICE_TYPE must be phone or 2in1 for a full source-profile build" >&2
    exit 2
    ;;
esac

mkdir -p "${PACKAGE_ROOT}" "${CONTAINER_HOME}" "${CCACHE_DIR}" "${LOG_DIR}"

# CACHE_ROOT is already bind-mounted below. Allow callers such as the six-image
# matrix runner to stage packages on a different filesystem without requiring
# PACKAGE_ROOT to live below CACHE_ROOT.
PACKAGE_MOUNT_ARGS=()
case "${PACKAGE_ROOT}/" in
  "${CACHE_ROOT}/"*) ;;
  *) PACKAGE_MOUNT_ARGS=(-v "${PACKAGE_ROOT}:${PACKAGE_ROOT}") ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found in PATH" >&2
  exit 1
fi

# Reuse the repository's prepared dependency image when it is already local.
# A clean host still falls back to Ubuntu and lets the inner build script
# install the exact package set.
if [ -z "${DOCKER_IMAGE}" ]; then
  if docker image inspect ohos-qemu-build-env:7.0-release >/dev/null 2>&1; then
    DOCKER_IMAGE=ohos-qemu-build-env:7.0-release
    SKIP_APT="${SKIP_APT:-1}"
  elif docker image inspect ohos-qemu-build-env:deps >/dev/null 2>&1; then
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

if [ "${DOCKER_SOURCE_SEED}" = "1" ] && [ ! -x "${OHOS_ROOT}/build.sh" ]; then
  echo "OpenHarmony checkout missing build.sh: ${OHOS_ROOT}" >&2
  exit 1
fi

if [ "${QEMU_JSVM_COMPONENT}" = "1" ] && \
   [ ! -f "${JSVM_ENGINE_ARTIFACTS}/manifest.json" ]; then
  echo "M144 JSVM artifacts are required: ${JSVM_ENGINE_ARTIFACTS}" >&2
  echo "build them first with scripts/build_m144_v8.sh" >&2
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
if [ "${DOCKER_SOURCE_SEED}" != "0" ] && [ "${DOCKER_SOURCE_SEED}" != "1" ]; then
  echo "DOCKER_SOURCE_SEED must be 0 or 1" >&2
  exit 2
fi
if [ "${PREPARE_ONLY}" != "0" ] && [ "${PREPARE_ONLY}" != "1" ]; then
  echo "PREPARE_ONLY must be 0 or 1" >&2
  exit 2
fi
if [ "${OHOS_GITHUB_FALLBACK}" != "0" ] && [ "${OHOS_GITHUB_FALLBACK}" != "1" ]; then
  echo "OHOS_GITHUB_FALLBACK must be 0 or 1" >&2
  exit 2
fi

seed_source_volume() {
  docker volume create "${DOCKER_SOURCE_VOLUME}" >/dev/null
  if [ "${DOCKER_SOURCE_SEED}" != "1" ]; then
    echo "use repo-managed source volume; host checkout seeding disabled"
    return
  fi

  local seed_marker=/target/.ohos-qemu-source-volume-seeded
  local refresh_arg=
  if [ "${DOCKER_SOURCE_REFRESH}" = "1" ]; then
    refresh_arg=refresh
  fi

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

prepare_sdkmanager_common_artifact() {
  local actual temp_file
  if [ -f "${SDKMANAGER_COMMON_ARTIFACT}" ]; then
    actual="$(shasum -a 512 "${SDKMANAGER_COMMON_ARTIFACT}" | awk '{print $1}')"
    if [ "${actual}" = "${SDKMANAGER_COMMON_SHA512}" ]; then
      echo "reuse verified sdkmanager-common ${SDKMANAGER_COMMON_VERSION}: ${SDKMANAGER_COMMON_ARTIFACT}"
      return
    fi
    echo "ignore mismatched sdkmanager-common artifact: ${actual}" >&2
  fi

  mkdir -p "$(dirname "${SDKMANAGER_COMMON_ARTIFACT}")"
  temp_file="${SDKMANAGER_COMMON_ARTIFACT}.tmp.$$"
  echo "download pinned sdkmanager-common ${SDKMANAGER_COMMON_VERSION} on host"
  if ! (
    unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
    curl --http1.1 -fsSL --connect-timeout 20 --retry 3 \
      "${SDKMANAGER_COMMON_URL}" -o "${temp_file}"
  ); then
    rm -f -- "${temp_file}"
    return 1
  fi
  actual="$(shasum -a 512 "${temp_file}" | awk '{print $1}')"
  if [ "${actual}" != "${SDKMANAGER_COMMON_SHA512}" ]; then
    rm -f -- "${temp_file}"
    echo "sdkmanager-common checksum mismatch: expected ${SDKMANAGER_COMMON_SHA512}, found ${actual}" >&2
    return 1
  fi
  mv "${temp_file}" "${SDKMANAGER_COMMON_ARTIFACT}"
}

LOG_FILE="${LOG_DIR}/${DEVICE_TYPE}_full_build_$(date -u +%Y%m%dT%H%M%SZ).log"

echo "=== ${DEVICE_TYPE} full source build ==="
echo "CACHE_ROOT=${CACHE_ROOT}"
echo "OHOS_ROOT=${OHOS_ROOT}"
echo "PACKAGE_ROOT=${PACKAGE_ROOT}"
echo "DEVICE_TYPE=${DEVICE_TYPE}"
echo "PRODUCTS=${PRODUCTS}"
echo "MANIFEST=${OHOS_BRANCH} @ ${MANIFEST_REVISION}"
echo "OHOS_PROJECT_MIRROR=${OHOS_PROJECT_MIRROR}"
echo "OHOS_GITHUB_FALLBACK=${OHOS_GITHUB_FALLBACK}"
echo "FALLBACK_MIRROR_ROOT=${FALLBACK_MIRROR_ROOT} FALLBACK_JOBS=${FALLBACK_JOBS}"
echo "OHOS_LFS_ASSET_ROOT=${OHOS_LFS_ASSET_ROOT} LFS_JOBS=${LFS_JOBS}"
echo "CONTAINER_NO_PROXY=${CONTAINER_NO_PROXY}"
echo "DOCKER_PLATFORM=${DOCKER_PLATFORM}"
echo "DOCKER_IMAGE=${DOCKER_IMAGE} SKIP_APT=${SKIP_APT}"
echo "DOCKER_SOURCE_VOLUME=${DOCKER_SOURCE_VOLUME} (mounted at ${OHOS_ROOT})"
echo "DOCKER_SOURCE_SEED=${DOCKER_SOURCE_SEED}"
echo "DOCKER_OUT_VOLUME=${DOCKER_OUT_VOLUME} (mounted at ${OHOS_ROOT}/out)"
echo "BUILD_JOBS=${BUILD_JOBS}"
echo "CCACHE_MAXSIZE=${CCACHE_MAXSIZE}"
echo "REPO_JOBS=${REPO_JOBS} REPO_CHECKOUT_JOBS=${REPO_CHECKOUT_JOBS}"
echo "SKIP_REPO_SYNC=${SKIP_REPO_SYNC} SKIP_PREBUILTS=${SKIP_PREBUILTS}"
echo "BUILD_ONLY_LOAD=${BUILD_ONLY_LOAD}"
echo "NO_PREBUILT_SDK=${NO_PREBUILT_SDK}"
echo "PREPARE_ONLY=${PREPARE_ONLY}"
echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE=${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}"
echo "QEMU_JSVM_COMPONENT=${QEMU_JSVM_COMPONENT}"
echo "QEMU_ACCESSIBILITY_COMPONENT=${QEMU_ACCESSIBILITY_COMPONENT}"
echo "JSVM_ENGINE_ARTIFACTS=${JSVM_ENGINE_ARTIFACTS}"
echo "SDKMANAGER_COMMON_ARTIFACT=${SDKMANAGER_COMMON_ARTIFACT}"
echo "LOG_FILE=${LOG_FILE}"
echo
echo "Full ${DEVICE_TYPE} QEMU capability stack:"
echo "  - QEMU rootfs /system compat symlinks"
echo "  - access_tokenid kernel ABI"
echo "  - case-insensitive host FS fixes (when source on macOS volume)"
echo "  - VirtioFS node/kernel copy fixes"
echo "  - standard VPN component patches"
echo "  - absolute-pointer component + virtio-tablet launcher"
echo "  - QoS authority kernel module/configuration"
echo "  - virtual vibrator product VDI"
echo "  - pinned GitHub former-LFS asset restoration"
echo "  - JSVM backed by ArkWeb M144 libv8_shared"
echo "  - armv7a_virt product components (when armv7a selected)"
echo "  - rich + effective productdefine/common/inherit/${DEVICE_TYPE}.json profile"
echo "  - package_standard_qemu.sh --device-type ${DEVICE_TYPE}"
echo "  - auditable resolved parts and profile metadata in each package"
echo

if [ "${SKIP_REPO_SYNC}" = "0" ] && [ -n "${OHOS_PROJECT_MIRROR}" ] && \
   [ "${OHOS_GITHUB_FALLBACK}" = "1" ]; then
  CACHE_ROOT="${CACHE_ROOT}" \
  FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT}" \
  FALLBACK_JOBS="${FALLBACK_JOBS}" \
    bash "${CACHE_PREPARER}"
fi

prepare_sdkmanager_common_artifact

CACHE_ROOT="${CACHE_ROOT}" \
QEMU_MESA_REVISION_CACHE="${QEMU_MESA_REVISION_CACHE}" \
  bash "${MESA_CACHE_PREPARER}"

CACHE_ROOT="${CACHE_ROOT}" \
OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT}" \
LFS_JOBS="${LFS_JOBS}" \
  bash "${LFS_CACHE_PREPARER}"

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
  -e NO_PROXY="${CONTAINER_NO_PROXY}" \
  -e no_proxy="${CONTAINER_NO_PROXY}" \
  -e NOFILE_LIMIT=1048576 \
  -e CACHE_ROOT="${CACHE_ROOT}" \
  -e OHOS_ROOT="${OHOS_ROOT}" \
  -e PACKAGE_ROOT="${PACKAGE_ROOT}" \
  -e CONTAINER_HOME="${CONTAINER_HOME}" \
  -e CCACHE_DIR="${CCACHE_DIR}" \
  -e CCACHE_MAXSIZE="${CCACHE_MAXSIZE}" \
  -e OHOS_BRANCH="${OHOS_BRANCH}" \
  -e MANIFEST_REVISION="${MANIFEST_REVISION}" \
  -e OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR}" \
  -e OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK}" \
  -e OHOS_FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT}" \
  -e OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT}" \
  -e QEMU_MESA_REVISION_CACHE="${QEMU_MESA_REVISION_CACHE}" \
  -e DEVICE_TYPE="${DEVICE_TYPE}" \
  -e DEVICE_TYPE_BUILD_PROFILE="${DEVICE_TYPE_BUILD_PROFILE}" \
  -e QEMU_2IN1_PROFILE_COMPONENT="${QEMU_2IN1_PROFILE_COMPONENT}" \
  -e QEMU_PHONE_PROFILE_COMPONENT="${QEMU_PHONE_PROFILE_COMPONENT}" \
  -e QEMU_QOS_COMPONENT=1 \
  -e QEMU_VIBRATOR_COMPONENT=1 \
  -e QEMU_ACCESSIBILITY_COMPONENT="${QEMU_ACCESSIBILITY_COMPONENT}" \
  -e QEMU_JSVM_COMPONENT="${QEMU_JSVM_COMPONENT}" \
  -e JSVM_ENGINE_ARTIFACTS="${JSVM_ENGINE_ARTIFACTS}" \
  -e SDKMANAGER_COMMON_VERSION="${SDKMANAGER_COMMON_VERSION}" \
  -e SDKMANAGER_COMMON_ARTIFACT="${SDKMANAGER_COMMON_ARTIFACT}" \
  -e SDKMANAGER_COMMON_SHA512="${SDKMANAGER_COMMON_SHA512}" \
  -e BUILD_JOBS="${BUILD_JOBS}" \
  -e KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS}" \
  -e REPO_JOBS="${REPO_JOBS}" \
  -e REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS}" \
  -e SKIP_REPO_SYNC="${SKIP_REPO_SYNC}" \
  -e SKIP_PREBUILTS="${SKIP_PREBUILTS}" \
  -e SKIP_GIT_LFS="${SKIP_GIT_LFS}" \
  -e BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD}" \
  -e NO_PREBUILT_SDK="${NO_PREBUILT_SDK}" \
  -e PREPARE_ONLY="${PREPARE_ONLY}" \
  -e PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" \
  -e SKIP_APT="${SKIP_APT}" \
  -e STANDARD_VPN_COMPONENT=1 \
  -e QEMU_ABSOLUTE_POINTER_COMPONENT=1 \
  -e ARMV7A_PRODUCT_COMPONENT=1 \
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
  ${PACKAGE_MOUNT_ARGS[@]+"${PACKAGE_MOUNT_ARGS[@]}"} \
  --mount "type=volume,src=${DOCKER_SOURCE_VOLUME},dst=${OHOS_ROOT}" \
  --mount "type=volume,src=${DOCKER_OUT_VOLUME},dst=${OHOS_ROOT}/out" \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  --tmpfs /tmp:exec,mode=1777,size=32g \
  "${DOCKER_IMAGE}" \
  bash -lc "ulimit -n ${NOFILE_LIMIT:-1048576} 2>/dev/null || true; ulimit -n; exec bash /work/scripts/build_standard_qemu_in_docker.sh $(printf '%q ' "$@")"
