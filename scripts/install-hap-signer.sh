#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_URL="${OHOS_QEMU_HAP_SIGNER_REPO_URL:-${OHOS_QEMU_HAPSIGNER_REPO_URL:-${OHOS_HAPSIGNER_REPO_URL:-${HAPSIGNER_REPO_URL:-https://github.com/ohos-rs/hapsigner-rs}}}}"
VERSION="${OHOS_QEMU_HAP_SIGNER_VERSION:-${OHOS_QEMU_HAPSIGNER_VERSION:-${OHOS_HAPSIGNER_VERSION:-${HAPSIGNER_VERSION:-v0.1.0}}}}"
DOWNLOAD_BASE_URL="${OHOS_QEMU_HAP_SIGNER_DOWNLOAD_BASE_URL:-${OHOS_QEMU_HAPSIGNER_DOWNLOAD_BASE_URL:-${OHOS_HAPSIGNER_DOWNLOAD_BASE_URL:-${HAPSIGNER_DOWNLOAD_BASE_URL:-}}}}"
GITHUB_TOKEN="${OHOS_QEMU_GITHUB_TOKEN:-${HAPSIGNER_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}}"
INSTALLER="${OHOS_QEMU_HAP_SIGNER_INSTALLER:-${OHOS_QEMU_HAPSIGNER_INSTALLER:-}}"
FORCE_RAW="${OHOS_QEMU_FORCE:-${HAPSIGNER_FORCE:-0}}"

if [ -n "${OHOS_QEMU_PREFIX:-}" ]; then
  default_prefix="${OHOS_QEMU_PREFIX}"
elif [ -n "${HAPSIGNER_PREFIX:-}" ]; then
  default_prefix="${HAPSIGNER_PREFIX}"
elif [ -f "${PACKAGE_ROOT}/manifest.json" ]; then
  default_prefix="${PACKAGE_ROOT}"
else
  default_prefix="${HOME}/.ohos-qemu"
fi

PREFIX="${default_prefix}"
FORCE=0
case "$(printf '%s' "${FORCE_RAW}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on) FORCE=1 ;;
  0|false|no|off|"") FORCE=0 ;;
  *)
    echo "OHOS_QEMU_FORCE / HAPSIGNER_FORCE must be boolean, got: ${FORCE_RAW}" >&2
    exit 2
    ;;
esac

pass_args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --*=*)
      set -- "${1%%=*}" "${1#*=}" "${@:2}"
      ;;
  esac
  case "$1" in
    --prefix)
      PREFIX="${2:-}"
      shift 2
      ;;
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --repo)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --download-base-url)
      DOWNLOAD_BASE_URL="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --no-force)
      FORCE=0
      shift
      ;;
    *)
      pass_args+=("$1")
      shift
      ;;
  esac
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
    if [ -n "${GITHUB_TOKEN}" ]; then
      curl -fsSL --retry 3 -H "Authorization: Bearer ${GITHUB_TOKEN}" -o "${temporary}" "${installer_url}"
    else
      curl -fsSL --retry 3 -o "${temporary}" "${installer_url}"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN}" ]; then
      wget -q --header="Authorization: Bearer ${GITHUB_TOKEN}" -O "${temporary}" "${installer_url}"
    else
      wget -q -O "${temporary}" "${installer_url}"
    fi
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
export HAPSIGNER_DOWNLOAD_BASE_URL="${DOWNLOAD_BASE_URL}"
export HAPSIGNER_GITHUB_TOKEN="${GITHUB_TOKEN}"

cmd_args=(--prefix "${PREFIX}" --version "${VERSION}")
if [ "${FORCE}" = 1 ]; then
  cmd_args+=(--force)
fi
if [ -n "${DOWNLOAD_BASE_URL}" ]; then
  cmd_args+=(--download-base-url "${DOWNLOAD_BASE_URL}")
fi
if [ "${#pass_args[@]}" -gt 0 ]; then
  cmd_args+=("${pass_args[@]}")
fi

bash "${INSTALLER}" "${cmd_args[@]}"
