#!/usr/bin/env bash
# One pinned LLVM dependency build. No QEMU image or package is started here.
set -euo pipefail
main() {
  [ "$#" = 1 ] || {
    echo 'usage: build_qemu_mesa_llvm_in_docker.sh armv7a_virt|arm64_virt|x86_64_virt' >&2
    exit 2
  }
  case "$1" in armv7a_virt|arm64_virt|x86_64_virt) ;; *) exit 2 ;; esac
  local script_dir repo cache output inputs volume recipe
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo="$(cd "${script_dir}/.." && pwd)"
  cache="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
  recipe="$(python3 "${script_dir}/qemu_mesa_llvm_artifacts.py" --recipe-hash)"
  output="${QEMU_MESA_LLVM_ARTIFACT_OUTPUT:-${cache}/artifacts/qemu-mesa-llvm/${recipe}/$1}"
  [ ! -e "${output}" ] || {
    echo "fresh QEMU_MESA_LLVM_ARTIFACT_OUTPUT required: ${output}" >&2
    exit 1
  }
  mkdir -p "${cache}/build-inputs" "$(dirname "${output}")"
  inputs="$(mktemp -d "${cache}/build-inputs/qemu-mesa-llvm-XXXXXX")"
  python3 "${script_dir}/snapshot_build_inputs.py" --source "${repo}" --destination "${inputs}"
  # Use a new owned build volume and retain it on failure for diagnosis.
  volume="${QEMU_MESA_LLVM_BUILD_VOLUME:-ohos-qemu-mesa-llvm-$1-$(basename "${inputs}")}"
  if docker volume inspect "${volume}" >/dev/null 2>&1; then
    echo "fresh QEMU_MESA_LLVM_BUILD_VOLUME required: ${volume}" >&2
    exit 1
  fi
  docker volume create "${volume}" >/dev/null
  echo "LLVM build volume: ${volume}"
  docker run --rm --platform linux/amd64 \
    --mount "type=volume,src=${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source},dst=/ohos,readonly" \
    --mount "type=volume,src=${DOCKER_OUT_VOLUME:-ohos-qemu-7_0-release-out},dst=/ohos/out,readonly" \
    --mount "type=volume,src=${M144_DOCKER_SOURCE_VOLUME:-ohos-qemu-arkweb-7_0-release-source},dst=/m144,readonly" \
    --mount "type=volume,src=${volume},dst=/llvm-build" \
    --mount "type=bind,src=${inputs},dst=/work,readonly" \
    --mount "type=bind,src=$(dirname "${output}"),dst=/artifacts" \
    "${DOCKER_IMAGE:-ohos-qemu-build-env:7.0-release-gn-qemu-user}" \
    python3 /work/scripts/build_qemu_mesa_llvm.py --product "$1" \
    --ohos-source-root /ohos --m144-source-root /m144/release/src \
    --output "/artifacts/$(basename "${output}")" \
    --build-root "/llvm-build/$1" --jobs "${QEMU_MESA_LLVM_BUILD_JOBS:-2}"
}
main "$@"
