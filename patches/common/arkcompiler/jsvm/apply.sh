#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE' >&2
usage: apply.sh --source-root ROOT --artifact-root DIR --profile FILE
                [--metadata FILE] [--arch arm|arm64|x86_64 ...]
                [--disable]
USAGE
}

SOURCE_ROOT=
ARTIFACT_ROOT=
PROFILE=
METADATA=
ACTION=enable
ARCHES=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --artifact-root) ARTIFACT_ROOT="${2:-}"; shift 2 ;;
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --metadata) METADATA="${2:-}"; shift 2 ;;
    --arch) ARCHES+=("${2:-}"); shift 2 ;;
    --disable) ACTION=disable; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "${SOURCE_ROOT}" ] || [ -z "${PROFILE}" ]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PROFILE_PATH="${SOURCE_ROOT}/${PROFILE}"
PROFILE_ARGS=(--profile "${PROFILE_PATH}")
if [ -n "${METADATA}" ]; then
  PROFILE_ARGS+=(--metadata "${SOURCE_ROOT}/${METADATA}")
fi

if [ "${ACTION}" = disable ]; then
  python3 "${SCRIPT_DIR}/profile.py" "${PROFILE_ARGS[@]}" disable
  echo "QEMU JSVM profile component disabled"
  exit 0
fi

if [ -z "${ARTIFACT_ROOT}" ]; then
  echo "--artifact-root is required when enabling JSVM" >&2
  exit 2
fi
if [ "${#ARCHES[@]}" -eq 0 ]; then
  ARCHES=(arm arm64 x86_64)
fi

VALIDATE_ARGS=(--artifact-root "${ARTIFACT_ROOT}")
for arch in "${ARCHES[@]}"; do
  VALIDATE_ARGS+=(--arch "${arch}")
done
python3 "${SCRIPT_DIR}/validate_artifacts.py" "${VALIDATE_ARGS[@]}"

for patch_file in \
  0001-adapt-jsvm-to-arkweb-m144.patch \
  0002-parse-gn-include-options.patch \
  0003-fix-jsvm-dfx-smart-pointers.patch \
  0004-track-source-location-shim.patch \
  0005-make-copy-v8-idempotent.patch \
  0006-adapt-jsvm-to-m144-v8-api.patch \
  0007-link-openharmony-libcxx.patch; do
  bash "${PATCH_ROOT}/lib/apply_patch.sh" \
    "${SOURCE_ROOT}" "${SCRIPT_DIR}/${patch_file}"
done

TARGET="${SOURCE_ROOT}/vendor/default/binary/artifacts/js_engine_url"
mkdir -p "${TARGET}/v8" "${TARGET}/v8-include"
install -m 0644 "${ARTIFACT_ROOT}/manifest.json" "${TARGET}/manifest.json"
rm -rf "${TARGET}/v8-include/v8-include"
cp -a "${ARTIFACT_ROOT}/v8-include/v8-include" "${TARGET}/v8-include/"
install -m 0644 "${SCRIPT_DIR}/files/source_location" \
  "${TARGET}/v8-include/v8-include/source_location"
for arch in "${ARCHES[@]}"; do
  rm -rf "${TARGET}/v8/${arch}"
  mkdir -p "${TARGET}/v8/${arch}"
  cp -a "${ARTIFACT_ROOT}/v8/${arch}/." "${TARGET}/v8/${arch}/"
done

python3 "${SCRIPT_DIR}/profile.py" "${PROFILE_ARGS[@]}" enable
echo "QEMU JSVM component configured from ${ARTIFACT_ROOT}"
