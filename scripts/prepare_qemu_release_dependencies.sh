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
  llvm_recipe="$(python3 "${script_dir}/qemu_mesa_llvm_artifacts.py" --recipe-hash)"
  export QEMU_MESA_LLVM_ARTIFACTS="${QEMU_MESA_LLVM_ARTIFACTS:-${cache_root}/artifacts/qemu-mesa-llvm/${llvm_recipe}}"
  frontend="${script_dir}/run_m144_release_build_docker.sh"
  if [ "${arch}" = arm ] && [ ! -f "${QEMU_ARKWEB_CORE_ARTIFACTS}/${arch}/core-artifact.json" ]; then
    source_volume="${M144_RELEASE_SOURCE_VOLUME:-ohos-qemu-arkweb-7_0-release-source}"
    ohos_volume="${DOCKER_SOURCE_VOLUME:-ohos-qemu-7_0-release-source}"
    bash "${frontend}" prepare "${arch}"
    docker run --rm --platform "${DOCKER_PLATFORM:-linux/amd64}" \
      --mount "type=volume,src=${source_volume},dst=/workspace" \
      --mount "type=volume,src=${ohos_volume},dst=/ohos,readonly" \
      "${DOCKER_IMAGE:-ohos-qemu-m144-build-env:7.0-release}" bash -lc '
        set -euo pipefail
        if [ -f /workspace/release/src/third_party/rust-toolchain/lib/rustlib/i686-unknown-linux-gnu/lib/libstd-0000000000000001.rlib ]; then
          exit 0
        fi
        cd /workspace/release/src
        rm -rf out/rk3568_i686_rust_bootstrap
        ./buildtools/linux64/gn gen out/rk3568_i686_rust_bootstrap --args="target_os=\"ohos\" target_cpu=\"arm\" product_name=\"rk3568\" is_debug=false is_official_build=true is_component_build=false use_musl=true use_ohos_sdk_sysroot=false build_chromium_with_ohos_src=false clang_base_path=\"//third_party/llvm-build/Release+Asserts\" clang_use_chrome_plugins=false llvm_ohos_mainline=true enable_rust=true enable_rust_cxx=true enable_chromium_prelude=true rust_sysroot_absolute=\"\" use_remoteexec=false"
        targets=$(grep -h "^build clang_x86_v8_arm/local_rustc_sysroot/lib/rustlib/i686-unknown-linux-gnu/lib/lib.*\\.rlib:" out/rk3568_i686_rust_bootstrap/clang_x86_v8_arm/obj/build/rust/std/rules/*.ninja | sed "s/^build //; s/:.*//")
        ./third_party/depot_tools/ninja -C out/rk3568_i686_rust_bootstrap -j "${M144_BUILD_JOBS:-6}" $targets
        mkdir -p third_party/rust-toolchain/lib/rustlib/i686-unknown-linux-gnu/lib
        python3 - << "PY"
from pathlib import Path
import shutil
src_dir = Path("out/rk3568_i686_rust_bootstrap/clang_x86_v8_arm/local_rustc_sysroot/lib/rustlib/i686-unknown-linux-gnu/lib")
dst_dir = Path("third_party/rust-toolchain/lib/rustlib/i686-unknown-linux-gnu/lib")
for rlib in sorted(src_dir.glob("lib*.rlib")):
    stem = rlib.stem[3:]
    half = len(stem) // 2
    crate = stem[:half]
    shutil.copy2(rlib, dst_dir / f"lib{crate}-0000000000000001.rlib")
PY
        rm -rf out/rk3568_i686_rust_bootstrap
      '
  fi
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
  if [ ! -f "${QEMU_MESA_LLVM_ARTIFACTS}/$1/manifest.json" ]; then
    QEMU_MESA_LLVM_ARTIFACT_OUTPUT="${QEMU_MESA_LLVM_ARTIFACTS}/$1" \
      bash "${script_dir}/build_qemu_mesa_llvm_in_docker.sh" "$1"
  fi
  python3 "${script_dir}/qemu_mesa_llvm_artifacts.py" \
    --artifact-root "${QEMU_MESA_LLVM_ARTIFACTS}/$1" --product "$1"
}
main "$@"
