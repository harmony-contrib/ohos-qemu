#!/usr/bin/env bash
# One ABI's complete fixed-release dependencies, before its OS build traversal.
set -euo pipefail
main() {
  [ "$#" = 1 ] || { echo 'usage: prepare_qemu_release_dependencies.sh armv7a_virt|arm64_virt|x86_64_virt' >&2; exit 2; }
  case "$1" in armv7a_virt) arch=arm ;; arm64_virt) arch=arm64 ;; x86_64_virt) arch=x86_64 ;; *) exit 2 ;; esac
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cache_root="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
  dependency_recipe="$(python3 "${script_dir}/m144_dependency_recipe.py")"
  dependency_root="${MATRIX_DEPENDENCY_ROOT:-${cache_root}/artifacts/m144-7.0-dependencies/${dependency_recipe}}/${arch}"
  export QEMU_ARKWEB_CORE_ARTIFACTS="${QEMU_ARKWEB_CORE_ARTIFACTS:-${cache_root}/artifacts/arkweb-m144-7.0/${dependency_recipe}}"
  export JSVM_ENGINE_ARTIFACTS="${JSVM_ENGINE_ARTIFACTS:-${dependency_root}/jsvm}"
  export QEMU_VULKAN_ARTIFACTS="${QEMU_VULKAN_ARTIFACTS:-${dependency_root}/swiftshader}"
  export QEMU_AVC_ARTIFACTS="${QEMU_AVC_ARTIFACTS:-${dependency_root}/avc}"
  frontend="${script_dir}/run_m144_release_build_docker.sh"
  if [ ! -f "${QEMU_ARKWEB_CORE_ARTIFACTS}/${arch}/core-artifact.json" ]; then
    if [ ! -f "${QEMU_ARKWEB_CORE_ARTIFACTS}/${arch}/native-build-evidence.json" ]; then
      bash "${frontend}" native "${arch}"
    fi
    bash "${frontend}" hap "${arch}"
  fi
  python3 "${script_dir}/m144_core_artifacts.py" --artifact-root "${QEMU_ARKWEB_CORE_ARTIFACTS}" --arch "${arch}"
  if [ ! -f "${JSVM_ENGINE_ARTIFACTS}/manifest.json" ]; then bash "${frontend}" v8 "${arch}"; fi
  python3 "${script_dir}/../patches/common/arkcompiler/jsvm/validate_artifacts.py" \
    --artifact-root "${JSVM_ENGINE_ARTIFACTS}" --arch "${arch}"
  if [ ! -f "${QEMU_VULKAN_ARTIFACTS}/manifest.json" ]; then bash "${frontend}" swiftshader "${arch}"; fi
  python3 "${script_dir}/verify_m144_swiftshader_artifacts.py" \
    --artifact-root "${QEMU_VULKAN_ARTIFACTS}" --arch "${arch}"
  if [ ! -f "${QEMU_AVC_ARTIFACTS}/manifest.json" ]; then bash "${frontend}" avc "${arch}"; fi
  python3 "${script_dir}/../patches/lib/avc_artifacts.py" --artifact-root "${QEMU_AVC_ARTIFACTS}" --arch "${arch}"
}
main "$@"
