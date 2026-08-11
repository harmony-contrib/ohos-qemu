#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PREFIX="${OHOS_QEMU_PREFIX:-${HOME}/.ohos-qemu}"

find_signer() {
  if [ -n "${OHOS_HAP_SIGNER:-}" ]; then
    printf '%s\n' "${OHOS_HAP_SIGNER}"
    return
  fi
  for candidate in \
    "${PACKAGE_ROOT}/bin/hap-sign" \
    "${PACKAGE_ROOT}/bin/hap-sign.exe" \
    "${PREFIX}/bin/hap-sign" \
    "${PREFIX}/bin/hap-sign.exe"
  do
    if [ -x "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
  if command -v hap-sign >/dev/null 2>&1; then
    command -v hap-sign
    return
  fi
  if command -v hap-sign.exe >/dev/null 2>&1; then
    command -v hap-sign.exe
    return
  fi
  return 1
}

if ! signer="$(find_signer)"; then
  echo "hap-sign is not installed" >&2
  echo "run ${SCRIPT_DIR}/install-hap-signer.sh first" >&2
  exit 1
fi

exec "${signer}" sign "$@"
