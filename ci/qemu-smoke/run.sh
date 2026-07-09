#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

usage() {
  cat <<'USAGE'
Usage:
  run.sh --package PACKAGE --guest-arch ARCH --host-platform PLATFORM

ARCH:
  armv7a
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
  armv7a|armv7)
    RUST_TARGET="armv7-unknown-linux-musleabi"
    OHOS_RUST_TARGET="armv7-unknown-linux-ohos"
    BIN_NAME="hello-armv7a"
    ;;
  aarch64)
    RUST_TARGET="aarch64-unknown-linux-musl"
    OHOS_RUST_TARGET="aarch64-unknown-linux-ohos"
    BIN_NAME="hello-aarch64"
    ;;
  x86_64)
    RUST_TARGET="x86_64-unknown-linux-musl"
    OHOS_RUST_TARGET="x86_64-unknown-linux-ohos"
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
export PATH="$(dirname "${HDC}"):${PATH}"

command_path_for_host() {
  local path="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "${path}" 2>/dev/null || printf '%s\n' "${path}"
  else
    printf '%s\n' "${path}"
  fi
}

cargo_target_env_var() {
  local target="$1"
  local suffix="$2"
  local upper
  upper="$(printf '%s' "${target}" | tr '[:lower:]-' '[:upper:]_')"
  printf 'CARGO_TARGET_%s_%s\n' "${upper}" "${suffix}"
}

find_ohos_sdk_native() {
  local candidate
  for candidate in \
    "${OHOS_SDK_NATIVE:-}" \
    "${OHOS_NDK_HOME:-}/native" \
    "${OHOS_BASE_SDK_HOME:-}/native" \
    "${OHOS_SDK_HOME:-}/native"
  do
    if [ -z "${candidate}" ] || [ "${candidate}" = "/native" ]; then
      continue
    fi
    candidate="$(normalize_host_path "${candidate}")"
    if [ -d "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
}

find_ohos_linker() {
  local native="$1"
  local suffix
  local candidate
  if [ "${HOST_PLATFORM}" = "windows" ]; then
    for suffix in ".cmd" ".bat" ".exe"; do
      candidate="${native}/llvm/bin/${OHOS_RUST_TARGET}-clang${suffix}"
      if [ -f "${candidate}" ]; then
        printf '%s\n' "${candidate}"
        return
      fi
    done
    create_windows_ohos_linker_wrapper "${native}"
    return
  else
    for suffix in "" ".cmd" ".bat" ".exe"; do
      candidate="${native}/llvm/bin/${OHOS_RUST_TARGET}-clang${suffix}"
      if [ -f "${candidate}" ]; then
        printf '%s\n' "${candidate}"
        return
      fi
    done
  fi
}

create_windows_ohos_linker_wrapper() {
  local native="$1"
  local wrapper_dir="${WORK}/linker-wrapper"
  local wrapper="${wrapper_dir}/${OHOS_RUST_TARGET}-clang.cmd"
  local clang="${native}/llvm/bin/clang.exe"
  local sysroot="${native}/sysroot"
  local clang_host
  local sysroot_host

  if [ ! -f "${clang}" ]; then
    echo "Windows clang.exe not found under ${native}/llvm/bin" >&2
    return 1
  fi
  if [ ! -d "${sysroot}" ]; then
    echo "OpenHarmony sysroot not found under ${native}" >&2
    return 1
  fi

  clang_host="$(command_path_for_host "${clang}")"
  sysroot_host="$(command_path_for_host "${sysroot}")"
  mkdir -p "${wrapper_dir}"
  cat >"${wrapper}" <<EOF
@echo off
"${clang_host}" --target=${OHOS_RUST_TARGET} --sysroot="${sysroot_host}" -fuse-ld=lld %*
exit /b %ERRORLEVEL%
EOF
  printf '%s\n' "${wrapper}"
}

create_hdc_runner_wrapper() {
  local wrapper_dir="${WORK}/hdc-wrapper"
  local real_hdc_posix="${HDC}"
  local real_hdc_host
  real_hdc_host="$(command_path_for_host "${HDC}")"
  mkdir -p "${wrapper_dir}"

  cat >"${wrapper_dir}/hdc" <<EOF
#!/usr/bin/env bash
set -euo pipefail
REAL_HDC="${real_hdc_posix}"
TARGET="127.0.0.1:5555"

if [ "\${1:-}" = "list" ] && [ "\${2:-}" = "targets" ]; then
  "\${REAL_HDC}" tconn "\${TARGET}" >/dev/null 2>&1 || true
  if "\${REAL_HDC}" list targets 2>/dev/null | grep -q "\${TARGET}"; then
    "\${REAL_HDC}" list targets | grep "\${TARGET}"
  else
    printf '%s\n' "\${TARGET}"
  fi
  exit 0
fi

exec "\${REAL_HDC}" -t "\${TARGET}" "\$@"
EOF
  chmod +x "${wrapper_dir}/hdc"

  cat >"${wrapper_dir}/hdc.cmd" <<EOF
@echo off
set "REAL_HDC=${real_hdc_host}"
set "TARGET=127.0.0.1:5555"

if /I "%~1"=="list" if /I "%~2"=="targets" (
  "%REAL_HDC%" tconn %TARGET% >nul 2>nul
  "%REAL_HDC%" list targets | findstr /C:"%TARGET%" >nul 2>nul
  if errorlevel 1 (
    echo %TARGET%
  ) else (
    "%REAL_HDC%" list targets | findstr /C:"%TARGET%"
  )
  exit /b 0
)

"%REAL_HDC%" -t %TARGET% %*
exit /b %ERRORLEVEL%
EOF

  printf '%s\n' "${wrapper_dir}"
}

prepare_windows_launcher() {
  local launcher="${PACKAGE_DIR}/launch/windows.ps1"
  local ci_launcher="${PACKAGE_DIR}/launch/windows-ci.ps1"
  if [ ! -f "${launcher}" ]; then
    echo "Windows launcher not found: ${launcher}" >&2
    exit 1
  fi
  cp "${launcher}" "${ci_launcher}"
  sed -i \
    's/\$AccelArgs = @("-accel", "whpx,kernel-irqchip=off")/\$AccelArgs = @("-accel", "tcg,thread=multi")/' \
    "${ci_launcher}"
  sed -i \
    's/Write-Host "WHPX acceleration enabled."/Write-Host "WHPX disabled for CI, using TCG software emulation."/' \
    "${ci_launcher}"
  printf '%s\n' "${ci_launcher}"
}

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
    WINDOWS_LAUNCHER="$(prepare_windows_launcher)"
    QEMU_DISPLAY=none QEMU_ACCEL=tcg powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${WINDOWS_LAUNCHER}" >"${LOG}" 2>&1 &
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

echo "::group::Wait for AccountMgr foreground user"
ACCOUNT_READY_ATTEMPTS="${QEMU_ACCOUNT_WAIT_ATTEMPTS:-120}"
ACCOUNT_READY_LOG="${WORK}/account-ready.log"
account_ready=0
for attempt in $(seq 1 "${ACCOUNT_READY_ATTEMPTS}"); do
  "${HDC}" -t 127.0.0.1:5555 shell '
    echo "bootevent.account.ready=$(param get bootevent.account.ready)"
    hidumper -s AccountMgr -a "-os_account_infos"
    bm dump -a | head -30
  ' >"${ACCOUNT_READY_LOG}" 2>&1 || true
  if grep -q 'bootevent.account.ready=true' "${ACCOUNT_READY_LOG}" &&
     grep -q 'ID: 100' "${ACCOUNT_READY_LOG}" &&
     grep -q 'isForeground: 1' "${ACCOUNT_READY_LOG}"; then
    account_ready=1
    cat "${ACCOUNT_READY_LOG}"
    break
  fi
  if ! kill -0 "${QEMU_PID}" >/dev/null 2>&1; then
    echo "QEMU exited before AccountMgr became ready" >&2
    cat "${ACCOUNT_READY_LOG}" || true
    tail -n 200 "${LOG}" || true
    exit 1
  fi
  if [ $((attempt % 20)) -eq 0 ]; then
    echo "still waiting for AccountMgr foreground user after ${attempt}/${ACCOUNT_READY_ATTEMPTS} attempts"
    cat "${ACCOUNT_READY_LOG}" || true
    tail -n 80 "${LOG}" || true
  fi
  sleep 3
done

if [ "${account_ready}" != "1" ]; then
  echo "AccountMgr did not initialize a foreground user in time" >&2
  cat "${ACCOUNT_READY_LOG}" || true
  "${HDC}" -t 127.0.0.1:5555 shell 'hilog -x | grep -iE "AccountMgr|AbilityManager|StartUser|SwitchToUser|highest priority|account.ready|Foreground" | tail -240' || true
  tail -n 240 "${LOG}" || true
  exit 1
fi
echo "::endgroup::"

echo "::group::Transfer and execute Rust binary"
"${HDC}" -t 127.0.0.1:5555 shell 'mkdir -p /data/local/tmp'
"${HDC}" -t 127.0.0.1:5555 file send "${WORK}/${BIN_NAME}" "/data/local/tmp/${BIN_NAME}"
"${HDC}" -t 127.0.0.1:5555 shell "chmod 755 /data/local/tmp/${BIN_NAME}"
"${HDC}" -t 127.0.0.1:5555 shell "uname -a; id; /data/local/tmp/${BIN_NAME} from-ci"
echo "::endgroup::"

echo "::group::Run ohos-test-runner Cargo smoke"
OHOS_SDK_NATIVE_DIR="$(find_ohos_sdk_native)"
if [ -z "${OHOS_SDK_NATIVE_DIR}" ]; then
  echo "OHOS SDK native directory not found. Ensure setup-ohos-sdk installed the native component." >&2
  exit 1
fi
OHOS_LINKER="$(find_ohos_linker "${OHOS_SDK_NATIVE_DIR}")"
if [ -z "${OHOS_LINKER}" ]; then
  echo "OpenHarmony clang linker not found for ${OHOS_RUST_TARGET} under ${OHOS_SDK_NATIVE_DIR}/llvm/bin" >&2
  find "${OHOS_SDK_NATIVE_DIR}/llvm/bin" -maxdepth 1 -name '*unknown-linux-ohos-clang*' -print 2>/dev/null || true
  exit 1
fi
echo "OpenHarmony SDK native: ${OHOS_SDK_NATIVE_DIR}"
echo "OpenHarmony Rust target: ${OHOS_RUST_TARGET}"
echo "OpenHarmony linker: ${OHOS_LINKER}"

rustup target add "${OHOS_RUST_TARGET}"
CARGO_INSTALL_ROOT_POSIX="${WORK}/cargo-install"
mkdir -p "${CARGO_INSTALL_ROOT_POSIX}"
export CARGO_INSTALL_ROOT="$(command_path_for_host "${CARGO_INSTALL_ROOT_POSIX}")"
export PATH="${CARGO_INSTALL_ROOT_POSIX}/bin:${PATH}"
if ! command -v ohos-test-runner >/dev/null 2>&1; then
  cargo install \
    --locked \
    --git https://github.com/openharmony-rs/ohos-test-runner.git \
    --rev 4ad3e3e14845522a87bb4c4b4957d34323662183 \
    ohos-test-runner
fi

RUNNER_ENV="$(cargo_target_env_var "${OHOS_RUST_TARGET}" RUNNER)"
LINKER_ENV="$(cargo_target_env_var "${OHOS_RUST_TARGET}" LINKER)"
LINKER_FOR_CARGO="$(command_path_for_host "${OHOS_LINKER}")"
HDC_WRAPPER_DIR="$(create_hdc_runner_wrapper)"
env \
  "PATH=${HDC_WRAPPER_DIR}:${PATH}" \
  "${RUNNER_ENV}=ohos-test-runner" \
  "${LINKER_ENV}=${LINKER_FOR_CARGO}" \
  RUST_LOG=debug \
  cargo test \
    --manifest-path "${ROOT}/ci/ohos-test-runner-smoke/Cargo.toml" \
    --target "${OHOS_RUST_TARGET}" \
    -- \
    --nocapture
echo "::endgroup::"

echo "::group::QEMU log tail"
tail -n 160 "${LOG}" || true
echo "::endgroup::"
