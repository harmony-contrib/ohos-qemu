#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"
PHASE_SCRIPT="${SCRIPT_DIR}/phase.sh"
PACKAGE_SCRIPT="${SCRIPT_DIR}/../../scripts/package_standard_qemu.sh"
TEST_ROOT="$(mktemp -d)"
FAKE_BIN="${TEST_ROOT}/bin"
WORK="${TEST_ROOT}/ohos-qemu-smoke-linux-x86_64"
QEMU_PID=

cleanup() {
  if [ -n "${QEMU_PID}" ]; then
    kill "${QEMU_PID}" >/dev/null 2>&1 || true
    wait "${QEMU_PID}" 2>/dev/null || true
  fi
  rm -rf "${TEST_ROOT}"
}
trap cleanup EXIT

bash -n "${RUN_SCRIPT}" "${PHASE_SCRIPT}" "${PACKAGE_SCRIPT}"

mkdir -p "${FAKE_BIN}" "${WORK}"
cat >"${FAKE_BIN}/hdc" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "${FAKE_BIN}/hdc"

FAKE_SDK="${TEST_ROOT}/ohos-sdk"
FAKE_PACKAGE_ROOT="${TEST_ROOT}/armv7a-package/openharmony-qemu-armv7a-armv7a_virt"
FAKE_PACKAGE="${TEST_ROOT}/armv7a-package.tar.gz"
RUSTC_ARGS="${TEST_ROOT}/armv7a-rustc-args.txt"
mkdir -p "${FAKE_SDK}/native/llvm/bin" "${FAKE_PACKAGE_ROOT}/launch"
: >"${FAKE_SDK}/native/llvm/bin/armv7-unknown-linux-ohos-clang"
: >"${FAKE_PACKAGE_ROOT}/launch/macos.command"
LC_ALL=C tar -czf "${FAKE_PACKAGE}" -C "${TEST_ROOT}/armv7a-package" .

cat >"${FAKE_BIN}/rustup" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat >"${FAKE_BIN}/rustc" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "\$@" >"${RUSTC_ARGS}"
while [ "\$#" -gt 0 ]; do
  if [ "\$1" = "-o" ]; then
    : >"\$2"
    exit 0
  fi
  shift
done
exit 1
EOF
chmod +x "${FAKE_BIN}/rustup" "${FAKE_BIN}/rustc"

RUNNER_TEMP="${TEST_ROOT}" \
OHOS_NDK_HOME="${FAKE_SDK}" \
PATH="${FAKE_BIN}:${PATH}" \
  bash "${RUN_SCRIPT}" \
    --package "${FAKE_PACKAGE}" \
    --guest-arch armv7a \
    --host-platform macos \
    --require-account false \
    --require-kvm false \
    --run-ohos-runner false \
    --phase prepare \
    >/dev/null

grep -Fxq 'armv7-unknown-linux-ohos' "${RUSTC_ARGS}"
grep -Fq "linker=${FAKE_SDK}/native/llvm/bin/armv7-unknown-linux-ohos-clang" "${RUSTC_ARGS}"
if grep -Eq 'musleabi|target-feature=\+crt-static' "${RUSTC_ARGS}"; then
  echo "armv7a prepare used a generic Linux/musl target" >&2
  exit 1
fi

FAKE_SOURCE="${TEST_ROOT}/package-source"
FAKE_OUTPUT="${TEST_ROOT}/package-output"
FAKE_IMAGES="${FAKE_SOURCE}/out/arm64_virt/packages/phone/images"
FAKE_VENDOR="${FAKE_SOURCE}/vendor/ohemu/qemu_arm64_linux_full"
FAKE_QEMU_ARGS="${TEST_ROOT}/qemu-args.txt"
FAKE_QEMU_PROBES="${TEST_ROOT}/qemu-probes.txt"
mkdir -p "${FAKE_IMAGES}" "${FAKE_VENDOR}" "${FAKE_OUTPUT}"
for image in Image ramdisk.img system.img vendor.img userdata.img updater.img \
  sys_prod.img chip_prod.img; do
  : >"${FAKE_IMAGES}/${image}"
done
cat >"${FAKE_VENDOR}/qemu_run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
OHOS_IMG="out/arm64_virt/packages/phone/images"
DISPLAY_TYPE="${QEMU_DISPLAY:-none}"
# Check hardware acceleration availability
ACCEL_SUPPORT=$(qemu-system-aarch64 -accel help 2>&1 | grep "Accelerators supported" || true)
if [ "$(uname)" = "Darwin" ] && echo "${ACCEL_SUPPORT}" | grep -qw hvf; then
  ACCEL_ARGS="-accel hvf"
else
  ACCEL_ARGS="-accel tcg"
fi
NET_ARGS=(
  -netdev user,id=net0,hostfwd=tcp::5555-:5555
)
qemu-system-aarch64 ${ACCEL_ARGS} \
  "${NET_ARGS[@]}" \
  -append "init=/init ohos.required_mount.system=/dev/block/vde@/system@ext4"
EOF
cat >"${FAKE_BIN}/debugfs" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "${FAKE_BIN}/debugfs"

PATH="${FAKE_BIN}:${PATH}" \
SEED_USERDATA_DIRS=0 \
INJECT_QEMU_RUNTIME_PARAMS=0 \
  bash "${PACKAGE_SCRIPT}" \
    --source-root "${FAKE_SOURCE}" \
    --product arm64_virt \
    --output-dir "${FAKE_OUTPUT}" \
    >/dev/null

PACKAGED_LAUNCHER="${FAKE_OUTPUT}/openharmony-qemu-arm64-arm64_virt/launch/qemu_run.sh"
grep -Fq 'ACCEL_SUPPORT=$(qemu-system-aarch64 -accel help 2>&1 || true)' \
  "${PACKAGED_LAUNCHER}"
if grep -Fq '| grep "Accelerators supported"' "${PACKAGED_LAUNCHER}"; then
  echo "packaged launcher still filters out multiline accelerator names" >&2
  exit 1
fi
grep -Fq 'HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"' "${PACKAGED_LAUNCHER}"
grep -Fq 'hostfwd=tcp::${HDC_HOST_PORT}-:5555' "${PACKAGED_LAUNCHER}"

cat >"${FAKE_BIN}/uname" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' Darwin
EOF
cat >"${FAKE_BIN}/qemu-system-aarch64" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [ "\${1:-}" = "-accel" ] && [ "\${2:-}" = "help" ]; then
  printf '%b\n' "\${FAKE_QEMU_ACCELS}"
  exit 0
fi
if printf '%s\n' "\$*" | grep -Fq -- '-S -display none -nodefaults'; then
  printf '%s\n' "\$*" >>"${FAKE_QEMU_PROBES}"
  if [ "\${FAKE_HVF_PROBE:-usable}" = "fail" ]; then
    exit 1
  fi
  exec sleep 60
fi
printf '%s\n' "\$*" >"${FAKE_QEMU_ARGS}"
EOF
chmod +x "${FAKE_BIN}/uname" "${FAKE_BIN}/qemu-system-aarch64"

for accel_output in \
  'Accelerators supported in QEMU binary:\nhvf\ntcg' \
  'Accelerators supported: hvf tcg'; do
  : >"${FAKE_QEMU_ARGS}"
  : >"${FAKE_QEMU_PROBES}"
  PATH="${FAKE_BIN}:${PATH}" \
  FAKE_QEMU_ACCELS="${accel_output}" \
  FAKE_HVF_PROBE=usable \
  QEMU_ACCEL_PROBE_SECONDS=0.1 \
  QEMU_DISPLAY=none \
    bash "${PACKAGED_LAUNCHER}" >/dev/null 2>&1
  grep -Fq -- '-accel hvf' "${FAKE_QEMU_ARGS}"
  grep -Fq -- '-accel hvf -M virt -cpu cortex-a57' "${FAKE_QEMU_PROBES}"
done

: >"${FAKE_QEMU_ARGS}"
PATH="${FAKE_BIN}:${PATH}" \
FAKE_QEMU_ACCELS='Accelerators supported in QEMU binary:\nhvf\ntcg' \
FAKE_HVF_PROBE=fail \
QEMU_ACCEL_PROBE_SECONDS=0.1 \
QEMU_DISPLAY=none \
  bash "${PACKAGED_LAUNCHER}" >/dev/null 2>&1
grep -Fq -- '-accel tcg' "${FAKE_QEMU_ARGS}"

: >"${FAKE_QEMU_ARGS}"
: >"${FAKE_QEMU_PROBES}"
PATH="${FAKE_BIN}:${PATH}" \
FAKE_QEMU_ACCELS='Accelerators supported in QEMU binary:\nhvf\ntcg' \
QEMU_ACCEL=tcg \
QEMU_DISPLAY=none \
  bash "${PACKAGED_LAUNCHER}" >/dev/null 2>&1
grep -Fq -- '-accel tcg' "${FAKE_QEMU_ARGS}"
if [ -s "${FAKE_QEMU_PROBES}" ]; then
  echo "explicit TCG unexpectedly probed HVF" >&2
  exit 1
fi

sleep 60 &
QEMU_PID=$!
printf '%s\n' "${QEMU_PID}" >"${WORK}/qemu.pid"
printf '%s\n' '[  288.593436] Kernel panic - not syncing: sysrq triggered crash' >"${WORK}/qemu.log"

set +e
panic_output="$(
  RUNNER_TEMP="${TEST_ROOT}" PATH="${FAKE_BIN}:${PATH}" \
    bash "${RUN_SCRIPT}" \
      --package unused.tar.gz \
      --guest-arch x86_64 \
      --host-platform linux \
      --require-account true \
      --require-kvm false \
      --run-ohos-runner false \
      --phase wait-account 2>&1
)"
panic_status=$?
set -e

if [ "${panic_status}" -eq 0 ]; then
  echo "wait-account unexpectedly accepted a panicked guest" >&2
  exit 1
fi
printf '%s\n' "${panic_output}" | grep -q 'OpenHarmony guest failed before waiting for AccountMgr'

printf '%s\n' \
  '[   47.730892] Child process composer_host(pid 407) exit with signal : 11' \
  >"${WORK}/qemu.log"
set +e
composer_output="$(
  RUNNER_TEMP="${TEST_ROOT}" PATH="${FAKE_BIN}:${PATH}" \
    bash "${RUN_SCRIPT}" \
      --package unused.tar.gz \
      --guest-arch x86_64 \
      --host-platform linux \
      --require-account true \
      --require-kvm false \
      --run-ohos-runner false \
      --phase wait-account 2>&1
)"
composer_status=$?
set -e

if [ "${composer_status}" -eq 0 ]; then
  echo "wait-account unexpectedly accepted a crashed composer_host" >&2
  exit 1
fi
printf '%s\n' "${composer_output}" | grep -q 'OpenHarmony guest failed before waiting for AccountMgr'

HDC_ARGS="${TEST_ROOT}/hdc-args.txt"
HDC_STATE="${TEST_ROOT}/hdc-state.txt"
cat >"${FAKE_BIN}/hdc" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${FAKE_HDC_ARGS}"
case "${1:-}" in
  tconn)
    count="$(cat "${FAKE_HDC_STATE}")"
    printf '%s\n' "$((count + 1))" >"${FAKE_HDC_STATE}"
    ;;
  list)
    if [ "$(cat "${FAKE_HDC_STATE}")" -ge 2 ]; then
      printf '%s\n' "${FAKE_HDC_TARGET} TCP Connected localhost"
    else
      printf '%s\n' "${FAKE_HDC_TARGET} TCP Offline localhost"
    fi
    ;;
  -t)
    if [ "$(cat "${FAKE_HDC_STATE}")" -lt 2 ]; then
      echo '[Fail][E001005] Device not found or connected' >&2
      exit 1
    fi
    cat <<'ACCOUNT'
bootevent.account.ready=true
ID: 100
isForeground: 1
ACCOUNT
    ;;
esac
EOF
chmod +x "${FAKE_BIN}/hdc"
: >"${WORK}/qemu.log"
: >"${HDC_ARGS}"
printf '%s\n' 0 >"${HDC_STATE}"

account_output="$(
  RUNNER_TEMP="${TEST_ROOT}" \
  QEMU_SMOKE_HDC_HOST_PORT=6554 \
  FAKE_HDC_ARGS="${HDC_ARGS}" \
  FAKE_HDC_STATE="${HDC_STATE}" \
  FAKE_HDC_TARGET=127.0.0.1:6554 \
  PATH="${FAKE_BIN}:${PATH}" \
    bash "${RUN_SCRIPT}" \
      --package unused.tar.gz \
      --guest-arch x86_64 \
      --host-platform linux \
      --require-account true \
      --require-kvm false \
      --run-ohos-runner false \
      --account-wait-attempts 3 \
      --phase wait-account
)"
printf '%s\n' "${account_output}" | grep -q 'AccountMgr user 100 is foreground at attempt 2'
grep -q 'attempt=1/3 transport=0' "${WORK}/account-ready.log"
grep -q 'attempt=2/3 transport=1' "${WORK}/account-ready.log"
[ "$(grep -c '^tconn 127.0.0.1:6554$' "${HDC_ARGS}")" -ge 2 ]

cat >"${FAKE_BIN}/hdc" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${FAKE_HDC_ARGS}"
case "${1:-}" in
  tconn)
    exit 0
    ;;
  list)
    printf '%s\n' "${FAKE_HDC_TARGET} TCP Connected localhost"
    ;;
  -t)
    printf '%s\n' '300.25 120.00'
    ;;
esac
EOF
chmod +x "${FAKE_BIN}/hdc"
: >"${HDC_ARGS}"

RUNNER_TEMP="${TEST_ROOT}" QEMU_SMOKE_HDC_HOST_PORT=6554 \
  FAKE_HDC_ARGS="${HDC_ARGS}" \
  FAKE_HDC_TARGET=127.0.0.1:6554 \
  PATH="${FAKE_BIN}:${PATH}" \
  bash "${RUN_SCRIPT}" \
    --package unused.tar.gz \
    --guest-arch x86_64 \
    --host-platform linux \
    --require-account true \
    --require-kvm false \
    --run-ohos-runner false \
    --minimum-guest-uptime 270 \
    --phase wait-stable \
    | grep -q 'Guest remained healthy through uptime 300s'

grep -Fq -- '-t 127.0.0.1:6554 shell cat /proc/uptime' "${HDC_ARGS}"
if grep -Fxq 'kill' "${HDC_ARGS}"; then
  echo "smoke test restarted the shared HDC server" >&2
  exit 1
fi

set +e
kvm_output="$(
  QEMU_SMOKE_PACKAGE=unused.tar.gz \
  QEMU_SMOKE_GUEST_ARCH=aarch64 \
  QEMU_SMOKE_HOST_PLATFORM=macos \
  QEMU_SMOKE_REQUIRE_ACCOUNT=true \
  QEMU_SMOKE_REQUIRE_KVM=true \
  QEMU_SMOKE_RUN_OHOS_RUNNER=false \
  QEMU_SMOKE_ACCOUNT_WAIT_ATTEMPTS=1 \
    bash "${PHASE_SCRIPT}" cleanup 2>&1
)"
kvm_status=$?
set -e

if [ "${kvm_status}" -ne 2 ]; then
  echo "invalid require-kvm combination returned ${kvm_status}, expected 2" >&2
  exit 1
fi
printf '%s\n' "${kvm_output}" | grep -q -- '--require-kvm is only supported'

echo "qemu smoke script tests passed"
