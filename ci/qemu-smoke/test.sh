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
