#!/usr/bin/env bash
# Build and package the complete phone/2in1 x armv7a/arm64/x86_64 matrix.
set -euo pipefail
export LC_ALL=C
export LANG=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_2in1_full_build_docker.sh"
VERIFY="${SCRIPT_DIR}/verify_device_type_package.sh"
LFS_ASSET_MAP="${SCRIPT_DIR}/../patches/common/build/github_lfs_assets/assets.tsv"

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages/device-matrix-7.0-release-$(date -u +%Y%m%d)}"
PRODUCTS="${PRODUCTS:-arm64_virt x86_64_virt armv7a_virt}"
DEVICE_TYPES="${DEVICE_TYPES:-2in1 phone}"
OHOS_BRANCH="${OHOS_BRANCH:-OpenHarmony-7.0-Release}"
MANIFEST_REVISION="${MANIFEST_REVISION:-f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549}"
OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR-https://github.com/openharmony/}"
OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK:-1}"
OHOS_GITHUB_NO_PROXY="${OHOS_GITHUB_NO_PROXY:-github.com,.github.com,githubusercontent.com,.githubusercontent.com}"
REPO_JOBS="${REPO_JOBS:-16}"
REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS:-4}"
FALLBACK_JOBS="${FALLBACK_JOBS:-10}"
FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT:-${CACHE_ROOT}/git-mirrors/openharmony-7.0-release}"
OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT:-${CACHE_ROOT}/artifacts/openharmony-7.0-lfs}"
LFS_JOBS="${LFS_JOBS:-10}"
CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-4G}"
MATRIX_SKIP_EXISTING="${MATRIX_SKIP_EXISTING:-1}"
MATRIX_PREPARE_SOURCE="${MATRIX_PREPARE_SOURCE:-1}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-1}"
DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME:-ohos-qemu-7_0-release-out}"
DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source}"
DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH:-0}"

if [ ! -x "${RUNNER}" ] || [ ! -x "${VERIFY}" ]; then
  echo "missing executable matrix dependency under ${SCRIPT_DIR}" >&2
  exit 1
fi
case "${MATRIX_SKIP_EXISTING}" in 0|1) ;; *)
  echo "MATRIX_SKIP_EXISTING must be 0 or 1" >&2
  exit 2
esac
case "${MATRIX_PREPARE_SOURCE}" in 0|1) ;; *)
  echo "MATRIX_PREPARE_SOURCE must be 0 or 1" >&2
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
    --expect-manifest-revision "${MANIFEST_REVISION}" \
    "${full_arg}"
}

mkdir -p "${PACKAGE_ROOT}"
echo "=== QEMU device-type package matrix ==="
echo "PACKAGE_ROOT=${PACKAGE_ROOT}"
echo "DEVICE_TYPES=${DEVICE_TYPES}"
echo "PRODUCTS=${PRODUCTS}"
echo "MANIFEST=${OHOS_BRANCH} @ ${MANIFEST_REVISION}"
echo "OHOS_PROJECT_MIRROR=${OHOS_PROJECT_MIRROR}"
echo "OHOS_GITHUB_FALLBACK=${OHOS_GITHUB_FALLBACK}"
echo "REPO_JOBS=${REPO_JOBS} REPO_CHECKOUT_JOBS=${REPO_CHECKOUT_JOBS}"
echo "FALLBACK_MIRROR_ROOT=${FALLBACK_MIRROR_ROOT} FALLBACK_JOBS=${FALLBACK_JOBS}"
echo "OHOS_LFS_ASSET_ROOT=${OHOS_LFS_ASSET_ROOT} LFS_JOBS=${LFS_JOBS}"
echo "CCACHE_MAXSIZE=${CCACHE_MAXSIZE}"
echo "DOCKER_SOURCE_VOLUME=${DOCKER_SOURCE_VOLUME}"
echo "DOCKER_OUT_VOLUME=${DOCKER_OUT_VOLUME}"
echo "MATRIX_SKIP_EXISTING=${MATRIX_SKIP_EXISTING}"
echo "MATRIX_PREPARE_SOURCE=${MATRIX_PREPARE_SOURCE}"
echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE=${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}"

refresh="${DOCKER_SOURCE_REFRESH}"
expected_packages=0
device_type_count=0
prepare_device_type=
for device_type in ${DEVICE_TYPES}; do
  case "${device_type}" in phone|2in1) ;; *)
    echo "unsupported matrix device type: ${device_type}" >&2
    exit 2
  esac
  if [ -z "${prepare_device_type}" ]; then
    prepare_device_type="${device_type}"
  fi
  device_type_count=$((device_type_count + 1))
done
if [ "${device_type_count}" -eq 0 ]; then
  echo "DEVICE_TYPES must contain phone and/or 2in1" >&2
  exit 2
fi

# Establish one clean, pinned source baseline and apply the complete product
# patch set before any architecture/device-type traversal begins. Individual
# builds still switch their selected profile, but never discover a missing
# optional product halfway through a multi-hour matrix.
if [ "${MATRIX_PREPARE_SOURCE}" = "1" ]; then
  echo
  echo "=== prepare pinned OpenHarmony source and patch all matrix products ==="
  DEVICE_TYPE="${prepare_device_type}" \
  PRODUCTS="${PRODUCTS}" \
  PACKAGE_ROOT="${PACKAGE_ROOT}" \
  CACHE_ROOT="${CACHE_ROOT}" \
  OHOS_BRANCH="${OHOS_BRANCH}" \
  MANIFEST_REVISION="${MANIFEST_REVISION}" \
  OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR}" \
  OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK}" \
  OHOS_GITHUB_NO_PROXY="${OHOS_GITHUB_NO_PROXY}" \
  REPO_JOBS="${REPO_JOBS}" \
  REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS}" \
  FALLBACK_JOBS="${FALLBACK_JOBS}" \
  FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT}" \
  OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT}" \
  LFS_JOBS="${LFS_JOBS}" \
  DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME}" \
  DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME}" \
  DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH}" \
  DOCKER_SOURCE_SEED=0 \
  SKIP_REPO_SYNC=0 \
  SKIP_PREBUILTS=0 \
  PREPARE_ONLY=1 \
    bash "${RUNNER}"
  refresh=0
fi

# Build both profiles for one architecture before pruning its product output.
# A profile switch deliberately removes that product's old output graph, while
# the final profile is pruned after packaging to limit peak disk use.
for product in ${PRODUCTS}; do
  device_type_index=0
  for device_type in ${DEVICE_TYPES}; do
    device_type_index=$((device_type_index + 1))
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
    prune_after_package=0
    if [ "${device_type_index}" -eq "${device_type_count}" ]; then
      prune_after_package="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}"
    fi
    DEVICE_TYPE="${device_type}" \
    PRODUCTS="${product}" \
    PACKAGE_ROOT="${PACKAGE_ROOT}" \
    CACHE_ROOT="${CACHE_ROOT}" \
    OHOS_BRANCH="${OHOS_BRANCH}" \
    MANIFEST_REVISION="${MANIFEST_REVISION}" \
    OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR}" \
    OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK}" \
    OHOS_GITHUB_NO_PROXY="${OHOS_GITHUB_NO_PROXY}" \
    REPO_JOBS="${REPO_JOBS}" \
    REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS}" \
    FALLBACK_JOBS="${FALLBACK_JOBS}" \
    FALLBACK_MIRROR_ROOT="${FALLBACK_MIRROR_ROOT}" \
    OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT}" \
    LFS_JOBS="${LFS_JOBS}" \
    CCACHE_MAXSIZE="${CCACHE_MAXSIZE}" \
    DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME}" \
    DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME}" \
    DOCKER_SOURCE_REFRESH="${refresh}" \
    DOCKER_SOURCE_SEED=0 \
    SKIP_REPO_SYNC=1 \
    SKIP_PREBUILTS=1 \
    PREPARE_ONLY=0 \
    PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${prune_after_package}" \
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

LFS_ASSET_MAP_SHA256="$(shasum -a 256 "${LFS_ASSET_MAP}" | awk '{print $1}')"
python3 - "${PACKAGE_ROOT}" "${expected_packages}" "${MANIFEST_REVISION}" \
  "${LFS_ASSET_MAP_SHA256}" \
  > "${PACKAGE_ROOT}/matrix-manifest.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_package_count = int(sys.argv[2])
expected_manifest_revision = sys.argv[3]
expected_lfs_asset_map_sha256 = sys.argv[4]
expected_qemu_mesa_revision = "995d2506d18924b48db0cf40e6ad7de04fc4e558"
packages = []
for archive in sorted(root.glob("openharmony-qemu-*.tar.gz")):
    package_dir = root / archive.name.removesuffix(".tar.gz")
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        continue
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    capabilities = manifest.get("capabilities", {})
    source_baseline = manifest.get("source_baseline", {})
    required_capability_names = (
        "absolute_pointer_sync",
        "thread_qos",
        "virtual_vibrator",
        "jsvm",
        "standard_vpn",
        "accessibility_test",
        "accessibility_cli",
        "virtio_multitouch",
        "device_type_full",
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    packages.append({
        "archive": archive.name,
        "sha256": digest,
        "size_bytes": archive.stat().st_size,
        "product": manifest["product"],
        "guest_arch": manifest["guest_arch"],
        "device_type": manifest["device_type"],
        "device_type_profile": manifest["device_type_profile"],
        "manifest_branch": source_baseline.get("manifest_branch", ""),
        "manifest_revision": source_baseline.get("manifest_revision", ""),
        "resolved_manifest_sha256": source_baseline.get(
            "resolved_manifest_sha256", ""
        ),
        "github_lfs_assets_sha256": source_baseline.get(
            "github_lfs_assets_sha256", ""
        ),
        "qemu_mesa_revision": source_baseline.get("qemu_mesa_revision", ""),
        "absolute_pointer_sync": capabilities.get("absolute_pointer_sync", False),
        "thread_qos": capabilities.get("thread_qos", False),
        "virtual_vibrator": capabilities.get("virtual_vibrator", False),
        "virtual_vibrator_mode": capabilities.get("virtual_vibrator_mode", ""),
        "jsvm": capabilities.get("jsvm", False),
        "jsvm_engine": capabilities.get("jsvm_engine", ""),
        "standard_vpn": capabilities.get("standard_vpn", False),
        "accessibility_test": capabilities.get("accessibility_test", False),
        "accessibility_cli": capabilities.get("accessibility_cli", False),
        "virtio_multitouch": capabilities.get("virtio_multitouch", False),
        "device_type_full": capabilities.get("device_type_full", False),
        "all_required_capabilities": all(
            capabilities.get(name, False) for name in required_capability_names
        ) and capabilities.get("virtual_vibrator_mode") == "simulated"
          and capabilities.get("jsvm_engine") == "ArkWeb M144 V8"
          and manifest.get("launcher", {}).get("accessibility") is True
          and manifest.get("launcher", {}).get("qmp_unix") is True
          and source_baseline.get("manifest_revision")
          == expected_manifest_revision
          and source_baseline.get("github_lfs_assets_sha256")
          == expected_lfs_asset_map_sha256
          and source_baseline.get("qemu_mesa_revision")
          == expected_qemu_mesa_revision,
        "pointer_device_default": manifest.get("launcher", {}).get(
            "pointer_device_default", ""
        ),
        "accessibility_launcher": manifest.get("launcher", {}).get(
            "accessibility", False
        ),
        "qmp_unix": manifest.get("launcher", {}).get("qmp_unix", False),
    })
if len(packages) != expected_package_count:
    raise SystemExit(
        f"expected {expected_package_count} package manifests, found {len(packages)}"
    )
missing_capabilities = [
    package["archive"]
    for package in packages
    if not package["all_required_capabilities"]
]
if missing_capabilities:
    raise SystemExit(
        "required capability contract failed: " + ", ".join(missing_capabilities)
    )
document = {
    "schema_version": 1,
    "expected_package_count": expected_package_count,
    "packages": packages,
}
print(json.dumps(document, indent=2, ensure_ascii=False))
PY

echo
echo "matrix complete: ${expected_packages} verified packages"
find "${PACKAGE_ROOT}" -maxdepth 1 -type f -name 'openharmony-qemu-*.tar.gz' -print | sort
echo "checksums: ${PACKAGE_ROOT}/SHA256SUMS"
echo "manifest:  ${PACKAGE_ROOT}/matrix-manifest.json"
