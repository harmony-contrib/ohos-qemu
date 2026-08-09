#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INSTALLER="${REPO_ROOT}/scripts/install.sh"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/ohos-qemu-install-test.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

ASSET_ROOT="${WORKDIR}/assets"
FALLBACK_ASSET_ROOT="${WORKDIR}/fallback-assets"
EMPTY_ASSET_ROOT="${WORKDIR}/empty-assets"
PREFIX="${WORKDIR}/install"
DEFAULT_PREFIX="${WORKDIR}/default-install"
FALLBACK_PREFIX="${WORKDIR}/fallback-install"
ENV_PREFIX="${WORKDIR}/env-install"
mkdir -p \
  "${ASSET_ROOT}" \
  "${FALLBACK_ASSET_ROOT}" \
  "${EMPTY_ASSET_ROOT}" \
  "${PREFIX}" \
  "${DEFAULT_PREFIX}" \
  "${FALLBACK_PREFIX}" \
  "${ENV_PREFIX}"

create_asset() {
  local package_dir="$1"
  local stage="${WORKDIR}/stage-${package_dir}"
  mkdir -p "${stage}/${package_dir}/launch"
  printf '#!/usr/bin/env bash\necho test launcher\n' \
    >"${stage}/${package_dir}/launch/linux.sh"
  printf '#!/usr/bin/env bash\necho test launcher\n' \
    >"${stage}/${package_dir}/launch/macos.command"
  printf 'Write-Output "test launcher"\n' \
    >"${stage}/${package_dir}/launch/windows.ps1"
  chmod +x \
    "${stage}/${package_dir}/launch/linux.sh" \
    "${stage}/${package_dir}/launch/macos.command"
  COPYFILE_DISABLE=1 tar -C "${stage}" -czf \
    "${ASSET_ROOT}/${package_dir}.tar.gz" "${package_dir}"
}

create_asset openharmony-qemu-x86_64-x86_64_virt
for package_base in \
  openharmony-qemu-arm64-arm64_virt \
  openharmony-qemu-armv7a-armv7a_virt \
  openharmony-qemu-x86_64-x86_64_virt
do
  create_asset "${package_base}-phone"
  create_asset "${package_base}-2in1"
done
cp "${ASSET_ROOT}/openharmony-qemu-x86_64-x86_64_virt.tar.gz" \
  "${FALLBACK_ASSET_ROOT}/"

COMMON_ARGS=(
  --prefix "${PREFIX}"
  --platform linux
  --release test-release
  --download-base-url "file://${ASSET_ROOT}"
)

# With no device argument, phone is selected and its suffixed asset wins.
bash "${INSTALLER}" \
  --prefix "${DEFAULT_PREFIX}" \
  --platform linux \
  --arch x86_64 \
  --release test-release \
  --download-base-url "file://${ASSET_ROOT}" \
  >"${WORKDIR}/default.log"
test -x \
  "${DEFAULT_PREFIX}/openharmony-qemu-x86_64-x86_64_virt-phone/launch/linux.sh"
test ! -e "${DEFAULT_PREFIX}/openharmony-qemu-x86_64-x86_64_virt"
grep -q '^device:    phone$' "${WORKDIR}/default.log"
grep -q '^package:   openharmony-qemu-x86_64-x86_64_virt-phone.tar.gz$' \
  "${WORKDIR}/default.log"

# Explicit phone falls back to a legacy no-suffix asset when needed.
bash "${INSTALLER}" \
  --prefix "${FALLBACK_PREFIX}" \
  --platform linux \
  --arch x86_64 \
  --device-type phone \
  --release test-release \
  --download-base-url "file://${FALLBACK_ASSET_ROOT}" \
  >"${WORKDIR}/fallback.log" 2>&1
test -x \
  "${FALLBACK_PREFIX}/openharmony-qemu-x86_64-x86_64_virt/launch/linux.sh"
grep -q 'package unavailable: openharmony-qemu-x86_64-x86_64_virt-phone.tar.gz' \
  "${WORKDIR}/fallback.log"
grep -q '^package:   openharmony-qemu-x86_64-x86_64_virt.tar.gz$' \
  "${WORKDIR}/fallback.log"

# CLI selection installs all six architecture/device packages side by side.
for arch in arm64 armv7a x86_64; do
  case "${arch}" in
    arm64) package_base=openharmony-qemu-arm64-arm64_virt ;;
    armv7a) package_base=openharmony-qemu-armv7a-armv7a_virt ;;
    x86_64) package_base=openharmony-qemu-x86_64-x86_64_virt ;;
  esac
  for device_type in phone 2in1; do
    log="${WORKDIR}/${arch}-${device_type}.log"
    # The CLI selection must override an environment value.
    OHOS_QEMU_DEVICE_TYPE=phone \
      bash "${INSTALLER}" "${COMMON_ARGS[@]}" \
        --arch "${arch}" --device-type "${device_type}" >"${log}"
    test -x "${PREFIX}/${package_base}-${device_type}/launch/linux.sh"
    grep -q "^device:    ${device_type}$" "${log}"
    grep -q "^package:   ${package_base}-${device_type}.tar.gz$" "${log}"
  done
done

# Environment-only selection supports architecture aliases as well.
OHOS_QEMU_DEVICE_TYPE=phone \
OHOS_QEMU_ARCH=aarch64 \
OHOS_QEMU_PLATFORM=macos \
OHOS_QEMU_PREFIX="${ENV_PREFIX}" \
OHOS_QEMU_RELEASE_TAG=test-release \
OHOS_QEMU_DOWNLOAD_BASE_URL="file://${ASSET_ROOT}" \
  bash "${INSTALLER}" >"${WORKDIR}/env.log"
test -x "${ENV_PREFIX}/openharmony-qemu-arm64-arm64_virt-phone/launch/macos.command"
grep -q '^arch:      arm64$' "${WORKDIR}/env.log"
grep -q '^device:    phone$' "${WORKDIR}/env.log"

# Missing phone candidates report both attempted assets.
if bash "${INSTALLER}" \
    --prefix "${WORKDIR}/missing-install" \
    --platform linux \
    --arch x86_64 \
    --release test-release \
    --download-base-url "file://${EMPTY_ASSET_ROOT}" \
    >"${WORKDIR}/missing.log" 2>&1; then
  echo "installer unexpectedly accepted a missing phone package" >&2
  exit 1
fi
grep -q 'no downloadable phone package found for x86_64' \
  "${WORKDIR}/missing.log"
grep -q 'openharmony-qemu-x86_64-x86_64_virt-phone.tar.gz' \
  "${WORKDIR}/missing.log"
grep -q 'openharmony-qemu-x86_64-x86_64_virt.tar.gz' \
  "${WORKDIR}/missing.log"

# 2in1 must not fall back to the legacy phone archive.
if bash "${INSTALLER}" \
    --prefix "${WORKDIR}/missing-2in1-install" \
    --platform linux \
    --arch x86_64 \
    --device-type 2in1 \
    --release test-release \
    --download-base-url "file://${FALLBACK_ASSET_ROOT}" \
    >"${WORKDIR}/missing-2in1.log" 2>&1; then
  echo "installer unexpectedly used a legacy package for 2in1" >&2
  exit 1
fi
grep -q 'no downloadable 2in1 package found for x86_64' \
  "${WORKDIR}/missing-2in1.log"

if bash "${INSTALLER}" --device-type tablet >"${WORKDIR}/invalid.log" 2>&1; then
  echo "installer unexpectedly accepted an unsupported device type" >&2
  exit 1
fi
grep -q 'unsupported --device-type: tablet' "${WORKDIR}/invalid.log"

if find "${WORKDIR}" -type f -path '*/downloads/*.tar.gz' | grep -q .; then
  echo "installer unexpectedly kept an archive without --keep-archive" >&2
  exit 1
fi

echo "install script tests passed"
