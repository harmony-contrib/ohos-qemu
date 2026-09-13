#!/usr/bin/env bash
set -euo pipefail

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
QEMU_MESA_REVISION_CACHE="${QEMU_MESA_REVISION_CACHE:-${CACHE_ROOT}/git-mirrors/qemu-mesa/third_party_mesa3d.git}"
QEMU_MESA_REPOSITORY="${QEMU_MESA_REPOSITORY:-https://github.com/openharmony/third_party_mesa3d.git}"
QEMU_MESA_COMMIT="995d2506d18924b48db0cf40e6ad7de04fc4e558"
QEMU_MESA_VERSION="21.3.3"
QEMU_MESA_REF="refs/ohos-qemu/mesa-${QEMU_MESA_VERSION}"

verify_cache() {
  local actual version
  [ -d "${QEMU_MESA_REVISION_CACHE}" ] || return 1
  actual="$(git --git-dir="${QEMU_MESA_REVISION_CACHE}" \
    rev-parse "${QEMU_MESA_REF}^{commit}" 2>/dev/null)" || return 1
  [ "${actual}" = "${QEMU_MESA_COMMIT}" ] || return 1
  version="$(git --git-dir="${QEMU_MESA_REVISION_CACHE}" \
    show "${QEMU_MESA_COMMIT}:VERSION" 2>/dev/null)" || return 1
  [ "${version}" = "${QEMU_MESA_VERSION}" ]
}

if verify_cache; then
  echo "reuse verified QEMU Mesa revision: ${QEMU_MESA_COMMIT} (${QEMU_MESA_VERSION})"
  exit 0
fi

if [ -e "${QEMU_MESA_REVISION_CACHE}" ]; then
  echo "invalid QEMU Mesa revision cache: ${QEMU_MESA_REVISION_CACHE}" >&2
  exit 1
fi

cache_parent="$(dirname "${QEMU_MESA_REVISION_CACHE}")"
mkdir -p "${cache_parent}"
temp_cache="$(mktemp -d "${cache_parent}/.third_party_mesa3d.XXXXXX")"
cleanup() {
  rm -rf -- "${temp_cache}"
}
trap cleanup EXIT

git init --quiet --bare "${temp_cache}"
echo "cache QEMU Mesa from GitHub: ${QEMU_MESA_COMMIT} (${QEMU_MESA_VERSION})"
GIT_TERMINAL_PROMPT=0 git --git-dir="${temp_cache}" \
  -c http.version=HTTP/1.1 fetch --quiet --no-tags --depth=1 \
  "${QEMU_MESA_REPOSITORY}" \
  "+${QEMU_MESA_COMMIT}:${QEMU_MESA_REF}"

actual="$(git --git-dir="${temp_cache}" rev-parse "${QEMU_MESA_REF}^{commit}")"
version="$(git --git-dir="${temp_cache}" show "${QEMU_MESA_COMMIT}:VERSION")"
if [ "${actual}" != "${QEMU_MESA_COMMIT}" ] || \
   [ "${version}" != "${QEMU_MESA_VERSION}" ]; then
  echo "QEMU Mesa revision verification failed: commit=${actual} version=${version}" >&2
  exit 1
fi
git --git-dir="${temp_cache}" config uploadpack.allowReachableSHA1InWant true
mv "${temp_cache}" "${QEMU_MESA_REVISION_CACHE}"
trap - EXIT
echo "QEMU Mesa revision cache ready: ${QEMU_MESA_REVISION_CACHE}"
