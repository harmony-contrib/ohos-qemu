#!/usr/bin/env bash
# Offline verification of deviceType metadata, source profile, and runtime files.
set -euo pipefail
export LC_ALL=C
export LANG=C
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LFS_ASSET_MAP="${SCRIPT_DIR}/../patches/common/build/github_lfs_assets/assets.tsv"

usage() {
  cat <<'USAGE'
Usage:
  verify_device_type_package.sh --package DIR [--expect-device-type TYPE]
                                [--expect-manifest-revision COMMIT]
                                [--require-full-2in1|--require-full-phone]
                                [--require-scene-window]

Checks (offline, no QEMU boot):
  1) manifest.json device_type
  2) pinned manifest/LFS baseline plus full source-profile evidence
  3) system.img ohos.para const.product.devicetype / characteristics
  4) profile-specific applications plus UI, Wukong, HNP, Launcher, and SystemUI
  5) sys_prod BMS compatibility for current QEMU system HAPs
  6) absolute-pointer guest capability and virtio-tablet launcher pairing
  7) self-contained accessibility CLI and --a11y launcher pairing
  8) userdata compressibility heuristic (dirty image warning)
USAGE
}

PACKAGE=
EXPECT=
REQUIRE_FULL_DEVICE=
REQUIRE_PC_WINDOW=0
EXPECT_MANIFEST_REVISION=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --package)
      PACKAGE="${2:-}"
      shift 2
      ;;
    --expect-device-type)
      EXPECT="${2:-}"
      shift 2
      ;;
    --expect-manifest-revision)
      EXPECT_MANIFEST_REVISION="${2:-}"
      shift 2
      ;;
    --require-full-2in1)
      REQUIRE_FULL_DEVICE=2in1
      shift
      ;;
    --require-full-phone)
      REQUIRE_FULL_DEVICE=phone
      shift
      ;;
    --require-pc-window|--require-scene-window)
      REQUIRE_PC_WINDOW=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${PACKAGE}" ]; then
  usage >&2
  exit 2
fi

PACKAGE="$(cd "${PACKAGE}" && pwd)"
FAIL=0

if ! command -v debugfs >/dev/null 2>&1; then
  for candidate in \
    /opt/homebrew/opt/e2fsprogs/sbin/debugfs \
    /usr/local/opt/e2fsprogs/sbin/debugfs
  do
    if [ -x "${candidate}" ]; then
      export PATH="$(dirname "${candidate}"):${PATH}"
      break
    fi
  done
fi

echo "== package: ${PACKAGE}"

if [ ! -f "${PACKAGE}/manifest.json" ]; then
  echo "FAIL: missing manifest.json" >&2
  exit 1
fi

MANIFEST_DT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("device_type",""))' "${PACKAGE}/manifest.json")"
MANIFEST_PROFILE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("device_type_profile",""))' "${PACKAGE}/manifest.json")"
MANIFEST_ARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("guest_arch",""))' "${PACKAGE}/manifest.json")"
case "${MANIFEST_ARCH}" in
  armv7a) ELF_MACHINE=40 ;;
  arm64) ELF_MACHINE=183 ;;
  x86_64) ELF_MACHINE=62 ;;
  *) echo "FAIL: unsupported manifest guest_arch ${MANIFEST_ARCH}" >&2; exit 1 ;;
esac
echo "manifest.device_type=${MANIFEST_DT}"
echo "manifest.device_type_profile=${MANIFEST_PROFILE:-missing}"
if [ -n "${EXPECT}" ] && [ "${MANIFEST_DT}" != "${EXPECT}" ]; then
  echo "FAIL: manifest device_type != ${EXPECT}" >&2
  FAIL=1
fi
if [ -n "${EXPECT_MANIFEST_REVISION}" ]; then
  if ! python3 - "${PACKAGE}/manifest.json" "${EXPECT_MANIFEST_REVISION}" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
expected = sys.argv[2]
baseline = manifest.get("source_baseline", {})
actual = baseline.get("manifest_revision", "")
if actual != expected:
    raise SystemExit(
        f"manifest source baseline mismatch: expected {expected}, found {actual or 'missing'}"
    )
PY
  then
    FAIL=1
  else
    echo "manifest.source_baseline.manifest_revision=${EXPECT_MANIFEST_REVISION}"
  fi
  if [ ! -f "${LFS_ASSET_MAP}" ]; then
    echo "FAIL: missing pinned GitHub/LFS asset map: ${LFS_ASSET_MAP}" >&2
    FAIL=1
  else
    EXPECTED_LFS_ASSET_MAP_SHA256="$(shasum -a 256 "${LFS_ASSET_MAP}" | awk '{print $1}')"
    ACTUAL_LFS_ASSET_MAP_SHA256="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("source_baseline", {}).get("github_lfs_assets_sha256", ""))' "${PACKAGE}/manifest.json")"
    if [ "${ACTUAL_LFS_ASSET_MAP_SHA256}" != "${EXPECTED_LFS_ASSET_MAP_SHA256}" ]; then
      echo "FAIL: package source baseline has the wrong GitHub/LFS asset map" >&2
      FAIL=1
    else
      echo "manifest.source_baseline.github_lfs_assets_sha256=${EXPECTED_LFS_ASSET_MAP_SHA256}"
    fi
    EXPECTED_QEMU_MESA_REVISION=995d2506d18924b48db0cf40e6ad7de04fc4e558
    ACTUAL_QEMU_MESA_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("source_baseline", {}).get("qemu_mesa_revision", ""))' "${PACKAGE}/manifest.json")"
    if [ "${ACTUAL_QEMU_MESA_REVISION}" != "${EXPECTED_QEMU_MESA_REVISION}" ]; then
      echo "FAIL: package source baseline has the wrong QEMU Mesa revision" >&2
      FAIL=1
    else
      echo "manifest.source_baseline.qemu_mesa_revision=${EXPECTED_QEMU_MESA_REVISION}"
    fi
  fi
fi

if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  EXPECTED_PROFILE="qemu_${REQUIRE_FULL_DEVICE}_full_source"
  EXPECTED_EFFECTIVE_PROFILE="vendor/ohemu/virt/virt_${REQUIRE_FULL_DEVICE}_full.json"
  if [ "${MANIFEST_DT}" != "${REQUIRE_FULL_DEVICE}" ] || \
     [ "${MANIFEST_PROFILE}" != "${EXPECTED_PROFILE}" ]; then
    echo "FAIL: package is not marked as a full source-built ${REQUIRE_FULL_DEVICE} profile" >&2
    FAIL=1
  fi
  if [ ! -f "${PACKAGE}/device-profile.json" ]; then
    echo "FAIL: missing device-profile.json full-build evidence" >&2
    FAIL=1
  else
    if ! python3 - "${PACKAGE}/manifest.json" "${PACKAGE}/device-profile.json" \
      "${REQUIRE_FULL_DEVICE}" "${EXPECTED_PROFILE}" "${EXPECTED_EFFECTIVE_PROFILE}" <<'PY'
import json
import re
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
profile = json.load(open(sys.argv[2], encoding="utf-8"))
device_type = sys.argv[3]
profile_name = sys.argv[4]
effective_profile = sys.argv[5]
required = set(profile.get("required_parts", []))
resolved = set(profile.get("resolved_parts", []))
checks = [
    manifest.get("device_type") == device_type,
    manifest.get("device_type_source") == "source_product_inherit",
    manifest.get("capabilities", {}).get("device_type_full") is True,
    manifest.get("capabilities", {}).get("device_type_param_only") is False,
    manifest.get("capabilities", {}).get("absolute_pointer_sync") is True,
    manifest.get("capabilities", {}).get("thread_qos") is True,
    manifest.get("capabilities", {}).get("virtual_vibrator") is True,
    manifest.get("capabilities", {}).get("virtual_vibrator_mode") == "simulated",
    manifest.get("capabilities", {}).get("jsvm") is True,
    manifest.get("capabilities", {}).get("jsvm_engine") == "ArkWeb M144 V8",
    manifest.get("capabilities", {}).get("standard_vpn") is True,
    manifest.get("capabilities", {}).get("accessibility_test") is True,
    manifest.get("capabilities", {}).get("accessibility_cli") is True,
    manifest.get("capabilities", {}).get("virtio_multitouch") is True,
    manifest.get("launcher", {}).get("pointer_device_default") == "virtio-tablet-pci",
    manifest.get("launcher", {}).get("accessibility") is True,
    manifest.get("launcher", {}).get("qmp_unix") is True,
    profile.get("device_type") == device_type,
    profile.get("profile") == profile_name,
    effective_profile in profile.get("inherit", []),
    profile.get("qemu_adaptations", {}).get("app_compatibility_parameter")
        == "const.bms.supportAppTypes=2in1,phone,default,tablet",
    profile.get("qemu_adaptations", {}).get("jsvm_engine")
        == "OpenHarmony-TPC ArkWeb M144 V8 shared library",
    "applications:prebuilt_hap" in required,
    "arkcompiler:jsvm" in required,
    bool(required),
    required <= resolved,
    profile.get("resolved_parts_count") == len(resolved),
    bool(re.fullmatch(r"[0-9a-f]{64}", profile.get("upstream_sha256", ""))),
]
if not all(checks):
    raise SystemExit(f"invalid or incomplete full {device_type} build evidence")
PY
    then
      echo "FAIL: invalid device-profile.json full-build evidence" >&2
      FAIL=1
    else
      echo "PASS: full ${REQUIRE_FULL_DEVICE} source profile evidence"
    fi
  fi
  if [ ! -f "${PACKAGE}/launch/qemu_run.sh" ] || \
     ! grep -q 'virtio-tablet-pci' "${PACKAGE}/launch/qemu_run.sh" || \
     grep -q 'virtio-mouse-pci' "${PACKAGE}/launch/qemu_run.sh"; then
    echo "FAIL: full ${REQUIRE_FULL_DEVICE} package lacks an exclusive virtio-tablet launcher" >&2
    FAIL=1
  else
    echo "PASS: absolute-pointer capability is paired with virtio-tablet"
  fi
  if [ ! -f "${PACKAGE}/launch/linux.sh" ] || \
     ! grep -q -- '--a11y' "${PACKAGE}/launch/linux.sh" || \
     ! grep -q 'virtio-multitouch-pci' "${PACKAGE}/launch/linux.sh" || \
     ! grep -q -- '-qmp' "${PACKAGE}/launch/linux.sh"; then
    echo "FAIL: full ${REQUIRE_FULL_DEVICE} package lacks the --a11y multitouch/QMP launcher" >&2
    FAIL=1
  else
    echo "PASS: accessibility capability is paired with --a11y multitouch/QMP"
  fi
fi

if ! command -v debugfs >/dev/null 2>&1; then
  if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
    echo "FAIL: debugfs is required for full ${REQUIRE_FULL_DEVICE} runtime verification" >&2
    exit 1
  fi
  echo "SKIP: debugfs not available for image inspection"
  exit "${FAIL}"
fi

dump_first_image_file() {
  local image="$1"
  local destination="$2"
  shift 2
  local path
  for path in "$@"; do
    if debugfs -R "stat ${path}" "${image}" 2>&1 | grep -q 'Inode:' && \
       debugfs -R "dump ${path} ${destination}" "${image}" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

SYSIMG="${PACKAGE}/images/system.img"
if [ ! -f "${SYSIMG}" ]; then
  echo "FAIL: missing images/system.img" >&2
  exit 1
fi

if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  KERNEL_CONFIG="${PACKAGE}/kernel.config"
  if [ ! -f "${KERNEL_CONFIG}" ]; then
    echo "FAIL: missing kernel.config QoS build evidence" >&2
    FAIL=1
  else
    for option in \
      CONFIG_AUTHORITY_CTRL=y \
      CONFIG_QOS_CTRL=y \
      CONFIG_QOS_AUTHORITY=y \
      CONFIG_QOS_POLICY_MAX_NR=6 \
      CONFIG_SCHED_LATENCY_NICE=y \
      CONFIG_UCLAMP_TASK=y \
      CONFIG_UCLAMP_TASK_GROUP=y
    do
      if ! grep -Fxq "${option}" "${KERNEL_CONFIG}"; then
        echo "FAIL: kernel.config is missing ${option}" >&2
        FAIL=1
      fi
    done
  fi
fi

echo "-- ohos.para --"
PARA="$(debugfs -R 'cat /etc/param/ohos.para' "${SYSIMG}" 2>/dev/null || true)"
if [ -z "${PARA}" ]; then
  PARA="$(debugfs -R 'cat /system/etc/param/ohos.para' "${SYSIMG}" 2>/dev/null || true)"
fi
printf '%s\n' "${PARA}" | grep -E 'const\.product\.devicetype|const\.build\.characteristics|const\.security\.developermode' || true
DT="$(printf '%s\n' "${PARA}" | sed -n 's/^const\.product\.devicetype=//p' | head -n1)"
CH="$(printf '%s\n' "${PARA}" | sed -n 's/^const\.build\.characteristics=//p' | head -n1)"
echo "parsed devicetype=${DT} characteristics=${CH}"
if [ -n "${EXPECT}" ]; then
  if [ "${DT}" != "${EXPECT}" ] || [ "${CH}" != "${EXPECT}" ]; then
    echo "FAIL: system.img deviceType params != ${EXPECT}" >&2
    FAIL=1
  else
    echo "PASS: system.img deviceType params match ${EXPECT}"
  fi
fi

echo "-- HNP artifacts --"
for path in \
  /system/bin/hnp \
  /bin/hnp \
  /system/bin/hnpcli \
  /bin/hnpcli \
  /system/lib64/libhnpapi.z.so \
  /system/lib/libhnpapi.z.so
do
  if debugfs -R "stat ${path}" "${SYSIMG}" 2>&1 | grep -q 'Inode:'; then
    echo "FOUND ${path}"
  fi
done

# List bin entries matching hnp
debugfs -R 'ls -l /system/bin' "${SYSIMG}" 2>/dev/null | grep -i hnp || echo "(no hnp* names under /system/bin listing)"
debugfs -R 'ls -l /bin' "${SYSIMG}" 2>/dev/null | grep -i hnp || true

echo "-- full device-profile runtime markers --"
RUNTIME_MARKER_FAIL=0
RUNTIME_MARKERS=(
  '/system/lib64/libui_appearance_service.z.so /system/lib/libui_appearance_service.z.so /lib64/libui_appearance_service.z.so /lib/libui_appearance_service.z.so'
  '/system/bin/wukong /bin/wukong'
  '/system/bin/hnp /bin/hnp'
  '/system/app/com.ohos.launcher/Launcher.hap /app/com.ohos.launcher/Launcher.hap'
  '/system/app/com.ohos.systemui /app/com.ohos.systemui'
  '/system/lib64/libjsvm.so /system/lib/libjsvm.so /system/lib64/ndk/libjsvm.so /system/lib/ndk/libjsvm.so /lib64/libjsvm.so /lib/libjsvm.so'
  '/system/lib64/libv8_shared.so /system/lib/libv8_shared.so /lib64/libv8_shared.so /lib/libv8_shared.so'
  '/system/bin/cli_tool/executable/ohos-a11yManager /bin/cli_tool/executable/ohos-a11yManager'
)
if [ "${REQUIRE_FULL_DEVICE}" = "2in1" ]; then
  RUNTIME_MARKERS+=(
    '/system/app/com.ohos.dlpmanager /app/com.ohos.dlpmanager'
    '/system/lib64/libdlp_permission_service.z.so /system/lib/libdlp_permission_service.z.so /lib64/libdlp_permission_service.z.so /lib/libdlp_permission_service.z.so'
  )
elif [ "${REQUIRE_FULL_DEVICE}" = "phone" ]; then
  RUNTIME_MARKERS+=(
    '/system/app/com.ohos.camera /app/com.ohos.camera'
    '/system/app/com.ohos.photos /app/com.ohos.photos'
    '/system/app/com.ohos.contacts /app/com.ohos.contacts'
    '/system/lib64/libtel_core_service.z.so /system/lib/libtel_core_service.z.so /lib64/libtel_core_service.z.so /lib/libtel_core_service.z.so'
  )
fi

echo "-- virtual vibrator VDI --"
VENDOR_IMG="${PACKAGE}/images/vendor.img"
VIBRATOR_FOUND=
if [ -f "${VENDOR_IMG}" ]; then
  for path in \
    /vendor/lib64/libhdi_product_vibrator_impl.z.so \
    /vendor/lib/libhdi_product_vibrator_impl.z.so \
    /lib64/libhdi_product_vibrator_impl.z.so \
    /lib/libhdi_product_vibrator_impl.z.so
  do
    if debugfs -R "stat ${path}" "${VENDOR_IMG}" 2>&1 | grep -q 'Inode:'; then
      VIBRATOR_FOUND="${path}"
      break
    fi
  done
fi
if [ -n "${VIBRATOR_FOUND}" ]; then
  echo "FOUND ${VIBRATOR_FOUND}"
  VIBRATOR_TMP="$(mktemp -d)"
  if ! debugfs -R "dump ${VIBRATOR_FOUND} ${VIBRATOR_TMP}/vibrator.so" \
      "${VENDOR_IMG}" >/dev/null 2>&1 || \
     ! python3 "$(dirname "$0")/verify_runtime_elf_contract.py" \
       --machine "${ELF_MACHINE}" --elf "${VIBRATOR_TMP}/vibrator.so" \
       --require-defined hdfVdiDesc; then
    echo "FAIL: QEMU virtual vibrator VDI does not export hdfVdiDesc" >&2
    FAIL=1
  else
    echo "PASS: virtual vibrator VDI exports hdfVdiDesc"
  fi
  rm -rf "${VIBRATOR_TMP}"
elif [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  echo "FAIL: vendor.img is missing the QEMU virtual vibrator VDI" >&2
  FAIL=1
fi
for candidates in "${RUNTIME_MARKERS[@]}"
do
  found=
  for path in ${candidates}; do
    if debugfs -R "stat ${path}" "${SYSIMG}" 2>&1 | grep -q 'Inode:'; then
      found="${path}"
      break
    fi
  done
  if [ -n "${found}" ]; then
    echo "FOUND ${found}"
  else
    echo "absent: ${candidates}"
    RUNTIME_MARKER_FAIL=1
  fi
done
if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  A11Y_TMP="$(mktemp -d)"
  if dump_first_image_file "${SYSIMG}" "${A11Y_TMP}/ohos-a11yManager" \
       /system/bin/cli_tool/executable/ohos-a11yManager \
       /bin/cli_tool/executable/ohos-a11yManager && \
     python3 - "${A11Y_TMP}/ohos-a11yManager" <<'PY'
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
required = (
    b"ability-enable",
    b"ability-disable",
    b"--name",
    b"--capabilities",
    b"qemu_accessibility_cli",
    b"ohos.permission.WRITE_ACCESSIBILITY_CONFIG",
    b"Failed to initialize the QEMU accessibility token",
)
missing = [value.decode() for value in required if value not in data]
if missing:
    raise SystemExit("missing accessibility CLI strings: " + ", ".join(missing))
PY
  then
    echo "PASS: generic accessibility manager CLI contract"
  else
    echo "FAIL: generic accessibility manager CLI contract" >&2
    FAIL=1
  fi
  rm -rf "${A11Y_TMP}"

  JSVM_TMP="$(mktemp -d)"
  if dump_first_image_file "${SYSIMG}" "${JSVM_TMP}/libjsvm.so" \
       /system/lib64/libjsvm.so \
       /system/lib/libjsvm.so \
       /system/lib64/ndk/libjsvm.so \
       /system/lib/ndk/libjsvm.so \
       /lib64/libjsvm.so \
       /lib/libjsvm.so && \
     dump_first_image_file "${SYSIMG}" "${JSVM_TMP}/libv8_shared.so" \
       /system/lib64/libv8_shared.so \
       /system/lib/libv8_shared.so \
       /lib64/libv8_shared.so \
       /lib/libv8_shared.so && \
     python3 "$(dirname "$0")/verify_runtime_elf_contract.py" \
       --machine "${ELF_MACHINE}" --jsvm "${JSVM_TMP}/libjsvm.so" \
       --v8 "${JSVM_TMP}/libv8_shared.so"; then
    echo "PASS: JSVM/ArkWeb M144 dynamic-symbol contract"
  else
    echo "FAIL: JSVM/ArkWeb M144 dynamic-symbol contract" >&2
    FAIL=1
  fi
  rm -rf "${JSVM_TMP}"
fi
if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  if [ "${RUNTIME_MARKER_FAIL}" -ne 0 ]; then
    echo "FAIL: full ${REQUIRE_FULL_DEVICE} runtime artifacts are incomplete" >&2
    FAIL=1
  else
    echo "PASS: full ${REQUIRE_FULL_DEVICE} runtime artifacts"
  fi
fi

echo "-- full device-profile system-application compatibility --"
SYS_PROD_IMG="${PACKAGE}/images/sys_prod.img"
APP_COMPATIBILITY_PARAMETER="const.bms.supportAppTypes=2in1,phone,default,tablet"
if [ -f "${SYS_PROD_IMG}" ]; then
  PRODUCT_PARAMS="$(debugfs -R 'cat /etc/param/product_virt.para' "${SYS_PROD_IMG}" 2>/dev/null || true)"
  if [ -z "${PRODUCT_PARAMS}" ]; then
    PRODUCT_PARAMS="$(debugfs -R 'cat /sys_prod/etc/param/product_virt.para' "${SYS_PROD_IMG}" 2>/dev/null || true)"
  fi
  if printf '%s\n' "${PRODUCT_PARAMS}" | grep -Fxq "${APP_COMPATIBILITY_PARAMETER}"; then
    echo "FOUND ${APP_COMPATIBILITY_PARAMETER}"
  elif [ -n "${REQUIRE_FULL_DEVICE}" ]; then
    echo "FAIL: sys_prod.img is missing ${APP_COMPATIBILITY_PARAMETER}" >&2
    FAIL=1
  else
    echo "absent: ${APP_COMPATIBILITY_PARAMETER}"
  fi
elif [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  echo "FAIL: missing images/sys_prod.img" >&2
  FAIL=1
else
  echo "SKIP: images/sys_prod.img is not present"
fi

if [ "${REQUIRE_PC_WINDOW}" = "1" ]; then
  if [ "${MANIFEST_DT}" != "2in1" ] || [ "${MANIFEST_PROFILE}" != "qemu_2in1_full_source" ]; then
    echo "FAIL: PC window validation requires a full 2in1 package" >&2
    FAIL=1
  fi
  if [ "$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1])).get("capabilities", {}).get("sceneboard_window_manager", False)).lower())' "${PACKAGE}/manifest.json")" != true ]; then
    echo "FAIL: SceneBoard WindowManager capability is not marked in manifest.json" >&2
    FAIL=1
  fi
  PC_WINDOW_TMP="$(mktemp -d "${TMPDIR:-/tmp}/ohos-pc-window-check.XXXXXX")"
  if ! python3 - "${PACKAGE}/device-profile.json" "${PC_WINDOW_TMP}/hashes.json" <<'PY'
import json
import re
import sys

profile = json.load(open(sys.argv[1], encoding="utf-8"))
adaptations = profile.get("qemu_adaptations", {})
board = adaptations.get("sceneboard_runtime") or {}
expected = {
    "SceneBoard.hap",
    "NotificationManagement.hap",
    "ThemeService.hap",
    "ThemeComponent.hap",
}
hashes = board.get("hap_sha256", {})
checks = [
    adaptations.get("window_architecture_feature") == "window_manager_use_sceneboard = true",
    adaptations.get("pc_window_parameter") == "const.window.multiWindowUIType=FreeFormMultiWindow",
    adaptations.get("pc_mode_parameter") == "persist.sceneboard.ispcmode=true",
    adaptations.get("boot_unlock_events") == [
        "usual.event.USER_UNLOCKED", "usual.event.SCREEN_UNLOCKED"
    ],
    adaptations.get("boot_unlock_trigger") == "bootevent.boot.completed=true",
    adaptations.get("boot_unlock_user_id") == 100,
    bool(re.fullmatch(r"[0-9a-f]{40}", board.get("native_source_revision", ""))),
    board.get("profile_valid_until", 0) > 1893456000,
    set(hashes) == expected,
    all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()),
]
if not all(checks):
    raise SystemExit("incomplete SceneBoard runtime build evidence")
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(hashes, output)
PY
  then
    echo "FAIL: SceneBoard runtime build evidence" >&2
    FAIL=1
  else
    while IFS= read -r hap; do
      expected_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "${PC_WINDOW_TMP}/hashes.json" "${hap}")"
      if dump_first_image_file "${SYSIMG}" "${PC_WINDOW_TMP}/${hap}" \
          "/system/app/SceneBoard/${hap}" "/app/SceneBoard/${hap}" && \
         [ "$(shasum -a 256 "${PC_WINDOW_TMP}/${hap}" | awk '{print $1}')" = "${expected_sha}" ]; then
        echo "PASS: SceneBoard ${hap} matches build evidence"
      else
        echo "FAIL: SceneBoard ${hap} is missing or has the wrong hash" >&2
        FAIL=1
      fi
    done <<'HAPS'
SceneBoard.hap
NotificationManagement.hap
ThemeService.hap
ThemeComponent.hap
HAPS
    if ! python3 - "${PACKAGE}/sceneboard-unlock-event.json" \
        "${PC_WINDOW_TMP}/SceneBoard.hap" <<'PY'
import hashlib
import json
import sys
from zipfile import ZipFile

evidence_path, hap_path = sys.argv[1:]
expected_legacy = "4866846a48fa6247ce48edf449fc306c5ce1a2f19f7338f6377621c5130b1549"
expected_patched = "f1ceb224f8ffa56181c5de199db9bcf7e3c25a84d4dd538f8600330019d63759"
try:
    evidence = json.load(open(evidence_path, encoding="utf-8"))
    with ZipFile(hap_path) as archive:
        actual = hashlib.sha256(archive.read("ets/modules.abc")).hexdigest()
except (FileNotFoundError, KeyError, ValueError) as exc:
    raise SystemExit(str(exc))
checks = [
    evidence.get("legacy_event") == "common.event.UNLOCK_SCREEN",
    evidence.get("ability_manager_event") == "usual.event.SCREEN_UNLOCKED",
    evidence.get("baseline_modules_abc_sha256") == expected_legacy,
    evidence.get("patched_modules_abc_sha256") == expected_patched,
    actual == expected_patched,
]
if not all(checks):
    raise SystemExit("SceneBoard unlock-event evidence does not match the installed ABC")
PY
    then
      echo "FAIL: SceneBoard does not publish the AbilityManager 7.0 screen-unlocked event" >&2
      FAIL=1
    else
      echo "PASS: SceneBoard publishes the AbilityManager 7.0 screen-unlocked event"
    fi
  fi
  if dump_first_image_file "${SYSIMG}" "${PC_WINDOW_TMP}/cem" \
       /system/bin/cem /bin/cem && \
     dump_first_image_file "${SYSIMG}" "${PC_WINDOW_TMP}/qemu_2in1_unlock.cfg" \
       /system/etc/init/qemu_2in1_unlock.cfg /etc/init/qemu_2in1_unlock.cfg && \
     python3 - "${PACKAGE}/qemu-2in1-boot-unlock.json" \
       "${PC_WINDOW_TMP}/cem" "${PC_WINDOW_TMP}/qemu_2in1_unlock.cfg" \
       "${ELF_MACHINE}" <<'PY'
import hashlib
import json
import re
import sys

evidence_path, cem_path, config_path, expected_machine = sys.argv[1:]
evidence = json.load(open(evidence_path, encoding="utf-8"))
cem = open(cem_path, "rb").read()
config_bytes = open(config_path, "rb").read()
config = json.loads(config_bytes)
if cem[:4] != b"\x7fELF" or int.from_bytes(cem[18:20], "little") != int(expected_machine):
    raise SystemExit("2in1 event publisher has the wrong ELF architecture")
if b"userId" not in cem:
    raise SystemExit("2in1 event publisher does not carry the userId Want parameter")
jobs = config.get("jobs", [])
services = config.get("services", [])
expected_paths = {
    "qemu_2in1_user_unlock": [
        "/system/bin/cem", "publish", "-e", "usual.event.USER_UNLOCKED", "-c", "100"
    ],
    "qemu_2in1_unlock": [
        "/system/bin/cem", "publish", "-e", "usual.event.SCREEN_UNLOCKED", "-u", "100"
    ],
}
checks = [
    evidence.get("schema_version") == 2,
    evidence.get("events") == [
        "usual.event.USER_UNLOCKED", "usual.event.SCREEN_UNLOCKED"
    ],
    evidence.get("user_id") == 100,
    evidence.get("trigger") == "bootevent.boot.completed=true",
    evidence.get("cem_path") == "/system/bin/cem",
    evidence.get("init_config_path") == "/system/etc/init/qemu_2in1_unlock.cfg",
    evidence.get("patched_cem_sha256") == hashlib.sha256(cem).hexdigest(),
    evidence.get("init_config_sha256") == hashlib.sha256(config_bytes).hexdigest(),
    bool(re.fullmatch(r"[0-9a-f]{64}", evidence.get("baseline_cem_sha256", ""))),
    jobs == [{
        "name": "param:bootevent.boot.completed=true",
        "condition": "bootevent.boot.completed=true",
        "cmds": ["start qemu_2in1_user_unlock", "start qemu_2in1_unlock"],
    }],
    len(services) == 2,
    {service.get("name") for service in services} == set(expected_paths),
]
for service in services:
    name = service.get("name")
    checks.extend([
        name in expected_paths,
        service.get("path") == expected_paths.get(name),
        service.get("uid") == "system",
        service.get("gid") == ["system"],
        service.get("apl") == "system_core",
        service.get("once") == 1,
        service.get("start-mode") == "condition",
        service.get("secon") == "u:r:cem:s0",
        set(service.get("permission", [])) == {
            "ohos.permission.PUBLISH_SYSTEM_COMMON_EVENT",
            "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS",
        },
    ])
if not all(checks):
    raise SystemExit("incomplete 2in1 boot-unlock publisher evidence")
PY
  then
    echo "PASS: 2in1 boot publisher sends user- and screen-unlocked events for user 100"
  else
    echo "FAIL: 2in1 boot-unlock publisher is missing or invalid" >&2
    FAIL=1
  fi
  SCENEBOARD_CONFIG="$(debugfs -R 'cat /etc/sceneboard.config' "${SYSIMG}" 2>/dev/null || true)"
  if [ "${SCENEBOARD_CONFIG}" != "ENABLED" ]; then
    echo "FAIL: SceneBoard runtime switch is not enabled" >&2
    FAIL=1
  fi
  if dump_first_image_file "${SYSIMG}" "${PC_WINDOW_TMP}/install_list.json" \
       /system/etc/app/install_list.json /etc/app/install_list.json && \
     dump_first_image_file "${SYSIMG}" "${PC_WINDOW_TMP}/install_list_capability.json" \
       /system/etc/app/install_list_capability.json /etc/app/install_list_capability.json && \
     python3 - "${PC_WINDOW_TMP}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
install = json.loads((root / "install_list.json").read_text())
capabilities = json.loads((root / "install_list_capability.json").read_text())
required = {"app_dir": "/system/app/SceneBoard", "removable": False}
signature = "8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5"
if required not in install.get("install_list", []):
    raise SystemExit("SceneBoard is missing from the system preinstall list")
if not any(entry.get("bundleName") == "com.ohos.sceneboard" and
           entry.get("app_signature") == [signature] and
           entry.get("allowAppUsePrivilegeExtension") is True
           for entry in capabilities.get("install_list", [])):
    raise SystemExit("SceneBoard is missing its privileged-extension capability")
PY
  then
    echo "PASS: SceneBoard first-boot preinstall and capabilities"
  else
    echo "FAIL: SceneBoard first-boot preinstall or capabilities are missing" >&2
    FAIL=1
  fi
  for parameter in \
    'const.window.multiWindowUIType=FreeFormMultiWindow' \
    'persist.sceneboard.ispcmode=true'; do
    if ! printf '%s\n' "${PRODUCT_PARAMS:-}" | grep -Fxq "${parameter}"; then
      echo "FAIL: PC window parameter is missing: ${parameter}" >&2
      FAIL=1
    fi
  done
  SCENEBOARD_APPFWK_PARAMS="$(debugfs -R 'cat /etc/param/appfwk.para' "${SYSIMG}" 2>/dev/null || true)"
  if [ -z "${SCENEBOARD_APPFWK_PARAMS}" ]; then
    SCENEBOARD_APPFWK_PARAMS="$(debugfs -R 'cat /system/etc/param/appfwk.para' "${SYSIMG}" 2>/dev/null || true)"
  fi
  if printf '%s\n' "${SCENEBOARD_APPFWK_PARAMS}" | \
     grep -Eq '^persist\.sys\.abilityms\.timeout_unit_time_ratio[[:space:]]*=[[:space:]]*10[[:space:]]*$'; then
    echo "PASS: SceneBoard lifecycle timeout is scaled for QEMU TCG"
  else
    echo "FAIL: 2in1 image is missing its SceneBoard lifecycle timeout scale" >&2
    FAIL=1
  fi
  if [ "${MANIFEST_ARCH}" = "armv7a" ]; then
    if python3 - "${PACKAGE}/launch/qemu_run.sh" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
display = re.search(r'case\s+"?\$\{DISPLAY_TYPE\}"?\s+in(.*?)esac', text, re.S)
headless = re.search(r'\bnone\)(.*?);;', display.group(1), re.S) if display else None
if not headless:
    raise SystemExit("missing DISPLAY_TYPE=none branch")
branch = headless.group(1)
if '-vnc 127.0.0.1:${QEMU_VNC_DISPLAY}' not in branch or '-display none' in branch:
    raise SystemExit("headless branch does not provide a loopback VNC scanout")
PY
    then
      echo "PASS: ARMv7a headless launcher provides a loopback DRM scanout"
    else
      echo "FAIL: ARMv7a headless launcher cannot provide a SceneBoard display" >&2
      FAIL=1
    fi
  fi
  rm -rf "${PC_WINDOW_TMP}"
fi

if [ -f "${PACKAGE}/images/userdata.img" ]; then
  UD_GZ="$(gzip -c -1 "${PACKAGE}/images/userdata.img" | wc -c | tr -d ' ')"
  echo "-- userdata.img gzip -1: ${UD_GZ} bytes --"
  if [ "${UD_GZ}" -gt 200000000 ]; then
    echo "WARN: userdata looks dirty (runtime-used); archive will be large" >&2
  else
    echo "PASS: userdata compressibility looks clean"
  fi
fi

if [ "${FAIL}" -ne 0 ]; then
  echo "RESULT: FAIL" >&2
  exit 1
fi
if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
  echo "RESULT: PASS (full source-built ${REQUIRE_FULL_DEVICE} profile)"
else
  echo "RESULT: PASS"
fi
