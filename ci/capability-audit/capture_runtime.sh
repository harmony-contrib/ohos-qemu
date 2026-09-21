#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: capture_runtime.sh --target HOST:PORT --device phone|2in1 --arch ARCH --output DIR

Capture a read-only runtime inventory from one booted OpenHarmony package.
The output is evidence for capability triage; it is not itself proof that an
API works.
EOF
}

TARGET=
DEVICE=
ARCH=
OUTPUT=
HDC="${HDC:-/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:?missing target}"; shift 2 ;;
    --device) DEVICE="${2:?missing device}"; shift 2 ;;
    --arch) ARCH="${2:?missing arch}"; shift 2 ;;
    --output) OUTPUT="${2:?missing output}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "${DEVICE}" in phone|2in1) ;; *) echo "invalid --device: ${DEVICE}" >&2; exit 2 ;; esac
[ -n "${TARGET}" ] || { echo "--target is required" >&2; exit 2; }
[ -n "${ARCH}" ] || { echo "--arch is required" >&2; exit 2; }
[ -n "${OUTPUT}" ] || { echo "--output is required" >&2; exit 2; }
[ -x "${HDC}" ] || { echo "HDC is not executable: ${HDC}" >&2; exit 2; }

mkdir -p "${OUTPUT}"

"${HDC}" tconn "${TARGET}" >/dev/null
actual_device="$("${HDC}" -t "${TARGET}" shell param get const.product.devicetype | tr -d '\r[:space:]')"
if [ "${actual_device}" != "${DEVICE}" ]; then
  echo "device identity mismatch: expected ${DEVICE}, got ${actual_device}" >&2
  exit 1
fi

capture() {
  local name="$1"
  local command="$2"
  {
    echo "# target=${TARGET}"
    echo "# device=${DEVICE}"
    echo "# arch=${ARCH}"
    echo "# command=${command}"
    python3 - "${HDC}" "${TARGET}" "${command}" <<'PY'
import subprocess
import sys

try:
    result = subprocess.run(
        [sys.argv[1], "-t", sys.argv[2], "shell", sys.argv[3]],
        stdout=sys.stdout,
        stderr=sys.stderr,
        timeout=60,
        check=False,
    )
    if result.returncode:
        print(f"# hdc_exit={result.returncode}")
except subprocess.TimeoutExpired:
    print("# probe_timeout_seconds=60")
PY
  } > "${OUTPUT}/${name}.txt"
}

capture identity \
  'param get const.product.devicetype; param get const.product.name; param get const.product.model; param get const.ohos.apiversion; param get const.ohos.fullname; param get persist.sys.abilityms.multi_process_model; param get const.max_native_child_process; uname -a; uptime; getenforce'
capture system_abilities 'hidumper -ls'
capture system_information_clusters 'hidumper -lc'
capture init_services 'begetctl dump_service all'
capture processes 'ps -A -o USER,PID,PPID,NAME,ARGS'
capture parameters 'begetctl param dump'
capture mounts 'cat /proc/filesystems; echo MOUNTS; cat /proc/mounts; echo CGROUPS; cat /proc/cgroups'
capture devices \
  'find /dev -maxdepth 3 -type b -o -type c -o -type d | sort; echo INPUT; cat /proc/bus/input/devices 2>/dev/null; echo DRM; ls -la /dev/dri 2>/dev/null; echo SND; ls -la /dev/snd 2>/dev/null'
capture kernel_backends \
  'for p in /proc/pressure/memory /proc/process_dmabuf_info /proc/purgeable_ashmem_trigger /proc/self/purgeable_heap /sys/kernel/tracing /sys/kernel/debug/tracing /sys/fs/bpf /dev/frz /dev/access_token_id /dev/xpm /dev/code_sign /dev/qos_ctrl /dev/auth_ctrl; do ls -ld "$p" 2>&1; done'
capture libraries \
  'find /system/lib /system/lib64 -maxdepth 4 -type f -o -type l 2>/dev/null | sort'
capture applications \
  'find /system/app /system/priv-app /system/system_ext -maxdepth 4 -type f 2>/dev/null | sort'
capture service_profiles \
  'find /system/profile /system/etc -maxdepth 4 -type f 2>/dev/null | grep -E "(/sa/|_sa_profile|systemability|\.xml$|\.json$|\.cfg$)" | sort'
capture bundles 'bm dump -a'
capture ability_state 'aa dump -a'
capture hdf "hidumper -s HdfDeviceServiceManager -a '-query'"
capture network 'hidumper --net; echo INTERFACES; ip addr; echo ROUTES; ip route; echo PROC_NET_DEV; cat /proc/net/dev'
capture storage 'hidumper --storage; echo MOUNTS; df -h'
capture memory 'hidumper --mem --prune'
capture faults 'hidumper -e --list -n 200'
capture boot_errors \
  'hilog -x | grep -Ei "fail|error|not found|unsupported|not support|denied|no such|cannot|unable|ENOSYS|ENOTSUP" | tail -n 12000'

python3 - "${OUTPUT}" "${TARGET}" "${DEVICE}" "${ARCH}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = []
for path in sorted(root.glob("*.txt")):
    data = path.read_bytes()
    files.append({
        "file": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
(root / "manifest.json").write_text(json.dumps({
    "schema_version": 1,
    "target": sys.argv[2],
    "device": sys.argv[3],
    "arch": sys.argv[4],
    "files": files,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "runtime capability inventory: ${OUTPUT}"
