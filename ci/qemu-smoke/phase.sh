#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: phase.sh PHASE" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec bash "${SCRIPT_DIR}/run.sh" \
  --package "${QEMU_SMOKE_PACKAGE:?QEMU_SMOKE_PACKAGE is required}" \
  --guest-arch "${QEMU_SMOKE_GUEST_ARCH:?QEMU_SMOKE_GUEST_ARCH is required}" \
  --host-platform "${QEMU_SMOKE_HOST_PLATFORM:?QEMU_SMOKE_HOST_PLATFORM is required}" \
  --require-account "${QEMU_SMOKE_REQUIRE_ACCOUNT:?QEMU_SMOKE_REQUIRE_ACCOUNT is required}" \
  --require-kvm "${QEMU_SMOKE_REQUIRE_KVM:-false}" \
  --run-ohos-runner "${QEMU_SMOKE_RUN_OHOS_RUNNER:?QEMU_SMOKE_RUN_OHOS_RUNNER is required}" \
  --account-wait-attempts "${QEMU_SMOKE_ACCOUNT_WAIT_ATTEMPTS:?QEMU_SMOKE_ACCOUNT_WAIT_ATTEMPTS is required}" \
  --phase "$1"
