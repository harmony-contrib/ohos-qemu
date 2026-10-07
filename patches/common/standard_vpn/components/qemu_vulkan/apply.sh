#!/usr/bin/env bash
set -euo pipefail

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
ARTIFACT_ROOT=
PRODUCTS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --artifact-root) ARTIFACT_ROOT="${2:-}"; shift 2 ;;
    --product) PRODUCTS+=("${2:-}"); shift 2 ;;
    *) echo "unknown QEMU Vulkan argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
[ -n "${ARTIFACT_ROOT}" ] || { echo "--artifact-root is required" >&2; exit 2; }
[ "${#PRODUCTS[@]}" -gt 0 ] || { echo "at least one --product is required" >&2; exit 2; }

# Validate the exact architecture before touching the source checkout.
arches=()
for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt) arches+=(arm) ;;
    arm64_virt) arches+=(arm64) ;;
    x86_64_virt) arches+=(x86_64) ;;
    *) echo "unsupported QEMU Vulkan product: ${product}" >&2; exit 2 ;;
  esac
done
python3 "${PATCH_ROOT}/../scripts/verify_m144_swiftshader_artifacts.py" \
  --artifact-root "${ARTIFACT_ROOT}" --arch "${arches[@]}"
for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt) arch=arm ;;
    arm64_virt) arch=arm64 ;;
    x86_64_virt) arch=x86_64 ;;
    *) echo "unsupported QEMU Vulkan product: ${product}" >&2; exit 2 ;;
  esac
  binary="${ARTIFACT_ROOT}/${arch}/libvk_swiftshader.so"
  [ -s "${binary}" ] || { echo "missing SwiftShader ICD: ${binary}" >&2; exit 1; }
  python3 - "${binary}" "${arch}" <<'PY'
import struct
import sys
from pathlib import Path

path, arch = Path(sys.argv[1]), sys.argv[2]
with path.open("rb") as source:
    header = source.read(20)
expected_class, expected_machine = {
    "arm": (1, 40),
    "arm64": (2, 183),
    "x86_64": (2, 62),
}[arch]
if (len(header) != 20 or header[:4] != b"\x7fELF"
        or header[4] != expected_class or header[5] != 1
        or struct.unpack_from("<H", header, 18)[0] != expected_machine):
    raise SystemExit(f"SwiftShader ELF architecture mismatch: {path} ({arch})")
PY
  readelf -d "${binary}" | grep -q NODELETE || {
    echo "SwiftShader ICD must be linked with -z nodelete: ${binary}" >&2
    exit 1
  }
  for symbol in vk_icdGetInstanceProcAddr vk_icdNegotiateLoaderICDInterfaceVersion; do
    readelf -Ws "${binary}" | grep " ${symbol}$" >/dev/null || {
      echo "SwiftShader ICD is missing ${symbol}: ${binary}" >&2
      exit 1
    }
  done
done

bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" \
  --source-root "${SOURCE_ROOT}"
target="${SOURCE_ROOT}/device/qemu/common/virt_full/hardware/vulkan"
install -D -m 0644 "${COMPONENT_DIR}/files/BUILD.gn" "${target}/BUILD.gn"
for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt) arch=arm ;;
    arm64_virt) arch=arm64 ;;
    x86_64_virt) arch=x86_64 ;;
  esac
  install -D -m 0644 "${ARTIFACT_ROOT}/${arch}/libvk_swiftshader.so" \
    "${target}/artifacts/${arch}/libvk_swiftshader.so"
  install -D -m 0644 "${COMPONENT_DIR}/files/${arch}/swiftshader.json" \
    "${target}/etc/vulkan/icd.d/${arch}/swiftshader.json"
  echo "installed ${arch} SwiftShader ICD: $(sha256sum "${ARTIFACT_ROOT}/${arch}/libvk_swiftshader.so")"
done
