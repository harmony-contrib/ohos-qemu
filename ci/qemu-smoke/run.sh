#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

usage() {
  cat <<'USAGE'
Usage:
  run.sh --package PACKAGE --guest-arch ARCH --host-platform PLATFORM

ARCH:
  aarch64
  x86_64

PLATFORM:
  linux
  macos
  windows
USAGE
}

PACKAGE=
GUEST_ARCH=
HOST_PLATFORM=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --package)
      PACKAGE="${2:-}"
      shift 2
      ;;
    --guest-arch)
      GUEST_ARCH="${2:-}"
      shift 2
      ;;
    --host-platform)
      HOST_PLATFORM="${2:-}"
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

if [ -z "${PACKAGE}" ] || [ -z "${GUEST_ARCH}" ] || [ -z "${HOST_PLATFORM}" ]; then
  usage >&2
  exit 2
fi

normalize_host_path() {
  local path="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "${path}" 2>/dev/null || printf '%s\n' "${path}"
  else
    printf '%s\n' "${path}"
  fi
}

case "${GUEST_ARCH}" in
  aarch64)
    RUST_TARGET="aarch64-unknown-linux-musl"
    BIN_NAME="hello-aarch64"
    ;;
  x86_64)
    RUST_TARGET="x86_64-unknown-linux-musl"
    BIN_NAME="hello-x86_64"
    ;;
  *)
    echo "unsupported guest arch: ${GUEST_ARCH}" >&2
    exit 2
    ;;
esac

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PACKAGE="$(normalize_host_path "${PACKAGE}")"
TEMP_ROOT="$(normalize_host_path "${RUNNER_TEMP:-${ROOT}/.tmp}")"
WORK="${TEMP_ROOT}/ohos-qemu-smoke-${HOST_PLATFORM}-${GUEST_ARCH}"
EXTRACT="${WORK}/extract"
LOG="${WORK}/qemu.log"
mkdir -p "${WORK}" "${EXTRACT}"
echo "work dir: ${WORK}"

echo "::group::Extract package"
case "${PACKAGE}" in
  *.tar.gz)
    tar -xzf "${PACKAGE}" -C "${EXTRACT}"
    ;;
  *.zip)
    unzip -q "${PACKAGE}" -d "${EXTRACT}"
    ;;
  *)
    echo "unsupported package format: ${PACKAGE}" >&2
    exit 2
    ;;
esac
PACKAGE_DIR="$(find "${EXTRACT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "${PACKAGE_DIR}" ]; then
  echo "package did not extract to a directory" >&2
  exit 1
fi
find "${PACKAGE_DIR}/launch" -maxdepth 1 -type f -print | sort
echo "::endgroup::"

echo "::group::Build Rust smoke executable"
rustup target add "${RUST_TARGET}"
rustc \
  --target "${RUST_TARGET}" \
  -C linker=rust-lld \
  -C target-feature=+crt-static \
  -C panic=abort \
  -O \
  "${ROOT}/ci/qemu-smoke/hello.rs" \
  -o "${WORK}/${BIN_NAME}"
file "${WORK}/${BIN_NAME}" || true
echo "::endgroup::"

find_hdc() {
  if command -v hdc >/dev/null 2>&1; then
    command -v hdc
    return
  fi
  local sdk_root="${OHOS_BASE_SDK_HOME:-${OHOS_SDK_HOME:-}}"
  if [ -n "${sdk_root}" ]; then
    sdk_root="$(normalize_host_path "${sdk_root}")"
    find "${sdk_root}" -path '*/toolchains/hdc*' -type f -perm -111 2>/dev/null | head -n 1
    return
  fi
  if [ -x "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc" ]; then
    printf '%s\n' "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"
    return
  fi
  find "${HOME}" -path '*/toolchains/hdc*' -type f -perm -111 2>/dev/null | head -n 1
}

HDC="$(find_hdc)"
if [ -z "${HDC}" ] || [ ! -x "${HDC}" ]; then
  echo "hdc not found. Ensure openharmony-rs/setup-ohos-sdk is run before this script." >&2
  exit 1
fi
echo "Using hdc: ${HDC}"

cleanup() {
  if [ -n "${QEMU_PID:-}" ] && kill -0 "${QEMU_PID}" >/dev/null 2>&1; then
    kill "${QEMU_PID}" >/dev/null 2>&1 || true
    wait "${QEMU_PID}" 2>/dev/null || true
    sleep 2
    kill -9 "${QEMU_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "::group::Start QEMU"
cd "${PACKAGE_DIR}"
case "${HOST_PLATFORM}" in
  linux)
    QEMU_DISPLAY=none ./launch/linux.sh >"${LOG}" 2>&1 &
    ;;
  macos)
    QEMU_DISPLAY=none ./launch/macos.command >"${LOG}" 2>&1 &
    ;;
  windows)
    QEMU_DISPLAY=none powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./launch/windows.ps1 >"${LOG}" 2>&1 &
    ;;
  *)
    echo "unsupported host platform: ${HOST_PLATFORM}" >&2
    exit 2
    ;;
esac
QEMU_PID=$!
echo "QEMU PID: ${QEMU_PID}"
echo "::endgroup::"

echo "::group::Wait for HDC"
"${HDC}" kill || true
"${HDC}" start || true
HDC_TCONN_LOG="${WORK}/hdc-tconn.log"
WAIT_ATTEMPTS="${QEMU_HDC_WAIT_ATTEMPTS:-240}"
connected=0
for attempt in $(seq 1 "${WAIT_ATTEMPTS}"); do
  if "${HDC}" tconn 127.0.0.1:5555 >"${HDC_TCONN_LOG}" 2>&1; then
    cat "${HDC_TCONN_LOG}"
    if "${HDC}" list targets | grep -q '127.0.0.1:5555'; then
      connected=1
      break
    fi
  else
    cat "${HDC_TCONN_LOG}" || true
  fi
  if ! kill -0 "${QEMU_PID}" >/dev/null 2>&1; then
    echo "QEMU exited before HDC became available" >&2
    tail -n 200 "${LOG}" || true
    exit 1
  fi
  if [ $((attempt % 20)) -eq 0 ]; then
    echo "still waiting for HDC after ${attempt}/${WAIT_ATTEMPTS} attempts"
    if (echo >/dev/tcp/127.0.0.1/5555) >/dev/null 2>&1; then
      echo "tcp port 127.0.0.1:5555 is open"
    else
      echo "tcp port 127.0.0.1:5555 is not open yet"
    fi
    tail -n 80 "${LOG}" || true
  fi
  sleep 3
done

if [ "${connected}" != "1" ]; then
  echo "HDC did not connect in time" >&2
  "${HDC}" list targets -v || true
  tail -n 240 "${LOG}" || true
  exit 1
fi
"${HDC}" list targets -v
echo "::endgroup::"

echo "::group::Transfer and execute Rust binary"
"${HDC}" -t 127.0.0.1:5555 shell 'mkdir -p /data/local/tmp'
"${HDC}" -t 127.0.0.1:5555 file send "${WORK}/${BIN_NAME}" "/data/local/tmp/${BIN_NAME}"
"${HDC}" -t 127.0.0.1:5555 shell "chmod 755 /data/local/tmp/${BIN_NAME}"
"${HDC}" -t 127.0.0.1:5555 shell "uname -a; id; /data/local/tmp/${BIN_NAME} from-ci"
echo "::endgroup::"

echo "::group::QEMU log tail"
tail -n 160 "${LOG}" || true
echo "::endgroup::"
