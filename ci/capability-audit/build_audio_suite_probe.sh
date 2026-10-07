#!/usr/bin/env bash
set -euo pipefail
# Use the pinned API 26 native SDK; older DevEco installations omit AudioSuite.
ARCH="${1:?Usage: build_audio_suite_probe.sh arm64|armv7a|x86_64 OUTPUT}"
OUTPUT="${2:?missing OUTPUT}"
SDK="${OHOS_SDK:?set OHOS_SDK to the API 26 native SDK}"
ARM_FLAGS=()
case "${ARCH}" in
  arm64) TARGET=aarch64-linux-ohos ;;
  armv7a) TARGET=arm-linux-ohos; ARM_FLAGS=(-march=armv7-a -mfloat-abi=softfp -mfpu=neon) ;;
  x86_64) TARGET=x86_64-linux-ohos ;;
  *) echo "unsupported probe architecture: ${ARCH}" >&2; exit 2 ;;
esac
[ -f "${SDK}/sysroot/usr/include/ohaudiosuite/native_audio_suite_engine.h" ] || {
  echo "API 26 AudioSuite header missing from ${SDK}" >&2; exit 1;
}
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${OUTPUT}"
"${SDK}/llvm/bin/clang++" --target="${TARGET}" --sysroot="${SDK}/sysroot" \
  ${ARM_FLAGS[@]+"${ARM_FLAGS[@]}"} -std=c++17 -O2 -g -Wall -Wextra -Werror \
  -fno-exceptions -fno-rtti -nostdlib++ "${ROOT}/probes/audio_suite.cpp" \
  -ldl -o "${OUTPUT}/audio_suite"
file "${OUTPUT}/audio_suite"
