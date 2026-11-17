#!/usr/bin/env bash
set -euo pipefail
WORK_ROOT="${M144_WORK_ROOT:-/workspace/release}"
SOURCE_ROOT="${WORK_ROOT}/src"
ARTIFACT_ROOT="${M144_AVC_ARTIFACT_ROOT:-/artifacts}"
COMPONENT=/work/patches/common/web/arkweb/m144_avc_encoder
bash "${COMPONENT}/apply.sh" --source-root "${WORK_ROOT}" --ohos-root /ohos
(cd "${SOURCE_ROOT}" && "${SOURCE_ROOT}/third_party/depot_tools/gn" format ohos/qemu_avc/BUILD.gn)
ARCHES=("$@")
[ "${#ARCHES[@]}" -gt 0 ] || { echo "explicit architectures are required" >&2; exit 2; }
for arch in "${ARCHES[@]}"; do
  case "${arch}" in
    arm) cpu=arm ;;
    arm64) cpu=arm64 ;;
    x86_64) cpu=x64 ;;
    *) echo "unsupported AVC architecture: ${arch}" >&2; exit 2 ;;
  esac
  template="${SOURCE_ROOT}/out/m144_${arch}/args.gn"
  grep -Eq '^target_os = "ohos"$' "${template}"
  grep -Eq "^target_cpu = \"${cpu}\"$" "${template}"
  # Own output graph, using the existing pinned toolchain/SDK configuration.
  # Do not replace V8/SwiftShader Ninja files with a reduced root graph.
  output="${SOURCE_ROOT}/out/qemu_avc_${arch}"
  mkdir -p "${output}"
  cp "${template}" "${output}/args.gn"
  (cd "${SOURCE_ROOT}" && "${SOURCE_ROOT}/third_party/depot_tools/gn" gen "${output}" \
    --root-target=//ohos/qemu_avc:avcenc_ohos)
  "${SOURCE_ROOT}/third_party/depot_tools/ninja" -C "${output}" -j "${M144_BUILD_JOBS:-2}" \
    ohos/qemu_avc:avcenc_ohos
  binary="${output}/libavcenc_ohos.z.so"
  [ -s "${binary}" ] || { echo "missing real AVC output: ${binary}" >&2; exit 1; }
  for symbol in InitEncoder EncodeProcess ReleaseEncoder; do
    readelf --dyn-syms --wide "${binary}" | grep " ${symbol}$" >/dev/null || {
      echo "AVC output is missing ${symbol}" >&2; exit 1
    }
  done
  install -D -m 0644 "${binary}" "${ARTIFACT_ROOT}/${arch}/libavcenc_ohos.z.so"
done
install -D -m 0644 "${SOURCE_ROOT}/third_party/openh264/src/LICENSE" \
  "${ARTIFACT_ROOT}/licenses/openh264-LICENSE"
for runtime in libc++ libc++abi compiler-rt; do
  install -D -m 0644 "${SOURCE_ROOT}/third_party/${runtime}/src/LICENSE.TXT" \
    "${ARTIFACT_ROOT}/licenses/${runtime}-LICENSE.TXT"
done
python3 /work/scripts/record_m144_avc_artifacts.py --artifact-root "${ARTIFACT_ROOT}" \
  --source-root "${SOURCE_ROOT}" --ohos-root /ohos --arch "${ARCHES[@]}"
