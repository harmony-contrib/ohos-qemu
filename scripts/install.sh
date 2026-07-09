#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${OHOS_QEMU_REPO_URL:-https://github.com/harmony-contrib/ohos-qemu}"
GIT_REF="${OHOS_QEMU_REF:-main}"
DOWNLOAD_BASE_URL="${OHOS_QEMU_DOWNLOAD_BASE_URL:-}"
GITHUB_TOKEN="${OHOS_QEMU_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"
PREFIX="${OHOS_QEMU_PREFIX:-${HOME}/.ohos-qemu}"
PLATFORM="${OHOS_QEMU_PLATFORM:-auto}"
ARCH="${OHOS_QEMU_ARCH:-auto}"
FORCE=0
KEEP_ARCHIVE=0

usage() {
  cat <<'USAGE'
Usage:
  install.sh [options]

Network installer for OpenHarmony QEMU image packages.

Options:
  --prefix DIR       Install directory. Default: $HOME/.ohos-qemu
  --platform NAME    Host platform: auto, linux, macos, windows
  --arch ARCH        Guest/package architecture: auto, arm64, aarch64, armv7a, x86_64
  --repo URL         GitHub repository URL. Default: https://github.com/harmony-contrib/ohos-qemu
  --ref REF          Git ref to download from. Default: main
  --download-base-url URL
                     Direct artifact base URL. Downloads URL/<package>.
                     Useful for GitHub Releases, private mirrors, or CDNs.
  --force            Replace an existing installed package directory
  --keep-archive     Keep the downloaded archive after extraction
  -h, --help         Show this help

Examples:
  curl -fsSL https://raw.githubusercontent.com/harmony-contrib/ohos-qemu/main/scripts/install.sh | bash
  bash scripts/install.sh --prefix "$HOME/opt/ohos-qemu" --arch arm64
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
    --repo)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --ref)
      GIT_REF="${2:-}"
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

if [ -z "${PREFIX}" ] || [ -z "${REPO_URL}" ] || [ -z "${GIT_REF}" ]; then
  usage >&2
  exit 2
fi

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

download_file() {
  local url="$1"
  local dest="$2"
  if command -v curl >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN}" ]; then
      curl -fL --retry 3 --retry-delay 2 \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -o "${dest}" "${url}"
    else
      curl -fL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN}" ]; then
      wget --header="Authorization: Bearer ${GITHUB_TOKEN}" -O "${dest}" "${url}"
    else
      wget -O "${dest}" "${url}"
    fi
  else
    echo "curl or wget is required to download ${url}" >&2
    exit 1
  fi
}

artifact_url() {
  local name="$1"
  if [ -n "${DOWNLOAD_BASE_URL}" ]; then
    printf '%s\n' "${DOWNLOAD_BASE_URL%/}/${name}"
  else
    printf '%s\n' "${REPO_URL%/}/raw/${GIT_REF}/artifacts/${name}"
  fi
}

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    LC_ALL=C LANG=C shasum -a 256 "${file}" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    LC_ALL=C LANG=C openssl dgst -sha256 "${file}" | awk '{print $NF}'
  else
    echo "sha256sum, shasum, or openssl is required for checksum verification" >&2
    exit 1
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
    PACKAGE="openharmony-qemu-arm64-arm64_virt.tar.gz"
    PACKAGE_DIR="openharmony-qemu-arm64-arm64_virt"
    EXPECTED_SHA256="e327603801c01b1042cb887fa998e0e89a7e30151de589be8071f905bdf925ce"
    ;;
  armv7a)
    PACKAGE="openharmony-qemu-armv7a-armv7a_virt.tar.gz"
    PACKAGE_DIR="openharmony-qemu-armv7a-armv7a_virt"
    EXPECTED_SHA256="98dda34c8120948605d36d3f2d546086a2c8e2370e24aa8f06f95d6eaac3ce25"
    ;;
  x86_64)
    PACKAGE="openharmony-qemu-x86_64-x86_64_virt.tar.gz"
    PACKAGE_DIR="openharmony-qemu-x86_64-x86_64_virt"
    EXPECTED_SHA256="7face629b19aaa1dcc39737c1b05360fae63eebee73589dcc25f4bcb3ea632c0"
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

RAW_URL="$(artifact_url "${PACKAGE}")"
INSTALL_DIR="${PREFIX}/${PACKAGE_DIR}"
ARCHIVE_DIR="${PREFIX}/downloads"
ARCHIVE_PATH="${ARCHIVE_DIR}/${PACKAGE}"

echo "OpenHarmony QEMU installer"
echo "repo:      ${REPO_URL}"
echo "ref:       ${GIT_REF}"
if [ -n "${DOWNLOAD_BASE_URL}" ]; then
  echo "mirror:    ${DOWNLOAD_BASE_URL}"
fi
echo "platform:  ${PLATFORM}"
echo "arch:      ${ARCH}"
echo "prefix:    ${PREFIX}"
echo "package:   ${PACKAGE}"

if [ -e "${INSTALL_DIR}" ] && [ "${FORCE}" != "1" ]; then
  echo "install directory already exists: ${INSTALL_DIR}" >&2
  echo "use --force to replace it" >&2
  exit 1
fi

mkdir -p "${PREFIX}" "${ARCHIVE_DIR}"
tmp_archive="${ARCHIVE_PATH}.tmp.$$"
trap 'rm -f "${tmp_archive}"' EXIT

echo "downloading: ${RAW_URL}"
download_file "${RAW_URL}" "${tmp_archive}"

ACTUAL_SHA256="$(sha256_file "${tmp_archive}")"
if [ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]; then
  echo "checksum mismatch for ${PACKAGE}" >&2
  echo "expected: ${EXPECTED_SHA256}" >&2
  echo "actual:   ${ACTUAL_SHA256}" >&2
  exit 1
fi
echo "checksum:  ${ACTUAL_SHA256}"

mv "${tmp_archive}" "${ARCHIVE_PATH}"
trap - EXIT

if [ "${FORCE}" = "1" ]; then
  rm -rf "${INSTALL_DIR}"
fi

echo "extracting to: ${PREFIX}"
tar -xzf "${ARCHIVE_PATH}" -C "${PREFIX}"

if [ "${KEEP_ARCHIVE}" != "1" ]; then
  rm -f "${ARCHIVE_PATH}"
fi

echo
echo "installed: ${INSTALL_DIR}"
echo "launcher:  ${INSTALL_DIR}/${LAUNCHER}"
case "${PLATFORM}" in
  windows)
    echo "run:       powershell -ExecutionPolicy Bypass -File \"${INSTALL_DIR}/${LAUNCHER}\""
    ;;
  *)
    echo "run:       \"${INSTALL_DIR}/${LAUNCHER}\""
    ;;
esac
