#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

WORK_ROOT="${M144_WORK_ROOT:-/workspace}"
SOURCE_ROOT="${WORK_ROOT}/src"
ARTIFACT_ROOT="${M144_ARTIFACT_ROOT:-/artifacts}"
OHOS_ROOT="${OHOS_ROOT:-/ohos}"
BUILD_JOBS="${M144_BUILD_JOBS:-$(nproc)}"
SYNC_JOBS="${M144_SYNC_JOBS:-8}"
SKIP_SYNC="${M144_SKIP_SYNC:-0}"
SKIP_APT="${M144_SKIP_APT:-0}"

CHROMIUM_REVISION=4ae5a7f106cdf9d3f42acd1c6ab007140dcd249f
V8_REVISION=1170083e0a717f67cead0abe20900f273ae01fb5
ARKWEB_REVISION=eff888fcd48ce0aa4dc4bf7b2474ed77f0353fa2
CEF_REVISION=d154063ab448260480a75a4e755a18aaf0baf7c4
WEBVIEW_REVISION=93dce838eea694887c707c28b3f4f0fa85f87326
DEPOT_TOOLS_REVISION=2e88a3f08bd8c4a0014eae82729beca935f7f188

ARCHES=("$@")
if [ "${#ARCHES[@]}" -eq 0 ]; then
  ARCHES=(arm arm64 x86_64)
fi
for arch in "${ARCHES[@]}"; do
  case "${arch}" in arm|arm64|x86_64) ;; *)
    echo "unsupported V8 architecture: ${arch}" >&2
    exit 2
    ;;
  esac
done
case "${SKIP_APT}" in 0|1) ;; *)
  echo "M144_SKIP_APT must be 0 or 1" >&2
  exit 2
esac

for repository in "${SOURCE_ROOT}" "${SOURCE_ROOT}/v8" \
  "${SOURCE_ROOT}/arkweb" "${SOURCE_ROOT}/cef" \
  "${SOURCE_ROOT}/arkweb/deps_code/webview"; do
  [ -d "${repository}/.git" ] || {
    echo "M144 repository is missing: ${repository}" >&2
    exit 1
  }
done
[ "$(git -C "${SOURCE_ROOT}" rev-parse HEAD)" = "${CHROMIUM_REVISION}" ] || {
  echo "chromium_src revision mismatch" >&2; exit 1;
}
[ "$(git -C "${SOURCE_ROOT}/v8" rev-parse HEAD)" = "${V8_REVISION}" ] || {
  echo "chromium_v8 revision mismatch" >&2; exit 1;
}
[ "$(git -C "${SOURCE_ROOT}/arkweb" rev-parse HEAD)" = "${ARKWEB_REVISION}" ] || {
  echo "chromium_arkweb revision mismatch" >&2; exit 1;
}
[ "$(git -C "${SOURCE_ROOT}/cef" rev-parse HEAD)" = "${CEF_REVISION}" ] || {
  echo "chromium_cef revision mismatch" >&2; exit 1;
}
[ "$(git -C "${SOURCE_ROOT}/arkweb/deps_code/webview" rev-parse HEAD)" = "${WEBVIEW_REVISION}" ] || {
  echo "OpenHarmony webview revision mismatch" >&2; exit 1;
}

if [ ! -d "${WORK_ROOT}/depot_tools/.git" ]; then
  git clone --filter=blob:none https://chromium.googlesource.com/chromium/tools/depot_tools.git \
    "${WORK_ROOT}/depot_tools"
fi
git -C "${WORK_ROOT}/depot_tools" fetch --depth=1 origin "${DEPOT_TOOLS_REVISION}"
git -C "${WORK_ROOT}/depot_tools" checkout --detach "${DEPOT_TOOLS_REVISION}"
if [ ! -f "${WORK_ROOT}/depot_tools/python3_bin_reldir.txt" ]; then
  (
    cd "${WORK_ROOT}/depot_tools"
    # Pinned depot_tools does not bootstrap its Python when auto-update is
    # disabled. GN's wrapper requires this pointer before its first launch.
    # shellcheck disable=SC1091
    source ./bootstrap_python3
    bootstrap_python3
  )
fi
export PATH="${WORK_ROOT}/depot_tools:${PATH}"
export DEPOT_TOOLS_UPDATE=0

python3 - "${WORK_ROOT}/.gclient" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_text(
    """solutions = [{
  'name': 'src',
  'url': 'https://github.com/OpenHarmony-TPC/chromium_src.git',
  'managed': False,
  'custom_deps': {'src/v8': None},
  'custom_vars': {
    'checkout_configuration': 'small',
    'checkout_linux': True,
    'checkout_android': False,
    'checkout_fuchsia': False,
  },
}]
target_os = ['linux']
target_os_only = True
""",
    encoding="utf-8",
)
PY

if [ "${SKIP_SYNC}" != "1" ]; then
  (
    cd "${WORK_ROOT}"
    gclient sync --nohooks --no-history --shallow --jobs "${SYNC_JOBS}"
  )
fi

if [ ! -x "${WORK_ROOT}/depot_tools/gn" ]; then
  echo "pinned depot_tools did not provision Chromium GN" >&2
  exit 1
fi

CHROMIUM_CLANG="${SOURCE_ROOT}/third_party/llvm-build/Release+Asserts/bin/clang"
if [ ! -x "${CHROMIUM_CLANG}" ]; then
  (
    cd "${SOURCE_ROOT}"
    python3 tools/clang/scripts/update.py
  )
fi

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
mkdir -p "${SOURCE_ROOT}/ohos_sdk/openharmony"
if [ -e "${SOURCE_ROOT}/ohos_sdk/openharmony/native" ] || \
   [ -L "${SOURCE_ROOT}/ohos_sdk/openharmony/native" ]; then
  rm -rf "${SOURCE_ROOT}/ohos_sdk/openharmony/native"
fi
ln -s "${SDK_NATIVE}" "${SOURCE_ROOT}/ohos_sdk/openharmony/native"

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

GN="${WORK_ROOT}/depot_tools/gn"
NINJA="${WORK_ROOT}/depot_tools/ninja"
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
    v8_enable_i18n_support=false
    v8_enable_builtins_optimization=false
    cppgc_enable_slim_write_barrier=false
    v8_enable_pointer_compression_8gb=false
    symbol_level=1"

  echo "generate ArkWeb M144 V8 build: ${arch}"
  (
    cd "${SOURCE_ROOT}"
    "${GN}" gen "${out_dir}" --root-target=//v8:v8_shared \
      --args="${gn_args}"
    "${NINJA}" -C "${out_dir}" -j "${BUILD_JOBS}" v8:v8_shared
  )

  unstripped="${SOURCE_ROOT}/${out_dir}/lib.unstripped/libv8_shared.so"
  if [ ! -s "${unstripped}" ]; then
    unstripped="${SOURCE_ROOT}/${out_dir}/libv8_shared.so"
  fi
  [ -s "${unstripped}" ] || {
    echo "v8_shared output is missing for ${arch}: ${SOURCE_ROOT}/${out_dir}" >&2
    exit 1
  }
  arch_root="${ARTIFACT_ROOT}/v8/${arch}"
  rm -rf "${arch_root}"
  mkdir -p "${arch_root}/lib.unstripped_v8/lib.unstripped"
  install -m 0644 "${unstripped}" \
    "${arch_root}/lib.unstripped_v8/lib.unstripped/libv8_shared.so"
  "${STRIP}" --strip-unneeded "${unstripped}" -o "${arch_root}/libv8_shared.so"
done

rm -rf "${ARTIFACT_ROOT}/v8-include/v8-include"
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
    "build_target": "v8:v8_shared",
    "source_patches": sorted(path.name for path in patch_root.glob("*.patch")),
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
