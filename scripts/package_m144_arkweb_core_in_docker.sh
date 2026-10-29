#!/usr/bin/env bash
# Package one already-built public M144 core through the official HAP entry.
set -euo pipefail
main() {
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEPOT_TOOLS_UPDATE=0
[ "$#" = 1 ] || { echo "specify one architecture: arm, arm64 or x86_64" >&2; exit 2; }
case "$1" in
  arm) BUILD_PRODUCT=rk3568; GUARD_ARCH=armv7a ;;
  arm64) BUILD_PRODUCT=rk3568_64; GUARD_ARCH=arm64 ;;
  x86_64) BUILD_PRODUCT=x86_64; GUARD_ARCH=x86_64 ;;
  *) echo "unsupported full ArkWeb architecture: $1" >&2; exit 2 ;;
esac
ARCH="$1"
WORK_ROOT="${M144_WORK_ROOT:-/workspace/release}"
SOURCE_ROOT="${WORK_ROOT}/src"
ARTIFACT_ROOT="${M144_CORE_ARTIFACT_ROOT:-/artifacts}"
OUTPUT="${ARTIFACT_ROOT}/${ARCH}"
OHOS_ROOT="${OHOS_ROOT:-/ohos}"
[ -f "${OUTPUT}/native-build-evidence.json" ] || { echo "actual native build must pass first" >&2; exit 1; }
[ ! -e "${OUTPUT}/package-build-inputs.json" ] && [ ! -e "${OUTPUT}/package-build-evidence.json" ] || \
  { echo "refusing to overwrite previous HAP evidence" >&2; exit 1; }
python3 - "${OUTPUT}" "${SOURCE_ROOT}/out/${BUILD_PRODUCT}" "${SOURCE_ROOT}" "${OHOS_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import subprocess
output, native, source, ohos = map(Path, sys.argv[1:])
result = json.loads((output / 'native-build-evidence.json').read_text())
if result.get('exit_code') != 0 or result.get('failures') or len(result.get('artifacts', {})) != 5:
    raise SystemExit('native build evidence is incomplete or failed')
inputs = json.loads((output / 'native-build-inputs.json').read_text())
if hashlib.sha256((output / 'native-build-inputs.json').read_bytes()).hexdigest() != result.get('native_inputs_sha256'):
    raise SystemExit('native build input provenance changed')
frozen = Path(inputs['frozen_inputs'])
manifest = frozen / 'build-inputs.json'
if hashlib.sha256(manifest.read_bytes()).hexdigest() != inputs['frozen_manifest_sha256']:
    raise SystemExit('native frozen manifest changed')
document = json.loads(manifest.read_text())
for name, digest in document['files_sha256'].items():
    if hashlib.sha256((frozen / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('native frozen input changed: ' + name)
roots = {'chromium': source, 'v8': source / 'v8', 'arkweb': source / 'arkweb', 'cef': source / 'cef',
         'webview': source / 'arkweb/deps_code/webview', 'depot_tools': source / 'third_party/depot_tools',
         'webrtc': source / 'third_party/webrtc', 'securec': source / 'third_party/bounds_checking_function'}
pins = {name: subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        for name, root in roots.items()}
diffs = {name: hashlib.sha256(subprocess.check_output(['git', '-C', str(root), 'diff', '--binary', 'HEAD'])).hexdigest()
         for name, root in roots.items()}
if pins != result.get('source_pins') or diffs != result.get('source_tracked_diffs_sha256_after_official_prepare'):
    raise SystemExit('actual source revisions/patches changed since the validated native build')
if hashlib.sha256((output / 'release-source-pins.json').read_bytes()).hexdigest() != inputs.get('release_source_graph_sha256'):
    raise SystemExit('complete release source graph evidence changed')
import sys as _sys
_sys.path.insert(0, str(frozen / 'scripts'))
from prepare_m144_release_cache import load_lock
from prepare_m144_release_sources import check_pins
actual_graph = check_pins(source.parent, load_lock(frozen / 'scripts/m144_release_source_lock.json'))
if actual_graph != json.loads((output / 'release-source-pins.json').read_text())['source_pins']:
    raise SystemExit('complete actual release source graph changed since native build')
for name, record in result['artifacts'].items():
    path = native / name
    if Path(record['path']).resolve() != path.resolve() or path.stat().st_size != record['size']:
        raise SystemExit('native architecture/output differs: ' + name)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != record['sha256']:
        raise SystemExit('native input changed before packaging: ' + name)
PY
NATIVE_FROZEN="$(python3 - "${OUTPUT}/native-build-inputs.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))['frozen_inputs'])
PY
)"
FROZEN="${OUTPUT}/hap-build-inputs"
mkdir "${FROZEN}"
mkdir -p "${FROZEN}/patches/common/web/arkweb"
cp -a "${NATIVE_FROZEN}/patches/lib" "${FROZEN}/patches/lib"
for component in m144_v8_shared m144_core_build m144_webrtc_thread_id m144_media_document_binding m144_window_contract m144_private_contract m144_angle_includes m144_adapter_header_format m144_core_package; do
  cp -a "${NATIVE_FROZEN}/patches/common/web/arkweb/${component}" "${FROZEN}/patches/common/web/arkweb/"
done
cp -a "${NATIVE_FROZEN}/scripts/verify_arkweb_core_image.py" "${NATIVE_FROZEN}/scripts/verify_alsa_config_image.py" \
  "${NATIVE_FROZEN}/scripts/verify_runtime_elf_contract.py" \
  "${NATIVE_FROZEN}/scripts/ext_image_entries.py" "${FROZEN}/"
PATCH_SCRIPT="${FROZEN}/patches/common/web/arkweb/m144_core_package/apply_core_and_package.sh"
bash "${PATCH_SCRIPT}" --source-root "${WORK_ROOT}"
export ARKWEB_PREPARED_SDK=1 ARKWEB_EXTRA_BUILD_PATCH_SCRIPT="${PATCH_SCRIPT}"
export PATH="${SOURCE_ROOT}/third_party/depot_tools:${PATH}"
HOST_ARGS="$(python3 - "${OUTPUT}/native-build-inputs.json" <<'PY'
import json
import sys
argv = json.load(open(sys.argv[1]))['argv']
print(argv[argv.index('-G') + 1])
PY
)"
BUILD_JOBS="${M144_CORE_BUILD_JOBS:-2}"
case "${BUILD_JOBS}" in 1|2|3|4|5|6|7|8) ;; *) echo "HAP validation uses 1 to 8 jobs" >&2; exit 2 ;; esac
BUILD_COMMAND=(bash "${SOURCE_ROOT}/arkweb/build/build.sh" -t w -A -without-nweb-ex -j "${BUILD_JOBS}" -G "${HOST_ARGS}" "${BUILD_PRODUCT}")
cp "${M144_HAP_TOOL_EVIDENCE:?paired HAP tools must pass preflight}" "${OUTPUT}/hap-host-tools-package.json"
python3 - "${OUTPUT}" "${FROZEN}" "${BUILD_COMMAND[@]}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
output, frozen = map(Path, sys.argv[1:3])
result = {'scope': 'official_public_core_HAP_build_inputs_NOT_guest_acceptance', 'argv': sys.argv[3:],
          'native_evidence_sha256': hashlib.sha256((output / 'native-build-evidence.json').read_bytes()).hexdigest(),
          'hap_host_tools_evidence_sha256': hashlib.sha256((output / 'hap-host-tools-package.json').read_bytes()).hexdigest(),
          'frozen_inputs_sha256': {str(path.relative_to(frozen)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in frozen.rglob('*') if path.is_file()},
          'first_artifact_behavior_gate_passed': False}
(output / 'package-build-inputs.json').write_text(json.dumps(result, indent=2) + '\n')
PY
cd "${WORK_ROOT}"
set +e
"${BUILD_COMMAND[@]}" >"${OUTPUT}/package-build.log" 2>&1
BUILD_RESULT="$?"
set -e
if [ "${BUILD_RESULT}" = 0 ]; then
  SIGNED_HAP="${SOURCE_ROOT}/out/${BUILD_PRODUCT}/NWeb-${BUILD_PRODUCT}.hap"
  python3 "${FROZEN}/verify_arkweb_core_image.py" --hap "${SIGNED_HAP}" --arch "${GUARD_ARCH}" \
    --output "${OUTPUT}/source-hap-abi-evidence.json" >"${OUTPUT}/source-hap-abi.log" 2>&1 || BUILD_RESULT="$?"
fi
if [ "${BUILD_RESULT}" = 0 ]; then
  java -jar "${SOURCE_ROOT}/ohos_sdk/26/toolchains/lib/hap-sign-tool.jar" verify-app \
    -inFile "${SIGNED_HAP}" -outCertChain "${OUTPUT}/verified-app-cert.cer" \
    -outProfile "${OUTPUT}/verified-app-profile.p7b" >"${OUTPUT}/verify-app.log" 2>&1 || BUILD_RESULT="$?"
  grep -Fq 'verify-app success' "${OUTPUT}/verify-app.log" || BUILD_RESULT=1
fi
if [ "${BUILD_RESULT}" = 0 ]; then
  python3 "${NATIVE_FROZEN}/scripts/verify_m144_hap_native_transform.py" \
    --artifact-directory "${OUTPUT}" --source-root "${SOURCE_ROOT}" --ohos-root "${OHOS_ROOT}" \
    --product "${BUILD_PRODUCT}" --arch "${ARCH}" --signed-hap "${SIGNED_HAP}" \
    --unsigned-hap "${SOURCE_ROOT}/out/${BUILD_PRODUCT}/ohos_nweb.hap" --repository "${NATIVE_FROZEN}" \
    >"${OUTPUT}/hap-native-transform.log" 2>&1 || BUILD_RESULT="$?"
fi
if [ "${BUILD_RESULT}" = 0 ]; then
  cp "${WORK_ROOT}/qemu-core-sdk-api26/preparation-evidence.json" "${OUTPUT}/sdk-preparation-evidence.json"
  python3 - "${OUTPUT}" "${SOURCE_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys
output, source = map(Path, sys.argv[1:])
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
records = {}
for name in ('BUILD.gn', 'add_kernel_permission.py', 'encaps.json', 'llvm-objcopy'):
    relative = 'third_party/ohos_nweb_hap/' + name
    actual = (source / relative).read_bytes()
    locked = subprocess.check_output(['git', '-C', str(source), 'show', revision + ':' + relative])
    if actual != locked:
        raise SystemExit('official HAP transformation input changed: ' + name)
    records[relative] = hashlib.sha256(actual).hexdigest()
(output / 'kernel-permission-input.json').write_text(json.dumps({
    'scope': 'unchanged_official_HAP_kernelpermission_input',
    'source_revision': revision, 'files_sha256': records,
    'note': 'Official add_kernel_permission_hap adds the unchanged .kernelpermission section to the engine. Final HAP hashes are distinct from pre-HAP native build hashes.'}, indent=2) + '\n')
PY
fi
python3 - "${OUTPUT}" "${BUILD_RESULT}" "${SOURCE_ROOT}/out/${BUILD_PRODUCT}/NWeb-${BUILD_PRODUCT}.hap" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import sys
output, code, hap = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
result = {'scope': 'official_source_HAP_packaging_ABI_and_signature_NOT_guest_acceptance',
          'exit_code': code, 'first_artifact_behavior_gate_passed': False, 'arkweb_behavior_validated': False}
if code == 0:
    target = output / 'ArkWebCore.hap'
    if target.exists():
        raise SystemExit('refusing to replace existing source HAP')
    shutil.copy2(hap, target)
    result.update(hap=str(target), hap_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
(output / 'package-build-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
PY
if [ "${BUILD_RESULT}" = 0 ]; then
  python3 /work/scripts/m144_core_artifacts.py --artifact-root "${ARTIFACT_ROOT}" --arch "${ARCH}" --record \
    >"${OUTPUT}/core-artifact-record.log" 2>&1 || BUILD_RESULT="$?"
fi
echo "public ArkWebCore HAP: arch=${ARCH} exit=${BUILD_RESULT}; new guest acceptance remains required"
exit "${BUILD_RESULT}"
}
main "$@"
