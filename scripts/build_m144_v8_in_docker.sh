#!/usr/bin/env bash
# Build V8 from the same complete, locked release graph as ArkWebCore.
set -euo pipefail
main() {
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEPOT_TOOLS_UPDATE=0
WORK_ROOT="${M144_WORK_ROOT:-/workspace/release}"
SOURCE_ROOT="${WORK_ROOT}/src"
ARTIFACT_ROOT="${M144_ARTIFACT_ROOT:-/artifacts}"
OHOS_ROOT="${OHOS_ROOT:-/ohos}"
BUILD_JOBS="${M144_BUILD_JOBS:-4}"
SKIP_APT="${M144_SKIP_APT:-0}"
ARCHES=("$@")
[ "${#ARCHES[@]}" -gt 0 ] || { echo "specify at least one V8 architecture" >&2; exit 2; }
for arch in "${ARCHES[@]}"; do
  case "${arch}" in arm|arm64|x86_64) ;; *) echo "unsupported V8 architecture" >&2; exit 2 ;; esac
done
[ "${M144_GN_ONLY:-0}" = 1 ] || [ ! -e "${ARTIFACT_ROOT}/manifest.json" ] || {
  echo "refusing to overwrite previously recorded V8 artifacts; select a new artifact root" >&2; exit 1;
}
mkdir -p "${ARTIFACT_ROOT}"
python3 /work/scripts/prepare_m144_release_sources.py --verify-only --work-root "${WORK_ROOT}" \
  --evidence "${ARTIFACT_ROOT}/release-source-pins-${M144_RELEASE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}.json"
DEPOT="${SOURCE_ROOT}/third_party/depot_tools"
export PATH="${DEPOT}:${PATH}"
CHROMIUM_CLANG="${SOURCE_ROOT}/third_party/llvm-build/Release+Asserts/bin/clang"
[ -x "${CHROMIUM_CLANG}" ] || { echo "locked release compiler missing" >&2; exit 1; }
[ "$("${SOURCE_ROOT}/third_party/node/linux/node-linux-x64/bin/node" --version)" = v24.11.1 ]
ensure_arm_snapshot_host_toolchain() {
  local arch
  local needs_i386=0
  for arch in "${ARCHES[@]}"; do
    if [ "${arch}" = arm ]; then
      needs_i386=1
      break
    fi
  done
  if [ "${needs_i386}" = 0 ]; then
    return
  fi

  local clangxx="${CHROMIUM_CLANG}++"
  local probe=/tmp/ohos-qemu-m144-i386-probe
  if printf '#include <asm/errno.h>\nint main() { return 0; }\n' | \
     "${clangxx}" --target=i386-unknown-linux-gnu -x c++ - -o "${probe}" \
       >/dev/null 2>&1; then
    rm -f "${probe}"
    echo "ArkWeb M144 arm snapshot host toolchain: i386 multilib ready"
    return
  fi
  rm -f "${probe}"

  if [ "${SKIP_APT}" = 1 ]; then
    echo "ArkWeb M144 arm requires gcc-multilib and g++-multilib" >&2
    exit 1
  fi
  if [ "$(id -u)" != 0 ] || ! command -v apt-get >/dev/null 2>&1; then
    echo "cannot install the i386 multilib toolchain required by M144 arm" >&2
    exit 1
  fi

  echo "install ArkWeb M144 arm snapshot host dependencies"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends gcc-multilib g++-multilib
  printf '#include <asm/errno.h>\nint main() { return 0; }\n' | \
    "${clangxx}" --target=i386-unknown-linux-gnu -x c++ - -o "${probe}"
  rm -f "${probe}"
}

ensure_arm_snapshot_host_toolchain

SDK_NATIVE="${OHOS_ROOT}/prebuilts/ohos-sdk/linux/26.0.0/native"
[ -x "${SDK_NATIVE}/llvm/bin/clang" ] || {
  echo "OpenHarmony API 26 native SDK is missing: ${SDK_NATIVE}" >&2
  exit 1
}
if [ ! -f "${WORK_ROOT}/qemu-core-sdk-api26/preparation-evidence.json" ]; then
  python3 /work/scripts/prepare_m144_core_sdk.py --source-root "${SOURCE_ROOT}" --ohos-root "${OHOS_ROOT}"
fi
python3 /work/scripts/build_m144_sdk_bti_runtimes.py --source /m144-tool-sources/sdk-llvm15 \
  --sdk "${WORK_ROOT}/qemu-core-sdk-api26/native" \
  --original-sdk "${SDK_NATIVE}"

ARKWEB_BUILD_ROOT="${SOURCE_ROOT}/arkweb/build"
mkdir -p "${WORK_ROOT}/arkweb-prepare-log"
bash /work/patches/common/web/arkweb/m144_v8_shared/apply.sh \
  --source-root "${WORK_ROOT}"
PREPARE_OUTPUT="${WORK_ROOT}/arkweb-prepare-log/prepare.stdout.log"
if ! bash "${ARKWEB_BUILD_ROOT}/prepare.sh" \
  "${WORK_ROOT}/arkweb-prepare-log" >"${PREPARE_OUTPUT}" 2>&1; then
  tail -200 "${PREPARE_OUTPUT}" >&2
  exit 1
fi
if [ ! -f "${SOURCE_ROOT}/arkweb/glue/BUILD.gn" ]; then
  echo "ArkWeb prepare did not generate ohos_glue" >&2
  exit 1
fi

# The CEF checkout deliberately does not track translator outputs such as
# cef_paths.gypi. Chromium's OpenHarmony BUILD files import CEF targets even
# when enable_cef=false, so generate the pinned checkout's metadata once just
# as ArkWeb's official build wrapper does.
if [ ! -f "${SOURCE_ROOT}/cef/cef_paths.gypi" ]; then
  (
    cd "${SOURCE_ROOT}/cef/tools"
    bash ./translator.sh
  )
fi

GN="${SOURCE_ROOT}/third_party/depot_tools/gn"
NINJA="${SOURCE_ROOT}/third_party/depot_tools/ninja"
STRIP="${SDK_NATIVE}/llvm/bin/llvm-strip"
[ -x "${NINJA}" ] || { echo "Chromium ninja is missing: ${NINJA}" >&2; exit 1; }
[ -x "${STRIP}" ] || { echo "OpenHarmony llvm-strip is missing: ${STRIP}" >&2; exit 1; }

mkdir -p "${ARTIFACT_ROOT}/v8" "${ARTIFACT_ROOT}/v8-include"
for arch in "${ARCHES[@]}"; do
  case "${arch}" in
    arm)
      target_cpu=arm
      product_name=rk3568
      pointer_compression=false
      pointer_compression_shared_cage=false
      ;;
    arm64)
      target_cpu=arm64
      product_name=rk3568
      pointer_compression=true
      pointer_compression_shared_cage=true
      ;;
    x86_64)
      target_cpu=x64
      product_name=all
      pointer_compression=true
      pointer_compression_shared_cage=true
      ;;
  esac
  out_dir="out/m144_${arch}"
  gn_args="
    target_os=\"ohos\"
    target_cpu=\"${target_cpu}\"
    product_name=\"${product_name}\"
    is_debug=false
    is_official_build=true
    is_component_build=false
    is_chrome_branded=false
    use_official_google_api_keys=false
    use_ozone=true
    use_aura=true
    enable_message_center=true
    ozone_auto_platforms=false
    ozone_platform=\"headless\"
    ozone_platform_headless=true
    use_alsa=false
    use_bluez=false
    use_cups=false
    use_dbus=false
    use_gio=false
    use_glib=false
    use_gtk=false
    use_kerberos=false
    use_libpci=false
    use_nss_certs=false
    use_pangocairo=false
    use_pulseaudio=false
    use_udev=false
    rtc_use_pipewire=false
    use_bundled_fontconfig=true
    use_sysroot=false
    use_musl=true
    use_ohos_sdk_sysroot=false
    clang_base_path=\"//third_party/llvm-build/Release+Asserts\"
    clang_use_chrome_plugins=false
    llvm_ohos_mainline=true
    use_remoteexec=false
    treat_warnings_as_errors=false
    fatal_linker_warnings=false
    build_chromium_with_ohos_src=false
    enable_arkweb=true
    arkweb_unittests=false
    enable_cef=false
    enable_ohos_nweb_hap=true
    v8_component_build=true
    use_custom_libcxx=true
    use_custom_libcxx_for_host=true
    v8_enable_pointer_compression=${pointer_compression}
    v8_enable_pointer_compression_shared_cage=${pointer_compression_shared_cage}
    v8_enable_sandbox=false
    v8_use_external_startup_data=false
    v8_deprecation_warnings=false
    v8_use_libm_trig_functions=false
    v8_enable_i18n_support=true
    icu_use_data_file=false
    v8_enable_builtins_optimization=false
    cppgc_enable_slim_write_barrier=false
    v8_enable_pointer_compression_8gb=false
    symbol_level=1"

  echo "generate ArkWeb M144 V8 build: ${arch}"
  (
    cd "${SOURCE_ROOT}"
    "${GN}" gen "${out_dir}" --root-target=//v8:v8_shared \
      --args="${gn_args}"
  )
  if [ "${M144_GN_ONLY:-0}" = 1 ]; then continue; fi
  "${NINJA}" -C "${SOURCE_ROOT}/${out_dir}" -j "${BUILD_JOBS}" v8:v8_shared

  unstripped="${SOURCE_ROOT}/${out_dir}/lib.unstripped/libv8_shared.so"
  if [ ! -s "${unstripped}" ]; then
    unstripped="${SOURCE_ROOT}/${out_dir}/libv8_shared.so"
  fi
  [ -s "${unstripped}" ] || {
    echo "v8_shared output is missing for ${arch}: ${SOURCE_ROOT}/${out_dir}" >&2
    exit 1
  }
  arch_root="${ARTIFACT_ROOT}/v8/${arch}"
  [ ! -e "${arch_root}" ] || { echo "refusing to replace existing V8 output: ${arch_root}" >&2; exit 1; }
  mkdir -p "${arch_root}/lib.unstripped_v8/lib.unstripped"
  cp "${SOURCE_ROOT}/${out_dir}/args.gn" "${arch_root}/args.gn"
  install -m 0644 "${unstripped}" \
    "${arch_root}/lib.unstripped_v8/lib.unstripped/libv8_shared.so"
  "${STRIP}" --strip-unneeded "${unstripped}" -o "${arch_root}/libv8_shared.so"
done

if [ "${M144_GN_ONLY:-0}" = 1 ]; then
  echo 'Prepared explicit pinned dependency GN graphs, not V8 artifacts'
  return 0
fi

[ ! -e "${ARTIFACT_ROOT}/v8-include/v8-include" ] || { echo "refusing to replace existing public V8 headers" >&2; exit 1; }
mkdir -p "${ARTIFACT_ROOT}/v8-include/v8-include"
cp -a "${SOURCE_ROOT}/v8/include/." \
  "${ARTIFACT_ROOT}/v8-include/v8-include/"

python3 - "${ARTIFACT_ROOT}" "${SOURCE_ROOT}" \
  /work/patches/common/web/arkweb/m144_v8_shared <<'PY'
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

artifact_root = Path(sys.argv[1])
source_root = Path(sys.argv[2])
patch_root = Path(sys.argv[3])

def revision(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()

def commit_date(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "show", "-s", "--format=%cI", "HEAD"],
        text=True,
    ).strip()

records = {}
for library in sorted((artifact_root / "v8").glob("*/**/libv8_shared.so")):
    relative = library.relative_to(artifact_root).as_posix()
    records[relative] = {
        "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "size": library.stat().st_size,
    }

headers = artifact_root / "v8-include/v8-include"
header_digest = hashlib.sha256()
for header in sorted(path for path in headers.rglob("*") if path.is_file()):
    header_digest.update(header.relative_to(headers).as_posix().encode())
    header_digest.update(b"\0")
    header_digest.update(header.read_bytes())

manifest = {
    "schema_version": 1,
    "engine": "ArkWeb M144 V8",
    "chromium_milestone": 144,
    "chromium_revision": revision(source_root),
    "v8_revision": revision(source_root / "v8"),
    "arkweb_revision": revision(source_root / "arkweb"),
    "cef_revision": revision(source_root / "cef"),
    "webview_revision": revision(source_root / "arkweb/deps_code/webview"),
    "source_commit_date": commit_date(source_root),
    "ohos_sdk_api": 26,
    "runtime_configuration": {"v8_enable_i18n_support": True, "icu_use_data_file": False,
                              "v8_use_external_startup_data": False},
    "build_args_sha256": {str(path.relative_to(artifact_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted((artifact_root / "v8").glob("*/args.gn"))},
    "libcxx_abi_namespace": "__h",
    "libcxx_abi_version": 1,
    "build_target": "v8:v8_shared",
    "source_patches": sorted(path.name for path in patch_root.glob("*.patch")),
    "source_patch_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(patch_root.glob("*.patch"))},
    "headers_sha256": header_digest.hexdigest(),
    "artifacts": records,
}
(artifact_root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

VALIDATE=(--artifact-root "${ARTIFACT_ROOT}")
for arch in "${ARCHES[@]}"; do VALIDATE+=(--arch "${arch}"); done
python3 /work/patches/common/arkcompiler/jsvm/validate_artifacts.py "${VALIDATE[@]}"
echo "ArkWeb M144 V8 artifacts are ready: ${ARTIFACT_ROOT}"

}
main "$@"
