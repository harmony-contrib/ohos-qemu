#!/usr/bin/env bash
# Offline verification of deviceType metadata, source profile, and runtime files.
set -euo pipefail
export LC_ALL=C
export LANG=C

usage() {
  cat <<'USAGE'
Usage:
  verify_device_type_package.sh --package DIR [--expect-device-type TYPE]
                                [--require-full-2in1|--require-full-phone]

Checks (offline, no QEMU boot):
  1) manifest.json device_type
  2) full source-profile evidence and resolved parts (when required)
  3) system.img ohos.para const.product.devicetype / characteristics
  4) profile-specific applications plus UI, Wukong, HNP, Launcher, and SystemUI
  5) sys_prod BMS compatibility for current QEMU system HAPs
  6) absolute-pointer guest capability and virtio-tablet launcher pairing
  7) userdata compressibility heuristic (dirty image warning)
USAGE
}

PACKAGE=
EXPECT=
REQUIRE_FULL_DEVICE=

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
    --require-full-2in1)
      REQUIRE_FULL_DEVICE=2in1
      shift
      ;;
    --require-full-phone)
      REQUIRE_FULL_DEVICE=phone
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
echo "manifest.device_type=${MANIFEST_DT}"
echo "manifest.device_type_profile=${MANIFEST_PROFILE:-missing}"
if [ -n "${EXPECT}" ] && [ "${MANIFEST_DT}" != "${EXPECT}" ]; then
  echo "FAIL: manifest device_type != ${EXPECT}" >&2
  FAIL=1
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
    manifest.get("launcher", {}).get("pointer_device_default") == "virtio-tablet-pci",
    profile.get("device_type") == device_type,
    profile.get("profile") == profile_name,
    effective_profile in profile.get("inherit", []),
    profile.get("qemu_adaptations", {}).get("app_compatibility_parameter")
        == "const.bms.supportAppTypes=2in1,phone,default,tablet",
    "applications:prebuilt_hap" in required,
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
fi

if ! command -v debugfs >/dev/null 2>&1; then
  if [ -n "${REQUIRE_FULL_DEVICE}" ]; then
    echo "FAIL: debugfs is required for full ${REQUIRE_FULL_DEVICE} runtime verification" >&2
    exit 1
  fi
  echo "SKIP: debugfs not available for image inspection"
  exit "${FAIL}"
fi

SYSIMG="${PACKAGE}/images/system.img"
if [ ! -f "${SYSIMG}" ]; then
  echo "FAIL: missing images/system.img" >&2
  exit 1
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
