#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

usage() {
  cat <<'USAGE'
Usage:
  run.sh --package PACKAGE --guest-arch ARCH --host-platform PLATFORM [options]

OPTIONS:
  --phase PHASE                   all, prepare, start, wait-hdc, wait-account,
                                  run-binary, run-ohos-runner, diagnostics, cleanup
  --require-account true|false    Require foreground user 100, default: true
  --run-ohos-runner true|false    Run the OpenHarmony Rust test runner, default: true
  --account-wait-attempts N       Account readiness attempts at 3 seconds each,
                                  default: 300

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
RUN_OHOS_RUNNER=true
REQUIRE_ACCOUNT=true
PHASE=all
ACCOUNT_WAIT_ATTEMPTS=300

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
    --run-ohos-runner)
      RUN_OHOS_RUNNER="${2:-}"
      shift 2
      ;;
    --require-account)
      REQUIRE_ACCOUNT="${2:-}"
      shift 2
      ;;
    --phase)
      PHASE="${2:-}"
      shift 2
      ;;
    --account-wait-attempts)
      ACCOUNT_WAIT_ATTEMPTS="${2:-}"
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

for bool_value in "${RUN_OHOS_RUNNER}" "${REQUIRE_ACCOUNT}"; do
  case "${bool_value}" in
    true|false)
      ;;
    *)
      echo "boolean options must be true or false: ${bool_value}" >&2
      exit 2
      ;;
  esac
done

case "${PHASE}" in
  all|prepare|start|wait-hdc|wait-account|run-binary|run-ohos-runner|diagnostics|cleanup)
    ;;
  *)
    echo "unsupported --phase: ${PHASE}" >&2
    exit 2
    ;;
esac

case "${ACCOUNT_WAIT_ATTEMPTS}" in
  ''|*[!0-9]*)
    echo "--account-wait-attempts must be a positive integer" >&2
    exit 2
    ;;
esac
if [ "${ACCOUNT_WAIT_ATTEMPTS}" -lt 1 ]; then
  echo "--account-wait-attempts must be a positive integer" >&2
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
PID_FILE="${WORK}/qemu.pid"
DIAGNOSTICS_DIR="${WORK}/diagnostics"
mkdir -p "${WORK}"
echo "work dir: ${WORK}"

find_hdc() {
  if command -v hdc >/dev/null 2>&1; then
    command -v hdc
    return
  fi
  local sdk_root="${OHOS_BASE_SDK_HOME:-${OHOS_SDK_HOME:-}}"
  if [ -n "${sdk_root}" ]; then
    sdk_root="$(normalize_host_path "${sdk_root}")"
    find "${sdk_root}" -path '*/toolchains/hdc*' -type f -perm -111 2>/dev/null | sed -n '1p'
    return
  fi
  if [ -x "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc" ]; then
    printf '%s\n' "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"
    return
  fi
  find "${HOME}" -path '*/toolchains/hdc*' -type f -perm -111 2>/dev/null | sed -n '1p'
}

load_package_dir() {
  PACKAGE_DIR="$(find "${EXTRACT}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sed -n '1p')"
  if [ -z "${PACKAGE_DIR}" ] || [ ! -d "${PACKAGE_DIR}" ]; then
    echo "package did not extract to a directory under ${EXTRACT}" >&2
    return 1
  fi
}

ensure_hdc() {
  HDC="$(find_hdc)"
  if [ -z "${HDC}" ] || [ ! -x "${HDC}" ]; then
    echo "hdc not found. Ensure openharmony-rs/setup-ohos-sdk is run before this script." >&2
    return 1
  fi
  echo "Using hdc: ${HDC}"
  export PATH="$(dirname "${HDC}"):${PATH}"
}

prepare_workspace() {
  echo "::group::Extract package"
  rm -rf "${EXTRACT}"
  mkdir -p "${EXTRACT}"
  case "${PACKAGE}" in
    *.tar.gz)
      tar -xzf "${PACKAGE}" -C "${EXTRACT}"
      ;;
    *.zip)
      unzip -q "${PACKAGE}" -d "${EXTRACT}"
      ;;
    *)
      echo "unsupported package format: ${PACKAGE}" >&2
      return 2
      ;;
  esac
  load_package_dir
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
  ensure_hdc
  echo "::endgroup::"
}

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

read_qemu_pid() {
  if [ ! -f "${PID_FILE}" ]; then
    echo "QEMU PID file not found: ${PID_FILE}" >&2
    return 1
  fi
  QEMU_PID="$(tr -d '[:space:]' <"${PID_FILE}")"
  case "${QEMU_PID}" in
    ''|*[!0-9]*)
      echo "invalid QEMU PID: ${QEMU_PID}" >&2
      return 1
      ;;
  esac
}

qemu_is_alive() {
  read_qemu_pid >/dev/null 2>&1 && kill -0 "${QEMU_PID}" >/dev/null 2>&1
}

start_qemu() {
  load_package_dir
  : >"${LOG}"
  rm -f "${PID_FILE}"
  cd "${PACKAGE_DIR}"
  case "${HOST_PLATFORM}" in
    linux)
      nohup env QEMU_DISPLAY=none ./launch/linux.sh >"${LOG}" 2>&1 </dev/null &
      ;;
    macos)
      nohup env QEMU_DISPLAY=none ./launch/macos.command >"${LOG}" 2>&1 </dev/null &
      ;;
    windows)
      WINDOWS_LAUNCHER="$(prepare_windows_launcher)"
      nohup env QEMU_DISPLAY=none QEMU_ACCEL=tcg powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${WINDOWS_LAUNCHER}" >"${LOG}" 2>&1 </dev/null &
      ;;
    *)
      echo "unsupported host platform: ${HOST_PLATFORM}" >&2
      return 2
      ;;
  esac
  QEMU_PID=$!
  printf '%s\n' "${QEMU_PID}" >"${PID_FILE}"
  echo "QEMU PID: ${QEMU_PID}"
  sleep 1
  if ! qemu_is_alive; then
    echo "QEMU exited immediately" >&2
    tail -n 200 "${LOG}" || true
    return 1
  fi
}

wait_for_hdc() {
  ensure_hdc
  read_qemu_pid
  "${HDC}" kill || true
  "${HDC}" start || true
  local hdc_tconn_log="${WORK}/hdc-tconn.log"
  local wait_attempts="${QEMU_HDC_WAIT_ATTEMPTS:-240}"
  local connected=0
  local attempt

  for attempt in $(seq 1 "${wait_attempts}"); do
    if "${HDC}" tconn 127.0.0.1:5555 >"${hdc_tconn_log}" 2>&1; then
      cat "${hdc_tconn_log}"
      if "${HDC}" list targets | grep -q '127.0.0.1:5555'; then
        connected=1
        break
      fi
    else
      cat "${hdc_tconn_log}" || true
    fi
    if ! qemu_is_alive; then
      echo "QEMU exited before HDC became available" >&2
      tail -n 200 "${LOG}" || true
      return 1
    fi
    if [ $((attempt % 20)) -eq 0 ]; then
      echo "still waiting for HDC after ${attempt}/${wait_attempts} attempts"
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
    return 1
  fi
  "${HDC}" list targets -v
}

wait_for_account() {
  if [ "${REQUIRE_ACCOUNT}" != "true" ]; then
    echo "AccountMgr readiness is not required for ${GUEST_ARCH} binary verification."
    return 0
  fi

  ensure_hdc
  read_qemu_pid
  local account_history_log="${WORK}/account-ready.log"
  local account_last_log="${WORK}/account-last.log"
  local param_ready=0
  local user_present=0
  local foreground=0
  local attempt
  : >"${account_history_log}"

  for attempt in $(seq 1 "${ACCOUNT_WAIT_ATTEMPTS}"); do
    "${HDC}" -t 127.0.0.1:5555 shell '
      echo "bootevent.account.ready=$(param get bootevent.account.ready)"
      hidumper -s AccountMgr -a "-os_account_infos"
    ' >"${account_last_log}" 2>&1 || true

    if [ "${param_ready}" = "0" ] && grep -Eq 'bootevent\.account\.ready=(true|"true")' "${account_last_log}"; then
      param_ready=1
      echo "AccountMgr parameter service is ready at attempt ${attempt}."
    fi
    if [ "${user_present}" = "0" ] && grep -Eq 'ID:[[:space:]]*100([^0-9]|$)' "${account_last_log}"; then
      user_present=1
      echo "AccountMgr user 100 exists at attempt ${attempt}."
    fi
    if [ "${foreground}" = "0" ] && grep -Eq 'isForeground:[[:space:]]*(1|true)([^[:alnum:]]|$)' "${account_last_log}"; then
      foreground=1
      echo "AccountMgr user 100 is foreground at attempt ${attempt}."
    fi

    printf 'attempt=%s/%s param_ready=%s user_100=%s foreground=%s\n' \
      "${attempt}" "${ACCOUNT_WAIT_ATTEMPTS}" "${param_ready}" "${user_present}" "${foreground}" \
      >>"${account_history_log}"

    if [ "${param_ready}" = "1" ] && [ "${user_present}" = "1" ] && [ "${foreground}" = "1" ]; then
      cat "${account_last_log}"
      return 0
    fi
    if ! qemu_is_alive; then
      echo "QEMU exited before AccountMgr became ready" >&2
      cat "${account_last_log}" || true
      tail -n 200 "${LOG}" || true
      return 1
    fi
    if [ $((attempt % 20)) -eq 0 ]; then
      echo "AccountMgr state after ${attempt}/${ACCOUNT_WAIT_ATTEMPTS}: param_ready=${param_ready} user_100=${user_present} foreground=${foreground}"
      {
        printf '\n===== attempt %s =====\n' "${attempt}"
        cat "${account_last_log}"
      } >>"${account_history_log}"
      tail -n 80 "${LOG}" || true
    fi
    sleep 3
  done

  echo "AccountMgr readiness timed out: param_ready=${param_ready} user_100=${user_present} foreground=${foreground}" >&2
  cat "${account_last_log}" || true
  "${HDC}" -t 127.0.0.1:5555 shell 'bm dump -a | head -80; hilog -x | grep -iE "AccountMgr|AbilityManager|StartUser|SwitchToUser|account.ready|Foreground" | tail -240' || true
  tail -n 240 "${LOG}" || true
  return 1
}

run_binary() {
  ensure_hdc
  if [ ! -f "${WORK}/${BIN_NAME}" ]; then
    echo "Rust smoke executable not found: ${WORK}/${BIN_NAME}" >&2
    return 1
  fi
  "${HDC}" -t 127.0.0.1:5555 shell 'mkdir -p /data/local/tmp'
  "${HDC}" -t 127.0.0.1:5555 file send "${WORK}/${BIN_NAME}" "/data/local/tmp/${BIN_NAME}"
  "${HDC}" -t 127.0.0.1:5555 shell "chmod 755 /data/local/tmp/${BIN_NAME}"
  "${HDC}" -t 127.0.0.1:5555 shell "uname -a; id; /data/local/tmp/${BIN_NAME} from-ci"
}

run_ohos_runner() {
  if [ "${RUN_OHOS_RUNNER}" != "true" ]; then
    echo "ohos-test-runner smoke disabled for ${GUEST_ARCH}; binary execution was verified."
    return 0
  fi

  ensure_hdc
  local ohos_sdk_native_dir
  local ohos_linker
  local cargo_install_root_posix
  local runner_env
  local linker_env
  local linker_for_cargo
  local hdc_wrapper_dir

  ohos_sdk_native_dir="$(find_ohos_sdk_native)"
  if [ -z "${ohos_sdk_native_dir}" ]; then
    echo "OHOS SDK native directory not found. Ensure setup-ohos-sdk installed the native component." >&2
    return 1
  fi
  ohos_linker="$(find_ohos_linker "${ohos_sdk_native_dir}")"
  if [ -z "${ohos_linker}" ]; then
    echo "OpenHarmony clang linker not found for ${OHOS_RUST_TARGET} under ${ohos_sdk_native_dir}/llvm/bin" >&2
    find "${ohos_sdk_native_dir}/llvm/bin" -maxdepth 1 -name '*unknown-linux-ohos-clang*' -print 2>/dev/null || true
    return 1
  fi
  echo "OpenHarmony SDK native: ${ohos_sdk_native_dir}"
  echo "OpenHarmony Rust target: ${OHOS_RUST_TARGET}"
  echo "OpenHarmony linker: ${ohos_linker}"

  rustup target add "${OHOS_RUST_TARGET}"
  cargo_install_root_posix="${WORK}/cargo-install"
  mkdir -p "${cargo_install_root_posix}"
  export CARGO_INSTALL_ROOT="$(command_path_for_host "${cargo_install_root_posix}")"
  export PATH="${cargo_install_root_posix}/bin:${PATH}"
  if ! command -v ohos-test-runner >/dev/null 2>&1; then
    cargo install \
      --locked \
      --git https://github.com/openharmony-rs/ohos-test-runner.git \
      --rev 4ad3e3e14845522a87bb4c4b4957d34323662183 \
      ohos-test-runner
  fi

  runner_env="$(cargo_target_env_var "${OHOS_RUST_TARGET}" RUNNER)"
  linker_env="$(cargo_target_env_var "${OHOS_RUST_TARGET}" LINKER)"
  linker_for_cargo="$(command_path_for_host "${ohos_linker}")"
  hdc_wrapper_dir="$(create_hdc_runner_wrapper)"
  env \
    "PATH=${hdc_wrapper_dir}:${PATH}" \
    "${runner_env}=ohos-test-runner" \
    "${linker_env}=${linker_for_cargo}" \
    RUST_LOG=debug \
    cargo test \
      --manifest-path "${ROOT}/ci/ohos-test-runner-smoke/Cargo.toml" \
      --target "${OHOS_RUST_TARGET}" \
      -- \
      --nocapture
}

collect_diagnostics() {
  mkdir -p "${DIAGNOSTICS_DIR}"
  {
    date
    uname -a || true
    printf 'host_platform=%s\n' "${HOST_PLATFORM}"
    printf 'guest_arch=%s\n' "${GUEST_ARCH}"
    printf 'require_account=%s\n' "${REQUIRE_ACCOUNT}"
    printf 'run_ohos_runner=%s\n' "${RUN_OHOS_RUNNER}"
    if read_qemu_pid >/dev/null 2>&1; then
      printf 'qemu_pid=%s\n' "${QEMU_PID}"
      if qemu_is_alive; then
        echo 'qemu_alive=true'
      else
        echo 'qemu_alive=false'
      fi
    else
      echo 'qemu_pid=unavailable'
    fi
  } >"${DIAGNOSTICS_DIR}/summary.log" 2>&1

  if [ -f "${LOG}" ]; then
    tail -n 400 "${LOG}" >"${DIAGNOSTICS_DIR}/qemu-tail.log" 2>&1 || true
  fi
  for log_file in hdc-tconn.log account-ready.log account-last.log; do
    if [ -f "${WORK}/${log_file}" ]; then
      cp "${WORK}/${log_file}" "${DIAGNOSTICS_DIR}/${log_file}" || true
    fi
  done

  if ensure_hdc >"${DIAGNOSTICS_DIR}/hdc-discovery.log" 2>&1; then
    {
      "${HDC}" list targets -v || true
      "${HDC}" -t 127.0.0.1:5555 shell '
        echo "bootevent.account.ready=$(param get bootevent.account.ready)"
        hidumper -s AccountMgr -a "-os_account_infos"
        bm dump -a | head -80
      ' || true
    } >"${DIAGNOSTICS_DIR}/guest-state.log" 2>&1
  fi

  find "${DIAGNOSTICS_DIR}" -maxdepth 1 -type f -print | sort
  return 0
}

cleanup_qemu() {
  if ! read_qemu_pid >/dev/null 2>&1; then
    return 0
  fi
  if [ "${HOST_PLATFORM}" = "windows" ] && command -v taskkill.exe >/dev/null 2>&1; then
    taskkill.exe //PID "${QEMU_PID}" //T //F >/dev/null 2>&1 || true
  elif kill -0 "${QEMU_PID}" >/dev/null 2>&1; then
    if command -v pgrep >/dev/null 2>&1; then
      while IFS= read -r child_pid; do
        kill "${child_pid}" >/dev/null 2>&1 || true
      done < <(pgrep -P "${QEMU_PID}" || true)
    fi
    kill "${QEMU_PID}" >/dev/null 2>&1 || true
    wait "${QEMU_PID}" 2>/dev/null || true
    sleep 2
    if command -v pgrep >/dev/null 2>&1; then
      while IFS= read -r child_pid; do
        kill -9 "${child_pid}" >/dev/null 2>&1 || true
      done < <(pgrep -P "${QEMU_PID}" || true)
    fi
    kill -9 "${QEMU_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${PID_FILE}"
}

run_all() {
  prepare_workspace
  start_qemu
  trap 'set +e; collect_diagnostics; cleanup_qemu' EXIT
  wait_for_hdc
  wait_for_account
  run_binary
  run_ohos_runner
}

case "${PHASE}" in
  all)
    run_all
    ;;
  prepare)
    prepare_workspace
    ;;
  start)
    start_qemu
    ;;
  wait-hdc)
    wait_for_hdc
    ;;
  wait-account)
    wait_for_account
    ;;
  run-binary)
    run_binary
    ;;
  run-ohos-runner)
    run_ohos_runner
    ;;
  diagnostics)
    collect_diagnostics
    ;;
  cleanup)
    cleanup_qemu
    ;;
esac
