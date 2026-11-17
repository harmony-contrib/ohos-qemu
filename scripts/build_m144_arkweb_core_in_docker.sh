#!/usr/bin/env bash
# One architecture at a time: actual official full-engine native build, not V8.
set -euo pipefail
main() {
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEPOT_TOOLS_UPDATE=0
[ "$#" = 1 ] || { echo "specify one architecture: arm, arm64 or x86_64" >&2; exit 2; }
case "$1" in
  arm) BUILD_PRODUCT=rk3568 ;;
  arm64) BUILD_PRODUCT=rk3568_64 ;;
  x86_64) BUILD_PRODUCT=x86_64 ;;
  *) echo "unsupported full ArkWeb architecture: $1" >&2; exit 2 ;;
esac
ARCH="$1"
WORK_ROOT="${M144_WORK_ROOT:-/workspace/release}"
SOURCE_ROOT="${WORK_ROOT}/src"
OHOS_ROOT="${OHOS_ROOT:-/ohos}"
ARTIFACT_ROOT="${M144_CORE_ARTIFACT_ROOT:-/artifacts}"
BUILD_JOBS="${M144_CORE_BUILD_JOBS:-2}"
case "${BUILD_JOBS}" in 1|2|3|4|5|6|7|8|9|10|11|12) ;; *) echo "full-core build uses 1 to 12 jobs" >&2; exit 2 ;; esac
OUTPUT="${ARTIFACT_ROOT}/${ARCH}"
mkdir -p "${OUTPUT}"
[ ! -e "${OUTPUT}/native-build-inputs.json" ] && [ ! -e "${OUTPUT}/native-build-evidence.json" ] || \
  { echo "refusing to overwrite prior core build inputs/evidence" >&2; exit 1; }
FROZEN="${OUTPUT}/frozen-build-inputs"
mkdir "${FROZEN}"
python3 /work/scripts/snapshot_build_inputs.py --source /work --destination "${FROZEN}"
python3 "${FROZEN}/scripts/prepare_m144_release_sources.py" --verify-only \
  --work-root "${WORK_ROOT}" --evidence "${OUTPUT}/release-source-pins.json"
NODE_ARCHIVE="${SOURCE_ROOT}/third_party/node/linux/node-linux-x64.tar.gz"
NODE_BINARY="${SOURCE_ROOT}/third_party/node/linux/node-linux-x64/bin/node"
if [ ! -x "${NODE_BINARY}" ]; then
  # This exact GCS object is pinned by the fixed Chromium DEPS. A nohooks
  # source preparation can retain the archive without its executable.
  [ "$(sha256sum "${NODE_ARCHIVE}" | awk '{print $1}')" = \
    f1becee9a78f65a094d17f9116727069aab5b235d4c9977346dbf8251a66a5db ] || \
    { echo "pinned Chromium Node archive differs" >&2; exit 1; }
  tar --skip-old-files -xzf "${NODE_ARCHIVE}" -C "${SOURCE_ROOT}/third_party/node/linux"
fi
[ "$("${NODE_BINARY}" --version)" = v24.11.1 ] || { echo "Chromium Node version differs" >&2; exit 1; }
# SecureC is now an actual locked release-manifest project, not a symlink
# supplied by an earlier V8 build or an unrelated OHOS source checkout.
if [ "${M144_CORE_SKIP_APT:-0}" != 1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends libglib2.0-dev libnss3-dev libdbus-1-dev \
    libatk1.0-dev libatk-bridge2.0-dev libcups2-dev libx11-dev libxcomposite-dev \
    libxdamage-dev libxext-dev libxfixes-dev libxrandr-dev libgbm-dev libasound2-dev \
    libpango1.0-dev libdrm-dev libxkbcommon-dev gcc-multilib g++-multilib jq openjdk-17-jdk-headless
fi
pkg-config --exists glib-2.0 gmodule-2.0 gobject-2.0 gthread-2.0 nss dbus-1
SDK_EVIDENCE="${WORK_ROOT}/qemu-core-sdk-api26/preparation-evidence.json"
python3 "${FROZEN}/scripts/prepare_m144_core_sdk.py" --source-root "${SOURCE_ROOT}" \
  --ohos-root "${OHOS_ROOT}" --complete-components
python3 "${FROZEN}/scripts/build_m144_sdk_bti_runtimes.py" --source /m144-tool-sources/sdk-llvm15 \
  --sdk "${WORK_ROOT}/qemu-core-sdk-api26/native" \
  --original-sdk "${OHOS_ROOT}/prebuilts/ohos-sdk/linux/26.0.0/native"
cp "${WORK_ROOT}/qemu-core-sdk-api26/bti-runtime-evidence.json" "${OUTPUT}/sdk-bti-runtime-evidence.json"
cp "${M144_TOOL_EVIDENCE:?fixed tool preparation must run before the native builder}" "${OUTPUT}/release-tools-evidence.json"
cp "${M144_HAP_TOOL_EVIDENCE:?paired HAP tools must pass preflight}" "${OUTPUT}/hap-host-tools-native.json"
python3 - "${SDK_EVIDENCE}" "${SOURCE_ROOT}" "${OHOS_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
evidence, source, ohos = map(Path, sys.argv[1:])
data = json.loads(evidence.read_text())
sdk = Path(data['private_sdk'])
if data['sdk_metadata']['apiVersion'] != '26' or data['sdk_metadata']['version'] != '26.0.0.39':
    raise SystemExit('invalid release SDK preparation evidence')
for name, record in data['components'].items():
    original = ohos / 'prebuilts/ohos-sdk/linux/26.0.0' / name
    if (record['source'] != str(original) or
            hashlib.sha256((original / 'oh-uni-package.json').read_bytes()).hexdigest() != record['metadata_sha256'] or
            (source / 'ohos_sdk/openharmony' / name).resolve() != (sdk / name).resolve()):
        raise SystemExit('prepared SDK input/layout changed: ' + name)
PY
if [ -L "${WORK_ROOT}/build" ] && \
   [ "$(readlink "${WORK_ROOT}/build")" = "${SOURCE_ROOT}/arkweb/build" ]; then
  # Recover only the exact earlier QEMU-owned layout; retain the prior alias.
  [ ! -e "${WORK_ROOT}/build.pre-core-layout-link" ] && \
    [ ! -L "${WORK_ROOT}/build.pre-core-layout-link" ]
  mv "${WORK_ROOT}/build" "${WORK_ROOT}/build.pre-core-layout-link"
  ln -s "${SOURCE_ROOT}/arkweb/build/build" "${WORK_ROOT}/build"
fi
[ -f "${WORK_ROOT}/build/config_to_gn.py" ] || { echo "official build layout is incomplete" >&2; exit 1; }
DEPOT="${SOURCE_ROOT}/third_party/depot_tools"
export PATH="${DEPOT}:${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64/bin:${PATH}"
PATCH_SCRIPT="${FROZEN}/patches/common/web/arkweb/m144_window_contract/apply_with_core_build.sh"
bash "${PATCH_SCRIPT}" --source-root "${WORK_ROOT}"
export ARKWEB_PREPARED_SDK=1 ARKWEB_EXTRA_BUILD_PATCH_SCRIPT="${PATCH_SCRIPT}"
RUST_VERSION="$("${SOURCE_ROOT}/third_party/rust-toolchain/bin/rustc" --version)"
RUST_GN_VERSION="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${RUST_VERSION}")"
HOST_ARGS="clang_base_path=\"//third_party/llvm-build/Release+Asserts\" rust_sysroot_absolute=\"//third_party/rust-toolchain\" rustc_version=${RUST_GN_VERSION} use_remoteexec=false"
cd "${WORK_ROOT}"
BUILD_COMMAND=(bash "${SOURCE_ROOT}/arkweb/build/build.sh" -t n -A -without-nweb-ex -j "${BUILD_JOBS}" -G "${HOST_ARGS}" "${BUILD_PRODUCT}")
python3 - "${OUTPUT}/native-build-inputs.json" "${ARCH}" "${SDK_EVIDENCE}" "${FROZEN}" "${SOURCE_ROOT}" "${OHOS_ROOT}" "${BUILD_COMMAND[@]}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import subprocess
path, arch, sdk, frozen, source, ohos, *argv = sys.argv[1:]
roots = {'chromium': Path(source), 'v8': Path(source) / 'v8', 'arkweb': Path(source) / 'arkweb',
         'cef': Path(source) / 'cef', 'webview': Path(source) / 'arkweb/deps_code/webview',
         'depot_tools': Path(source) / 'third_party/depot_tools',
         'webrtc': Path(source) / 'third_party/webrtc', 'securec': Path(source) / 'third_party/bounds_checking_function'}
pins = {name: subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        for name, root in roots.items()}
diffs = {name: hashlib.sha256(subprocess.check_output(['git', '-C', str(root), 'diff', '--binary', 'HEAD'])).hexdigest()
         for name, root in roots.items()}
manifest = Path(frozen) / 'build-inputs.json'
Path(path).write_text(json.dumps({'scope': 'official_full_engine_native_candidate_NOT_HAP_or_guest_acceptance',
    'arch': arch, 'argv': argv, 'sdk_evidence_sha256': hashlib.sha256(Path(sdk).read_bytes()).hexdigest(),
    'source_pins': pins, 'frozen_inputs': frozen,
    'release_source_graph_sha256': hashlib.sha256((Path(path).parent / 'release-source-pins.json').read_bytes()).hexdigest(),
    'sdk_bti_runtime_evidence_sha256': hashlib.sha256((Path(path).parent / 'sdk-bti-runtime-evidence.json').read_bytes()).hexdigest(),
    'release_tools_evidence_sha256': hashlib.sha256((Path(path).parent / 'release-tools-evidence.json').read_bytes()).hexdigest(),
    'hap_host_tools_evidence_sha256': hashlib.sha256((Path(path).parent / 'hap-host-tools-native.json').read_bytes()).hexdigest(),
    'source_tracked_diffs_sha256_before_official_prepare': diffs,
    'frozen_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
    'frozen_tree_sha256': json.loads(manifest.read_text())['tree_sha256'],
    'first_artifact_behavior_gate_passed': False}, indent=2) + '\n')
PY
set +e
"${BUILD_COMMAND[@]}" >"${OUTPUT}/native-build.log" 2>&1
BUILD_RESULT="$?"
set -e
python3 - "${OUTPUT}" "${SOURCE_ROOT}/out/${BUILD_PRODUCT}" "${BUILD_RESULT}" "${ARCH}" "${SOURCE_ROOT}" "${OHOS_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import struct
import sys
import subprocess
import shutil
output, native, code = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
expected = {'arm': (1, 40), 'arm64': (2, 183), 'x86_64': (2, 62)}[sys.argv[4]]
source, ohos = map(Path, sys.argv[5:7])
roots = {'chromium': source, 'v8': source / 'v8', 'arkweb': source / 'arkweb', 'cef': source / 'cef',
         'webview': source / 'arkweb/deps_code/webview', 'depot_tools': source / 'third_party/depot_tools',
         'webrtc': source / 'third_party/webrtc', 'securec': source / 'third_party/bounds_checking_function'}
inputs = json.loads((output / 'native-build-inputs.json').read_text())
pins = {name: subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        for name, root in roots.items()}
diffs = {name: hashlib.sha256(subprocess.check_output(['git', '-C', str(root), 'diff', '--binary', 'HEAD'])).hexdigest()
         for name, root in roots.items()}
artifacts = {}
failures = []
if pins != inputs['source_pins']:
    failures.append('pinned source revision changed during native build')
for name in ('libadapter_ndk_stub.so', 'libarkweb_engine.so', 'libarkweb_render.so', 'libarkweb_crashpad_handler.so', 'libffmpeg.so'):
    path = native / name
    if path.is_file():
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        artifacts[name] = {'path': str(path), 'sha256': digest.hexdigest(), 'size': path.stat().st_size}
        with path.open('rb') as stream:
            header = stream.read(64)
        if (len(header) < 64 or header[:7] != b'\x7fELF' + bytes((expected[0], 1, 1))
                or struct.unpack_from('<HH', header, 16) != (3, expected[1])):
            failures.append('wrong actual native ELF ABI: ' + name)
    else:
        failures.append('missing actual native library: ' + name)
if code == 0 and not failures:
    archived = output / 'native-libraries'
    archived.mkdir()
    for name, record in artifacts.items():
        destination = archived / name
        shutil.copy2(native / name, destination)
        if (destination.stat().st_size != record['size'] or
                hashlib.sha256(destination.read_bytes()).hexdigest() != record['sha256']):
            failures.append('archived native output differs: ' + name)
result = {'scope': 'actual_official_full_engine_native_build_NOT_signed_HAP_or_guest_acceptance',
          'exit_code': code, 'artifacts': artifacts, 'failures': failures,
          'source_pins': pins, 'source_tracked_diffs_sha256_after_official_prepare': diffs,
          'native_inputs_sha256': hashlib.sha256((output / 'native-build-inputs.json').read_bytes()).hexdigest(),
          'first_artifact_behavior_gate_passed': False}
(output / 'native-build-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
if code == 0 and failures:
    raise SystemExit('official native command returned success without required actual-ABI libraries')
PY
echo "full ArkWeb native build: arch=${ARCH} exit=${BUILD_RESULT}; HAP/runtime still require validation"
exit "${BUILD_RESULT}"
}
main "$@"
