#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
OHOS_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing source root}"; shift 2 ;;
    --ohos-root) OHOS_ROOT="${2:?missing OHOS root}"; shift 2 ;;
    *) echo "unknown M144 AVC argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] && [ -n "${OHOS_ROOT}" ] || {
  echo "usage: apply.sh --source-root M144_ROOT --ohos-root FIXED_OHOS_ROOT" >&2
  exit 2
}
ABI_HEADER="${OHOS_ROOT}/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/AvcEnc_Typedef.h"
[ "$(git -C "${OHOS_ROOT}/foundation/multimedia/av_codec" rev-parse HEAD)" = e5c525670d1f6622d441c9e5bf975ea0579ea177 ] || {
  echo "AVCodec checkout does not match fixed 7.0 source" >&2; exit 1
}
[ "$(sha256sum "${ABI_HEADER}" | cut -d ' ' -f 1)" = 728c5432611d621c26f426d64835cb7542b34d32c1b0f167aa6af8754a9edcf7 ] || {
  echo "AVC wrapper ABI header differs from fixed 7.0 source" >&2; exit 1
}
[ "$(git -C "${SOURCE_ROOT}/src" rev-parse HEAD)" = a8168622b056f25c2e68d5f12fe2759bad2d9a44 ] &&
[ "$(git -C "${SOURCE_ROOT}/src/third_party/openh264/src" rev-parse HEAD)" = 652bdb7719f30b52b08e506645a7322ff1b2cc6f ] || {
  echo "M144/OpenH264 checkout does not match pinned source" >&2; exit 1
}
git -C "${SOURCE_ROOT}/src/third_party/openh264/src" diff --quiet HEAD -- || {
  echo "OpenH264 sources are dirty; preserve them and refuse an unrecorded backend" >&2; exit 1
}
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
DESTINATION="${SOURCE_ROOT}/src/ohos/qemu_avc"
mkdir -p "${DESTINATION}"
for file in BUILD.gn qemu_avc_encoder.cc avcenc.map; do
  install -m 0644 "${COMPONENT_DIR}/files/${file}" "${DESTINATION}/${file}"
done
install -m 0644 "${ABI_HEADER}" "${DESTINATION}/AvcEnc_Typedef.h"
echo "Prepared real OpenH264 AVC adapter; compile and newly packaged runtime validation still required"
