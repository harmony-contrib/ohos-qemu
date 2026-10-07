#!/usr/bin/env bash
# A single fixed source graph for V8, native ArkWeb and the signed core HAP.
set -euo pipefail
main() {
  [ "$#" = 2 ] || { echo 'usage: run_m144_release_build_docker.sh prepare|native|hap|v8|swiftshader|avc arm|arm64|x86_64' >&2; exit 2; }
  mode="$1" arch="$2"
  case "${mode}" in prepare|native|hap|v8|swiftshader|avc) ;; *) echo 'unsupported M144 build stage' >&2; exit 2 ;; esac
  case "${arch}" in arm|arm64|x86_64) ;; *) echo 'unsupported M144 target architecture' >&2; exit 2 ;; esac
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"
  cache_root="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
  dependency_recipe="$(python3 "${script_dir}/m144_dependency_recipe.py")"
  source_cache="${M144_RELEASE_CACHE:-${cache_root}/git-mirrors/arkweb-7.0-release}"
  tool_source_cache="${M144_TOOL_SOURCE_CACHE:-${cache_root}/git-mirrors/m144-tool-sources}"
  source_volume="${M144_RELEASE_SOURCE_VOLUME:-ohos-qemu-arkweb-7_0-release-source}"
  ohos_volume="${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source}"
  image="${DOCKER_IMAGE:-}"
  artifacts="${QEMU_ARKWEB_CORE_ARTIFACTS:-${cache_root}/artifacts/arkweb-m144-7.0/${dependency_recipe}}"
  if [ "${mode}" = v8 ]; then artifacts="${JSVM_ENGINE_ARTIFACTS:-${cache_root}/artifacts/jsvm-m144-7.0/${dependency_recipe}}"; fi
  if [ "${mode}" = swiftshader ]; then artifacts="${QEMU_VULKAN_ARTIFACTS:-${cache_root}/artifacts/swiftshader-m144-7.0/${dependency_recipe}}"; fi
  if [ "${mode}" = avc ]; then artifacts="${QEMU_AVC_ARTIFACTS:-${cache_root}/artifacts/avc-m144-7.0/${dependency_recipe}}"; fi
  command -v docker >/dev/null || { echo 'local Docker is required' >&2; exit 1; }
  mkdir -p "${cache_root}/build-inputs" "${artifacts}"
  frozen="$(mktemp -d "${cache_root}/build-inputs/m144-release-XXXXXX")"
  python3 "${script_dir}/snapshot_build_inputs.py" --source "${repo_root}" --destination "${frozen}"
  default_prepared_image=0
  if [ -z "${image}" ]; then
    image=ohos-qemu-m144-build-env:7.0-release
    base_image=ubuntu:22.04
    if docker image inspect ohos-qemu-build-env:7.0-release >/dev/null 2>&1; then
      base_image=ohos-qemu-build-env:7.0-release
    fi
    # BuildKit caches this exact repository-owned dependency recipe. Native,
    # HAP and the next ABI do not each download/install the same host packages.
    docker build --platform "${DOCKER_PLATFORM:-linux/amd64}" \
      --build-arg "BASE_IMAGE=${base_image}" -t "${image}" \
      -f "${frozen}/scripts/docker/m144-build-env.Dockerfile" "${frozen}"
    default_prepared_image=1
  fi
  run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  if [ "${M144_SKIP_FETCH:-0}" != 1 ]; then
    python3 "${frozen}/scripts/prepare_m144_release_cache.py" --cache-root "${source_cache}" \
      --evidence "${artifacts}/cache-preparation-${run_id}.json" --jobs "${M144_SYNC_JOBS:-8}"
  fi
  lfs_options=()
  if [ "${M144_SKIP_FETCH:-0}" = 1 ]; then lfs_options+=(--no-fetch); fi
  python3 "${frozen}/scripts/prepare_m144_release_lfs.py" --cache-root "${source_cache}" \
    --evidence "${artifacts}/lfs-preparation-${run_id}.json" ${lfs_options[@]+"${lfs_options[@]}"}
  python3 "${frozen}/scripts/prepare_m144_tool_sources.py" --root "${tool_source_cache}" \
    --evidence "${artifacts}/tool-source-preparation-${run_id}.json" ${lfs_options[@]+"${lfs_options[@]}"} gn sdk-llvm15
  hap_tool_mounts=()
  case "${mode}" in
    native|hap)
      hap_tool_cache="$(python3 "${frozen}/scripts/prepare_m144_release_hap_cache.py" \
        --cache-root "${cache_root}/artifacts/m144-release-host-tools")"
      hap_tool_mounts+=(--mount "type=bind,src=${hap_tool_cache},dst=/m144-hap-tools,readonly")
      ;;
  esac
  docker volume create "${source_volume}" >/dev/null
  docker volume inspect "${ohos_volume}" >/dev/null || \
    { echo 'prepare the pinned OpenHarmony release/SDK source volume first' >&2; exit 1; }
  docker run --rm --platform "${DOCKER_PLATFORM:-linux/amd64}" \
    --ulimit nofile=1048576:1048576 \
    --mount "type=volume,src=${source_volume},dst=/workspace" \
    --mount "type=volume,src=${ohos_volume},dst=/ohos,readonly" \
    --mount "type=bind,src=${source_cache},dst=/m144-cache,readonly" \
    --mount "type=bind,src=${tool_source_cache},dst=/m144-tool-sources,readonly" \
    --mount "type=bind,src=${frozen},dst=/work,readonly" \
    --mount "type=bind,src=${artifacts},dst=/artifacts" \
    ${hap_tool_mounts[@]+"${hap_tool_mounts[@]}"} \
    -e M144_WORK_ROOT=/workspace/release -e OHOS_ROOT=/ohos \
    -e M144_CORE_BUILD_JOBS="${M144_CORE_BUILD_JOBS:-4}" \
    -e M144_BUILD_JOBS="${M144_BUILD_JOBS:-4}" \
    -e M144_CORE_SKIP_APT="${M144_CORE_SKIP_APT:-${default_prepared_image}}" \
    -e M144_SKIP_APT="${M144_SKIP_APT:-${default_prepared_image}}" \
    -e M144_RELEASE_STAGE="${mode}" -e M144_RELEASE_ARCH="${arch}" \
    -e M144_V8_ARCHES="${M144_V8_ARCHES:-${arch}}" \
    -e M144_DEPENDENCY_ARCHES="${M144_DEPENDENCY_ARCHES:-${arch}}" \
    -e M144_RELEASE_RUN_ID="${run_id}" "${image}" bash -lc '
      set -euo pipefail
      export LANG=C.UTF-8 LC_ALL=C.UTF-8
      # A clean host can use Ubuntu directly, without a manually committed
      # dependency image or an assumed prior V8/container preparation.
      for required_tool in git git-lfs python3 flock; do
        if ! command -v "${required_tool}" >/dev/null 2>&1; then
          export DEBIAN_FRONTEND=noninteractive
          apt-get update
          apt-get install -y --no-install-recommends git git-lfs python3 ca-certificates util-linux
          break
        fi
      done
      exec 9>/workspace/.m144-release-build.lock
      flock -n 9 || { echo "another build owns the release source volume" >&2; exit 1; }
      bash /work/scripts/prepare_m144_build_host.sh
      export M144_CORE_SKIP_APT=1 M144_SKIP_APT=1
      python3 /work/scripts/prepare_m144_release_sources.py --work-root /workspace/release \
        --cache-root /m144-cache --evidence "/artifacts/source-preparation-${M144_RELEASE_RUN_ID}.json"
      export M144_TOOL_EVIDENCE="/artifacts/release-tools-${M144_RELEASE_RUN_ID}.json"
      python3 /work/scripts/prepare_m144_release_tools.py --source-root /workspace/release/src \
        --cache-root /workspace/tool-downloads --tool-source-root /m144-tool-sources \
        --evidence "${M144_TOOL_EVIDENCE}"
      case "${M144_RELEASE_STAGE}" in
        native|hap)
          export M144_HAP_TOOL_EVIDENCE="/artifacts/hap-host-tools-${M144_RELEASE_RUN_ID}.json"
          python3 /work/scripts/prepare_m144_hap_tools.py --source-root /workspace/release/src \
            --ohos-root /ohos --cache-root /m144-hap-tools \
            --evidence "${M144_HAP_TOOL_EVIDENCE}" --preflight
          export npm_config_offline=true NPM_CONFIG_OFFLINE=true
          ;;
      esac
      case "${M144_RELEASE_STAGE}" in
        prepare) ;;
        native) bash /work/scripts/build_m144_arkweb_core_in_docker.sh "${M144_RELEASE_ARCH}" ;;
        hap) bash /work/scripts/package_m144_arkweb_core_in_docker.sh "${M144_RELEASE_ARCH}" ;;
        v8) read -r -a arches <<< "${M144_V8_ARCHES:-${M144_RELEASE_ARCH}}"
            bash /work/scripts/build_m144_v8_in_docker.sh "${arches[@]}" ;;
        swiftshader|avc)
            read -r -a arches <<< "${M144_DEPENDENCY_ARCHES}"
            M144_GN_ONLY=1 bash /work/scripts/build_m144_v8_in_docker.sh "${arches[@]}"
            if [ "${M144_RELEASE_STAGE}" = swiftshader ]; then
              bash /work/scripts/build_m144_swiftshader_in_docker.sh "${arches[@]}"
            else
              bash /work/scripts/build_m144_avc_encoder_in_docker.sh "${arches[@]}"
            fi ;;
      esac'
}
main "$@"
