#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${OHOS_QEMU_REPO_URL:-https://github.com/harmony-contrib/ohos-qemu}"
RELEASE_TAG="${OHOS_QEMU_RELEASE_TAG:-${OHOS_QEMU_REF:-v20260809}}"
DOWNLOAD_BASE_URL="${OHOS_QEMU_DOWNLOAD_BASE_URL:-}"
GITHUB_TOKEN="${OHOS_QEMU_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"
PREFIX="${OHOS_QEMU_PREFIX:-${HOME}/.ohos-qemu}"
PLATFORM="${OHOS_QEMU_PLATFORM:-auto}"
ARCH="${OHOS_QEMU_ARCH:-auto}"
DEVICE_TYPE="${OHOS_QEMU_DEVICE_TYPE:-phone}"
FORCE=0
KEEP_ARCHIVE=0
INSTALL_HAP_SIGNER="${OHOS_QEMU_INSTALL_HAP_SIGNER:-1}"
HAP_SIGNER_REPO_URL="${OHOS_QEMU_HAPSIGNER_REPO_URL:-https://github.com/ohos-rs/hapsigner-rs}"
HAP_SIGNER_VERSION="${OHOS_QEMU_HAPSIGNER_VERSION:-v0.1.0}"
HAP_SIGNER_DOWNLOAD_BASE_URL="${OHOS_QEMU_HAPSIGNER_DOWNLOAD_BASE_URL:-}"
HAP_SIGNER_INSTALLER="${OHOS_QEMU_HAPSIGNER_INSTALLER:-}"

usage() {
  cat <<'USAGE'
Usage:
  install.sh [options]

Network installer for OpenHarmony QEMU image packages.

Options:
  --prefix DIR       Install directory. Default: $HOME/.ohos-qemu
  --platform NAME    Host platform: auto, linux, macos, windows
  --arch ARCH        Guest/package architecture: auto, arm64, aarch64, armv7a, x86_64
  --device-type TYPE Device type package: phone or 2in1. Default: phone
  --repo URL         GitHub repository URL. Default: https://github.com/harmony-contrib/ohos-qemu
  --release TAG      Release tag to download. Default: v20260809
  --download-base-url URL
                     Direct artifact base URL. Downloads URL/<package>.
                     Useful for GitHub Releases, private mirrors, or CDNs.
  --force            Replace an existing installed package directory
  --keep-archive     Keep the downloaded archive after extraction
  --with-hap-signer  Install the pure Rust hap-sign CLI (default)
  --without-hap-signer
                     Install only the QEMU image package
  --hap-signer-version TAG
                     hap-sign release tag. Default: v0.1.0
  --hap-signer-download-base-url URL
                     Direct URL containing hap-sign release assets
  -h, --help         Show this help

Examples:
  curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash -s -- --release v20260809
  bash scripts/install.sh --prefix "$HOME/opt/ohos-qemu" --arch arm64 --device-type phone
  bash scripts/install.sh --release RELEASE_TAG --arch x86_64 --device-type 2in1
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      PREFIX="${2:-}"
      shift 2
      ;;
    --platform)
      PLATFORM="${2:-}"
      shift 2
      ;;
    --arch)
      ARCH="${2:-}"
      shift 2
      ;;
    --device-type)
      DEVICE_TYPE="${2:-}"
      shift 2
      ;;
    --repo)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --release|--ref)
      RELEASE_TAG="${2:-}"
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
    --keep-archive)
      KEEP_ARCHIVE=1
      shift
      ;;
    --with-hap-signer)
      INSTALL_HAP_SIGNER=1
      shift
      ;;
    --without-hap-signer)
      INSTALL_HAP_SIGNER=0
      shift
      ;;
    --hap-signer-version)
      HAP_SIGNER_VERSION="${2:-}"
      shift 2
      ;;
    --hap-signer-download-base-url)
      HAP_SIGNER_DOWNLOAD_BASE_URL="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${PREFIX}" ] || [ -z "${REPO_URL}" ] || [ -z "${RELEASE_TAG}" ]; then
  usage >&2
  exit 2
fi

case "${INSTALL_HAP_SIGNER}" in
  0|1) ;;
  *)
    echo "OHOS_QEMU_INSTALL_HAP_SIGNER must be 0 or 1" >&2
    exit 2
    ;;
esac

case "${DEVICE_TYPE}" in
  phone|2in1)
    ;;
  *)
    echo "unsupported --device-type: ${DEVICE_TYPE}" >&2
    echo "expected phone or 2in1" >&2
    exit 2
    ;;
esac

detect_platform() {
  case "$(uname -s)" in
    Linux)
      printf '%s\n' linux
      ;;
    Darwin)
      printf '%s\n' macos
      ;;
    MINGW*|MSYS*|CYGWIN*)
      printf '%s\n' windows
      ;;
    *)
      echo "unsupported host platform: $(uname -s)" >&2
      exit 2
      ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    arm64|aarch64)
      printf '%s\n' arm64
      ;;
    x86_64|amd64)
      printf '%s\n' x86_64
      ;;
    *)
      echo "unsupported host architecture: $(uname -m)" >&2
      exit 2
      ;;
  esac
}

try_download_file() {
  local url="$1"
  local dest="$2"
  if command -v curl >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN}" ]; then
      if curl -fL --retry 3 --retry-delay 2 \
          -H "Authorization: Bearer ${GITHUB_TOKEN}" \
          -o "${dest}" "${url}"; then
        return 0
      fi
    else
      if curl -fL --retry 3 --retry-delay 2 -o "${dest}" "${url}"; then
        return 0
      fi
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN}" ]; then
      if wget --header="Authorization: Bearer ${GITHUB_TOKEN}" \
          -O "${dest}" "${url}"; then
        return 0
      fi
    else
      if wget -O "${dest}" "${url}"; then
        return 0
      fi
    fi
  fi
  rm -f "${dest}"
  return 1
}

artifact_url() {
  local name="$1"
  if [ -n "${DOWNLOAD_BASE_URL}" ]; then
    printf '%s\n' "${DOWNLOAD_BASE_URL%/}/${name}"
  else
    printf '%s\n' "${REPO_URL%/}/releases/download/${RELEASE_TAG}/${name}"
  fi
}

install_hap_signer() {
  local installer="${HAP_SIGNER_INSTALLER}"
  local temporary=""
  local installer_url
  local signer_repo_path
  local args=(--prefix "${PREFIX}" --version "${HAP_SIGNER_VERSION}")
  if [ "${FORCE}" = 1 ]; then
    args+=(--force)
  fi
  if [ -n "${HAP_SIGNER_DOWNLOAD_BASE_URL}" ]; then
    args+=(--download-base-url "${HAP_SIGNER_DOWNLOAD_BASE_URL}")
  fi
  if [ -z "${installer}" ]; then
    temporary="$(mktemp "${TMPDIR:-/tmp}/hapsigner-installer.XXXXXX")"
    installer_url="${HAP_SIGNER_REPO_URL%/}/raw/${HAP_SIGNER_VERSION}/install.sh"
    case "${HAP_SIGNER_REPO_URL}" in
      https://github.com/*)
        signer_repo_path="${HAP_SIGNER_REPO_URL#https://github.com/}"
        signer_repo_path="${signer_repo_path%.git}"
        installer_url="https://raw.githubusercontent.com/${signer_repo_path}/${HAP_SIGNER_VERSION}/install.sh"
        ;;
    esac
    echo "downloading signer installer: ${installer_url}"
    if ! try_download_file "${installer_url}" "${temporary}"; then
      rm -f "${temporary}"
      echo "unable to download the hap-sign installer" >&2
      return 1
    fi
    installer="${temporary}"
  fi
  HAPSIGNER_REPO_URL="${HAP_SIGNER_REPO_URL}" \
  HAPSIGNER_VERSION="${HAP_SIGNER_VERSION}" \
  HAPSIGNER_DOWNLOAD_BASE_URL="${HAP_SIGNER_DOWNLOAD_BASE_URL}" \
  HAPSIGNER_GITHUB_TOKEN="${GITHUB_TOKEN}" \
    bash "${installer}" "${args[@]}"
  if [ -n "${temporary}" ]; then
    rm -f "${temporary}"
  fi
}

case "${PLATFORM}" in
  auto)
    PLATFORM="$(detect_platform)"
    ;;
  linux|macos|windows)
    ;;
  *)
    echo "unsupported --platform: ${PLATFORM}" >&2
    exit 2
    ;;
esac

case "${ARCH}" in
  auto)
    ARCH="$(detect_arch)"
    ;;
  aarch64)
    ARCH="arm64"
    ;;
  armv7)
    ARCH="armv7a"
    ;;
  arm64|armv7a|x86_64)
    ;;
  *)
    echo "unsupported --arch: ${ARCH}" >&2
    exit 2
    ;;
esac

case "${ARCH}" in
  arm64)
    PACKAGE_BASE_DIR="openharmony-qemu-arm64-arm64_virt"
    ;;
  armv7a)
    PACKAGE_BASE_DIR="openharmony-qemu-armv7a-armv7a_virt"
    ;;
  x86_64)
    PACKAGE_BASE_DIR="openharmony-qemu-x86_64-x86_64_virt"
    ;;
esac

case "${DEVICE_TYPE}" in
  phone)
    PACKAGE_CANDIDATES=(
      "${PACKAGE_BASE_DIR}-phone.tar.gz"
      "${PACKAGE_BASE_DIR}.tar.gz"
    )
    ;;
  2in1)
    PACKAGE_CANDIDATES=("${PACKAGE_BASE_DIR}-2in1.tar.gz")
    ;;
esac

case "${PLATFORM}" in
  linux)
    LAUNCHER="launch/linux.sh"
    ;;
  macos)
    LAUNCHER="launch/macos.command"
    ;;
  windows)
    LAUNCHER="launch/windows.ps1"
    ;;
esac

ARCHIVE_DIR="${PREFIX}/downloads"

echo "OpenHarmony QEMU installer"
echo "repo:      ${REPO_URL}"
echo "release:   ${RELEASE_TAG}"
if [ -n "${DOWNLOAD_BASE_URL}" ]; then
  echo "mirror:    ${DOWNLOAD_BASE_URL}"
fi
echo "platform:  ${PLATFORM}"
echo "arch:      ${ARCH}"
echo "device:    ${DEVICE_TYPE}"
echo "prefix:    ${PREFIX}"

if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
  echo "curl or wget is required to download QEMU packages" >&2
  exit 1
fi

mkdir -p "${PREFIX}" "${ARCHIVE_DIR}"
tmp_archive="${ARCHIVE_DIR}/.openharmony-qemu-download.tmp.$$"
trap 'rm -f "${tmp_archive}"' EXIT

PACKAGE=
ATTEMPTED_URLS=()
for candidate in "${PACKAGE_CANDIDATES[@]}"; do
  candidate_url="$(artifact_url "${candidate}")"
  ATTEMPTED_URLS+=("${candidate_url}")
  echo "downloading: ${candidate_url}"
  if try_download_file "${candidate_url}" "${tmp_archive}"; then
    PACKAGE="${candidate}"
    break
  fi
  echo "package unavailable: ${candidate}" >&2
done

if [ -z "${PACKAGE}" ]; then
  echo "no downloadable ${DEVICE_TYPE} package found for ${ARCH}" >&2
  echo "tried:" >&2
  printf '  %s\n' "${ATTEMPTED_URLS[@]}" >&2
  exit 1
fi

PACKAGE_DIR="${PACKAGE%.tar.gz}"
INSTALL_DIR="${PREFIX}/${PACKAGE_DIR}"
ARCHIVE_PATH="${ARCHIVE_DIR}/${PACKAGE}"
echo "package:   ${PACKAGE}"

if [ -e "${INSTALL_DIR}" ] && [ "${FORCE}" != "1" ]; then
  echo "install directory already exists: ${INSTALL_DIR}" >&2
  echo "use --force to replace it" >&2
  exit 1
fi

mv "${tmp_archive}" "${ARCHIVE_PATH}"
trap - EXIT

if [ "${FORCE}" = "1" ]; then
  rm -rf "${INSTALL_DIR}"
fi

echo "extracting to: ${PREFIX}"
tar -xzf "${ARCHIVE_PATH}" -C "${PREFIX}"

if [ ! -d "${INSTALL_DIR}" ]; then
  echo "archive did not contain the expected package directory: ${PACKAGE_DIR}" >&2
  exit 1
fi

if [ "${KEEP_ARCHIVE}" != "1" ]; then
  rm -f "${ARCHIVE_PATH}"
fi

if [ "${INSTALL_HAP_SIGNER}" = 1 ]; then
  install_hap_signer
fi

echo
echo "installed: ${INSTALL_DIR}"
echo "launcher:  ${INSTALL_DIR}/${LAUNCHER}"
if [ "${INSTALL_HAP_SIGNER}" = 1 ]; then
  case "${PLATFORM}" in
    windows) echo "signer:    ${PREFIX}/bin/hap-sign.exe" ;;
    *) echo "signer:    ${PREFIX}/bin/hap-sign" ;;
  esac
fi
case "${PLATFORM}" in
  windows)
    echo "run:       powershell -ExecutionPolicy Bypass -File \"${INSTALL_DIR}/${LAUNCHER}\""
    ;;
  *)
    echo "run:       \"${INSTALL_DIR}/${LAUNCHER}\""
    ;;
esac
