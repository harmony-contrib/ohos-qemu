#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: build_native_probes.sh --arch arm64|armv7a|x86_64 --output DIR" >&2
}

ARCH=
OUTPUT=
SDK="${OHOS_SDK:-/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/native}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:?missing arch}"; shift 2 ;;
    --output) OUTPUT="${2:?missing output}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

case "${ARCH}" in
  arm64) TARGET=aarch64-linux-ohos; LIBDIR=aarch64-linux-ohos ;;
  armv7a) TARGET=arm-linux-ohos; LIBDIR=arm-linux-ohos ;;
  x86_64) TARGET=x86_64-linux-ohos; LIBDIR=x86_64-linux-ohos ;;
  *) usage; exit 2 ;;
esac
[ -n "${OUTPUT}" ] || { usage; exit 2; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${OUTPUT}"
build_family() {
  local family="$1"
  local library="$2"
  local macro
  macro="$(printf '%s' "${family}" | tr '[:lower:]' '[:upper:]')"
  "${SDK}/llvm/bin/clang" \
    --target="${TARGET}" \
    --sysroot="${SDK}/sysroot" \
    -O2 -g -Wall -Wextra -Werror -Wno-unused-function -ffunction-sections \
    -D"PROBE_${macro}" \
    "${ROOT}/probes/hardware_services.c" \
    -L"${SDK}/sysroot/usr/lib/${LIBDIR}" \
    -Wl,--gc-sections -Wl,--as-needed \
    "-l${library}" \
    -o "${OUTPUT}/hardware_${family}"
}

build_family battery ohbattery_info
build_family bluetooth bluetooth_ndk
build_family wifi wifi_ndk
build_family location location_ndk
build_family network net_connection
build_family audio ohaudio
build_family audio_stream ohaudio
build_family camera ohcamera
build_family sensor ohsensor
build_family vibrator ohvibrator.z
build_family telephony telephony_radio
build_family display native_display_manager
build_family image_effect image_effect

"${SDK}/llvm/bin/clang" \
  --target="${TARGET}" --sysroot="${SDK}/sysroot" \
  -O2 -g -Wall -Wextra -Werror \
  "${ROOT}/probes/huks.c" \
  -L"${SDK}/sysroot/usr/lib/${LIBDIR}" -lhuks_ndk.z \
  -o "${OUTPUT}/huks"

"${SDK}/llvm/bin/clang" \
  --target="${TARGET}" --sysroot="${SDK}/sysroot" \
  -O2 -g -Wall -Wextra -Werror \
  "${ROOT}/probes/egl_gles.c" \
  -L"${SDK}/sysroot/usr/lib/${LIBDIR}" -lEGL -lGLESv3 \
  -o "${OUTPUT}/egl_gles"

file "${OUTPUT}"/hardware_* "${OUTPUT}/huks" "${OUTPUT}/egl_gles"
