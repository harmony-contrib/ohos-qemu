#!/usr/bin/env bash
# Build the QEMU Vulkan ICD from the pinned ArkWeb/Chromium M144 checkout.
set -euo pipefail

WORK_ROOT="${M144_WORK_ROOT:-/workspace/release}"
SOURCE_ROOT="${WORK_ROOT}/src"
ARTIFACT_ROOT="${M144_SWIFTSHADER_ARTIFACT_ROOT:-/artifacts}"
BUILD_JOBS="${M144_BUILD_JOBS:-$(nproc)}"
CHROMIUM_REVISION=a8168622b056f25c2e68d5f12fe2759bad2d9a44
V8_REVISION=bb352490a41083cfb4fba0fadcb0c5099f4aafa7
ARKWEB_REVISION=f3d904432cc1c57468f2b7fe01979d25e0157581

# build_m144_v8.sh leaves an SDK symlink under src/ohos_sdk pointing into
# /ohos. The ICD build needs the same pinned source/SDK volume, not a host seed.
for header in native_window/external_window.h native_buffer/native_buffer.h; do
  [ -f "${SOURCE_ROOT}/ohos_sdk/openharmony/native/sysroot/usr/include/${header}" ] || {
    echo "M144 NativeWindow SDK header is missing: ${header}; mount the pinned source at /ohos" >&2
    exit 1
  }
done

for specification in \
  "${SOURCE_ROOT}:${CHROMIUM_REVISION}" \
  "${SOURCE_ROOT}/v8:${V8_REVISION}" \
  "${SOURCE_ROOT}/arkweb:${ARKWEB_REVISION}"; do
  repository="${specification%:*}"
  revision="${specification#*:}"
  [ "$(git -C "${repository}" rev-parse HEAD)" = "${revision}" ] || {
    echo "M144 revision mismatch: ${repository}" >&2
    exit 1
  }
done

bash /work/patches/common/web/arkweb/m144_swiftshader/apply.sh \
  --source-root "${WORK_ROOT}"

ARCHES=("$@")
if [ "${#ARCHES[@]}" -eq 0 ]; then
  ARCHES=(arm arm64 x86_64)
fi
for arch in "${ARCHES[@]}"; do
  case "${arch}" in
    arm) target_cpu=arm ;;
    arm64) target_cpu=arm64 ;;
    x86_64) target_cpu=x64 ;;
    *) echo "unsupported SwiftShader architecture: ${arch}" >&2; exit 2 ;;
  esac
  out_dir="${SOURCE_ROOT}/out/m144_${arch}"
  args="${out_dir}/args.gn"
  [ -f "${args}" ] || {
    echo "M144 GN output is missing for ${arch}; build M144 V8 first: ${args}" >&2
    exit 1
  }
  grep -Eq "^target_os = \"ohos\"$" "${args}" || {
    echo "M144 GN output is not configured for OpenHarmony: ${args}" >&2
    exit 1
  }
  grep -Eq "^target_cpu = \"${target_cpu}\"$" "${args}" || {
    echo "M144 GN output has the wrong architecture: ${args}" >&2
    exit 1
  }
  "${SOURCE_ROOT}/third_party/depot_tools/ninja" -C "${out_dir}" -j "${BUILD_JOBS}" \
    third_party/swiftshader/src/Vulkan:swiftshader_libvulkan
  binary="${out_dir}/libvk_swiftshader.so"
  [ -s "${binary}" ] || {
    echo "M144 SwiftShader ICD is missing: ${binary}" >&2
    exit 1
  }
  readelf -d "${binary}" | grep -q NODELETE || {
    echo "M144 SwiftShader ICD is missing NODELETE: ${binary}" >&2
    exit 1
  }
  install -D -m 0644 "${binary}" \
    "${ARTIFACT_ROOT}/${arch}/libvk_swiftshader.so"
done

python3 - "${ARTIFACT_ROOT}" "${SOURCE_ROOT}" \
  /work/patches/common/web/arkweb/m144_swiftshader <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

artifact_root, source_root, patch_root = map(Path, sys.argv[1:])
libraries = sorted(artifact_root.glob("*/libvk_swiftshader.so"))
artifacts = {
    library.relative_to(artifact_root).as_posix(): {
        "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "size": library.stat().st_size,
    }
    for library in libraries
}
manifest = {
    "schema_version": 1,
    "engine": "ArkWeb M144 SwiftShader Vulkan ICD",
    "chromium_milestone": 144,
    "chromium_revision": subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip(),
    "v8_revision": subprocess.check_output(
        ["git", "-C", str(source_root / "v8"), "rev-parse", "HEAD"], text=True
    ).strip(),
    "arkweb_revision": subprocess.check_output(
        ["git", "-C", str(source_root / "arkweb"), "rev-parse", "HEAD"], text=True
    ).strip(),
    "build_target": "third_party/swiftshader/src/Vulkan:swiftshader_libvulkan",
    "source_patches": sorted(path.name for path in patch_root.glob("*.patch")),
    "source_patch_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(patch_root.glob("*.patch"))},
    "artifacts": artifacts,
}
(artifact_root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
python3 /work/scripts/verify_m144_swiftshader_artifacts.py --artifact-root "${ARTIFACT_ROOT}" --arch "${ARCHES[@]}"
