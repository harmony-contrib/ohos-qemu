#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
SOURCE_ROOT=
ARTIFACT_ROOT=
ARCHES=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    --artifact-root) ARTIFACT_ROOT="${2:?missing artifacts}"; shift 2 ;;
    --product)
      case "${2:-}" in
        armv7a_virt) ARCHES+=(arm) ;;
        arm64_virt) ARCHES+=(arm64) ;;
        x86_64_virt) ARCHES+=(x86_64) ;;
        *) echo "unsupported AVC QEMU product: ${2:-}" >&2; exit 2 ;;
      esac
      shift 2 ;;
    *) echo "unknown software AVC argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] && [ -n "${ARTIFACT_ROOT}" ] && [ "${#ARCHES[@]}" -gt 0 ] || {
  echo "usage: apply.sh --source-root ROOT --artifact-root ARTIFACTS --product PRODUCT" >&2; exit 2
}
# Check all requested ABI/source hashes before touching the shared source.
if [ "$(git -C "${SOURCE_ROOT}/foundation/multimedia/av_codec" rev-parse HEAD)" != \
    e5c525670d1f6622d441c9e5bf975ea0579ea177 ]; then
  echo "software AVC requires the pinned OpenHarmony 7.0 av_codec wrapper" >&2; exit 1
fi
ABI_HEADER="${SOURCE_ROOT}/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/AvcEnc_Typedef.h"
if [ "$(sha256sum "${ABI_HEADER}" | cut -d ' ' -f 1)" != \
    728c5432611d621c26f426d64835cb7542b34d32c1b0f167aa6af8754a9edcf7 ]; then
  echo "software AVC wrapper source/ABI differs from the pinned compatibility contract" >&2; exit 1
fi
python3 "${COMPONENT_DIR}/../avc_eos/verify_source.py" --source-root "${SOURCE_ROOT}" --require-patched
python3 "${PATCH_ROOT}/lib/avc_artifacts.py" --artifact-root "${ARTIFACT_ROOT}" --arch "${ARCHES[@]}"
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
DESTINATION="${SOURCE_ROOT}/foundation/multimedia/av_codec/qemu_avc"
install -D -m 0644 "${COMPONENT_DIR}/files/BUILD.gn" "${DESTINATION}/BUILD.gn"
install -D -m 0644 "${ARTIFACT_ROOT}/manifest.json" "${DESTINATION}/provenance.json"
for arch in "${ARCHES[@]}"; do
  install -D -m 0644 "${ARTIFACT_ROOT}/${arch}/libavcenc_ohos.z.so" \
    "${DESTINATION}/artifacts/${arch}/libavcenc_ohos.z.so"
done
for notice in openh264-LICENSE libc++-LICENSE.TXT libc++abi-LICENSE.TXT compiler-rt-LICENSE.TXT; do
  install -D -m 0644 "${ARTIFACT_ROOT}/licenses/${notice}" "${DESTINATION}/licenses/${notice}"
done
