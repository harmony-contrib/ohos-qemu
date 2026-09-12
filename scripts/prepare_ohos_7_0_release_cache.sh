#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FALLBACK_MAP="${FALLBACK_MAP:-${SCRIPT_DIR}/openharmony_7_0_release_github_fallback.tsv}"
CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT:-${CACHE_ROOT}/git-mirrors/openharmony-7.0-release}"
FALLBACK_JOBS="${FALLBACK_JOBS:-10}"
RELEASE_TAG="OpenHarmony-v7.0-Release"

case "${FALLBACK_JOBS}" in
  ''|*[!0-9]*|0)
    echo "FALLBACK_JOBS must be a positive integer" >&2
    exit 2
    ;;
esac
if [ ! -f "${FALLBACK_MAP}" ]; then
  echo "missing fallback map: ${FALLBACK_MAP}" >&2
  exit 1
fi

mkdir -p "${FALLBACK_MIRROR_ROOT}"

prepare_one() {
  local project="$1"
  local source="$2"
  local expected="$3"
  local target="${FALLBACK_MIRROR_ROOT}/${project}.git"
  local actual temp_dir backup remote

  if [ -d "${target}" ] && \
     actual="$(git --git-dir="${target}" rev-parse "${RELEASE_TAG}^{commit}" 2>/dev/null)" && \
     [ "${actual}" = "${expected}" ]; then
    echo "reuse verified OpenHarmony release cache: ${project} @ ${expected}"
    return
  fi

  temp_dir="$(mktemp -d "${FALLBACK_MIRROR_ROOT}/.${project}.XXXXXX")"
  case "${source}" in
    github-cache) remote="https://github.com/openharmony/${project}.git" ;;
    gitcode-cache) remote="https://gitcode.com/openharmony/${project}.git" ;;
    *) echo "unsupported cache source for ${project}: ${source}" >&2; return 2 ;;
  esac
  echo "cache OpenHarmony release tag from ${source}: ${project} @ ${expected}"
  if ! (
    if [ "${source}" = "gitcode-cache" ]; then
      unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
    fi
    GIT_TERMINAL_PROMPT=0 git -c http.version=HTTP/1.1 clone \
      --quiet --bare --depth=1 --branch "${RELEASE_TAG}" \
      "${remote}" "${temp_dir}"
  ); then
    rm -rf -- "${temp_dir}"
    echo "failed to cache ${project}; removed partial clone ${temp_dir}" >&2
    return 1
  fi

  actual="$(git --git-dir="${temp_dir}" rev-parse "${RELEASE_TAG}^{commit}")"
  if [ "${actual}" != "${expected}" ]; then
    mv "${temp_dir}" "${temp_dir}.unexpected-${actual}"
    echo "${project} release tag mismatch: expected ${expected}, found ${actual}" >&2
    return 1
  fi
  git --git-dir="${temp_dir}" config uploadpack.allowReachableSHA1InWant true

  if [ -e "${target}" ]; then
    backup="${target}.stale-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    mv "${target}" "${backup}"
    echo "moved stale cache to ${backup}"
  fi
  mv "${temp_dir}" "${target}"
}

export FALLBACK_MIRROR_ROOT RELEASE_TAG
export -f prepare_one

awk '$1 !~ /^#/ && $2 != "omit" { print $1, $2, $3 }' "${FALLBACK_MAP}" \
  | xargs -n 3 -P "${FALLBACK_JOBS}" bash -c 'prepare_one "$1" "$2" "$3"' _

echo "OpenHarmony 7.0 release cache ready: ${FALLBACK_MIRROR_ROOT}"
