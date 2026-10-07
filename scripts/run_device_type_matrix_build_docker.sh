#!/usr/bin/env bash
# Build a representative package, require real behavior evidence, then complete
# the phone/2in1 x armv7a/arm64/x86_64 matrix. Static checks are not this gate.
set -euo pipefail
export LC_ALL=C
export LANG=C

main() {

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
DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME:-ohos-qemu-7_0-release-out}"
DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source}"
DOCKER_SOURCE_REFRESH="${DOCKER_SOURCE_REFRESH:-0}"
MATRIX_FIRST_PRODUCT="${MATRIX_FIRST_PRODUCT:-arm64_virt}"
MATRIX_FIRST_DEVICE_TYPE="${MATRIX_FIRST_DEVICE_TYPE:-phone}"
MATRIX_FIRST_ARTIFACT_EVIDENCE="${MATRIX_FIRST_ARTIFACT_EVIDENCE:-${PACKAGE_ROOT}/first-artifact-behavior.json}"
MATRIX_FIRST_VALIDATOR="${MATRIX_FIRST_VALIDATOR:-${SCRIPT_DIR}/validate_packaged_qemu.sh}"
MATRIX_PACKAGE_VALIDATOR="${MATRIX_PACKAGE_VALIDATOR:-${MATRIX_FIRST_VALIDATOR}}"
MATRIX_RUNTIME_EVIDENCE_ROOT="${MATRIX_RUNTIME_EVIDENCE_ROOT:-${PACKAGE_ROOT}/runtime-evidence}"
MATRIX_BUILD_DEPENDENCIES="${MATRIX_BUILD_DEPENDENCIES:-1}"
dependency_recipe="$(python3 "${SCRIPT_DIR}/m144_dependency_recipe.py")"
MATRIX_DEPENDENCY_ROOT="${MATRIX_DEPENDENCY_ROOT:-${CACHE_ROOT}/artifacts/m144-7.0-dependencies/${dependency_recipe}}"
matrix_jsvm_shared="${JSVM_ENGINE_ARTIFACTS:-}"
matrix_vulkan_shared="${QEMU_VULKAN_ARTIFACTS:-}"
matrix_avc_shared="${QEMU_AVC_ARTIFACTS:-}"
export QEMU_ARKWEB_CORE_ARTIFACTS="${QEMU_ARKWEB_CORE_ARTIFACTS:-${CACHE_ROOT}/artifacts/arkweb-m144-7.0/${dependency_recipe}}"

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
case "${MATRIX_BUILD_DEPENDENCIES}" in 0|1) ;; *) echo 'MATRIX_BUILD_DEPENDENCIES must be 0 or 1' >&2; exit 2 ;; esac

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
  local scene_args=()
  case "${device_type}" in
    2in1)
      full_arg=--require-full-2in1
      scene_args=(--require-scene-window)
      ;;
    phone) full_arg=--require-full-phone ;;
    *) return 2 ;;
  esac
  bash "${VERIFY}" \
    --package "${package_dir}" \
    --expect-device-type "${device_type}" \
    --expect-manifest-revision "${MANIFEST_REVISION}" \
    "${full_arg}" \
    ${scene_args[@]+"${scene_args[@]}"}
}

select_arch_dependencies() {
  local dependency_arch
  case "$1" in armv7a_virt) dependency_arch=arm ;; arm64_virt) dependency_arch=arm64 ;; x86_64_virt) dependency_arch=x86_64 ;; *) return 2 ;; esac
  export JSVM_ENGINE_ARTIFACTS="${matrix_jsvm_shared:-${MATRIX_DEPENDENCY_ROOT}/${dependency_arch}/jsvm}"
  export QEMU_VULKAN_ARTIFACTS="${matrix_vulkan_shared:-${MATRIX_DEPENDENCY_ROOT}/${dependency_arch}/swiftshader}"
  export QEMU_AVC_ARTIFACTS="${matrix_avc_shared:-${MATRIX_DEPENDENCY_ROOT}/${dependency_arch}/avc}"
}

prepare_arch_dependencies() {
  select_arch_dependencies "$1"
  if [ "${MATRIX_BUILD_DEPENDENCIES}" = 1 ]; then
    bash "${SCRIPT_DIR}/prepare_qemu_release_dependencies.sh" "$1"
  fi
}

verify_current_inputs() {
  python3 - "${SCRIPT_DIR}" "$1" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from snapshot_build_inputs import digest_files
from verify_first_artifact_gate import archive_inputs
current = digest_files(Path(sys.argv[1]).parent)
inputs = archive_inputs(Path(sys.argv[2]))
if (inputs.get('files_sha256') != current or inputs.get('tree_sha256') !=
        hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()):
    raise SystemExit('archive is not from the current frozen build/validation recipes')
PY
}

verify_package_runtime() {
  local profile="$1" product="$2" directory="$3" archive="$4"
  local evidence="${MATRIX_RUNTIME_EVIDENCE_ROOT}/$(basename "${directory}").json"
  if [ "${archive}" = "${first_tar}" ]; then evidence="${MATRIX_FIRST_ARTIFACT_EVIDENCE}"; fi
  if python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py" --archive "${archive}" \
    --evidence "${evidence}" --repository "${SCRIPT_DIR}/.." --product "${product}" \
    --device-type "${profile}" >/dev/null 2>&1; then
    return 0
  fi
  [ -n "${MATRIX_PACKAGE_VALIDATOR}" ] && [ -f "${MATRIX_PACKAGE_VALIDATOR}" ] || {
    echo 'each delivered archive requires its own real boot/behavior evidence or local package validator' >&2; return 1;
  }
  mkdir -p "${MATRIX_RUNTIME_EVIDENCE_ROOT}"
  bash "${MATRIX_PACKAGE_VALIDATOR}" --package-archive "${archive}" \
    --package-directory "${directory}" --evidence-output "${evidence}"
  python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py" --archive "${archive}" \
    --evidence "${evidence}" --repository "${SCRIPT_DIR}/.." --product "${product}" \
    --device-type "${profile}"
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
echo "Product output is retained until its archive-bound runtime probes finish."

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
case " ${PRODUCTS} " in *" ${MATRIX_FIRST_PRODUCT} "*) ;; *)
  echo 'representative product must be included in PRODUCTS' >&2; exit 2 ;; esac
case " ${DEVICE_TYPES} " in *" ${MATRIX_FIRST_DEVICE_TYPE} "*) ;; *)
  echo 'representative device profile must be included in DEVICE_TYPES' >&2; exit 2 ;; esac
first_arch="$(product_arch "${MATRIX_FIRST_PRODUCT}")"
first_name="openharmony-qemu-${first_arch}-${MATRIX_FIRST_PRODUCT}-${MATRIX_FIRST_DEVICE_TYPE}"
first_dir="${PACKAGE_ROOT}/${first_name}"
first_tar="${first_dir}.tar.gz"

# Bootstrap source/SDK without requiring already-built M144 dependencies.
# Other ABIs' dependencies and profile traversal wait for the real first gate.
if [ "${MATRIX_PREPARE_SOURCE}" = "1" ]; then
  echo
  echo "=== prepare pinned OpenHarmony source and API26 SDK before dependencies ==="
  DEVICE_TYPE="${MATRIX_FIRST_DEVICE_TYPE}" \
  PRODUCTS="${MATRIX_FIRST_PRODUCT}" \
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
  SOURCE_PREPARE_ONLY=1 \
    bash "${RUNNER}"
  refresh=0
fi
prepare_arch_dependencies "${MATRIX_FIRST_PRODUCT}"

# Never start the remaining five before the new representative archive has
# actually booted and passed the intended behavior/boundary/regression checks.
if ! { [ "${MATRIX_SKIP_EXISTING}" = 1 ] && [ -f "${first_tar}" ] &&
       verify_package "${MATRIX_FIRST_DEVICE_TYPE}" "${first_dir}" >/dev/null 2>&1 &&
       verify_current_inputs "${first_tar}" >/dev/null 2>&1; }; then
  DEVICE_TYPE="${MATRIX_FIRST_DEVICE_TYPE}" PRODUCTS="${MATRIX_FIRST_PRODUCT}" \
  PACKAGE_ROOT="${PACKAGE_ROOT}" CACHE_ROOT="${CACHE_ROOT}" \
  OHOS_BRANCH="${OHOS_BRANCH}" MANIFEST_REVISION="${MANIFEST_REVISION}" \
  DOCKER_SOURCE_VOLUME="${DOCKER_SOURCE_VOLUME}" DOCKER_OUT_VOLUME="${DOCKER_OUT_VOLUME}" \
  DOCKER_SOURCE_REFRESH="${refresh}" SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 PREPARE_ONLY=0 \
  PRUNE_PRODUCT_OUT_AFTER_PACKAGE=0 bash "${RUNNER}"
  refresh=0
fi
verify_package "${MATRIX_FIRST_DEVICE_TYPE}" "${first_dir}"
verify_current_inputs "${first_tar}"
if [ -n "${MATRIX_FIRST_VALIDATOR}" ]; then
  [ -f "${MATRIX_FIRST_VALIDATOR}" ] || { echo 'first-artifact validator script is missing' >&2; exit 1; }
  bash "${MATRIX_FIRST_VALIDATOR}" --package-archive "${first_tar}" \
    --package-directory "${first_dir}" --evidence-output "${MATRIX_FIRST_ARTIFACT_EVIDENCE}"
fi
python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py" \
  --archive "${first_tar}" --evidence "${MATRIX_FIRST_ARTIFACT_EVIDENCE}" \
  --repository "${SCRIPT_DIR}/.." --product "${MATRIX_FIRST_PRODUCT}" \
  --device-type "${MATRIX_FIRST_DEVICE_TYPE}"

# Validate each profile before switching its graph. Runtime probes require the
# actual just-built private innerkits; never prune them merely because tar
# succeeded. The profile switch already replaces that product's old graph.
for product in ${PRODUCTS}; do
  prepare_arch_dependencies "${product}"
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
       verify_package "${device_type}" "${package_dir}" >/dev/null 2>&1 && \
       verify_current_inputs "${package_tar}" >/dev/null 2>&1; then
      echo "reuse verified matrix package: ${package_tar}"
      verify_package_runtime "${device_type}" "${product}" "${package_dir}" "${package_tar}"
      continue
    fi

    echo
    echo "=== build ${device_type} / ${product} ==="
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
    PRUNE_PRODUCT_OUT_AFTER_PACKAGE=0 \
      bash "${RUNNER}"
    refresh=0

    verify_package "${device_type}" "${package_dir}"
    verify_current_inputs "${package_tar}"
    if [ ! -f "${package_tar}" ]; then
      echo "matrix build did not create archive: ${package_tar}" >&2
      exit 1
    fi
    verify_package_runtime "${device_type}" "${product}" "${package_dir}" "${package_tar}"
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
  "${LFS_ASSET_MAP_SHA256}" "${MATRIX_RUNTIME_EVIDENCE_ROOT}" "${first_tar}" "${MATRIX_FIRST_ARTIFACT_EVIDENCE}" \
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
runtime_root = Path(sys.argv[5])
first_archive = Path(sys.argv[6])
first_evidence = Path(sys.argv[7])
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
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    digest = digest.hexdigest()
    runtime_evidence = first_evidence if archive == first_archive else runtime_root / (package_dir.name + '.json')
    runtime = json.loads(runtime_evidence.read_text())
    if (runtime.get('scope') != 'new_packaged_qemu_behavior' or runtime.get('first_artifact_behavior_gate_passed') is not True
            or runtime.get('package', {}).get('sha256') != digest):
        raise SystemExit('runtime evidence no longer matches delivered archive: ' + archive.name)
    packages.append({
        "archive": archive.name,
        "sha256": digest,
        "runtime_validated": True,
        "runtime_evidence": str(runtime_evidence),
        "runtime_evidence_sha256": hashlib.sha256(runtime_evidence.read_bytes()).hexdigest(),
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
        "sceneboard_window_manager": capabilities.get("sceneboard_window_manager", False),
        "all_required_packaging_capabilities": all(
            capabilities.get(name, False) for name in required_capability_names
        ) and (manifest["device_type"] != "2in1" or
               capabilities.get("sceneboard_window_manager") is True)
          and capabilities.get("virtual_vibrator_mode") == "simulated"
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
    if not package["all_required_packaging_capabilities"] or not package['runtime_validated']
]
if missing_capabilities:
    raise SystemExit(
        "required packaging/runtime contract failed: " + ", ".join(missing_capabilities)
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
}

main "$@"
