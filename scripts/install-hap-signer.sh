#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_URL="${OHOS_HAPSIGNER_REPO_URL:-https://github.com/ohos-rs/hapsigner-rs}"
VERSION="${OHOS_HAPSIGNER_VERSION:-v0.1.0}"
INSTALLER="${OHOS_QEMU_HAPSIGNER_INSTALLER:-}"

if [ -n "${OHOS_QEMU_PREFIX:-}" ]; then
  default_prefix="${OHOS_QEMU_PREFIX}"
elif [ -f "${PACKAGE_ROOT}/manifest.json" ]; then
  default_prefix="${PACKAGE_ROOT}"
else
  default_prefix="${HOME}/.ohos-qemu"
fi

has_prefix=0
for argument in "$@"; do
  if [ "${argument}" = --prefix ]; then
    has_prefix=1
    break
  fi
done

temporary=""
cleanup() {
  if [ -n "${temporary}" ]; then
    rm -f "${temporary}"
  fi
}
trap cleanup EXIT

if [ -z "${INSTALLER}" ]; then
  temporary="$(mktemp "${TMPDIR:-/tmp}/hapsigner-installer.XXXXXX")"
  installer_url="${REPO_URL%/}/raw/${VERSION}/install.sh"
  case "${REPO_URL}" in
    https://github.com/*)
      repo_path="${REPO_URL#https://github.com/}"
      repo_path="${repo_path%.git}"
      installer_url="https://raw.githubusercontent.com/${repo_path}/${VERSION}/install.sh"
      ;;
  esac
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 -o "${temporary}" "${installer_url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${temporary}" "${installer_url}"
  else
    echo "curl or wget is required" >&2
    exit 1
  fi
  INSTALLER="${temporary}"
fi

if [ ! -f "${INSTALLER}" ]; then
  echo "hapsigner installer not found: ${INSTALLER}" >&2
  exit 1
fi

export HAPSIGNER_REPO_URL="${REPO_URL}"
export HAPSIGNER_VERSION="${VERSION}"
if [ "${has_prefix}" = 1 ]; then
  bash "${INSTALLER}" --version "${VERSION}" "$@"
else
  bash "${INSTALLER}" --prefix "${default_prefix}" --version "${VERSION}" "$@"
fi
