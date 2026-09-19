#!/usr/bin/env bash
# Boot a fresh 2in1 archive and exercise the WindowManager and Native child APIs.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: validate-package.sh {arm64|x86_64|armv7a} PACKAGE.tar.gz EVIDENCE_DIR" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH="$1"
ARCHIVE="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
EVIDENCE="$(mkdir -p "$3" && cd "$3" && pwd)"
BINDINGS_EXAMPLES="${BINDINGS_EXAMPLES:-}"
if [ ! -f "$ARCHIVE" ] || [ ! -x "$BINDINGS_EXAMPLES/scripts/run-ohostest.sh" ]; then
  echo "archive missing or BINDINGS_EXAMPLES is not set to the PR #156 examples-ui directory" >&2
  exit 2
fi
case "$ARCH" in
  arm64) SMOKE_ARCH=aarch64; TEST_ARCH=arm64 ;;
  x86_64) SMOKE_ARCH=x86_64; TEST_ARCH=x64 ;;
  armv7a) SMOKE_ARCH=armv7a; TEST_ARCH=arm ;;
  *) echo "unsupported architecture: $ARCH" >&2; exit 2 ;;
esac
export RUNNER_TEMP="$EVIDENCE/boot"
export QEMU_SMOKE_HDC_HOST_PORT="${QEMU_SMOKE_HDC_HOST_PORT:-5566}"
export QEMU_SMOKE_ACCEL="${QEMU_SMOKE_ACCEL:-tcg}"
export QEMU_QMP_SOCKET="/tmp/ohos-wm-qmp-${ARCH}-$$.sock"
export HDC_TARGET="127.0.0.1:$QEMU_SMOKE_HDC_HOST_PORT"
export E2E_DIAGNOSTICS_DIR="$EVIDENCE/ohostest"
export WINDOW_MANAGER_GRANT_SCREEN_CAPTURE=1
export ARKDOWN="${ARKDOWN:-$BINDINGS_EXAMPLES/node_modules/.bin/arkdown}"
export HAP_SIGN="${HAP_SIGN:-$BINDINGS_EXAMPLES/.tools/hapsigner-0.2.0/bin/hap-sign}"
mkdir -p "$E2E_DIAGNOSTICS_DIR" "$EVIDENCE/tmp"
export TMPDIR="$EVIDENCE/tmp"
SMOKE=(bash "$ROOT/ci/qemu-smoke/run.sh" --package "$ARCHIVE" \
  --guest-arch "$SMOKE_ARCH" --host-platform macos --run-ohos-runner false \
  --account-wait-attempts 600)

"${SMOKE[@]}" --phase prepare > "$EVIDENCE/prepare.log" 2>&1
cleanup() {
  status=$?
  trap - EXIT
  "${SMOKE[@]}" --phase diagnostics > "$EVIDENCE/diagnostics.log" 2>&1 || true
  "${SMOKE[@]}" --phase cleanup > "$EVIDENCE/cleanup.log" 2>&1 || true
  if [ -n "${wake_pid:-}" ]; then
    kill "$wake_pid" 2>/dev/null || true
    wait "$wake_pid" 2>/dev/null || true
  fi
  rm -f "$QEMU_QMP_SOCKET"
  exit "$status"
}
trap cleanup EXIT

PACKAGE="$RUNNER_TEMP/ohos-qemu-smoke-macos-$SMOKE_ARCH/extract/$(basename "$ARCHIVE" .tar.gz)"
bash "$ROOT/scripts/verify_device_type_package.sh" --package "$PACKAGE" \
  --expect-device-type 2in1 --require-full-2in1 --require-scene-window \
  > "$EVIDENCE/package-check.log" 2>&1
python3 "$ROOT/scripts/verify_native_child_process_package.py" --package "$PACKAGE" \
  --output "$EVIDENCE/native-elf.json" > "$EVIDENCE/native-elf.log" 2>&1
python3 "$ROOT/scripts/native_child_process_eligibility.py" \
  "$PACKAGE/images/system.img" --require-enabled > "$EVIDENCE/eligibility.log" 2>&1

"${SMOKE[@]}" --phase start > "$EVIDENCE/start.log" 2>&1
python3 "$ROOT/ci/window-manager/qmp-wake.py" "$QEMU_QMP_SOCKET" \
  > "$EVIDENCE/qmp-wake.log" 2>&1 &
wake_pid=$!
"${SMOKE[@]}" --phase wait-hdc > "$EVIDENCE/wait-hdc.log" 2>&1
hdc -t "$HDC_TARGET" shell 'power-shell timeout -o 86400000; power-shell wakeup' \
  > "$EVIDENCE/keep-awake.log" 2>&1
"${SMOKE[@]}" --phase wait-account > "$EVIDENCE/wait-account.log" 2>&1
# HDC and the foreground account become ready before SceneBoard has registered
# with DMS. Wait for that registration on every architecture before sending
# the unlock gesture. ARMv7a additionally needs a non-zero desktop work area.
scene_ready=0
: > "$EVIDENCE/sceneboard-readiness.log"
for attempt in $(seq 1 300); do
  display_state="$(hdc -t "$HDC_TARGET" shell \
    'hidumper -s DisplayManagerService -a "-a"' 2>/dev/null || true)"
  printf '\n-- attempt %s --\n%s\n' "$attempt" "$display_state" \
    >> "$EVIDENCE/sceneboard-readiness.log"
  if printf '%s\n' "$display_state" | grep -Eq '\[ScbPid:\][[:space:]]+[1-9][0-9]*'; then
    if [ "$ARCH" != armv7a ] || \
       printf '%s\n' "$display_state" | grep -Eq 'AvailableArea<X,Y,W,H>[[:space:]]+0,[[:space:]]*[1-9][0-9]*,'; then
      scene_ready=1
      break
    fi
  fi
  sleep 2
done
if [ "$scene_ready" -ne 1 ]; then
  echo "$ARCH SceneBoard did not register a usable display" >&2
  exit 1
fi
# The QEMU-specific publishers send USER_UNLOCKED and SCREEN_UNLOCKED after
# boot completion, when AbilityManager has subscribed and the foreground
# account is ready. AbilityManager requires both before removing its first-boot
# UI-ability interceptor.
# ScreenLockSystemAbility can keep reporting the state of the headless virtual
# lock surface, so retain that state only as diagnostics. The four API cases
# below prove that AbilityManager accepted the event and launched the test UI
# ability, and that SceneBoard then created a usable window.
hdc -t "$HDC_TARGET" shell \
  'hidumper -s 3704 -a "-all" | grep -E "screenState|screenLocked|deviceLocked|interactiveState"' \
  > "$EVIDENCE/screenlock-state.txt" 2>&1 || true
hdc -t "$HDC_TARGET" shell \
  'hilog -x -e "USER_UNLOCKED|SCREEN_UNLOCKED|on screen unlocked|ScreenUnlock|qemu_2in1_.*unlock|common event"' \
  > "$EVIDENCE/boot-unlock-event.log" 2>&1 || true
hdc -t "$HDC_TARGET" shell \
  'param get const.window.multiWindowUIType; param get persist.sceneboard.ispcmode; param get persist.sys.abilityms.timeout_unit_time_ratio; cat /etc/sceneboard.config; ps -A | grep -i sceneboard; param get const.max_native_child_process; param get persist.sys.abilityms.multi_process_model' \
  > "$EVIDENCE/sceneboard-runtime.txt" 2>&1
rg -q 'FreeFormMultiWindow' "$EVIDENCE/sceneboard-runtime.txt"
rg -q 'ENABLED' "$EVIDENCE/sceneboard-runtime.txt"
rg -q -i 'sceneboard' "$EVIDENCE/sceneboard-runtime.txt"
hdc -t "$HDC_TARGET" shell 'bm dump -n com.ohos.sceneboard' \
  > "$EVIDENCE/sceneboard-bundle.txt" 2>&1
export HAP_SIGN_DEVICE_ID="$(hdc -t "$HDC_TARGET" shell 'bm get --udid' | tr -d '\r' | sed -nE 's/^[[:space:]]*([[:xdigit:]]{64})[[:space:]]*$/\1/p')"
test "${#HAP_SIGN_DEVICE_ID}" -eq 64

bash "$BINDINGS_EXAMPLES/scripts/run-ohostest.sh" --arch "$TEST_ARCH" window_manager \
  > "$EVIDENCE/window-manager-ohostest.log" 2>&1
hdc -t "$HDC_TARGET" shell 'hilog -x -e WINDOW_MANAGER_' > "$EVIDENCE/hilog.txt" 2>&1
rg 'WINDOW_MANAGER_(API|CALLBACK)_REPORT' "$EVIDENCE/hilog.txt" \
  > "$EVIDENCE/window-manager-reports.txt"
rg -q 'WINDOW_MANAGER_API_REPORT .*properties=ok;.*frame_redraw=ok' "$EVIDENCE/window-manager-reports.txt"
rg -q 'WINDOW_MANAGER_CALLBACK_REPORT snapshot_callbacks=1;.*unregister_frame_callback=ok' "$EVIDENCE/window-manager-reports.txt"

BUILD_ARGS=(--arch "$ARCH" --udid "$HAP_SIGN_DEVICE_ID" --output "$EVIDENCE/native-app")
RUN_ARGS=(--target "$HDC_TARGET" --evidence "$EVIDENCE/native-regression" \
  --device-type 2in1 --timeout 1800)
if [ "$ARCH" = armv7a ]; then
  BUILD_ARGS+=(--foreground-probe)
  RUN_ARGS+=(--isolated-cases)
fi
python3 "$ROOT/ci/native-child-process/build.py" "${BUILD_ARGS[@]}" \
  > "$EVIDENCE/native-build.log" 2>&1
python3 "$ROOT/ci/native-child-process/run.py" "${RUN_ARGS[@]}" \
  --hap "$EVIDENCE/native-app/entry/build/default/outputs/default/entry-default-signed.hap" \
  > "$EVIDENCE/native-run.log" 2>&1

python3 - "$ARCHIVE" "$EVIDENCE" "$ARCH" "$HDC_TARGET" <<'PY'
import hashlib, json, sys
from pathlib import Path
archive, evidence = map(Path, sys.argv[1:3])
native = json.loads((evidence / 'native-regression/result.json').read_text())
assert native['passed'] and native['expected_cases'] == 21
ohostest = (evidence / 'ohostest/ohostest-window_manager.log').read_text()
assert ohostest.count('OHOS_REPORT_STATUS_CODE: 0') == 4
assert 'OHOS_REPORT_STATUS_CODE: -1' not in ohostest
assert 'OHOS_REPORT_STATUS_CODE: -2' not in ohostest
digest = hashlib.sha256()
with archive.open('rb') as stream:
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        digest.update(block)
(evidence / 'validation.json').write_text(json.dumps({
    'passed': True, 'architecture': sys.argv[3], 'device_type': '2in1',
    'archive': str(archive), 'archive_sha256': digest.hexdigest(),
    'window_manager_cases': 4, 'native_child_cases': 21,
    'target': sys.argv[4],
}, indent=2) + '\n')
PY
echo "WindowManager and Native child package validation passed: $ARCHIVE"
