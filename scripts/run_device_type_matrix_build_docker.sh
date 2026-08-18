#!/usr/bin/env bash
# Build and package the complete phone/2in1 x armv7a/arm64/x86_64 matrix.
set -euo pipefail
export LC_ALL=C
export LANG=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_2in1_full_build_docker.sh"
VERIFY="${SCRIPT_DIR}/verify_device_type_package.sh"

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages/device-matrix-$(date -u +%Y%m%d)}"
PRODUCTS="${PRODUCTS:-arm64_virt x86_64_virt armv7a_virt}"
DEVICE_TYPES="${DEVICE_TYPES:-2in1 phone}"
MATRIX_SKIP_EXISTING="${MATRIX_SKIP_EXISTING:-1}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-1}"
DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME:-ohos-qemu-2in1-out}"
DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME:-ohos-qemu-2in1-source}"
DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH:-0}"

if [ ! -x "${RUNNER}" ] || [ ! -x "${VERIFY}" ]; then
  echo "missing executable matrix dependency under ${SCRIPT_DIR}" >&2
  exit 1
fi
case "${MATRIX_SKIP_EXISTING}" in 0|1) ;; *)
  echo "MATRIX_SKIP_EXISTING must be 0 or 1" >&2
  exit 2
esac
case "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" in 0|1) ;; *)
  echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE must be 0 or 1" >&2
  exit 2
esac

product_arch() {
  case "$1" in
    arm64_virt) echo arm64 ;;
    x86_64_virt) echo x86_64 ;;
    armv7a_virt) echo armv7a ;;
    *) echo "unsupported matrix product: $1" >&2; return 2 ;;
  esac
}

verify_package() {
  local device_type="$1"
  local package_dir="$2"
  local full_arg
  case "${device_type}" in
    2in1) full_arg=--require-full-2in1 ;;
    phone) full_arg=--require-full-phone ;;
    *) return 2 ;;
  esac
  bash "${VERIFY}" \
    --package "${package_dir}" \
    --expect-device-type "${device_type}" \
    "${full_arg}"
}

mkdir -p "${PACKAGE_ROOT}"
echo "=== QEMU device-type package matrix ==="
echo "PACKAGE_ROOT=${PACKAGE_ROOT}"
echo "DEVICE_TYPES=${DEVICE_TYPES}"
echo "PRODUCTS=${PRODUCTS}"
echo "DOCKER_SOURCE_VOLUME=${DOCKER_SOURCE_VOLUME}"
echo "DOCKER_OUT_VOLUME=${DOCKER_OUT_VOLUME}"
echo "MATRIX_SKIP_EXISTING=${MATRIX_SKIP_EXISTING}"
echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE=${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}"

refresh="${DOCKER_SOURCE_REFRESH}"
expected_packages=0
# Keep 2in1 first: it reuses an existing full arm64 cache when available.
for device_type in ${DEVICE_TYPES}; do
  case "${device_type}" in phone|2in1) ;; *)
    echo "unsupported matrix device type: ${device_type}" >&2
    exit 2
  esac
  for product in ${PRODUCTS}; do
    arch="$(product_arch "${product}")"
    package_name="openharmony-qemu-${arch}-${product}-${device_type}"
    package_dir="${PACKAGE_ROOT}/${package_name}"
    package_tar="${package_dir}.tar.gz"
    expected_packages=$((expected_packages + 1))

    if [ "${MATRIX_SKIP_EXISTING}" = "1" ] && \
       [ -d "${package_dir}" ] && [ -f "${package_tar}" ] && \
       verify_package "${device_type}" "${package_dir}" >/dev/null 2>&1; then
      echo "reuse verified matrix package: ${package_tar}"
      continue
    fi

    echo
    echo "=== build ${device_type} / ${product} ==="
    DEVICE_TYPE="${device_type}" \
    PRODUCTS="${product}" \
    PACKAGE_ROOT="${PACKAGE_ROOT}" \
    CACHE_ROOT="${CACHE_ROOT}" \
    DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME}" \
    DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME}" \
    DOCKER_SOURCE_REFRESH="${refresh}" \
    PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" \
      bash "${RUNNER}"
    refresh=0

    verify_package "${device_type}" "${package_dir}"
    if [ ! -f "${package_tar}" ]; then
      echo "matrix build did not create archive: ${package_tar}" >&2
      exit 1
    fi
  done
done

actual_packages="$(find "${PACKAGE_ROOT}" -maxdepth 1 -type f \
  \( -name 'openharmony-qemu-*-phone.tar.gz' -o \
  -name 'openharmony-qemu-*-2in1.tar.gz' \) | wc -l | tr -d ' ')"
if [ "${actual_packages}" -ne "${expected_packages}" ]; then
  echo "expected ${expected_packages} matrix archives, found ${actual_packages}" >&2
  exit 1
fi

(
  cd "${PACKAGE_ROOT}"
  env LC_ALL=C LANG=C shasum -a 256 openharmony-qemu-*-phone.tar.gz \
    openharmony-qemu-*-2in1.tar.gz > SHA256SUMS
)

python3 - "${PACKAGE_ROOT}" > "${PACKAGE_ROOT}/matrix-manifest.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
packages = []
for archive in sorted(root.glob("openharmony-qemu-*.tar.gz")):
    package_dir = root / archive.name.removesuffix(".tar.gz")
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        continue
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    packages.append({
        "archive": archive.name,
        "sha256": digest,
        "size_bytes": archive.stat().st_size,
        "product": manifest["product"],
        "guest_arch": manifest["guest_arch"],
        "device_type": manifest["device_type"],
        "device_type_profile": manifest["device_type_profile"],
        "absolute_pointer_sync": manifest.get("capabilities", {}).get(
            "absolute_pointer_sync", False
        ),
        "pointer_device_default": manifest.get("launcher", {}).get(
            "pointer_device_default", ""
        ),
    })
document = {
    "schema_version": 1,
    "expected_package_count": len(packages),
    "packages": packages,
}
print(json.dumps(document, indent=2, ensure_ascii=False))
PY

echo
echo "matrix complete: ${expected_packages} verified packages"
find "${PACKAGE_ROOT}" -maxdepth 1 -type f -name 'openharmony-qemu-*.tar.gz' -print | sort
echo "checksums: ${PACKAGE_ROOT}/SHA256SUMS"
echo "manifest:  ${PACKAGE_ROOT}/matrix-manifest.json"
