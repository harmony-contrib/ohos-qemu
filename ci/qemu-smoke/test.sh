#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"
PHASE_SCRIPT="${SCRIPT_DIR}/phase.sh"
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

bash -n "${RUN_SCRIPT}" "${PHASE_SCRIPT}"

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
cat >"${FAKE_BIN}/hdc" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"${HDC_ARGS}"
printf '%s\n' '300.25 120.00'
EOF
chmod +x "${FAKE_BIN}/hdc"
: >"${WORK}/qemu.log"
: >"${HDC_ARGS}"

RUNNER_TEMP="${TEST_ROOT}" QEMU_SMOKE_HDC_HOST_PORT=6554 \
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
