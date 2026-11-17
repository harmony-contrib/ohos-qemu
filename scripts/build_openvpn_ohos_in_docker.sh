#!/usr/bin/env bash
# Fixed-source backend build only. It does not install into a QEMU image.
set -euo pipefail
main() {
  [ "$#" = 1 ] || { echo 'usage: build_openvpn_ohos_in_docker.sh arm64_virt|armv7a_virt|x86_64_virt' >&2; exit 2; }
  case "$1" in arm64_virt|armv7a_virt|x86_64_virt) ;; *) exit 2 ;; esac
  local script_dir repo cache archive output inputs
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo="$(cd "${script_dir}/.." && pwd)"
  cache="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
  archive="${OPENVPN_SOURCE_ARCHIVE:-${cache}/artifacts/openvpn-source/openvpn-dc1f569087135894ac2703aeabd7a960ee9452d4.tar.gz}"
  output="${OPENVPN_ARTIFACT_OUTPUT:-${cache}/artifacts/openvpn-ohos/$1}"
  [ ! -e "${output}" ] || { echo "fresh OPENVPN_ARTIFACT_OUTPUT required: ${output}" >&2; exit 1; }
  python3 "${script_dir}/openvpn_source_archive.py" --output "${archive}"
  mkdir -p "${cache}/build-inputs" "$(dirname "${output}")"
  inputs="$(mktemp -d "${cache}/build-inputs/openvpn-XXXXXX")"
  python3 "${script_dir}/snapshot_build_inputs.py" --source "${repo}" --destination "${inputs}"
  # Out is read-only: the caller must first prepare its fixed OHOS musl/OpenSSL.
  # No source refresh, output pruning, role changes or running guest mutation.
  docker run --rm --platform linux/amd64 \
    --mount "type=volume,src=${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source},dst=/ohos,readonly" \
    --mount "type=volume,src=${DOCKER_OUT_VOLUME:-ohos-qemu-7_0-release-out},dst=/ohos/out,readonly" \
    --mount "type=bind,src=${inputs},dst=/work,readonly" \
    --mount "type=bind,src=${archive},dst=/source.tar.gz,readonly" \
    --mount "type=bind,src=$(dirname "${output}"),dst=/artifacts" \
    "${DOCKER_IMAGE:-ohos-qemu-build-env:7.0-release-gn-qemu-user}" \
    python3 /work/scripts/build_openvpn_ohos.py --source-root /ohos --archive /source.tar.gz \
    --output "/artifacts/$(basename "${output}")" --product "$1" --jobs "${OPENVPN_BUILD_JOBS:-2}"
}
main "$@"
