#!/usr/bin/env bash
set -euo pipefail
ARCH=
OUTPUT=
SDK="${OHOS_SDK:-/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/native}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:?missing arch}"; shift 2 ;;
    --output) OUTPUT="${2:?missing output}"; shift 2 ;;
    *) echo "usage: build_access_token_probe.sh --arch arm64|armv7a|x86_64 --output DIR" >&2; exit 2 ;;
  esac
done
ARM_FLAGS=()
case "${ARCH}" in
  arm64) TARGET=aarch64-linux-ohos ;;
  armv7a) TARGET=arm-linux-ohos; ARM_FLAGS=(-march=armv7-a -mfloat-abi=softfp -mfpu=neon) ;;
  x86_64) TARGET=x86_64-linux-ohos ;;
  *) echo "unsupported architecture: ${ARCH}" >&2; exit 2 ;;
esac
[ -n "${OUTPUT}" ] || { echo "--output is required" >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${OUTPUT}"
for PROBE in access_token_kernel access_token_userid bpf_syscall; do
  "${SDK}/llvm/bin/clang" --target="${TARGET}" --sysroot="${SDK}/sysroot" \
    ${ARM_FLAGS[@]+"${ARM_FLAGS[@]}"} -std=gnu11 -O2 -g -Wall -Wextra -Werror -pthread \
    "${SCRIPT_DIR}/probes/${PROBE}.c" -o "${OUTPUT}/${PROBE}"
  file "${OUTPUT}/${PROBE}"
  shasum -a 256 "${OUTPUT}/${PROBE}"
done
