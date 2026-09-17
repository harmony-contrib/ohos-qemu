#!/usr/bin/env bash
# Validate the actual archive in an extracted private guest, then discard it.
set -euo pipefail
export LC_ALL=C LANG=C
if [ "$#" -ne 2 ]; then
  echo "usage: validate-package.sh PACKAGE.tar.gz EVIDENCE_DIR" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCHIVE="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$1")"
EVIDENCE="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$2")"
mkdir -p "$EVIDENCE"
rm -f "$EVIDENCE/validation.json"
case "$(basename "$ARCHIVE")" in
  *-arm64-*) ARCH=arm64; SMOKE_ARCH=aarch64 ;;
  *-armv7a-*) ARCH=armv7a; SMOKE_ARCH=armv7a ;;
  *-x86_64-*) ARCH=x86_64; SMOKE_ARCH=x86_64 ;;
  *) echo "unknown package architecture: $ARCHIVE" >&2; exit 2 ;;
esac
RUN_NATIVE=0
EXPECTED_CASES=0
if [[ "$(basename "$ARCHIVE")" == *-2in1.tar.gz ]] || [ "${NATIVE_CHILD_TEST_PHONE:-0}" = 1 ]; then
  RUN_NATIVE=1
  for tool in "${ARKDOWN:-arkdown}" "${HAP_SIGN:-hap-sign}"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "Native regression host tool missing: $tool (set ARKDOWN and HAP_SIGN)" >&2
      exit 2
    fi
  done
fi
export RUNNER_TEMP="$EVIDENCE/boot"
export QEMU_SMOKE_HDC_HOST_PORT="${QEMU_SMOKE_HDC_HOST_PORT:-5566}"
export QEMU_SMOKE_ACCEL="${QEMU_SMOKE_ACCEL:-auto}"
TARGET="127.0.0.1:${QEMU_SMOKE_HDC_HOST_PORT}"
SMOKE=(bash "$ROOT/ci/qemu-smoke/run.sh" --package "$ARCHIVE" --guest-arch "$SMOKE_ARCH"
  --host-platform macos --run-ohos-runner false
  --minimum-guest-uptime "${NATIVE_CHILD_PRE_TEST_UPTIME:-180}")
python3 - "$ARCHIVE" "$EVIDENCE/archive.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1]); h = hashlib.sha256()
with p.open('rb') as f:
    for block in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(block)
Path(sys.argv[2]).write_text(json.dumps({'archive': str(p), 'sha256': h.hexdigest(), 'size_bytes': p.stat().st_size}, indent=2) + '\n')
PY
"${SMOKE[@]}" --phase prepare
EXTRACT="$RUNNER_TEMP/ohos-qemu-smoke-macos-$SMOKE_ARCH/extract"
PACKAGE="$EXTRACT/$(basename "$ARCHIVE" .tar.gz)"
TYPE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["device_type"])' "$PACKAGE/manifest.json")"
bash "$ROOT/scripts/verify_device_type_package.sh" --package "$PACKAGE" \
  --expect-device-type "$TYPE" "--require-full-$TYPE"
python3 "$ROOT/scripts/verify_native_child_process_package.py" --package "$PACKAGE" \
  --output "$EVIDENCE/native-child-process-elf.json"
if [ "$RUN_NATIVE" = 1 ]; then
  if [ "${NATIVE_CHILD_REQUIRE_PACKAGED:-0}" = 1 ]; then
    python3 "$ROOT/scripts/native_child_process_eligibility.py" \
      "$PACKAGE/images/system.img" --require-enabled
  else
    python3 "$ROOT/ci/native-child-process/enable-private-image.py" "$PACKAGE/images/system.img"
  fi
fi
cleanup() {
  status=$?
  trap - EXIT
  if [ "$status" -ne 0 ]; then
    hdc -t "$TARGET" shell 'hilog -x' > "$EVIDENCE/hilog-on-failure.txt" 2>&1 || true
  fi
  "${SMOKE[@]}" --phase diagnostics || true
  "${SMOKE[@]}" --phase cleanup || true
  if [ "$status" -eq 0 ] && [ -f "$EVIDENCE/validation.json" ] && [ "${KEEP_TEST_IMAGE:-0}" != 1 ]; then
    rm -rf "$EXTRACT"
  fi
  exit "$status"
}
trap cleanup EXIT
"${SMOKE[@]}" --phase start
"${SMOKE[@]}" --phase wait-hdc
"${SMOKE[@]}" --phase wait-account
"${SMOKE[@]}" --phase run-binary
if [ "${NATIVE_CHILD_PRE_TEST_UPTIME:-0}" -gt 0 ]; then
  "${SMOKE[@]}" --phase wait-stable
fi
if [ "$RUN_NATIVE" = 1 ]; then
  # Eligibility was written to the freshly extracted image before boot.
  # Check the actual runtime values without relying on a guest reboot.
  settings="$(hdc -t "$TARGET" shell 'param get const.max_native_child_process; param get persist.sys.abilityms.multi_process_model' | tr -d '\r')"
  [ "$(printf '%s\n' "$settings" | sed -n '1p' | tr -d ' ')" = 50 ] &&
  [ "$(printf '%s\n' "$settings" | sed -n '2p' | tr -d ' ')" = true ] ||
    { echo "private guest child-process setup failed: $settings" >&2; exit 1; }
  UDID="$(hdc -t "$TARGET" shell 'bm get --udid' | tr -d '\r' | sed -nE 's/^[[:space:]]*([[:xdigit:]]{64})[[:space:]]*$/\1/p')"
  EXPECTED_CASES=21
  BUILD_ARGS=(--arch "$ARCH" --udid "$UDID" --output "$EVIDENCE/app")
  if [ "${NATIVE_CHILD_FOREGROUND_PROBE:-0}" = 1 ] ||
     { [ "$ARCH" = armv7a ] && [ "$TYPE" = 2in1 ]; }; then
    BUILD_ARGS+=(--foreground-probe)
  fi
  RUN_ARGS=(--device-type "$TYPE")
  if [ -n "${NATIVE_CHILD_SINGLE_CASE:-}" ]; then
    BUILD_ARGS+=(--single-case "$NATIVE_CHILD_SINGLE_CASE")
    if [ "$NATIVE_CHILD_SINGLE_CASE" = core ]; then EXPECTED_CASES=3
    else EXPECTED_CASES=2; fi
    RUN_ARGS+=(--expected-cases "$EXPECTED_CASES")
  elif [ "$ARCH" = armv7a ]; then
    RUN_ARGS+=(--isolated-cases --timeout 1800)
  fi
  python3 "$ROOT/ci/native-child-process/build.py" "${BUILD_ARGS[@]}"
  python3 "$ROOT/ci/native-child-process/run.py" --target "$TARGET" \
    --hap "$EVIDENCE/app/entry/build/default/outputs/default/entry-default-signed.hap" \
    --evidence "$EVIDENCE/native-regression" "${RUN_ARGS[@]}"
fi
"${SMOKE[@]}" --phase run-ui-switch
"${SMOKE[@]}" --phase wait-stable
python3 - "$EVIDENCE" "$TYPE" "$RUN_NATIVE" "$EXPECTED_CASES" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); result = json.loads((root / 'archive.json').read_text())
result.update(passed=True, device_type=sys.argv[2], boot=True, ui_switch=True,
              native_regression=sys.argv[3] == '1', native_regression_cases=int(sys.argv[4]))
(root / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
PY
echo "PACKAGE VALIDATION PASSED: $ARCHIVE"
