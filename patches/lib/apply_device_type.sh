#!/usr/bin/env bash
# Use the full Docker builder's ordered component plan, without a build.
set -euo pipefail
main() {
  device_type="${1:-}"
  case "${device_type}" in phone|2in1) ;; *) echo 'usage: apply_device_type.sh phone|2in1 ...' >&2; exit 2 ;; esac
  shift
  source_root= v8_root= core_root= vulkan_root= avc_root= lfs_root=
  products=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --source-root|--v8-artifact-root|--core-artifact-root|--vulkan-artifact-root|--avc-artifact-root|--lfs-asset-root)
        [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "missing value: $1" >&2; exit 2; }
        case "$1" in
          --source-root) source_root="$2" ;; --v8-artifact-root) v8_root="$2" ;;
          --core-artifact-root) core_root="$2" ;; --vulkan-artifact-root) vulkan_root="$2" ;;
          --avc-artifact-root) avc_root="$2" ;; --lfs-asset-root) lfs_root="$2" ;;
        esac
        shift 2 ;;
      --product)
        [ "$#" -ge 2 ] || { echo 'missing product' >&2; exit 2; }
        case "$2" in armv7a_virt|arm64_virt|x86_64_virt) products+=("$2") ;; *) echo 'unsupported product' >&2; exit 2 ;; esac
        shift 2 ;;
      --help|-h)
        echo 'usage: apply.sh --source-root ROOT --v8-artifact-root V8 --core-artifact-root CORE --vulkan-artifact-root ICD --avc-artifact-root AVC --lfs-asset-root LFS --product PRODUCT [...]'
        echo 'Run in prepared local Ubuntu 22.04 Docker; does not build or package.'
        return 0 ;;
      *) echo "unsupported argument: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "${source_root}" ] && [ -n "${v8_root}" ] && [ -n "${core_root}" ] && \
    [ -n "${vulkan_root}" ] && [ -n "${avc_root}" ] && [ -n "${lfs_root}" ] && \
    [ "${#products[@]}" -gt 0 ] || { echo 'all dependency roots and at least one product are required' >&2; exit 2; }
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export DEVICE_TYPE="${device_type}" OHOS_ROOT="${source_root}"
  export JSVM_ENGINE_ARTIFACTS="${v8_root}" QEMU_ARKWEB_CORE_ARTIFACTS="${core_root}"
  export QEMU_VULKAN_ARTIFACTS="${vulkan_root}" QEMU_AVC_ARTIFACTS="${avc_root}"
  export OHOS_LFS_ASSET_ROOT="${lfs_root}" PATCH_COMPONENTS_ONLY=1
  export QEMU_JSVM_COMPONENT=1 QEMU_VULKAN_COMPONENT=1
  exec bash "${script_dir}/../../scripts/build_standard_qemu_in_docker.sh" "${products[@]}"
}
main "$@"
