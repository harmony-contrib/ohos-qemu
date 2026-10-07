#!/usr/bin/env bash
set -euo pipefail
ARCH=
OUTPUT=
SDK="${OHOS_SDK:-/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/native}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:?missing arch}"; shift 2 ;;
    --output) OUTPUT="${2:?missing output}"; shift 2 ;;
    *) echo "Usage: build_graphics_probes.sh --arch arm64|armv7a|x86_64 --output DIR" >&2; exit 2 ;;
  esac
done
ARM_FLAGS=()
case "${ARCH}" in
  arm64) TARGET=aarch64-linux-ohos ;;
  armv7a) TARGET=arm-linux-ohos; ARM_FLAGS=(-march=armv7-a -mfloat-abi=softfp -mfpu=neon) ;;
  x86_64) TARGET=x86_64-linux-ohos ;;
  *) echo "unsupported graphics probe architecture: ${ARCH}" >&2; exit 2 ;;
esac
[ -n "${OUTPUT}" ] || { echo "--output is required" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${OUTPUT}"
for name in vulkan_device_probe vulkan_headless_probe vulkan_extension_probe; do
  "${SDK}/llvm/bin/clang" --target="${TARGET}" --sysroot="${SDK}/sysroot" \
    ${ARM_FLAGS[@]+"${ARM_FLAGS[@]}"} -O2 -g -Wall -Wextra -Werror \
    "${ROOT}/${name}.c" -L"${SDK}/sysroot/usr/lib/${TARGET}" -lvulkan -o "${OUTPUT}/${name}"
done
"${SDK}/llvm/bin/clang" --target="${TARGET}" --sysroot="${SDK}/sysroot" \
  ${ARM_FLAGS[@]+"${ARM_FLAGS[@]}"} -O2 -g -Wall -Wextra -Werror \
  "${ROOT}/vulkan_ohos_surface_probe.c" -L"${SDK}/sysroot/usr/lib/${TARGET}" \
  -lvulkan -lnative_image -lnative_window -lnative_buffer -o "${OUTPUT}/vulkan_ohos_surface_probe"
"${SDK}/llvm/bin/clang" --target="${TARGET}" --sysroot="${SDK}/sysroot" \
  ${ARM_FLAGS[@]+"${ARM_FLAGS[@]}"} -O2 -g -Wall -Wextra -Werror \
  "${ROOT}/egl_extension_probe.c" -ldl -o "${OUTPUT}/egl_extension_probe"
file "${OUTPUT}"/vulkan_* "${OUTPUT}/egl_extension_probe"
