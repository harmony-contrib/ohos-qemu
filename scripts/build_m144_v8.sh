#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
SEED_ROOT="${M144_SEED_ROOT:-${CACHE_ROOT}/arkweb-m144}"
OHOS_ROOT="${OHOS_ROOT:-${CACHE_ROOT}/openharmony}"
ARTIFACT_ROOT="${JSVM_ENGINE_ARTIFACTS:-${CACHE_ROOT}/artifacts/jsvm-m144}"
SOURCE_VOLUME="${M144_SOURCE_VOLUME:-ohos-qemu-arkweb-m144-source}"
DOCKER_IMAGE="${DOCKER_IMAGE:-ohos-qemu-build-env:deps}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
REFRESH_SOURCE="${M144_REFRESH_SOURCE:-0}"
BUILD_JOBS="${M144_BUILD_JOBS:-8}"
SYNC_JOBS="${M144_SYNC_JOBS:-8}"

CHROMIUM_REVISION=4ae5a7f106cdf9d3f42acd1c6ab007140dcd249f
V8_REVISION=1170083e0a717f67cead0abe20900f273ae01fb5
ARKWEB_REVISION=eff888fcd48ce0aa4dc4bf7b2474ed77f0353fa2
CEF_REVISION=d154063ab448260480a75a4e755a18aaf0baf7c4
WEBVIEW_REVISION=93dce838eea694887c707c28b3f4f0fa85f87326
WEBVIEW_ROOT="${OHOS_ROOT}/base/web/webview"

ARCHES=("$@")
if [ "${#ARCHES[@]}" -eq 0 ]; then ARCHES=(arm arm64 x86_64); fi
for arch in "${ARCHES[@]}"; do
  case "${arch}" in arm|arm64|x86_64) ;; *)
    echo "usage: build_m144_v8.sh [arm] [arm64] [x86_64]" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
[ -d "${OHOS_ROOT}/prebuilts/ohos-sdk/linux/26.0.0/native" ] || {
  echo "OpenHarmony API 26 SDK is missing under ${OHOS_ROOT}" >&2; exit 1;
}
for repository in "${SEED_ROOT}/src" "${SEED_ROOT}/v8" \
  "${SEED_ROOT}/src/arkweb" "${SEED_ROOT}/cef"; do
  [ -d "${repository}/.git" ] || {
    echo "M144 seed repository is missing: ${repository}" >&2
    echo "fetch chromium_src, chromium_v8, and chromium_arkweb master into ${SEED_ROOT}" >&2
    exit 1
  }
done
[ "$(git -C "${SEED_ROOT}/src" rev-parse HEAD)" = "${CHROMIUM_REVISION}" ]
[ "$(git -C "${SEED_ROOT}/v8" rev-parse HEAD)" = "${V8_REVISION}" ]
[ "$(git -C "${SEED_ROOT}/src/arkweb" rev-parse HEAD)" = "${ARKWEB_REVISION}" ]
[ "$(git -C "${SEED_ROOT}/cef" rev-parse HEAD)" = "${CEF_REVISION}" ]
[ -d "${WEBVIEW_ROOT}" ] || {
  echo "OpenHarmony ArkWeb interface source is missing: ${WEBVIEW_ROOT}" >&2
  exit 1
}
[ "$(git -C "${WEBVIEW_ROOT}" rev-parse HEAD)" = "${WEBVIEW_REVISION}" ] || {
  echo "OpenHarmony ArkWeb interface revision mismatch: ${WEBVIEW_ROOT}" >&2
  exit 1
}

docker volume create "${SOURCE_VOLUME}" >/dev/null
if [ "${REFRESH_SOURCE}" = "1" ]; then
  docker run --rm --platform "${DOCKER_PLATFORM}" \
    --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
    "${DOCKER_IMAGE}" bash -lc \
    'set -euo pipefail; for path in /workspace/src /workspace/depot_tools /workspace/.core-sources-ready; do [ ! -e "$path" ] || rm -rf "$path"; done'
fi

if ! docker run --rm --platform "${DOCKER_PLATFORM}" \
  --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
  "${DOCKER_IMAGE}" test -f /workspace/.core-sources-ready
then
  docker run --rm --platform "${DOCKER_PLATFORM}" \
    --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
    -v "${SEED_ROOT}/src:/seed/chromium:ro" \
    -v "${SEED_ROOT}/v8:/seed/v8:ro" \
    -v "${SEED_ROOT}/src/arkweb:/seed/arkweb:ro" \
    "${DOCKER_IMAGE}" bash -lc \
    'set -euo pipefail
     export GIT_LFS_SKIP_SMUDGE=1
     git clone --no-local /seed/chromium /workspace/src
     git clone --no-local /seed/v8 /workspace/src/v8
     git clone --no-local /seed/arkweb /workspace/src/arkweb
     touch /workspace/.core-sources-ready'
fi

# ArkWeb's generated glue comes from the matching OpenHarmony webview
# interface repository, which is not part of Chromium's DEPS graph.
if ! docker run --rm --platform "${DOCKER_PLATFORM}" \
  --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
  "${DOCKER_IMAGE}" bash -lc \
  'test -d /workspace/src/arkweb/deps_code/webview/.git ||
   test -f /workspace/src/arkweb/deps_code/webview/.git'
then
  docker run --rm --platform "${DOCKER_PLATFORM}" \
    --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
    -v "${OHOS_ROOT}:/seed/ohos:ro" \
    "${DOCKER_IMAGE}" bash -lc \
    'set -euo pipefail
     export GIT_LFS_SKIP_SMUDGE=1
     mkdir -p /workspace/src/arkweb/deps_code
     git clone --no-local /seed/ohos/base/web/webview /workspace/src/arkweb/deps_code/webview'
fi

# CEF is imported by Chromium's root BUILD.gn but is not part of upstream
# Chromium DEPS, so provision the OpenHarmony-TPC checkout independently.
if ! docker run --rm --platform "${DOCKER_PLATFORM}" \
  --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
  "${DOCKER_IMAGE}" test -d /workspace/src/cef/.git
then
  docker run --rm --platform "${DOCKER_PLATFORM}" \
    --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
    -v "${SEED_ROOT}/cef:/seed/cef:ro" \
    "${DOCKER_IMAGE}" bash -lc \
    'set -euo pipefail
     target=/workspace/src/cef
     if [ -e "${target}" ]; then rm -rf "${target}"; fi
     mkdir -p "${target}"
     rsync -a --delete /seed/cef/ "${target}/"'
fi

mkdir -p "${ARTIFACT_ROOT}"
echo "Build ArkWeb M144 V8: arches=${ARCHES[*]} artifacts=${ARTIFACT_ROOT}"
docker run --rm --platform "${DOCKER_PLATFORM}" \
  --ulimit nofile=1048576:1048576 \
  --mount "type=volume,src=${SOURCE_VOLUME},dst=/workspace" \
  -v "${OHOS_ROOT}:/ohos:ro" \
  -v "${ARTIFACT_ROOT}:/artifacts" \
  -v "${REPO_ROOT}:/work:ro" \
  -e M144_BUILD_JOBS="${BUILD_JOBS}" \
  -e M144_SYNC_JOBS="${SYNC_JOBS}" \
  -e M144_SKIP_SYNC="${M144_SKIP_SYNC:-0}" \
  "${DOCKER_IMAGE}" \
  bash /work/scripts/build_m144_v8_in_docker.sh "${ARCHES[@]}"
