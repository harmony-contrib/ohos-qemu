#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

for e2fs_dir in \
  /opt/homebrew/opt/e2fsprogs/sbin \
  /opt/homebrew/opt/e2fsprogs/bin \
  /usr/local/opt/e2fsprogs/sbin \
  /usr/local/opt/e2fsprogs/bin
do
  if [ -d "${e2fs_dir}" ]; then
    PATH="${e2fs_dir}:${PATH}"
  fi
done
export PATH

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  package_standard_qemu.sh --source-root ROOT --product PRODUCT --output-dir DIR
  package_standard_qemu.sh --rewrite-arm64-launcher FILE
  package_standard_qemu.sh --rewrite-package DIR

Products:
  armv7a_virt
  x86_64_virt
  arm64_virt
  qemu-arm64-linux-min

Optional:
  --device-type TYPE   Force const.product.devicetype / const.build.characteristics
                       (e.g. 2in1, phone, default). When set, the package name
                       gains a -<TYPE> suffix unless DEVICE_TYPE_NAME_SUFFIX=0.
  --device-type-profile PROFILE
                       Build provenance: default, param_only,
                       qemu_phone_full_source, or qemu_2in1_full_source. A full
                       profile is accepted only when its source inherit and
                       resolved preloader parts verify.

This packages already-built OpenHarmony standard-system QEMU images and
generates Linux, macOS, and Windows launchers where applicable.

--rewrite-package rewrites launch scripts inside an existing package directory
without re-copying guest images (useful when only launchers changed).

To repackage existing release packages with a new deviceType only, prefer:
  scripts/repackage_device_type.sh --device-type 2in1 ...
USAGE
}

SOURCE_ROOT=
PRODUCT=
OUTPUT_DIR=
REWRITE_ARM64_LAUNCHER=
REWRITE_PACKAGE=
DEVICE_TYPE="${DEVICE_TYPE:-}"
DEVICE_TYPE_PROFILE="${DEVICE_TYPE_BUILD_PROFILE:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --product)
      PRODUCT="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --device-type)
      DEVICE_TYPE="${2:-}"
      shift 2
      ;;
    --device-type-profile)
      DEVICE_TYPE_PROFILE="${2:-}"
      shift 2
      ;;
    --rewrite-arm64-launcher)
      REWRITE_ARM64_LAUNCHER="${2:-}"
      shift 2
      ;;
    --rewrite-package)
      REWRITE_PACKAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "${REWRITE_ARM64_LAUNCHER}" ] && [ -z "${REWRITE_PACKAGE}" ] && \
   { [ -z "${SOURCE_ROOT}" ] || [ -z "${PRODUCT}" ] || [ -z "${OUTPUT_DIR}" ]; }; then
  usage >&2
  exit 2
fi

if [ -n "${DEVICE_TYPE}" ]; then
  case "${DEVICE_TYPE}" in
    default|phone|tablet|2in1|tv|wearable|car|liteWearable) ;;
    *)
      echo "unsupported --device-type: ${DEVICE_TYPE}" >&2
      exit 2
      ;;
  esac
fi

if [ -z "${DEVICE_TYPE_PROFILE}" ]; then
  if [ -n "${DEVICE_TYPE}" ]; then
    DEVICE_TYPE_PROFILE=param_only
  else
    DEVICE_TYPE_PROFILE=default
  fi
fi
case "${DEVICE_TYPE_PROFILE}" in
  default|param_only|qemu_phone_full_source|qemu_2in1_full_source) ;;
  *)
    echo "unsupported --device-type-profile: ${DEVICE_TYPE_PROFILE}" >&2
    exit 2
    ;;
esac
if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] && [ "${DEVICE_TYPE}" != "2in1" ]; then
  echo "qemu_2in1_full_source profile requires --device-type 2in1" >&2
  exit 2
fi
if [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ] && [ "${DEVICE_TYPE}" != "phone" ]; then
  echo "qemu_phone_full_source profile requires --device-type phone" >&2
  exit 2
fi
sed_in_place_extended() {
  local expr="$1"
  local file="$2"
  if sed --version >/dev/null 2>&1; then
    sed -i -E "${expr}" "${file}"
  else
    sed -i '' -E "${expr}" "${file}"
  fi
}

replace_arm64_acceleration_block() {
  local file="$1"
  local replacement
  local output
  replacement="$(mktemp)"
  output="$(mktemp)"

  cat >"${replacement}" <<'EOF'
# Select an accelerator. QEMU's help output only reports compiled-in
# accelerators, so auto mode also probes whether HVF is usable by this host.
ACCEL_SUPPORT=$(qemu-system-aarch64 -accel help 2>&1 || true)
ACCEL_MODE="${QEMU_ACCEL:-auto}"

probe_hvf() {
    local probe_pid
    (
        ulimit -c 0
        exec qemu-system-aarch64 \
            -accel hvf \
            -M virt \
            -cpu cortex-a57 \
            -S \
            -display none \
            -nodefaults \
            -no-user-config \
            -monitor none \
            -serial none
    ) </dev/null >/dev/null 2>&1 &
    probe_pid=$!
    sleep "${QEMU_ACCEL_PROBE_SECONDS:-1}"
    if kill -0 "${probe_pid}" >/dev/null 2>&1; then
        kill "${probe_pid}" >/dev/null 2>&1 || true
        wait "${probe_pid}" 2>/dev/null || true
        return 0
    fi
    wait "${probe_pid}" 2>/dev/null || true
    return 1
}

case "${ACCEL_MODE}" in
    auto)
        if [ "$(uname)" = "Darwin" ]; then
            if echo "${ACCEL_SUPPORT}" | grep -qw hvf && probe_hvf; then
                ACCEL_ARGS="-accel hvf"
                echo "macOS Hypervisor acceleration enabled." >&2
            else
                ACCEL_ARGS="-accel tcg"
                echo "HVF is unavailable on this host, using TCG software emulation." >&2
            fi
        elif [ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ] && \
             echo "${ACCEL_SUPPORT}" | grep -qw kvm; then
            ACCEL_ARGS="-accel kvm"
            echo "KVM acceleration enabled." >&2
        else
            ACCEL_ARGS="-accel tcg"
            echo "Hardware acceleration not available, using TCG software emulation." >&2
        fi
        ;;
    hvf)
        if [ "$(uname)" != "Darwin" ] || ! echo "${ACCEL_SUPPORT}" | grep -qw hvf; then
            echo "QEMU_ACCEL=hvf requested, but HVF is not available." >&2
            exit 1
        fi
        ACCEL_ARGS="-accel hvf"
        echo "HVF acceleration explicitly requested." >&2
        ;;
    kvm)
        if [ ! -e /dev/kvm ] || [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ] || \
           ! echo "${ACCEL_SUPPORT}" | grep -qw kvm; then
            echo "QEMU_ACCEL=kvm requested, but usable KVM is not available." >&2
            exit 1
        fi
        ACCEL_ARGS="-accel kvm"
        echo "KVM acceleration explicitly requested." >&2
        ;;
    tcg)
        ACCEL_ARGS="-accel tcg"
        echo "TCG software emulation explicitly requested." >&2
        ;;
    *)
        echo "Unsupported QEMU_ACCEL=${ACCEL_MODE}; expected auto, hvf, kvm, or tcg." >&2
        exit 2
        ;;
esac

EOF

  if ! awk -v replacement="${replacement}" '
    BEGIN { skipping = 0; replaced = 0 }
    !skipping && /^# Check hardware acceleration availability/ {
      while ((getline line < replacement) > 0) print line
      close(replacement)
      skipping = 1
      replaced = 1
      next
    }
    skipping && /^NET_ARGS=\(/ { skipping = 0 }
    !skipping { print }
    END {
      if (!replaced || skipping) exit 42
    }
  ' "${file}" >"${output}"; then
    rm -f "${replacement}" "${output}"
    echo "unable to replace ARM64 accelerator block in ${file}" >&2
    exit 1
  fi

  mv "${output}" "${file}"
  rm -f "${replacement}"
}

# Product-specific QEMU resource defaults used when packaging launchers.
launcher_defaults_for_product() {
  local product="$1"
  case "${product}" in
    armv7a_virt)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=3072
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_DEFAULT_CPU=cortex-a7
      LAUNCHER_QEMU_UNIX=qemu-system-arm
      LAUNCHER_QEMU_WIN=qemu-system-arm.exe
      ;;
    x86_64_virt)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_DEFAULT_CPU=max
      LAUNCHER_QEMU_UNIX=qemu-system-x86_64
      LAUNCHER_QEMU_WIN=qemu-system-x86_64.exe
      ;;
    arm64_virt)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_DEFAULT_CPU=cortex-a57
      LAUNCHER_QEMU_UNIX=qemu-system-aarch64
      LAUNCHER_QEMU_WIN=qemu-system-aarch64.exe
      ;;
    qemu-arm64-linux-min)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=1024
      LAUNCHER_DEFAULT_DISPLAY=none
      LAUNCHER_DEFAULT_CPU=cortex-a57
      LAUNCHER_QEMU_UNIX=qemu-system-aarch64
      LAUNCHER_QEMU_WIN=qemu-system-aarch64.exe
      ;;
    *)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_DEFAULT_CPU=max
      LAUNCHER_QEMU_UNIX=qemu-system-x86_64
      LAUNCHER_QEMU_WIN=qemu-system-x86_64.exe
      ;;
  esac
}

inject_launcher_resource_defaults() {
  local file="$1"
  local default_smp="$2"
  local default_mem="$3"
  local default_qemu_bin="$4"
  local default_cpu="${5:-max}"
  local block
  local tmp

  # Upgrade previously-normalized launchers that already have resolution vars.
  if grep -q '^QEMU_XRES=' "${file}"; then
    if ! grep -q '^QEMU_CPU=' "${file}"; then
      tmp="$(mktemp)"
      awk -v default_cpu="${default_cpu}" '
        { print }
        !done && /^QEMU_MEMORY=/ {
          print "QEMU_CPU=\"${QEMU_CPU:-" default_cpu "}\""
          done = 1
        }
        END { if (!done) exit 42 }
      ' "${file}" >"${tmp}" || {
        rm -f "${tmp}"
        echo "unable to inject QEMU_CPU into ${file}" >&2
        exit 1
      }
      mv "${tmp}" "${file}"
    fi
    if ! grep -q '^QEMU_SERIAL_PORT=' "${file}"; then
      sed_in_place_extended \
        's|^(QEMU_VNC_DISPLAY=.*)$|\1\
QEMU_SERIAL_PORT="${QEMU_SERIAL_PORT:-}"|' \
        "${file}"
    fi
    if ! grep -q '^QEMU_ACCEL=' "${file}"; then
      sed_in_place_extended \
        's|^(QEMU_BIN=.*)$|\1\
QEMU_ACCEL="${QEMU_ACCEL:-auto}"|' \
        "${file}" || \
      sed_in_place_extended \
        's|^(QEMU_EXTRA_ARGS=.*)$|\1\
QEMU_ACCEL="${QEMU_ACCEL:-auto}"|' \
        "${file}"
    fi
    return 0
  fi

  block="$(mktemp)"
  cat >"${block}" <<EOF
# Launch resources (CLI wrappers export these; env overrides defaults).
QEMU_XRES="\${QEMU_XRES:-800}"
QEMU_YRES="\${QEMU_YRES:-500}"
QEMU_SMP="\${QEMU_SMP:-${default_smp}}"
QEMU_MEMORY="\${QEMU_MEMORY:-${default_mem}}"
QEMU_CPU="\${QEMU_CPU:-${default_cpu}}"
QEMU_VNC_DISPLAY="\${QEMU_VNC_DISPLAY:-21}"
QEMU_SERIAL_PORT="\${QEMU_SERIAL_PORT:-}"
QEMU_EXTRA_ARGS="\${QEMU_EXTRA_ARGS:-}"
QEMU_BIN="\${QEMU_BIN:-${default_qemu_bin}}"
QEMU_ACCEL="\${QEMU_ACCEL:-auto}"
EOF

  tmp="$(mktemp)"
  if grep -q '^HDC_HOST_PORT=' "${file}"; then
    awk -v block="${block}" '
      { print }
      /^HDC_HOST_PORT=/ && !done {
        while ((getline line < block) > 0) print line
        close(block)
        done = 1
      }
      END { if (!done) exit 42 }
    ' "${file}" >"${tmp}" || {
      # Fall back: prepend after shebang / first non-comment assignment area.
      cat "${file}" >"${tmp}"
      cat "${block}" >>"${tmp}"
    }
  elif grep -q '^DISPLAY_TYPE=' "${file}"; then
    awk -v block="${block}" '
      { print }
      /^DISPLAY_TYPE=/ && !done {
        while ((getline line < block) > 0) print line
        close(block)
        done = 1
      }
      END { if (!done) exit 42 }
    ' "${file}" >"${tmp}" || {
      cat "${file}" >"${tmp}"
      cat "${block}" >>"${tmp}"
    }
  else
    # Insert after the first OHOS_IMG assignment, else at top after shebang.
    if grep -q '^OHOS_IMG=' "${file}"; then
      awk -v block="${block}" '
        { print }
        /^OHOS_IMG=/ && !done {
          while ((getline line < block) > 0) print line
          close(block)
          done = 1
        }
      ' "${file}" >"${tmp}"
    else
      {
        if head -n1 "${file}" | grep -q '^#!'; then
          head -n1 "${file}"
          cat "${block}"
          tail -n +2 "${file}"
        else
          cat "${block}"
          cat "${file}"
        fi
      } >"${tmp}"
    fi
  fi
  mv "${tmp}" "${file}"
  rm -f "${block}"
}

ensure_qemu_peer_lan_support() {
  local file="$1"
  local qemu_bin="$2"
  python3 - "${file}" "${qemu_bin}" <<'PEER_PY'
import re
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
# Strip any previous peer LAN block when rewriting an already-normalized launcher.
text = re.sub(
    r'\n?# QEMU_PEER_LAN_V1:.*?^esac\n?',
    '\n',
    text,
    flags=re.M | re.S,
)
text = text.replace('${QEMU_PEER_NIC_ARGS} -device', '-device')
nics = list(re.finditer(r'virtio-net-(?:pci|device),netdev=([A-Za-z0-9_-]+)(?:,mac=([0-9a-fA-F:]+|\$\{QEMU_MGMT_MAC\}))?', text))
net_ids = {m.group(1) for m in nics}
nic_count = len(net_ids)
serial = re.search(r'(?<![A-Za-z0-9_.])sn=([A-Za-z0-9_-]+|\$\{QEMU_GUEST_SERIAL\})', text)
original_serial = serial.group(1) if serial and serial.group(1) != '${QEMU_GUEST_SERIAL}' else '0023456789'
mac_val = nics[0].group(2) if nics and nics[0].group(2) and nics[0].group(2) != '${QEMU_MGMT_MAC}' else None
original_mac = mac_val if mac_val else '52:54:00:12:34:56'
def nic(match):
    base = re.sub(r',mac=([0-9a-fA-F:]+|\$\{QEMU_MGMT_MAC\})$', '', match.group())
    return base + ',mac=${QEMU_MGMT_MAC}'
if nic_count == 1:
    text = re.sub(r'virtio-net-(?:pci|device),netdev=[A-Za-z0-9_-]+(?:,mac=(?:[0-9a-fA-F:]+|\$\{QEMU_MGMT_MAC\}))?', nic, text)
    # SoftBus's real default LNN Ethernet manager registers eth0 only and
    # accepts one main IP subnet. In paired mode enumerate the data NIC first;
    # management remains a separate NIC. The actual guests must still prove
    # the mapping by configured MAC, not infer it from this source ordering.
    text, peer_nic_slots = re.subn(
        r'(?<!\S)-device([ \t]+)(virtio-net-(?:pci|device),netdev=[A-Za-z0-9_-]+,mac=\$\{QEMU_MGMT_MAC\})',
        lambda match: '${QEMU_PEER_NIC_ARGS} -device' + match[1] + match[2], text)
    if peer_nic_slots < 1:
        raise SystemExit('unable to place the optional peer NIC before the management NIC')
if serial and nic_count == 1:
    text = re.sub(r'(?<![A-Za-z0-9_.])sn=(?:[A-Za-z0-9_-]+|\$\{QEMU_GUEST_SERIAL\})', 'sn=${QEMU_GUEST_SERIAL}', text)
block = r'''# QEMU_PEER_LAN_V1: optional real two-QEMU Ethernet link; user NIC remains management.
# QEMU_PEER_LAN_V2_DATA_FIRST: paired data NIC precedes management; runtime must verify both actual MAC mappings.
QEMU_INSTANCE_ID="${QEMU_INSTANCE_ID:-}"
if [ -n "${QEMU_INSTANCE_ID}" ]; then
  if ! [[ "${QEMU_INSTANCE_ID}" =~ ^[1-9][0-9]{0,2}$ ]]; then
    echo "QEMU_INSTANCE_ID must be an integer 1..999, got: ${QEMU_INSTANCE_ID}" >&2; exit 2
  fi
  qemu_inst_hex="$(printf '%02x' "$(((QEMU_INSTANCE_ID + 85) & 255))")"
  QEMU_MGMT_MAC="${QEMU_MGMT_MAC:-52:54:00:12:34:${qemu_inst_hex}}"
  QEMU_PEER_MAC="${QEMU_PEER_MAC:-52:54:00:12:35:${qemu_inst_hex}}"
  QEMU_INSTANCE_UUID="${QEMU_INSTANCE_UUID:-00000000-0000-4000-8000-$(printf '%012x' "${QEMU_INSTANCE_ID}")}"
  QEMU_GUEST_SERIAL="${QEMU_GUEST_SERIAL:-$(printf '00234567%02d' "$((QEMU_INSTANCE_ID % 100))")}"
fi
QEMU_PEER_MODE="${QEMU_PEER_MODE:-off}"
if [[ "${QEMU_PEER_MODE}" =~ ^(listen|connect):([1-9][0-9]{0,4})$ ]]; then
  QEMU_PEER_PORT="${QEMU_PEER_PORT:-${BASH_REMATCH[2]}}"
  QEMU_PEER_MODE="${BASH_REMATCH[1]}"
fi
if [ "${QEMU_PEER_MODE}" = "listen" ] || [ "${QEMU_PEER_MODE}" = "connect" ]; then
  QEMU_PEER_PORT="${QEMU_PEER_PORT:-6666}"
  if [ "${QEMU_PEER_MODE}" = "listen" ]; then
    QEMU_MGMT_MAC="${QEMU_MGMT_MAC:-52:54:00:12:34:56}"
    QEMU_PEER_MAC="${QEMU_PEER_MAC:-52:54:00:12:35:56}"
    QEMU_INSTANCE_UUID="${QEMU_INSTANCE_UUID:-00000000-0000-4000-8000-000000000001}"
    QEMU_GUEST_SERIAL="${QEMU_GUEST_SERIAL:-0023456701}"
  else
    QEMU_MGMT_MAC="${QEMU_MGMT_MAC:-52:54:00:12:34:57}"
    QEMU_PEER_MAC="${QEMU_PEER_MAC:-52:54:00:12:35:57}"
    QEMU_INSTANCE_UUID="${QEMU_INSTANCE_UUID:-00000000-0000-4000-8000-000000000002}"
    QEMU_GUEST_SERIAL="${QEMU_GUEST_SERIAL:-0023456702}"
  fi
fi
QEMU_MGMT_MAC="${QEMU_MGMT_MAC:-@MGMT_MAC@}"
QEMU_GUEST_SERIAL="${QEMU_GUEST_SERIAL:-@SERIAL@}"
QEMU_PEER_NIC_ARGS=''
if ! [[ "${QEMU_MGMT_MAC}" =~ ^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$ ]]; then
  echo "QEMU_MGMT_MAC must be a valid MAC address" >&2; exit 2
fi
if [ -n "${QEMU_GUEST_SERIAL}" ] && ! [[ "${QEMU_GUEST_SERIAL}" =~ ^[A-Za-z0-9_-]{1,32}$ ]]; then
  echo "QEMU_GUEST_SERIAL must contain 1..32 safe serial characters" >&2; exit 2
fi
case "${QEMU_PEER_MODE}" in
  off)
    if [ -n "${QEMU_INSTANCE_UUID:-}" ]; then
      case " ${QEMU_EXTRA_ARGS} " in
        *" -uuid "*) ;;
        *) QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -uuid ${QEMU_INSTANCE_UUID}" ;;
      esac
    fi
    ;;
  listen|connect)
    if [ "$((16#${QEMU_MGMT_MAC%%:*} & 3))" -ne 2 ]; then
      echo "peer LAN requires a locally administered unicast management MAC" >&2; exit 2
    fi
    if [ @NIC_COUNT@ -ne 1 ] || [ @HAS_SERIAL@ -ne 1 ]; then
      echo "peer LAN requires exactly one recognized management NIC and an existing boot sn parameter" >&2; exit 2
    fi
    if ! [[ "${QEMU_PEER_PORT:-}" =~ ^[1-9][0-9]{0,4}$ ]] ||
       [ "${QEMU_PEER_PORT}" -gt 65535 ] || [ "${QEMU_PEER_PORT}" = "${HDC_HOST_PORT:-5555}" ]; then
      echo "QEMU_PEER_PORT must be 1..65535 and distinct from HDC" >&2; exit 2
    fi
    if ! [[ "${QEMU_PEER_MAC:-}" =~ ^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$ ]] ||
       [ "$((16#${QEMU_PEER_MAC%%:*} & 3))" -ne 2 ] ||
       [ "$(echo "${QEMU_PEER_MAC}" | tr 'A-F' 'a-f')" = "$(echo "${QEMU_MGMT_MAC}" | tr 'A-F' 'a-f')" ]; then
      echo "peer LAN requires a distinct locally administered unicast QEMU_PEER_MAC" >&2; exit 2
    fi
    if ! [[ "${QEMU_INSTANCE_UUID:-}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] ||
       [ -z "${QEMU_GUEST_SERIAL}" ]; then
      echo "peer LAN requires explicit QEMU_INSTANCE_UUID and boot serial; actual guest UDID must still be verified" >&2; exit 2
    fi
    case " ${QEMU_EXTRA_ARGS} " in
      *peer_lan*|*" -uuid "*) echo "peer LAN/UUID arguments are reserved by the configured instance" >&2; exit 2 ;;
    esac
    if ! "${QEMU_BIN}" -M @MACHINE@ -netdev help 2>&1 | grep -qx stream; then
      echo "selected QEMU does not advertise the stream network backend" >&2; exit 2
    fi
    if [ "${QEMU_PEER_MODE}" = listen ]; then
      QEMU_PEER_ENDPOINT="server=on"
    else
      QEMU_PEER_ENDPOINT="server=off,reconnect-ms=250"
    fi
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -uuid ${QEMU_INSTANCE_UUID} -netdev stream,id=peer_lan,${QEMU_PEER_ENDPOINT},addr.type=inet,addr.host=127.0.0.1,addr.port=${QEMU_PEER_PORT}"
    QEMU_PEER_NIC_ARGS="-device virtio-net-pci,id=peer_lan_nic,netdev=peer_lan,mac=${QEMU_PEER_MAC}"
    if [ -n "${QEMU_PEER_CAPTURE_FILE:-}" ]; then
      if ! [[ "${QEMU_PEER_CAPTURE_FILE}" =~ ^/[A-Za-z0-9_./-]+$ ]] || [ -e "${QEMU_PEER_CAPTURE_FILE}" ] || [ -L "${QEMU_PEER_CAPTURE_FILE}" ]; then
        echo "peer capture requires a new absolute path containing only safe characters" >&2; exit 2
      fi
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -object filter-dump,id=peer_lan_capture,netdev=peer_lan,file=${QEMU_PEER_CAPTURE_FILE}"
    fi
    ;;
  *) echo "QEMU_PEER_MODE must be off, listen, or connect" >&2; exit 2 ;;
esac
'''.replace('@MGMT_MAC@', original_mac).replace('@SERIAL@', original_serial).replace('@NIC_COUNT@', str(nic_count)).replace(
    '@HAS_SERIAL@', str(int(serial is not None))).replace('@MACHINE@', 'q35' if sys.argv[2] == 'qemu-system-x86_64' else 'virt')
text, count = re.subn(r'^QEMU_BIN=.*$', lambda match: match.group() + '\n' + block, text, count=1, flags=re.M)
if count != 1:
    raise SystemExit('unable to insert optional peer LAN after launch binary resources')
path.write_text(text)
PEER_PY
}

normalize_common_qemu_launcher() {
  local file="$1"
  local default_smp="${2:-4}"
  local default_mem="${3:-4096}"
  local default_qemu_bin="${4:-qemu-system-x86_64}"
  local default_cpu="${5:-max}"
  local pointer_device="${6:-virtio-mouse-pci}"

  sed_in_place_extended 's|^OHOS_IMG="(out/[^"]+)"$|OHOS_IMG="${OHOS_IMG:-\1}"|' "${file}"
  if ! grep -q '^HDC_HOST_PORT=' "${file}"; then
    sed_in_place_extended 's|^(DISPLAY_TYPE=.*)$|\1\
HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"|' "${file}"
  fi
  sed_in_place_extended 's|hostfwd=tcp::5555-:5555|hostfwd=tcp::${HDC_HOST_PORT}-:5555|g' "${file}"
  # Initialize packaged RTCs in UTC; retain the host clock and guest time service.
  sed_in_place_extended \
    's|-rtc base=localtime,clock=host|-rtc base=utc,clock=host|g' \
    "${file}"
  sed_in_place_extended 's|init=/init|init=/bin/init|g' "${file}"
  sed_in_place_extended 's|ohos\.required_mount\.system=/dev/block/([^ @]+)@/system@ext4|ohos.required_mount.system=/dev/block/\1@/usr@ext4|g' "${file}"
  # Do not consume the trailing backslash that escapes the closing quote in
  # the ARM launchers' QEMU_CMD string.
  sed_in_place_extended 's#(ohos\.required_mount\.data=/dev/block/[^ @]+@/data)@(ext4|f2fs)@[^ @"]+@wait[^ "\\]*#\1@f2fs@nosuid,nodev,noatime,usrquota,grpquota,prjquota@wait,required,reservedsize=104857600#g' "${file}"
  if ! grep -q 'oemmode=rd' "${file}"; then
    sed_in_place_extended 's|-append \\"[[:space:]]*|-append \\"oemmode=rd |' "${file}"
    sed_in_place_extended 's|-append "[[:space:]]*|-append "oemmode=rd |' "${file}"
  fi
  if ! grep -q 'developer_mode=1' "${file}"; then
    sed_in_place_extended \
      's|oemmode=rd|oemmode=rd buildvariant=eng developer_mode=1|' \
      "${file}"
  fi

  # Keep ES1370 playback on card 0 and the real ALSA capture input on card 1.
  # Applying this before launcher generation also covers the ARM command string.
  if ! grep -q 'snd-aloop.id=QemuCapture' "${file}"; then
    sed_in_place_extended \
      's|oemmode=rd|oemmode=rd snd-ens1370.index=0 snd-aloop.index=1 snd-aloop.id=QemuCapture snd-aloop.pcm_substreams=1|g' \
      "${file}"
  fi

  # OpenHarmony's composer service still needs a display device when the host
  # frontend is disabled. Without virtio-gpu, headless boots lose
  # composer_host/render_service and the critical foundation process exits.
  sed_in_place_extended \
    's|DISPLAY_ARGS="-display none|DISPLAY_ARGS="-device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES} -display none|' \
    "${file}"
  # Only inject virtio-gpu before a bare "-display none" line when the previous
  # non-empty line is not already a virtio-gpu device (avoids duplicates).
  local tmp_display
  tmp_display="$(mktemp)"
  awk '
    {
      line = $0
      if (line ~ /^[[:space:]]*-display none$/ && prev !~ /virtio-gpu/) {
        match(line, /^([[:space:]]*)/)
        print substr(line, RSTART, RLENGTH) "-device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}"
      }
      print line
      if (line ~ /[^[:space:]]/) prev = line
    }
  ' "${file}" >"${tmp_display}"
  mv "${tmp_display}" "${file}"

  inject_launcher_resource_defaults \
    "${file}" "${default_smp}" "${default_mem}" "${default_qemu_bin}" \
    "${default_cpu}"

  ensure_qemu_peer_lan_support "${file}" "${default_qemu_bin}"

  # Observe real sleep/wake through a supported option, without editing the
  # packaged launcher or disabling the guest's power policy.
  if ! grep -q '^QEMU_KERNEL_LOG_LEVEL=' "${file}"; then
    local tmp_log_level
    tmp_log_level="$(mktemp)"
    awk '
      { print }
      /^QEMU_CPU=/ {
        print "QEMU_KERNEL_LOG_LEVEL=\"${QEMU_KERNEL_LOG_LEVEL:-4}\""
        print "case \"${QEMU_KERNEL_LOG_LEVEL}\" in"
        print "  [0-8]) ;;"
        print "  *) echo \"kernel log level must be 0..8\" >&2; exit 2 ;;"
        print "esac"
      }
    ' "${file}" >"${tmp_log_level}"
    mv "${tmp_log_level}" "${file}"
  fi
  if grep -Eq 'loglevel=[0-9]+' "${file}"; then
    sed_in_place_extended 's|loglevel=[0-9]+|loglevel=${QEMU_KERNEL_LOG_LEVEL}|g' "${file}"
  elif ! grep -q 'loglevel=${QEMU_KERNEL_LOG_LEVEL}' "${file}"; then
    sed_in_place_extended 's|oemmode=rd|oemmode=rd loglevel=${QEMU_KERNEL_LOG_LEVEL}|g' "${file}"
  fi

  # Guest GPU resolution: replace hard-coded xres/yres, then bare virtio-gpu-pci
  # (only when not already followed by ,xres=...).
  sed_in_place_extended \
    's/xres=[0-9]+,yres=[0-9]+/xres=${QEMU_XRES},yres=${QEMU_YRES}/g' \
    "${file}"
  sed_in_place_extended \
    's/virtio-gpu-pci(["[:space:]])/virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}\1/g' \
    "${file}"
  sed_in_place_extended \
    's/virtio-gpu-pci$/virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}/g' \
    "${file}"
  # A variable-sized graphical frontend needs an absolute pointing device.
  # Keep legacy packages on virtio-mouse unless the guest MMI fix was verified.
  sed_in_place_extended \
    "s/virtio-(mouse|tablet)-pci/${pointer_device}/g" \
    "${file}"
  # Multitouch also advertises BTN handling. Register it before the pointer,
  # otherwise QEMU sends buttons to multitouch but absolute motion to tablet.
  # Do not merge those independent devices or invent a guest pressed state.
  if ! grep -q '^QEMU_A11Y_INPUT_ARGS=' "${file}"; then
    local tmp_a11y_input
    tmp_a11y_input="$(mktemp)"
    awk '
      { print }
      /^QEMU_EXTRA_ARGS=/ && !done {
        print "QEMU_A11Y_INPUT_ARGS=\"\""
        print "case \"${QEMU_ACCESSIBILITY:-0}\" in"
        print "  0) ;;"
        print "  1) QEMU_A11Y_INPUT_ARGS=\"-device virtio-multitouch-pci\" ;;"
        print "  *) echo \"QEMU_ACCESSIBILITY must be 0 or 1\" >&2; exit 2 ;;"
        print "esac"
        done = 1
      }
      END { if (!done) exit 42 }
    ' "${file}" >"${tmp_a11y_input}" || {
      rm -f "${tmp_a11y_input}"
      echo "unable to wire accessibility input before the pointer" >&2
      exit 1
    }
    mv "${tmp_a11y_input}" "${file}"
  fi
  if ! grep -Fq '${QEMU_A11Y_INPUT_ARGS} -device' "${file}"; then
    sed_in_place_extended \
      "s|-device ${pointer_device}|\${QEMU_A11Y_INPUT_ARGS} -device ${pointer_device}|g" \
      "${file}"
  fi
  # Collapse accidental double xres/yres annotations and duplicate device lines.
  sed_in_place_extended \
    's/virtio-gpu-pci,xres=\$\{QEMU_XRES\},yres=\$\{QEMU_YRES\},xres=\$\{QEMU_XRES\},yres=\$\{QEMU_YRES\}/virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}/g' \
    "${file}"
  local tmp_dedupe
  tmp_dedupe="$(mktemp)"
  awk '
    {
      if ($0 ~ /virtio-gpu-pci/ && $0 == prev) next
      print
      prev = $0
    }
  ' "${file}" >"${tmp_dedupe}"
  mv "${tmp_dedupe}" "${file}"

  # CPU model / count / memory. Keep existing product defaults while allowing
  # CLI wrappers and direct qemu_run.sh users to override the CPU model.
  sed_in_place_extended \
    's/-cpu (max|cortex-a57|cortex-a7)/-cpu ${QEMU_CPU}/g' "${file}"
  sed_in_place_extended 's/-smp [0-9]+/-smp ${QEMU_SMP}/g' "${file}"
  sed_in_place_extended 's/-m [0-9]+[MmGg]?/-m ${QEMU_MEMORY}/g' "${file}"

  # VNC display number (default 21 -> TCP 5921).
  sed_in_place_extended 's/-vnc :[0-9]+/-vnc :${QEMU_VNC_DISPLAY}/g' "${file}"
  sed_in_place_extended \
    's/VNC on port 5921/VNC on port $((5900 + QEMU_VNC_DISPLAY))/g' \
    "${file}" || true
  sed_in_place_extended \
    's/VNC on 127\.0\.0\.1:5921/VNC on 127.0.0.1:$((5900 + QEMU_VNC_DISPLAY))/g' \
    "${file}" || true

  # Prefer QEMU_BIN for the main system emulator binary, but do not rewrite the
  # default assignment QEMU_BIN="${QEMU_BIN:-qemu-system-...}".
  if [ -n "${default_qemu_bin}" ]; then
    local tmp_bin
    tmp_bin="$(mktemp)"
    awk -v bin="${default_qemu_bin}" '
      /^QEMU_BIN=/ { print; next }
      {
        gsub(bin, "${QEMU_BIN}")
        print
      }
    ' "${file}" >"${tmp_bin}"
    mv "${tmp_bin}" "${file}"
  fi

  # Make QEMU_ACCEL actually work on launchers that only auto-probed KVM.
  ensure_qemu_accel_env_support "${file}" "${default_qemu_bin}"

  # Optional telnet serial when QEMU_SERIAL_PORT is set.
  ensure_qemu_serial_port_support "${file}"

  # Optional userdata.img sparse expansion when QEMU_USERDATA_SIZE is set.
  ensure_qemu_userdata_size_support "${file}"

  # Auto headless when no host display is available (Linux SSH, CI).
  ensure_auto_headless_support "${file}"

  # Probe host QEMU display backends (Cocoa on macOS, SDL/GTK on Linux, VNC fallback).
  ensure_qemu_display_backend_support "${file}"

  # Wire Category 1 (audio backend, VirtFS 9p shared folder, USB xHCI/storage/host,
  # virtio-balloon) and Category 2 (virtual AT modem RIL over virtio-serial, Wi-Fi
  # mode, Bluetooth USB passthrough) capabilities.
  ensure_qemu_extended_capabilities_support "${file}"

  # Append optional extra QEMU arguments at the invocation site.
  # Do not treat the QEMU_EXTRA_ARGS= assignment line as already wired.
  if ! grep -Eq 'eval "\$QEMU_CMD \$\{QEMU_EXTRA_ARGS\}"|eval "\$\{QEMU_CMD\} \$\{QEMU_EXTRA_ARGS\}"|\\$\{QEMU_EXTRA_ARGS\}[[:space:]]*$' "${file}" && \
     ! grep -Eq '[[:space:]]\$\{QEMU_EXTRA_ARGS\}[[:space:]]*$' "${file}"; then
    if grep -q 'eval "$QEMU_CMD"' "${file}"; then
      sed_in_place_extended \
        's|eval "\$QEMU_CMD"|eval "\$QEMU_CMD \${QEMU_EXTRA_ARGS}"|g' \
        "${file}"
    elif grep -q 'eval "${QEMU_CMD}"' "${file}"; then
      sed_in_place_extended \
        's|eval "\$\{QEMU_CMD\}"|eval "\$\{QEMU_CMD\} \${QEMU_EXTRA_ARGS}"|g' \
        "${file}"
    fi
    # x86-style multi-line exec ending in -append "...".
    if grep -qE 'exec (\$\{QEMU_BIN\}|"\$\{QEMU_BIN\}"|qemu-system-)' "${file}" && \
       ! grep -Eq '[[:space:]]\$\{QEMU_EXTRA_ARGS\}[[:space:]]*$' "${file}"; then
      if grep -q -- '-append ' "${file}"; then
        sed_in_place_extended \
          's|(-append "[^"]*")$|\1 \\\
    \${QEMU_EXTRA_ARGS}|' \
          "${file}" || true
      fi
    fi
  fi
  # Preserve the owning launch process for supervision and signal handling.
  # ARM64 upstream uses eval without exec, which otherwise orphans QEMU when
  # a boot/test launcher is interrupted. Existing direct exec branches stay.
  sed_in_place_extended 's#^[[:space:]]*eval "(\$QEMU_CMD|\$\{QEMU_CMD\})#eval "exec \1#' "${file}"
}

ensure_armv7a_sceneboard_headless_scanout() {
  local file="$1"
  local product="$2"
  local device_type_profile="$3"

  if [ "${product}" != "armv7a_virt" ] || \
     { [ "${device_type_profile}" != "qemu_2in1_full_source" ] && \
       [ "${device_type_profile}" != "qemu_phone_full_source" ]; }; then
    return 0
  fi

  # ARMv7a's composer does not create a DRM connector with -display none.
  # Keep headless mode private to the host while providing a real scanout for
  # RenderService and SceneBoard.
  sed_in_place_extended \
    's|(DISPLAY_ARGS="[^"]*)-display none|\1-vnc 127.0.0.1:${QEMU_VNC_DISPLAY}|' \
    "${file}"
  if ! grep -Fq -- '-vnc 127.0.0.1:${QEMU_VNC_DISPLAY}' "${file}"; then
    echo "ARMv7a SceneBoard launcher is missing its loopback headless scanout" >&2
    exit 1
  fi
}

ensure_x86_64_disable_acpi_suspend() {
  local file="$1"
  local product="$2"

  if [ "${product}" != "x86_64_virt" ]; then
    return 0
  fi
  if grep -q 'ICH9-LPC.disable_s3=1' "${file}"; then
    return 0
  fi

  local tmp
  tmp="$(mktemp)"
  awk '
    BEGIN { injected = 0 }
    {
      print
      if (!injected && $0 ~ /-machine "\$\{MACHINE\}" \\$/) {
        print "    -global ICH9-LPC.disable_s3=1 -global ICH9-LPC.disable_s4=1 \\"
        injected = 1
      }
    }
    END { if (!injected) exit 42 }
  ' "${file}" >"${tmp}" || {
    rm -f "${tmp}"
    echo "unable to disable x86_64 ICH9-LPC ACPI S3/S4 in ${file}" >&2
    exit 1
  }
  mv "${tmp}" "${file}"
}

ensure_qemu_accel_env_support() {
  local file="$1"
  local default_qemu_bin="${2:-qemu-system-x86_64}"

  # Already has explicit QEMU_ACCEL case handling (arm64 full launcher).
  if grep -q 'ACCEL_MODE="${QEMU_ACCEL' "${file}" || \
     grep -q 'case "${ACCEL_MODE}"' "${file}"; then
    return 0
  fi

  # x86_64 launcher: MACHINE=q35,accel=kvm style.
  if grep -q 'MACHINE="q35,accel=kvm"' "${file}" || \
     grep -q "MACHINE='q35,accel=kvm'" "${file}"; then
    local tmp
    tmp="$(mktemp)"
    awk '
      BEGIN { skipping = 0; replaced = 0 }
      !skipping && /if \[ -e \/dev\/kvm \] && \[ -r \/dev\/kvm \]; then/ {
        print "# Acceleration (QEMU_ACCEL=auto|kvm|tcg)."
        print "ACCEL_MODE=\"${QEMU_ACCEL:-auto}\""
        print "case \"${ACCEL_MODE}\" in"
        print "  kvm)"
        print "    if [ ! -e /dev/kvm ] || [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then"
        print "      echo \"QEMU_ACCEL=kvm requested, but usable KVM is not available.\" >&2"
        print "      exit 1"
        print "    fi"
        print "    MACHINE=\"q35,accel=kvm\""
        print "    ACCEL_ARGS=\"\""
        print "    echo \"KVM acceleration explicitly requested.\" >&2"
        print "    ;;"
        print "  tcg)"
        print "    MACHINE=\"q35\""
        print "    ACCEL_ARGS=\"-accel tcg,thread=multi\""
        print "    echo \"TCG software emulation explicitly requested.\" >&2"
        print "    ;;"
        print "  auto|*)"
        print "    if [ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then"
        print "      MACHINE=\"q35,accel=kvm\""
        print "      ACCEL_ARGS=\"\""
        print "      echo \"KVM acceleration enabled.\" >&2"
        print "    else"
        print "      MACHINE=\"q35\""
        print "      ACCEL_ARGS=\"-accel tcg,thread=multi\""
        print "      echo \"Hardware acceleration not available, using TCG software emulation.\" >&2"
        print "    fi"
        print "    ;;"
        print "esac"
        skipping = 1
        replaced = 1
        next
      }
      skipping && /^fi$/ {
        skipping = 0
        next
      }
      !skipping { print }
      END { if (!replaced || skipping) exit 42 }
    ' "${file}" >"${tmp}" || {
      rm -f "${tmp}"
      return 0
    }
    mv "${tmp}" "${file}"
    return 0
  fi

  # armv7a-style ACCEL_ARGS only block.
  if grep -q 'ACCEL_ARGS="-accel kvm"' "${file}" || \
     grep -q 'ACCEL_ARGS="-accel tcg' "${file}"; then
    if grep -q 'ACCEL_SUPPORT=' "${file}"; then
      local tmp
      tmp="$(mktemp)"
      awk '
        BEGIN { skipping = 0; replaced = 0 }
        !skipping && /^ACCEL_SUPPORT=/ {
          print
          print "ACCEL_MODE=\"${QEMU_ACCEL:-auto}\""
          print "case \"${ACCEL_MODE}\" in"
          print "  kvm)"
          print "    if [ ! -e /dev/kvm ] || [ ! -r /dev/kvm ] || \\"
          print "       ! echo \"${ACCEL_SUPPORT}\" | grep -qw kvm; then"
          print "      echo \"QEMU_ACCEL=kvm requested, but usable KVM is not available.\" >&2"
          print "      exit 1"
          print "    fi"
          print "    ACCEL_ARGS=\"-accel kvm\""
          print "    echo \"KVM acceleration explicitly requested.\" >&2"
          print "    ;;"
          print "  tcg)"
          print "    ACCEL_ARGS=\"-accel tcg,thread=multi\""
          print "    echo \"TCG software emulation explicitly requested.\" >&2"
          print "    ;;"
          print "  auto|*)"
          print "    if [ -e /dev/kvm ] && [ -r /dev/kvm ] && \\"
          print "       echo \"${ACCEL_SUPPORT}\" | grep -qw kvm; then"
          print "      ACCEL_ARGS=\"-accel kvm\""
          print "      echo \"KVM acceleration enabled.\" >&2"
          print "    else"
          print "      ACCEL_ARGS=\"-accel tcg,thread=multi\""
          print "      echo \"Hardware acceleration not available, using TCG software emulation.\" >&2"
          print "    fi"
          print "    ;;"
          print "esac"
          skipping = 1
          replaced = 1
          next
        }
        skipping && /^NET_ARGS=\(/ {
          skipping = 0
          print
          next
        }
        skipping && /^case "\$\{DISPLAY_TYPE\}"/ {
          skipping = 0
          print
          next
        }
        !skipping { print }
        END { if (!replaced) exit 42 }
      ' "${file}" >"${tmp}" || {
        rm -f "${tmp}"
        return 0
      }
      mv "${tmp}" "${file}"
    fi
  fi
}

ensure_qemu_serial_port_support() {
  local file="$1"
  if grep -q 'QEMU_SERIAL_PORT applied' "${file}"; then
    return 0
  fi
  # Prepend telnet serial onto QEMU_EXTRA_ARGS so both string- and array-style
  # launchers pick it up without rewriting DISPLAY_ARGS.
  local tmp
  tmp="$(mktemp)"
  awk '
    BEGIN { done = 0 }
    {
      print
      if (!done && /^QEMU_EXTRA_ARGS=/) {
        print "# Optional telnet serial console (QEMU_SERIAL_PORT / --serial-port)."
        print "if [ -n \"${QEMU_SERIAL_PORT:-}\" ]; then"
        print "  QEMU_EXTRA_ARGS=\"-serial telnet:127.0.0.1:${QEMU_SERIAL_PORT},server,nowait ${QEMU_EXTRA_ARGS}\""
        print "  echo \"Serial telnet console: 127.0.0.1:${QEMU_SERIAL_PORT} (QEMU_SERIAL_PORT applied)\" >&2"
        print "fi"
        done = 1
      }
    }
  ' "${file}" >"${tmp}"
  mv "${tmp}" "${file}"
}

ensure_qemu_userdata_size_support() {
  local file="$1"
  # QEMU_USERDATA_SIZE_V1 and QEMU_RESET_V1 are wired inside ensure_qemu_extended_capabilities_support
  # after QEMU_INSTANCE_ID and QEMU_USERDATA_FILE are resolved so custom userdata paths, per-instance
  # userdata images, and custom userdata sizes are all handled consistently.
  return 0
}

ensure_auto_headless_support() {
  local file="$1"
  if grep -q 'Auto-selected headless display' "${file}"; then
    return 0
  fi
  if ! grep -q 'DISPLAY_TYPE=' "${file}"; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk '
    BEGIN { done = 0 }
    {
      print
      if (!done && /^DISPLAY_TYPE=/) {
        print "# Auto headless when the host has no graphical display (e.g. SSH/CI)."
        print "if [ \"${DISPLAY_TYPE}\" != \"none\" ] && [ \"${DISPLAY_TYPE}\" != \"vnc\" ] && \\"
        print "   [ -z \"${DISPLAY:-}\" ] && [ -z \"${WAYLAND_DISPLAY:-}\" ] && \\"
        print "   [ \"$(uname -s)\" = \"Linux\" ]; then"
        print "  echo \"No DISPLAY/WAYLAND_DISPLAY; Auto-selected headless display (none).\" >&2"
        print "  DISPLAY_TYPE=\"none\""
        print "fi"
        done = 1
      }
    }
  ' "${file}" >"${tmp}"
  mv "${tmp}" "${file}"
}

ensure_qemu_display_backend_support() {
  local file="$1"
  python3 - "${file}" <<'DISPLAY_PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# Normalize default DISPLAY_TYPE assignment when QEMU_DISPLAY is unset.
text = re.sub(
    r'^DISPLAY_TYPE="\$\{QEMU_DISPLAY:-[^}]+\}"$',
    'DISPLAY_TYPE="${QEMU_DISPLAY:-sdl}"',
    text,
    count=1,
    flags=re.M,
)

detect_block = """# Detect supported display types
DETECT_DISPLAYS=$(${QEMU_BIN} -display help 2>&1 | grep -A 10 "Available display" || true)
HAS_COCOA=$(echo "$DETECT_DISPLAYS" | grep -qw cocoa && echo yes || echo no)
HAS_SDL=$(echo "$DETECT_DISPLAYS" | grep -qw sdl && echo yes || echo no)
HAS_GTK=$(echo "$DETECT_DISPLAYS" | grep -qw gtk && echo yes || echo no)

# Auto-detect best display for macOS/Linux when 'sdl', 'gtk', or 'auto' is requested
if [ "${DISPLAY_TYPE}" = "sdl" ] || [ "${DISPLAY_TYPE}" = "gtk" ] || [ "${DISPLAY_TYPE}" = "auto" ]; then
    if [ "$(uname)" = "Darwin" ] && [ "${HAS_COCOA}" = "yes" ]; then
        DISPLAY_TYPE="cocoa"
        echo "Auto-selected: Cocoa (macOS preferred)" >&2
    elif [ "${DISPLAY_TYPE}" = "gtk" ] && [ "${HAS_GTK}" = "yes" ]; then
        DISPLAY_TYPE="gtk"
        echo "Auto-selected: GTK" >&2
    elif [ "${HAS_SDL}" = "yes" ]; then
        DISPLAY_TYPE="sdl"
        echo "Auto-selected: SDL" >&2
    elif [ "${HAS_GTK}" = "yes" ]; then
        DISPLAY_TYPE="gtk"
        echo "Auto-selected: GTK" >&2
    elif [ "${HAS_COCOA}" = "yes" ]; then
        DISPLAY_TYPE="cocoa"
        echo "Auto-selected: Cocoa" >&2
    else
        echo "Warning: Neither SDL, GTK, nor Cocoa available, falling back to VNC" >&2
        DISPLAY_TYPE="vnc"
    fi
fi
"""

pattern = re.compile(
    r'(?:# Detect supported display types\n.*?\n)?'
    r'(?:# Set display arguments based on DISPLAY_TYPE\n)?'
    r'case "\$\{DISPLAY_TYPE\}" in\n.*?^esac$',
    re.M | re.S,
)
match = pattern.search(text)
if not match:
    raise SystemExit(f"unable to locate DISPLAY_TYPE case block in {path}")

old_case = match.group(0)
if "DISPLAY_ARGS=(" in old_case:
    new_case = detect_block + """
case "${DISPLAY_TYPE}" in
    none)
        DISPLAY_ARGS=(
            -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
            -display none
            -serial mon:stdio
        )
        ;;
    vnc)
        DISPLAY_ARGS=(
            -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
            -vnc :${QEMU_VNC_DISPLAY}
            -serial stdio
        )
        echo "Display: VNC on port $((5900 + QEMU_VNC_DISPLAY))" >&2
        ;;
    cocoa)
        if [ "${HAS_COCOA}" = "no" ]; then
            echo "Warning: Cocoa not supported, falling back to VNC" >&2
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -vnc :${QEMU_VNC_DISPLAY}
                -serial stdio
            )
        else
            if [ "$(uname)" = "Darwin" ]; then
                defaults write "$(basename "${QEMU_BIN}")" NSAppSleepDisabled -bool YES 2>/dev/null || true
                if command -v taskpolicy >/dev/null 2>&1; then
                    ( while kill -0 $$ 2>/dev/null; do taskpolicy -B -p $$ 2>/dev/null || true; sleep 1; done ) </dev/null >/dev/null 2>&1 &
                fi
            fi
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -display cocoa
                -serial stdio
            )
            echo "Display: Cocoa (macOS native)" >&2
        fi
        ;;
    gtk)
        if [ "${HAS_GTK}" = "no" ]; then
            echo "Warning: GTK not supported, falling back to VNC" >&2
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -vnc :${QEMU_VNC_DISPLAY}
                -serial stdio
            )
        else
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -display gtk,gl=off
                -serial stdio
            )
            echo "Display: GTK" >&2
        fi
        ;;
    sdl|*)
        if [ "${HAS_SDL}" = "no" ]; then
            echo "Warning: SDL not supported, falling back to VNC" >&2
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -vnc :${QEMU_VNC_DISPLAY}
                -serial stdio
            )
        else
            DISPLAY_ARGS=(
                -device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES}
                -display sdl,gl=off
                -serial stdio
            )
            echo "Display: SDL" >&2
        fi
        ;;
esac"""
else:
    none_match = re.search(
        r'none\)\s*\n\s*(DISPLAY_ARGS="[^"]+")',
        old_case,
    )
    none_display_args = (
        none_match.group(1)
        if none_match
        else 'DISPLAY_ARGS="-device virtio-gpu-pci,xres=${QEMU_XRES},yres=${QEMU_YRES} -display none -monitor none -chardev stdio,id=serial0,signal=off -serial chardev:serial0"'
    )
    serial_tail_match = re.search(r'(-monitor none\b.*)"$', none_display_args)
    serial_tail = " " + serial_tail_match.group(1) if serial_tail_match else " -monitor none -serial file:/dev/fd/1"
    new_case = detect_block + f"""
# Set display arguments based on DISPLAY_TYPE
case "${{DISPLAY_TYPE}}" in
    none)
        {none_display_args}
        echo "Display: none (no graphics)"
        ;;
    vnc)
        DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -vnc :${{QEMU_VNC_DISPLAY}}{serial_tail}"
        echo "Display: VNC on port $((5900 + QEMU_VNC_DISPLAY))"
        ;;
    cocoa)
        if [ "${{HAS_COCOA}}" = "no" ]; then
            echo "Warning: Cocoa not supported, falling back to VNC" >&2
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -vnc :${{QEMU_VNC_DISPLAY}}{serial_tail}"
        else
            if [ "$(uname)" = "Darwin" ]; then
                defaults write "$(basename "${{QEMU_BIN}}")" NSAppSleepDisabled -bool YES 2>/dev/null || true
                if command -v taskpolicy >/dev/null 2>&1; then
                    ( while kill -0 $$ 2>/dev/null; do taskpolicy -B -p $$ 2>/dev/null || true; sleep 1; done ) </dev/null >/dev/null 2>&1 &
                fi
            fi
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -display cocoa{serial_tail}"
            echo "Display: Cocoa (macOS native)"
        fi
        ;;
    gtk)
        if [ "${{HAS_GTK}}" = "no" ]; then
            echo "Warning: GTK not supported, falling back to VNC" >&2
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -vnc :${{QEMU_VNC_DISPLAY}}{serial_tail}"
        else
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -display gtk,gl=off{serial_tail}"
            echo "Display: GTK"
        fi
        ;;
    sdl|*)
        if [ "${{HAS_SDL}}" = "no" ]; then
            echo "Warning: SDL not supported, falling back to VNC" >&2
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -vnc :${{QEMU_VNC_DISPLAY}}{serial_tail}"
        else
            DISPLAY_ARGS="-device virtio-gpu-pci,xres=${{QEMU_XRES}},yres=${{QEMU_YRES}} -display sdl,gl=off{serial_tail}"
            echo "Display: SDL"
        fi
        ;;
esac"""

text = text[:match.start()] + new_case + text[match.end():]
path.write_text(text, encoding="utf-8")
DISPLAY_PY
}

ensure_qemu_extended_capabilities_support() {
  local file="$1"
  python3 - "${file}" <<'EXT_CAP_PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# Remove any previous QEMU_CAPABILITIES_V1 block if rewriting an already-normalized launcher.
text = re.sub(
    r'\n?# QEMU_CAPABILITIES_V1_BEGIN\n.*?# QEMU_CAPABILITIES_V1_END\n?',
    '\n',
    text,
    flags=re.S,
)
# Remove any legacy pre-capabilities QEMU_USERDATA_SIZE_V1 block so userdata reset/resize
# runs after QEMU_INSTANCE_ID and QEMU_USERDATA_FILE are resolved.
text = re.sub(
    r'\n?# QEMU_USERDATA_SIZE_V1: optional sparse expansion of userdata\.img before boot\.\nQEMU_USERDATA_SIZE=.*?guest init will resize F2FS /data on boot\." >&2\n  fi\nfi\n?',
    '\n',
    text,
    flags=re.S,
)

cap_block = r'''# QEMU_CAPABILITIES_V1_BEGIN
QEMU_RESET="${QEMU_RESET:-0}"
QEMU_USERDATA_SIZE="${QEMU_USERDATA_SIZE:-}"
QEMU_AUDIO_BACKEND="${QEMU_AUDIO_BACKEND:-auto}"
QEMU_SHARED_DIR="${QEMU_SHARED_DIR:-}"
QEMU_USB="${QEMU_USB:-0}"
QEMU_USB_DISK="${QEMU_USB_DISK:-}"
QEMU_USB_HOST="${QEMU_USB_HOST:-}"
QEMU_USB_SERIAL="${QEMU_USB_SERIAL:-off}"
QEMU_BT_USB="${QEMU_BT_USB:-}"
QEMU_BALLOON="${QEMU_BALLOON:-0}"
QEMU_RNG="${QEMU_RNG:-on}"
QEMU_PORT_FORWARD="${QEMU_PORT_FORWARD:-}"
QEMU_RIL_MODEM="${QEMU_RIL_MODEM:-auto}"
QEMU_WIFI_MODE="${QEMU_WIFI_MODE:-auto}"
QEMU_GPS="${QEMU_GPS:-}"
QEMU_SENSOR="${QEMU_SENSOR:-}"
QEMU_BATTERY="${QEMU_BATTERY:-}"
QEMU_THERMAL="${QEMU_THERMAL:-}"
QEMU_SDCARD="${QEMU_SDCARD:-}"
QEMU_NVME_DISK="${QEMU_NVME_DISK:-}"
QEMU_RTC="${QEMU_RTC:-utc}"
QEMU_WATCHDOG="${QEMU_WATCHDOG:-none}"
QEMU_TPM="${QEMU_TPM:-}"
QEMU_CLIPBOARD="${QEMU_CLIPBOARD:-auto}"
QEMU_CAMERA_FEED="${QEMU_CAMERA_FEED:-}"
QEMU_HW_BRIDGE="${QEMU_HW_BRIDGE:-auto}"
QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:-}"
QEMU_HOSTFWD_EXTRAS=""
if [ -n "${QEMU_PORT_FORWARD}" ]; then
  for pf_rule in $(echo "${QEMU_PORT_FORWARD}" | tr ',' ' '); do
    [ -n "${pf_rule}" ] || continue
    if [[ "${pf_rule}" =~ ^((tcp|udp):)?([1-9][0-9]{0,4}):([1-9][0-9]{0,4})$ ]]; then
      pf_proto="${BASH_REMATCH[2]:-tcp}"
      pf_hport="${BASH_REMATCH[3]}"
      pf_gport="${BASH_REMATCH[4]}"
      if [ "${pf_hport}" -gt 65535 ] || [ "${pf_gport}" -gt 65535 ]; then
        echo "port-forward ports must be 1..65535, got: ${pf_rule}" >&2
        exit 2
      fi
      QEMU_HOSTFWD_EXTRAS="${QEMU_HOSTFWD_EXTRAS},hostfwd=${pf_proto}::${pf_hport}-:${pf_gport}"
    else
      echo "invalid QEMU_PORT_FORWARD rule: ${pf_rule} (expected [tcp|udp:]HOST_PORT:GUEST_PORT)" >&2
      exit 2
    fi
  done
  if declare -p NET_ARGS >/dev/null 2>&1; then
    case "${NET_ARGS[1]:-}" in
      user,*hostfwd=*) NET_ARGS[1]="${NET_ARGS[1]}${QEMU_HOSTFWD_EXTRAS}" ;;
    esac
  fi
  echo "Custom host port forwarding enabled: ${QEMU_PORT_FORWARD}" >&2
fi

# 0. Multi-Instance Disk Isolation (--instance ID / --userdata-file PATH / --reset / --userdata-size)
case "${QEMU_RESET}" in
  0|1) ;;
  *)
    echo "QEMU_RESET must be 0 or 1, got: ${QEMU_RESET}" >&2
    exit 2
    ;;
esac
if [ -n "${QEMU_USERDATA_SIZE}" ]; then
  if [[ "${QEMU_USERDATA_SIZE}" =~ ^([1-9][0-9]*)([MmGg]([Ii]?[Bb])?)?$ ]]; then
    userdata_num="${BASH_REMATCH[1]}"
    userdata_unit="${BASH_REMATCH[2]:-M}"
    case "${userdata_unit}" in
      [Gg]*) userdata_target_bytes=$((userdata_num * 1024 * 1024 * 1024)) ;;
      *) userdata_target_bytes=$((userdata_num * 1024 * 1024)) ;;
    esac
  else
    echo "invalid userdata size: ${QEMU_USERDATA_SIZE} (expected e.g. 4096, 4096M, 4G, 8G)" >&2
    exit 2
  fi
  if [ "${QEMU_RESET}" = "1" ] && [ "${userdata_target_bytes}" -lt 2147483648 ]; then
    echo "cannot reset userdata.img below minimum F2FS image size 2147483648 bytes (2G), got: ${QEMU_USERDATA_SIZE}" >&2
    exit 2
  fi
fi

QEMU_PRISTINE_F2FS_B64="7d3NbhvHAQfwXX5JdoRWDYwg1aW82SlqWqJkRw4KNG1yKvwCvRSgSEqWLYmqSMtuTmmBoocecs4hD9FD7z71HVrAT2AECPoBBHXhdGd3KMmGncrGOra4vx8wO/xYDsVZSeD8OZy9mESLCVBhi+1//yNNvpecyy7Xs7KQlXA5jeW/b4W95vN9/5nt8E1WaklRWrEOtz9x4/msvJOVpaLNNN71+/+sdc9/9vH5P/30z4NfffTF21eSQdJLJlkBquZiVnb3i8t3d4t6tFXUt+LtvcPtvN5dO4x1ccfu7Xh9VNR3hxt5C3d70/2K/yqrW8X+o/0741Bv7vT6od7a3sxv398rnnB8uDVtJ39AbzzJ97vVO8hvHww38np7PMrrrU+Kn+9erD8ZT4r2BrHd3+YPTyaTaV3cPrw3LF7X/u287u9N4u1Fu6PB8F6oD2Mdny652Stex81xUQ+KHyc53B3cLvYv+uk3/dHd7hn7PbixvXfnXvtweDDeHu213+8sd1bWLo8ONsaTXv/25eXl1fXly1u994fLve6gf/3q6tX2pem9H27c2d4ZDA/ea1/6aKe3t/WL7OqkaK8frh+12u12Vjqr7Us3J5P98QdXrmxtT27e2ej0R7tXdnYOi83l/YPRrWF/0snubA+vr69du7a2vjm4trK+OhxeG6z3NwYba1eXu92V1c3+5vXlbq+7svLeT9pPP/ONGx+f+vm8/iT5fMH/Ql5QIyvN+H6zoTtextt/33yYygFADiAHAOQAcgA5gBxADoAcoDI5QP7GfDFJHibLv8xv/PFcXr0V91nLyq+z8jB7Iz8XRwLh/fw3z/Bth+g0+6fpcfuNWMJzfpiV+2Es8v2T+waOIQAAAJzWgwd//EsacwAAAACqon60WYqfrIdNulR8lptvakvFh7r5pr6kz2bo6MsBAAAAKqix8FVJLZX7ffMwSE0ulDbmTcI888cltfb1dPp6KR6FzfxrOPJyAAAAAKiCPLJpygEAAACgMjlASw4AAAAAlckB5pwvAAAAACohnC8gH2yfIgf4sn4cHtSeM65/erGE8JCwisKj5+w/99T+zbTIDE6TAwAAAAAv5q//6jxOYw7QcN6IqsqPqKVCX8KZXyo0hnuNE1Va/LnHv/o0/nYUlfk3AAAwE2oxB3hyRNA8OUIEAAAAzr780716zAEAAACA2c8BGnIAAAAAqEwO0LROIAAAAFRCWCcwH3gvlrlMXHmLupXXUnlLw5WotAXmSlxcbqG0lswxAQAAeCM1WsZsAEClzOsCAKrsnByAN1tDFwAAAJTo/NM5QBpLvgxAcU6BsFmKI7I0XAjnFayFCyFFqC/pRQAAADgb3ilygLgMYPzstVlULd0DAAAAMyL/rD+NOQAAAAAw+zlATQ4AAAAAlckB6s/8XkCjuD9+PaBZXIvfEmgdPRYAAICzqH60WYoDwOlycM3pIDAsCdeajgEtCzdLGuYDAAAAyAHkAJXRkgMAAABUUGPhq5JayieMlzauDKeuSy6U1VoIO+aSxyW19nV4qaWd2/xR2Mx/90d+Tg4AAAAAVZBHNvNyAAAAAKhMDvBIDgAAAFBBvhfw4mbjewFhUYhwvL78edJ+otcXT1zO/OH+g1vPqp95/Hmuo0Pc1hcAAAC8OvXk6NyAR2P1sBZkGnOAT393PDLN73/3+HEvkgNMmWLw7TlAmvV2TRYAAADAK9JIjicvTHOAcBqImhzgteQA9ay3G3IAAAAAXpFmLCdzgHAGyLoc4LXkAM2st1tyAAAAAF6RViwnc4BGyADaxaC9/n9bqOePrE0v1o6WDgAAINOZ1h19AcCbK405wA9+dP9vIR/49INzeUlO5AZN3QQzTagH1VXXBVBZDV0A1X3/H3MAY30gfdn7fREIAADOjHrMAS7+0HwAqCrzAaDC7wN0AVSW+QBQ4b//mAMY6wPmAwAAwOxrxhzgws/MB4CqMh8Aqst8AKgu8wGguloxBzDWB8wHAACA2fc/"

reset_userdata_image_file() {
  local target_img="$1"
  local desired_bytes="${2:-2147483648}"
  if [ "${desired_bytes}" -lt 2147483648 ]; then
    desired_bytes=2147483648
  fi
  mkdir -p "$(dirname "${target_img}")"
  python3 - "${target_img}" "${desired_bytes}" "${QEMU_PRISTINE_F2FS_B64}" <<'RESET_PY'
import base64
import os
import struct
import sys
import zlib

target_path = sys.argv[1]
desired_bytes = max(2147483648, int(sys.argv[2]))
payload = zlib.decompress(base64.b64decode(sys.argv[3]), -15)
pos = 0
count = struct.unpack_from("<I", payload, pos)[0]
pos += 4
tmp_path = f"{target_path}.reset.{os.getpid()}"
with open(tmp_path, "wb") as f:
    f.truncate(desired_bytes)
    for _ in range(count):
        blk_idx, blk_len = struct.unpack_from("<II", payload, pos)
        pos += 8
        f.seek(blk_idx * 4096)
        f.write(payload[pos : pos + blk_len])
        pos += blk_len
os.replace(tmp_path, target_path)
RESET_PY
}

QEMU_USERDATA_FILE="${QEMU_USERDATA_FILE:-}"
QEMU_SYS_PROD_FILE="${QEMU_SYS_PROD_FILE:-${OHOS_IMG}/sys_prod.img}"
QEMU_CHIP_PROD_FILE="${QEMU_CHIP_PROD_FILE:-${OHOS_IMG}/chip_prod.img}"
if [ -n "${QEMU_INSTANCE_ID:-}" ] && [ "${QEMU_INSTANCE_ID}" != "1" ]; then
  qemu_inst_dir="${OHOS_IMG}/instances/instance-${QEMU_INSTANCE_ID}"
  mkdir -p "${qemu_inst_dir}"
  if [ ! -f "${qemu_inst_dir}/userdata.img" ]; then
    reset_userdata_image_file "${qemu_inst_dir}/userdata.img" 2147483648
  fi
  for inst_img in sys_prod.img chip_prod.img; do
    if { [ ! -f "${qemu_inst_dir}/${inst_img}" ] || [ "${QEMU_RESET}" = "1" ]; } && [ -f "${OHOS_IMG}/${inst_img}" ]; then
      cp -c "${OHOS_IMG}/${inst_img}" "${qemu_inst_dir}/${inst_img}" 2>/dev/null || \
        cp --reflink=auto "${OHOS_IMG}/${inst_img}" "${qemu_inst_dir}/${inst_img}" 2>/dev/null || \
        cp "${OHOS_IMG}/${inst_img}" "${qemu_inst_dir}/${inst_img}"
    fi
  done
  QEMU_USERDATA_FILE="${QEMU_USERDATA_FILE:-${qemu_inst_dir}/userdata.img}"
  QEMU_SYS_PROD_FILE="${qemu_inst_dir}/sys_prod.img"
  QEMU_CHIP_PROD_FILE="${qemu_inst_dir}/chip_prod.img"
  echo "Multi-instance disk isolation active (instance=${QEMU_INSTANCE_ID}): ${qemu_inst_dir}" >&2
fi
QEMU_USERDATA_FILE="${QEMU_USERDATA_FILE:-${OHOS_IMG}/userdata.img}"

# QEMU_RESET_V1: optional factory reset of active userdata.img before boot.
if [ "${QEMU_RESET}" = "1" ]; then
  userdata_pre_reset_bytes=2147483648
  if [ -f "${QEMU_USERDATA_FILE}" ]; then
    userdata_pre_reset_bytes=$(stat -f "%z" "${QEMU_USERDATA_FILE}" 2>/dev/null || stat -c "%s" "${QEMU_USERDATA_FILE}" 2>/dev/null || wc -c < "${QEMU_USERDATA_FILE}" | tr -d "[:space:]")
  fi
  if [ -n "${QEMU_USERDATA_SIZE}" ]; then
    reset_userdata_image_file "${QEMU_USERDATA_FILE}" 2147483648
    echo "Reset ${QEMU_USERDATA_FILE} to clean factory F2FS image (2147483648 bytes)." >&2
  elif [ "${userdata_pre_reset_bytes}" -gt 2147483648 ]; then
    reset_userdata_image_file "${QEMU_USERDATA_FILE}" "${userdata_pre_reset_bytes}"
    echo "Reset ${QEMU_USERDATA_FILE} to clean factory F2FS image (preserved custom size: ${userdata_pre_reset_bytes} bytes; guest init will resize F2FS /data on boot)." >&2
  else
    reset_userdata_image_file "${QEMU_USERDATA_FILE}" 2147483648
    echo "Reset ${QEMU_USERDATA_FILE} to clean factory F2FS image (2147483648 bytes)." >&2
  fi
fi

# QEMU_USERDATA_SIZE_V1: optional sparse expansion of userdata.img before boot.
if [ -n "${QEMU_USERDATA_SIZE}" ]; then
  userdata_img="${QEMU_USERDATA_FILE}"
  if [ ! -f "${userdata_img}" ]; then
    echo "userdata.img not found at ${userdata_img}" >&2
    exit 2
  fi
  userdata_current_bytes=$(stat -f "%z" "${userdata_img}" 2>/dev/null || stat -c "%s" "${userdata_img}" 2>/dev/null || wc -c < "${userdata_img}" | tr -d "[:space:]")
  if [ "${userdata_target_bytes}" -lt "${userdata_current_bytes}" ]; then
    echo "cannot shrink userdata.img from ${userdata_current_bytes} bytes to ${userdata_target_bytes} bytes (${QEMU_USERDATA_SIZE}); pass --reset --userdata-size ${QEMU_USERDATA_SIZE} or restore a smaller userdata.img first" >&2
    exit 2
  elif [ "${userdata_target_bytes}" -gt "${userdata_current_bytes}" ]; then
    if command -v truncate >/dev/null 2>&1; then
      truncate -s "${userdata_target_bytes}" "${userdata_img}"
    else
      dd if=/dev/null of="${userdata_img}" bs=1 count=0 seek="${userdata_target_bytes}" status=none 2>/dev/null || \
        dd if=/dev/null of="${userdata_img}" bs=1 count=0 seek="${userdata_target_bytes}" 2>/dev/null
    fi
    echo "Expanded ${userdata_img} from ${userdata_current_bytes} to ${userdata_target_bytes} bytes (${QEMU_USERDATA_SIZE}); guest init will resize F2FS /data on boot." >&2
  fi
fi

# 1. Host Audio Backend (Category 1: ES1370 + host audiodev)
DETECT_AUDIODEVS="$(${QEMU_BIN} -audiodev help 2>&1 || true)"
case "${QEMU_AUDIO_BACKEND}" in
  auto)
    if [ "${DISPLAY_TYPE}" = "none" ] || [ "${DISPLAY_TYPE}" = "vnc" ]; then
      QEMU_RESOLVED_AUDIO="none"
    elif [ "$(uname -s)" = "Darwin" ] && echo "${DETECT_AUDIODEVS}" | grep -qw coreaudio; then
      QEMU_RESOLVED_AUDIO="coreaudio"
    elif echo "${DETECT_AUDIODEVS}" | grep -qw pipewire; then
      QEMU_RESOLVED_AUDIO="pipewire"
    elif echo "${DETECT_AUDIODEVS}" | grep -qw pa; then
      QEMU_RESOLVED_AUDIO="pa"
    elif echo "${DETECT_AUDIODEVS}" | grep -qw alsa; then
      QEMU_RESOLVED_AUDIO="alsa"
    elif echo "${DETECT_AUDIODEVS}" | grep -qw sdl; then
      QEMU_RESOLVED_AUDIO="sdl"
    else
      QEMU_RESOLVED_AUDIO="none"
    fi
    QEMU_AUDIO_DEV_ARG="-audiodev ${QEMU_RESOLVED_AUDIO},id=ohos_audio"
    echo "Audio backend: ${QEMU_RESOLVED_AUDIO} (auto)" >&2
    ;;
  none|coreaudio|pa|pipewire|alsa|sdl|dsound|oss|jack)
    QEMU_AUDIO_DEV_ARG="-audiodev ${QEMU_AUDIO_BACKEND},id=ohos_audio"
    echo "Audio backend: ${QEMU_AUDIO_BACKEND}" >&2
    ;;
  wav|wav:*)
    qemu_wav_path="${QEMU_AUDIO_BACKEND#wav}"
    qemu_wav_path="${qemu_wav_path#:}"
    if [ -z "${qemu_wav_path}" ]; then
      qemu_wav_path="/tmp/openharmony-qemu-audio-${HDC_HOST_PORT}.wav"
    fi
    QEMU_AUDIO_DEV_ARG="-audiodev wav,id=ohos_audio,path=${qemu_wav_path}"
    echo "Audio backend: wav (${qemu_wav_path})" >&2
    ;;
  *)
    echo "invalid QEMU_AUDIO_BACKEND: ${QEMU_AUDIO_BACKEND} (expected auto|none|coreaudio|pa|pipewire|alsa|sdl|dsound|wav[:PATH])" >&2
    exit 2
    ;;
esac

# 2. Host-Guest Shared Directory via VirtFS 9p (Category 1: virtio-9p-pci)
if [ -n "${QEMU_SHARED_DIR}" ]; then
  qemu_share_host_dir="${QEMU_SHARED_DIR}"
  qemu_share_tag="hostshare"
  if [[ "${QEMU_SHARED_DIR}" =~ ^(.+):([A-Za-z0-9_.-]+)$ ]] && [ -d "${BASH_REMATCH[1]}" ]; then
    qemu_share_host_dir="${BASH_REMATCH[1]}"
    qemu_share_tag="${BASH_REMATCH[2]}"
  fi
  if [ ! -d "${qemu_share_host_dir}" ]; then
    echo "shared directory not found: ${qemu_share_host_dir}" >&2
    exit 2
  fi
  qemu_share_host_dir="$(cd "${qemu_share_host_dir}" && pwd)"
  QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -fsdev local,id=fsdev_hostshare,path=${qemu_share_host_dir},security_model=mapped-xattr -device virtio-9p-pci,fsdev=fsdev_hostshare,mount_tag=${qemu_share_tag}"
  QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.share_tag=${qemu_share_tag}"
  echo "VirtFS 9p shared directory: ${qemu_share_host_dir} (tag=${qemu_share_tag} -> /mnt/share, /data/share)" >&2
fi

# Helper to auto-create/expand/format disk images specified as FILE or FILE:SIZE
prepare_qemu_disk_image() {
  local spec="$1"
  local label="$2"
  local img_path="${spec}"
  local size_spec=""
  if [[ "${spec}" =~ ^(.+):([1-9][0-9]*[MmGg]([Ii]?[Bb])?)$ ]]; then
    img_path="${BASH_REMATCH[1]}"
    size_spec="${BASH_REMATCH[2]}"
  fi
  local newly_created=0
  if [ -n "${size_spec}" ]; then
    if [[ "${size_spec}" =~ ^([1-9][0-9]*)([MmGg]([Ii]?[Bb])?)?$ ]]; then
      local snum="${BASH_REMATCH[1]}"
      local sunit="${BASH_REMATCH[2]:-M}"
      local target_bytes=0
      case "${sunit}" in
        [Gg]*) target_bytes=$((snum * 1024 * 1024 * 1024)) ;;
        *) target_bytes=$((snum * 1024 * 1024)) ;;
      esac
      if [ ! -f "${img_path}" ]; then
        newly_created=1
        mkdir -p "$(dirname "${img_path}")"
        if command -v truncate >/dev/null 2>&1; then
          truncate -s "${target_bytes}" "${img_path}"
        else
          dd if=/dev/null of="${img_path}" bs=1 count=0 seek="${target_bytes}" status=none 2>/dev/null || \
            dd if=/dev/null of="${img_path}" bs=1 count=0 seek="${target_bytes}" 2>/dev/null
        fi
      else
        local cur_bytes
        cur_bytes="$(stat -f "%z" "${img_path}" 2>/dev/null || stat -c "%s" "${img_path}" 2>/dev/null || echo 0)"
        if [ "${target_bytes}" -gt "${cur_bytes}" ]; then
          if command -v truncate >/dev/null 2>&1; then
            truncate -s "${target_bytes}" "${img_path}"
          else
            dd if=/dev/null of="${img_path}" bs=1 count=0 seek="${target_bytes}" status=none 2>/dev/null || \
              dd if=/dev/null of="${img_path}" bs=1 count=0 seek="${target_bytes}" 2>/dev/null
          fi
        fi
      fi
    fi
  fi
  if [ ! -f "${img_path}" ]; then
    echo "${label} image not found: ${img_path} (append :SIZE e.g. ${img_path}:64M to auto-create)" >&2
    exit 2
  fi
  if [ "${newly_created}" = "1" ]; then
    for mke2fs_bin in mke2fs /opt/homebrew/opt/e2fsprogs/sbin/mke2fs /usr/local/opt/e2fsprogs/sbin/mke2fs /sbin/mke2fs /usr/sbin/mke2fs; do
      if command -v "${mke2fs_bin}" >/dev/null 2>&1; then
        "${mke2fs_bin}" -t ext4 -F -q "${img_path}" >/dev/null 2>&1 || true
        break
      fi
    done
  fi
  PREPARED_DISK_PATH="${img_path}"
}

# 3. USB xHCI Controller, Virtual USB Storage & USB Host Passthrough (Category 1 & 2)
qemu_ext_scsi_added=0
ensure_ext_scsi_bus() {
  if [ "${qemu_ext_scsi_added}" = "0" ]; then
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device virtio-scsi-pci,id=scsi_ext0"
    qemu_ext_scsi_added=1
  fi
}
case "${QEMU_USB}" in
  0|1) ;;
  *) echo "QEMU_USB must be 0 or 1, got: ${QEMU_USB}" >&2; exit 2 ;;
esac
if [ "${QEMU_USB}" = "1" ] || [ -n "${QEMU_USB_DISK}" ] || [ -n "${QEMU_USB_HOST}" ] || [ -n "${QEMU_BT_USB}" ] || \
   { [ -n "${QEMU_USB_SERIAL}" ] && [ "${QEMU_USB_SERIAL}" != "off" ] && [ "${QEMU_USB_SERIAL}" != "0" ]; }; then
  QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device qemu-xhci,id=xhci0"
  echo "USB xHCI controller enabled (xhci0)." >&2
fi
if [ -n "${QEMU_USB_DISK}" ]; then
  prepare_qemu_disk_image "${QEMU_USB_DISK}" "USB disk"
  QEMU_USB_DISK="${PREPARED_DISK_PATH}"
  case "$(basename "${QEMU_BIN}")" in
    *qemu-system-arm)
      ensure_ext_scsi_bus
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -drive if=none,id=usb_disk0,file=${QEMU_USB_DISK},format=raw -device scsi-hd,bus=scsi_ext0.0,channel=0,scsi-id=0,lun=2,drive=usb_disk0,removable=on,vendor=OHOS,product=USBDISK0,serial=ohos-usbdisk0"
      ;;
    *)
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -drive if=none,id=usb_disk0,file=${QEMU_USB_DISK},format=raw -device usb-storage,bus=xhci0.0,drive=usb_disk0"
      ;;
  esac
  echo "USB mass storage attached: ${QEMU_USB_DISK} (-> /mnt/data/external/usb, /data/usb)" >&2
fi
if [ -n "${QEMU_USB_HOST}" ]; then
  if [[ "${QEMU_USB_HOST}" =~ ^(0x)?([0-9a-fA-F]{1,4}):(0x)?([0-9a-fA-F]{1,4})$ ]]; then
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device usb-host,bus=xhci0.0,vendorid=0x${BASH_REMATCH[2]},productid=0x${BASH_REMATCH[4]}"
    echo "USB host passthrough attached: 0x${BASH_REMATCH[2]}:0x${BASH_REMATCH[4]}" >&2
  else
    echo "invalid QEMU_USB_HOST=${QEMU_USB_HOST} (expected VID:PID hex, e.g. 1234:5678)" >&2
    exit 2
  fi
fi
if [ -n "${QEMU_BT_USB}" ]; then
  if [[ "${QEMU_BT_USB}" =~ ^(0x)?([0-9a-fA-F]{1,4}):(0x)?([0-9a-fA-F]{1,4})$ ]]; then
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device usb-host,bus=xhci0.0,vendorid=0x${BASH_REMATCH[2]},productid=0x${BASH_REMATCH[4]}"
    echo "Bluetooth USB adapter passthrough attached: 0x${BASH_REMATCH[2]}:0x${BASH_REMATCH[4]}" >&2
  else
    echo "invalid QEMU_BT_USB=${QEMU_BT_USB} (expected VID:PID hex, e.g. 0a12:0001)" >&2
    exit 2
  fi
fi

# 4. VirtIO Memory Balloon (virtio-balloon-pci) & VirtIO Hardware RNG (virtio-rng-pci)
case "${QEMU_BALLOON}" in
  0) ;;
  1)
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device virtio-balloon-pci,id=balloon0"
    echo "VirtIO memory balloon enabled (balloon0)." >&2
    ;;
  *) echo "QEMU_BALLOON must be 0 or 1, got: ${QEMU_BALLOON}" >&2; exit 2 ;;
esac
case "${QEMU_RNG}" in
  auto|on|1)
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device virtio-rng-pci,id=rng0"
    ;;
  off|0|none) ;;
  *)
    echo "invalid QEMU_RNG=${QEMU_RNG} (expected auto|on|off)" >&2
    exit 2
    ;;
esac

# 5. Virtual Wi-Fi Mode (Category 2: mac80211_hwsim / virt_wifi)
case "${QEMU_WIFI_MODE}" in
  auto) ;;
  hwsim|virt_wifi|off)
    QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.wifi=${QEMU_WIFI_MODE}"
    ;;
  *)
    echo "invalid QEMU_WIFI_MODE=${QEMU_WIFI_MODE} (expected auto|hwsim|virt_wifi|off)" >&2
    exit 2
    ;;
esac

# 6. External SD Card & NVMe Storage (--sdcard FILE[:SIZE], --nvme-disk FILE[:SIZE])
if [ -n "${QEMU_SDCARD}" ]; then
  prepare_qemu_disk_image "${QEMU_SDCARD}" "SD card"
  qemu_sdcard_path="${PREPARED_DISK_PATH}"
  case "$(basename "${QEMU_BIN}")" in
    *x86_64*)
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device sdhci-pci,id=sdhci0 -drive if=none,id=sdcard_drive0,file=${qemu_sdcard_path},format=raw -device sd-card,drive=sdcard_drive0"
      ;;
    *)
      ensure_ext_scsi_bus
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -drive if=none,id=sdcard_drive0,file=${qemu_sdcard_path},format=raw -device scsi-hd,bus=scsi_ext0.0,channel=0,scsi-id=0,lun=0,drive=sdcard_drive0,removable=on,vendor=OHOS,product=SDCARD0,serial=ohos-sdcard0"
      ;;
  esac
  echo "External SD card attached: ${qemu_sdcard_path} (-> /dev/mmcblk0, /mnt/data/external/sdcard, /data/sdcard)" >&2
fi
if [ -n "${QEMU_NVME_DISK}" ]; then
  prepare_qemu_disk_image "${QEMU_NVME_DISK}" "NVMe disk"
  qemu_nvme_path="${PREPARED_DISK_PATH}"
  case "$(basename "${QEMU_BIN}")" in
    *x86_64*)
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -drive if=none,id=nvme_drive0,file=${qemu_nvme_path},format=raw -device nvme,drive=nvme_drive0,serial=ohos-nvme0"
      ;;
    *)
      ensure_ext_scsi_bus
      QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -drive if=none,id=nvme_drive0,file=${qemu_nvme_path},format=raw -device scsi-hd,bus=scsi_ext0.0,channel=0,scsi-id=0,lun=1,drive=nvme_drive0,vendor=OHOS,product=NVME0,serial=ohos-nvme0"
      ;;
  esac
  echo "NVMe disk attached: ${qemu_nvme_path} (-> /dev/nvme0n1, /mnt/data/external/nvme, /data/nvme)" >&2
fi

# 7. RTC Clock Sync (--rtc utc|localtime|host) & Hardware Watchdog (--watchdog none|i6300esb[:ACTION])
case "${QEMU_RTC}" in
  utc)
    QEMU_RTC_BASE="utc"
    ;;
  localtime|host)
    QEMU_RTC_BASE="localtime"
    echo "RTC clock mode: ${QEMU_RTC} (base=localtime,clock=host)" >&2
    ;;
  *)
    echo "invalid QEMU_RTC=${QEMU_RTC} (expected utc|localtime|host)" >&2
    exit 2
    ;;
esac
case "${QEMU_WATCHDOG}" in
  none|off|0) ;;
  i6300esb|on|1)
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device i6300esb -watchdog-action reset"
    echo "Hardware watchdog enabled: i6300esb (action=reset)" >&2
    ;;
  i6300esb:*)
    qemu_wdt_act="${QEMU_WATCHDOG#i6300esb:}"
    case "${qemu_wdt_act}" in
      reset|shutdown|poweroff|pause|debug|none)
        QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device i6300esb -watchdog-action ${qemu_wdt_act}"
        echo "Hardware watchdog enabled: i6300esb (action=${qemu_wdt_act})" >&2
        ;;
      *)
        echo "invalid watchdog action in QEMU_WATCHDOG=${QEMU_WATCHDOG} (expected reset|shutdown|poweroff|pause|debug|none)" >&2
        exit 2
        ;;
    esac
    ;;
  *)
    echo "invalid QEMU_WATCHDOG=${QEMU_WATCHDOG} (expected none|i6300esb[:reset|shutdown|poweroff|pause|debug|none])" >&2
    exit 2
    ;;
esac

# 8. TPM 2.0 Emulator (--tpm PATH)
if [ -n "${QEMU_TPM}" ]; then
  qemu_tpm_sock="${QEMU_TPM}"
  if [ -d "${QEMU_TPM}" ]; then
    qemu_tpm_sock="${QEMU_TPM%/}/swtpm.sock"
    if [ ! -S "${qemu_tpm_sock}" ] && command -v swtpm >/dev/null 2>&1; then
      swtpm socket --tpm2 --tpmstate dir="${QEMU_TPM}" --ctrl type=unixio,path="${qemu_tpm_sock}" --daemon 2>/dev/null || true
      for _ in $(seq 1 20); do
        [ -S "${qemu_tpm_sock}" ] && break
        sleep 0.05
      done
    fi
  fi
  if [ ! -S "${qemu_tpm_sock}" ]; then
    echo "TPM socket not found at ${qemu_tpm_sock} (provide a running swtpm control socket or directory with swtpm installed)" >&2
    exit 2
  fi
  case "$(basename "${QEMU_BIN}")" in
    *x86_64*) qemu_tpm_dev="tpm-crb" ;;
    *) qemu_tpm_dev="tpm-tis-device" ;;
  esac
  QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -chardev socket,id=chrtpm0,path=${qemu_tpm_sock} -tpmdev emulator,id=tpm0,chardev=chrtpm0 -device ${qemu_tpm_dev},tpmdev=tpm0"
  echo "TPM 2.0 attached: ${qemu_tpm_sock} (${qemu_tpm_dev})" >&2
fi

# 9. Boot-time GPS, Sensor, Battery, Thermal, Camera & Clipboard Configuration
if [ -n "${QEMU_GPS}" ]; then
  if [[ "${QEMU_GPS}" =~ [[:space:]] ]]; then
    echo "QEMU_GPS cannot contain spaces (expected LAT,LON[,ALT[,SPEED[,BEARING[,HACC[,VACC]]]]])" >&2
    exit 2
  fi
  [ "${QEMU_HW_BRIDGE}" = "off" ] && QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.gps=${QEMU_GPS}"
  echo "GPS initial location: ${QEMU_GPS}" >&2
fi
if [ -n "${QEMU_SENSOR}" ]; then
  if [[ "${QEMU_SENSOR}" =~ [[:space:]] ]]; then
    echo "QEMU_SENSOR cannot contain spaces (expected AX,AY,AZ[:RX,RY,RZ,RW])" >&2
    exit 2
  fi
  [ "${QEMU_HW_BRIDGE}" = "off" ] && QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.sensor=${QEMU_SENSOR}"
  echo "Sensor initial state: ${QEMU_SENSOR}" >&2
fi
if [ -n "${QEMU_BATTERY}" ]; then
  if ! [[ "${QEMU_BATTERY}" =~ ^([0-9]{1,3})(:(charging|discharging|full|not_charging|not-charging))?$ ]]; then
    echo "invalid QEMU_BATTERY=${QEMU_BATTERY} (expected LEVEL[:charging|discharging|full|not_charging], e.g. 85:discharging)" >&2
    exit 2
  fi
  QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.battery=${QEMU_BATTERY}"
  echo "Battery simulation: ${QEMU_BATTERY}" >&2
fi
if [ -n "${QEMU_THERMAL}" ]; then
  if ! [[ "${QEMU_THERMAL}" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
    echo "invalid QEMU_THERMAL=${QEMU_THERMAL} (expected temperature in Celsius, e.g. 36.5)" >&2
    exit 2
  fi
  [ "${QEMU_HW_BRIDGE}" = "off" ] && QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.thermal=${QEMU_THERMAL}"
  echo "Thermal simulation: ${QEMU_THERMAL} C" >&2
fi
if [ -n "${QEMU_CAMERA_FEED}" ]; then
  if [[ "${QEMU_CAMERA_FEED}" =~ [[:space:]] ]]; then
    echo "QEMU_CAMERA_FEED cannot contain spaces (expected bars|smpte|squares|checkers|cross|ramp|noise|moving)" >&2
    exit 2
  fi
  [ "${QEMU_HW_BRIDGE}" = "off" ] && QEMU_BOOT_EXTRAS="${QEMU_BOOT_EXTRAS:+${QEMU_BOOT_EXTRAS} }ohos.boot.qemu.camera=${QEMU_CAMERA_FEED}"
  echo "Virtual camera feed pattern: ${QEMU_CAMERA_FEED}" >&2
fi

# 10. Cellular RIL Virtual AT Modem & Dynamic Hardware Bridge over VirtIO Serial
qemu_virtio_serial_bus_added=0
ensure_virtio_serial_bus() {
  if [ "${qemu_virtio_serial_bus_added}" = "0" ]; then
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -device virtio-serial-pci,id=virtio_serial0"
    qemu_virtio_serial_bus_added=1
  fi
}

qemu_pkg_root="$(cd "$(dirname "$0")/.." && pwd)"
case "${QEMU_RIL_MODEM}" in
  auto|on)
    qemu_at_modem_py="${qemu_pkg_root}/tools/qemu_at_modem.py"
    if [ -f "${qemu_at_modem_py}" ] && command -v python3 >/dev/null 2>&1; then
      qemu_ril_socket="/tmp/openharmony-qemu-ril-${HDC_HOST_PORT}.sock"
      qemu_ril_pidfile="/tmp/openharmony-qemu-ril-${HDC_HOST_PORT}.pid"
      qemu_ril_logfile="/tmp/openharmony-qemu-ril-${HDC_HOST_PORT}.log"
      if [ -f "${qemu_ril_pidfile}" ]; then
        old_ril_pid="$(cat "${qemu_ril_pidfile}" 2>/dev/null || true)"
        if [ -n "${old_ril_pid}" ]; then
          kill "${old_ril_pid}" 2>/dev/null || true
        fi
        rm -f "${qemu_ril_pidfile}"
      fi
      rm -f "${qemu_ril_socket}"
      python3 "${qemu_at_modem_py}" --socket "${qemu_ril_socket}" --pidfile "${qemu_ril_pidfile}" --log "${qemu_ril_logfile}" </dev/null >/dev/null 2>&1 &
      for _ in $(seq 1 25); do
        [ -S "${qemu_ril_socket}" ] && break
        sleep 0.05
      done
      if [ -S "${qemu_ril_socket}" ]; then
        (
          while kill -0 $$ 2>/dev/null; do
            sleep 1
          done
          if [ -f "${qemu_ril_pidfile}" ]; then
            kill "$(cat "${qemu_ril_pidfile}" 2>/dev/null)" 2>/dev/null || true
            rm -f "${qemu_ril_pidfile}"
          fi
          rm -f "${qemu_ril_socket}"
        ) </dev/null >/dev/null 2>&1 &
        ensure_virtio_serial_bus
        QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -chardev socket,id=ril_chardev,path=${qemu_ril_socket} -device virtserialport,bus=virtio_serial0.0,nr=1,chardev=ril_chardev,name=ohos.ril.at0"
        echo "Cellular RIL virtual AT modem attached: ${qemu_ril_socket} (ohos.ril.at0 -> /dev/ttyRIL0)" >&2
      elif [ "${QEMU_RIL_MODEM}" = "on" ]; then
        echo "failed to start RIL virtual AT modem socket at ${qemu_ril_socket}" >&2
        exit 2
      fi
    elif [ "${QEMU_RIL_MODEM}" = "on" ]; then
      echo "QEMU_RIL_MODEM=on requires python3 and ${qemu_at_modem_py}" >&2
      exit 2
    fi
    ;;
  off) ;;
  *)
    echo "invalid QEMU_RIL_MODEM=${QEMU_RIL_MODEM} (expected auto|on|off)" >&2
    exit 2
    ;;
esac

qemu_usb_serial_socket=""
case "${QEMU_USB_SERIAL}" in
  off|0|"") ;;
  auto|on|1|loopback)
    qemu_usb_serial_socket="/tmp/openharmony-qemu-usb-serial-${HDC_HOST_PORT}.sock"
    rm -f "${qemu_usb_serial_socket}"
    ;;
  pty|unix:*|tcp:*) ;;
  *)
    echo "invalid QEMU_USB_SERIAL=${QEMU_USB_SERIAL} (expected off|auto|on|loopback|pty|unix:PATH|tcp:HOST:PORT)" >&2
    exit 2
    ;;
esac

case "${QEMU_HW_BRIDGE}" in
  auto|on)
    qemu_hw_ctrl_py="${qemu_pkg_root}/tools/qemu_hw_controller.py"
    if [ -f "${qemu_hw_ctrl_py}" ] && command -v python3 >/dev/null 2>&1; then
      qemu_hw_socket="/tmp/openharmony-qemu-hw-${HDC_HOST_PORT}.sock"
      qemu_hw_ctrl_socket="/tmp/openharmony-qemu-hw-${HDC_HOST_PORT}.ctrl.sock"
      qemu_hw_pidfile="/tmp/openharmony-qemu-hw-${HDC_HOST_PORT}.pid"
      qemu_hw_logfile="/tmp/openharmony-qemu-hw-${HDC_HOST_PORT}.log"
      if [ -f "${qemu_hw_pidfile}" ]; then
        old_hw_pid="$(cat "${qemu_hw_pidfile}" 2>/dev/null || true)"
        if [ -n "${old_hw_pid}" ]; then
          kill "${old_hw_pid}" 2>/dev/null || true
        fi
        rm -f "${qemu_hw_pidfile}"
      fi
      rm -f "${qemu_hw_socket}" "${qemu_hw_ctrl_socket}"
      hw_ctrl_args=(
        --daemon
        --socket "${qemu_hw_socket}"
        --ctrl-socket "${qemu_hw_ctrl_socket}"
        --pidfile "${qemu_hw_pidfile}"
        --log "${qemu_hw_logfile}"
      )
      [ -n "${qemu_usb_serial_socket}" ] && hw_ctrl_args+=(--usb-serial-socket "${qemu_usb_serial_socket}" --usb-serial-mode loopback)
      [ -n "${QEMU_GPS}" ] && hw_ctrl_args+=(--gps "${QEMU_GPS}")
      [ -n "${QEMU_SENSOR}" ] && hw_ctrl_args+=(--sensor "${QEMU_SENSOR}")
      [ -n "${QEMU_BATTERY}" ] && hw_ctrl_args+=(--battery "${QEMU_BATTERY}")
      [ -n "${QEMU_THERMAL}" ] && hw_ctrl_args+=(--thermal "${QEMU_THERMAL}")
      [ -n "${QEMU_CAMERA_FEED}" ] && hw_ctrl_args+=(--camera "${QEMU_CAMERA_FEED}")
      case "${QEMU_CLIPBOARD}" in
        auto|off) ;;
        on) hw_ctrl_args+=(--clipboard-sync) ;;
        text:*) hw_ctrl_args+=(--clipboard "${QEMU_CLIPBOARD#text:}") ;;
        *) hw_ctrl_args+=(--clipboard "${QEMU_CLIPBOARD}") ;;
      esac
      python3 "${qemu_hw_ctrl_py}" "${hw_ctrl_args[@]}" </dev/null >/dev/null 2>&1 &
      for _ in $(seq 1 25); do
        [ -S "${qemu_hw_socket}" ] && break
        sleep 0.05
      done
      if [ -S "${qemu_hw_socket}" ]; then
        (
          while kill -0 $$ 2>/dev/null; do
            sleep 1
          done
          if [ -f "${qemu_hw_pidfile}" ]; then
            kill "$(cat "${qemu_hw_pidfile}" 2>/dev/null)" 2>/dev/null || true
            rm -f "${qemu_hw_pidfile}"
          fi
          rm -f "${qemu_hw_socket}" "${qemu_hw_ctrl_socket}" "${qemu_usb_serial_socket}"
        ) </dev/null >/dev/null 2>&1 &
        ensure_virtio_serial_bus
        QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -chardev socket,id=hw_bridge_chardev,path=${qemu_hw_socket} -device virtserialport,bus=virtio_serial0.0,nr=2,chardev=hw_bridge_chardev,name=ohos.hw.bridge0"
        echo "Hardware control bridge attached: ${qemu_hw_ctrl_socket} (ohos.hw.bridge0 -> /vendor/bin/qemu-hw-bridge)" >&2
      elif [ "${QEMU_HW_BRIDGE}" = "on" ]; then
        echo "failed to start hardware control bridge socket at ${qemu_hw_socket}" >&2
        exit 2
      fi
    elif [ "${QEMU_HW_BRIDGE}" = "on" ]; then
      echo "QEMU_HW_BRIDGE=on requires python3 and ${qemu_hw_ctrl_py}" >&2
      exit 2
    fi
    ;;
  off) ;;
  *)
    echo "invalid QEMU_HW_BRIDGE=${QEMU_HW_BRIDGE} (expected auto|on|off)" >&2
    exit 2
    ;;
esac

if [ -n "${QEMU_USB_SERIAL}" ] && [ "${QEMU_USB_SERIAL}" != "off" ] && [ "${QEMU_USB_SERIAL}" != "0" ]; then
  usb_serial_chr_spec=""
  case "${QEMU_USB_SERIAL}" in
    auto|on|1|loopback)
      if [ -n "${qemu_usb_serial_socket}" ] && [ -S "${qemu_usb_serial_socket}" ]; then
        usb_serial_chr_spec="socket,id=usb_serial_chr0,path=${qemu_usb_serial_socket}"
      else
        usb_serial_chr_spec="pty,id=usb_serial_chr0"
      fi
      ;;
    pty)
      usb_serial_chr_spec="pty,id=usb_serial_chr0"
      ;;
    unix:*)
      usb_serial_chr_spec="socket,id=usb_serial_chr0,path=${QEMU_USB_SERIAL#unix:},server=on,wait=off"
      ;;
    tcp:*)
      usb_tcp_spec="${QEMU_USB_SERIAL#tcp:}"
      usb_tcp_host="${usb_tcp_spec%:*}"
      usb_tcp_port="${usb_tcp_spec##*:}"
      [ "${usb_tcp_host}" = "${usb_tcp_port}" ] && usb_tcp_host="127.0.0.1"
      usb_serial_chr_spec="socket,id=usb_serial_chr0,host=${usb_tcp_host},port=${usb_tcp_port},server=on,wait=off"
      ;;
  esac
  if grep -q '^CONFIG_USB_SERIAL_FTDI_SIO=y' "${qemu_pkg_root}/kernel.config" 2>/dev/null && \
     grep -q '^CONFIG_USB_XHCI_HCD=y' "${qemu_pkg_root}/kernel.config" 2>/dev/null; then
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -chardev ${usb_serial_chr_spec} -device usb-serial,bus=xhci0.0,chardev=usb_serial_chr0,id=usb_serial0"
    echo "USB FTDI serial adapter attached: ${QEMU_USB_SERIAL} (usb-serial 0403:6001 -> /dev/ttyUSB0)" >&2
  else
    ensure_virtio_serial_bus
    QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS} -chardev null,id=usb_serial_bus_chr0 -device usb-serial,bus=xhci0.0,chardev=usb_serial_bus_chr0,id=usb_serial0 -chardev ${usb_serial_chr_spec} -device virtserialport,bus=virtio_serial0.0,nr=3,chardev=usb_serial_chr0,name=ohos.usb.serial0"
    echo "USB FTDI serial adapter attached: ${QEMU_USB_SERIAL} (usb-serial 0403:6001 + ohos.usb.serial0 -> /dev/ttyUSB0)" >&2
  fi
fi
# QEMU_CAPABILITIES_V1_END'''

# Replace hardcoded -audiodev none,id=ohos_audio with ${QEMU_AUDIO_DEV_ARG}.
if "-audiodev none,id=ohos_audio" in text or "-audiodev ${QEMU_AUDIO_DEV_ARG}" in text:
    text = text.replace("-audiodev none,id=ohos_audio", "${QEMU_AUDIO_DEV_ARG}")
elif "ES1370" not in text and "es1370" not in text:
    cap_block += '\nQEMU_EXTRA_ARGS="${QEMU_AUDIO_DEV_ARG} -device ES1370,audiodev=ohos_audio ${QEMU_EXTRA_ARGS}"'

# Parameterize -rtc base=... with ${QEMU_RTC_BASE}.
if "-rtc base=utc,clock=host" in text or "-rtc base=${QEMU_RTC_BASE},clock=host" in text:
    text = text.replace("-rtc base=utc,clock=host", "-rtc base=${QEMU_RTC_BASE},clock=host")
else:
    cap_block += '\nQEMU_EXTRA_ARGS="-rtc base=${QEMU_RTC_BASE},clock=host ${QEMU_EXTRA_ARGS}"'

# Parameterize direct -netdev user hostfwd with ${QEMU_HOSTFWD_EXTRAS} when NET_ARGS array is not used.
if "NET_ARGS=(" not in text:
    text = re.sub(
        r'hostfwd=tcp::\$\{HDC_HOST_PORT\}-:5555(?:\$\{QEMU_HOSTFWD_EXTRAS\})?',
        'hostfwd=tcp::${HDC_HOST_PORT}-:5555${QEMU_HOSTFWD_EXTRAS}',
        text,
    )

# Wire per-instance writable disk variables and disable write locking on read-only base images.
for img_name, var_name in [
    ("userdata.img", "${QEMU_USERDATA_FILE}"),
    ("sys_prod.img", "${QEMU_SYS_PROD_FILE}"),
    ("chip_prod.img", "${QEMU_CHIP_PROD_FILE}"),
]:
    text = text.replace(f'file="${{OHOS_IMG}}/{img_name}"', f'file="{var_name}"')
    text = text.replace(f'file=${{OHOS_IMG}}/{img_name}', f'file={var_name}')

for ro_id in ("updater", "system", "vendor"):
    text = re.sub(
        rf'(format=raw,id={ro_id})(?!,file\.locking=off)',
        r'\1,file.locking=off',
        text,
    )

# Ensure kernel -append places ${QEMU_BOOT_EXTRAS} at the end (after ohos.required_mount.data)
# and strips leading indentation on continuation lines so 32-bit ARM COMMAND_LINE_SIZE (1024)
# never truncates ohos.required_mount.* parameters.
text = text.replace("oemmode=rd ${QEMU_BOOT_EXTRAS} ", "oemmode=rd ")
text = re.sub(
    r'\\\n[ \t]+(default_boot_device=|sn=|ip=|loglevel=|console=|init=|root=|ohos\.required_mount\.)',
    r'\\\n\1',
    text,
)
if "${QEMU_BOOT_EXTRAS}" not in text:
    text = re.sub(
        r'(reservedsize=104857600)',
        r'\1 ${QEMU_BOOT_EXTRAS}',
        text,
        count=1,
    )

# Insert cap_block right after the DISPLAY_TYPE case ... esac block.
display_case_pattern = re.compile(
    r'(case "\$\{DISPLAY_TYPE\}" in\n.*?^esac$)',
    re.M | re.S,
)
match = display_case_pattern.search(text)
if not match:
    raise SystemExit(f"unable to locate DISPLAY_TYPE case block for capabilities in {path}")

text = text[:match.end()] + "\n\n" + cap_block + text[match.end():]
path.write_text(text, encoding="utf-8")
EXT_CAP_PY
}

write_unix_cli_wrapper() {
  local dest="$1"
  local default_smp="$2"
  local default_mem="$3"
  local default_display="$4"
  local default_qemu_bin="$5"
  local default_cpu="${6:-max}"

  cat >"${dest}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

HERE="\$(cd "\$(dirname "\$0")/.." && pwd)"
export OHOS_IMG="\${HERE}/images"

DEFAULT_SMP="${default_smp}"
DEFAULT_MEMORY="${default_mem}"
DEFAULT_DISPLAY="${default_display}"
DEFAULT_QEMU_BIN="${default_qemu_bin}"
DEFAULT_CPU="${default_cpu}"
DEFAULT_XRES=800
DEFAULT_YRES=500
DEFAULT_HDC_PORT=5555
DEFAULT_VNC_DISPLAY=21

usage() {
  cat <<USAGE
Usage: \$(basename "\$0") [OPTIONS] [-- QEMU_EXTRA_ARGS...]

Launch the packaged OpenHarmony QEMU image.

Options:
  -r, --resolution WxH   Guest GPU resolution (default: \${DEFAULT_XRES}x\${DEFAULT_YRES})
      --width N          Guest GPU width (alternative to --resolution)
      --height N         Guest GPU height (alternative to --resolution)
  -m, --memory SIZE      RAM size for QEMU -m (default: \${DEFAULT_MEMORY}; accepts 4096, 4096M, 4G)
      --userdata-size SIZE  Expand images/userdata.img before boot (e.g. 4096, 4096M, 4G, 8G;
                         guest init automatically resizes F2FS /data on boot)
      --reset            Reset the active userdata.img to a clean factory F2FS image before boot
                         (preserves any custom userdata size unless --userdata-size is also set)
  -s, --smp N            Virtual CPUs (default: \${DEFAULT_SMP})
      --cpu MODEL        QEMU CPU model (default: \${DEFAULT_CPU})
  -d, --display TYPE     none|vnc|sdl|gtk|cocoa|auto (default: \${DEFAULT_DISPLAY})
      --headless         Alias for --display none
  -c, --connect HOST:PORT  HDC forward address (default: 127.0.0.1:\${DEFAULT_HDC_PORT})
      --hdc-port PORT    HDC host TCP port (default: \${DEFAULT_HDC_PORT})
      --vnc-display N    VNC display number (default: \${DEFAULT_VNC_DISPLAY} => TCP \$((5900 + DEFAULT_VNC_DISPLAY)))
      --serial-port PORT Expose guest serial on telnet 127.0.0.1:PORT
      --kernel-log-level N Kernel console verbosity 0..8 (default: 4)
      --a11y            Enable virtio multitouch and a QMP control socket
      --qmp-socket PATH QMP Unix socket (implies QMP; default with --a11y:
                        /tmp/openharmony-qemu-a11y-<HDC_PORT>.sock)
      --audio MODE       Host audio backend: auto|none|coreaudio|pa|pipewire|alsa|sdl|dsound|wav[:PATH] (default: auto)
      --shared-dir DIR[:TAG]  Share host directory into guest via VirtFS 9p (mounted at /mnt/share and /data/share)
      --usb              Enable USB xHCI controller (qemu-xhci)
      --usb-disk FILE[:SIZE]  Attach raw disk image as USB mass storage on xHCI
      --usb-host VID:PID Passthrough host USB device by hex VID:PID (e.g. 1234:5678)
      --usb-serial MODE  Attach USB FTDI serial adapter: off|auto|on|loopback|pty|unix:PATH|tcp:HOST:PORT (default: off)
      --bt-usb VID:PID   Passthrough host USB Bluetooth adapter by hex VID:PID (e.g. 0a12:0001)
      --balloon          Enable VirtIO memory balloon device (virtio-balloon-pci)
      --rng MODE         VirtIO hardware RNG device (virtio-rng-pci): auto|on|off (default: on)
      --port-forward SPEC  Custom host-to-guest port forward: [tcp|udp:]HOST_PORT:GUEST_PORT (comma-separated or repeated)
      --ril-modem MODE   Virtual AT cellular modem over virtio-serial: auto|on|off (default: auto)
      --wifi MODE        Virtual Wi-Fi mode: auto|hwsim|virt_wifi|off (default: auto)
      --gps COORDS       Initial GPS location: LAT,LON[,ALT[,SPEED[,BEARING[,HACC[,VACC]]]]]
      --sensor VALUES    Initial accelerometer/rotation: AX,AY,AZ[:RX,RY,RZ,RW]
      --battery SPEC     Battery simulation: LEVEL[:charging|discharging|full|not_charging] (default: 100:charging)
      --thermal TEMP_C   Thermal temperature simulation in Celsius (e.g. 25.0, 38.5)
      --sdcard FILE[:SIZE]    Attach external SD card image (mounted at /mnt/data/external/sdcard and /data/sdcard)
      --nvme-disk FILE[:SIZE] Attach NVMe / high-speed disk image (mounted at /mnt/data/external/nvme and /data/nvme)
      --instance ID      Multi-instance ID 1..999 (auto-isolates disks, MACs, UUID, serial, HDC port, VNC display)
      --peer MODE        Two-instance DSoftBus peer LAN: off|listen[:PORT]|connect[:PORT]
      --userdata-file PATH  Override writable userdata.img path for this instance
      --rtc MODE         RTC clock base: utc|localtime|host (default: utc)
      --watchdog MODEL   Hardware watchdog: none|i6300esb[:reset|shutdown|poweroff|pause|none] (default: none)
      --tpm PATH         Attach TPM 2.0 emulator (swtpm unix socket or state directory)
      --clipboard MODE   Host-guest clipboard bridge: auto|on|off|text:STRING (default: auto)
      --camera-feed PAT  Virtual V4L2 camera test pattern: bars|smpte|squares|checkers|cross|ramp|noise|moving
  -a, --accel MODE       auto|hvf|kvm|tcg|whpx (default: auto)
  -q, --qemu PATH        Path to the qemu-system-* binary (default: \${DEFAULT_QEMU_BIN})
  -h, --help             Show this help

CLI flags override environment variables, which override the defaults above.
Supported environment variables:
  QEMU_DISPLAY QEMU_XRES QEMU_YRES QEMU_SMP QEMU_MEMORY QEMU_CPU
  QEMU_RESET QEMU_USERDATA_SIZE QEMU_USERDATA_FILE QEMU_INSTANCE_ID
  QEMU_AUDIO_BACKEND QEMU_SHARED_DIR
  QEMU_USB QEMU_USB_DISK QEMU_USB_HOST QEMU_USB_SERIAL QEMU_BT_USB QEMU_BALLOON QEMU_RNG
  QEMU_PORT_FORWARD QEMU_RIL_MODEM QEMU_WIFI_MODE
  QEMU_GPS QEMU_SENSOR QEMU_BATTERY QEMU_THERMAL
  QEMU_SDCARD QEMU_NVME_DISK QEMU_RTC QEMU_WATCHDOG QEMU_TPM
  QEMU_CLIPBOARD QEMU_CAMERA_FEED QEMU_HW_BRIDGE
  QEMU_HDC_HOST_PORT QEMU_VNC_DISPLAY QEMU_SERIAL_PORT
  QEMU_KERNEL_LOG_LEVEL
  QEMU_ACCESSIBILITY QEMU_QMP_SOCKET
  QEMU_ACCEL QEMU_BIN QEMU_EXTRA_ARGS
  QEMU_PEER_MODE=off|listen|connect QEMU_PEER_PORT QEMU_PEER_MAC QEMU_MGMT_MAC
  QEMU_INSTANCE_UUID QEMU_GUEST_SERIAL QEMU_PEER_CAPTURE_FILE
  (peer LAN: POSIX full products only; separate instance disks and actual distinct UDIDs required)
USAGE
}

while [ "\$#" -gt 0 ]; do
  case "\$1" in
    --*=*)
      set -- "\${1%%=*}" "\${1#*=}" "\${@:2}"
      ;;
  esac
  case "\$1" in
    -r|--resolution)
      res="\${2:-}"
      [ -n "\${res}" ] || { echo "missing value for \$1" >&2; exit 2; }
      case "\${res}" in
        *x*)
          export QEMU_XRES="\${res%x*}"
          export QEMU_YRES="\${res#*x}"
          ;;
        *)
          echo "resolution must be WxH, got: \${res}" >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --width)
      export QEMU_XRES="\${2:?missing width}"
      shift 2
      ;;
    --height)
      export QEMU_YRES="\${2:?missing height}"
      shift 2
      ;;
    -m|--memory)
      export QEMU_MEMORY="\${2:?missing memory value}"
      shift 2
      ;;
    --userdata-size|--data-size)
      export QEMU_USERDATA_SIZE="\${2:?missing userdata size}"
      shift 2
      ;;
    --reset|--reset-userdata)
      export QEMU_RESET=1
      shift
      ;;
    -s|--smp)
      export QEMU_SMP="\${2:?missing smp value}"
      shift 2
      ;;
    --cpu)
      export QEMU_CPU="\${2:?missing cpu model}"
      shift 2
      ;;
    -d|--display)
      export QEMU_DISPLAY="\${2:?missing display type}"
      shift 2
      ;;
    --headless)
      export QEMU_DISPLAY=none
      shift
      ;;
    -c|--connect)
      key="\${2:?missing connect key}"
      case "\${key}" in
        *:*)
          export QEMU_HDC_HOST_PORT="\${key##*:}"
          ;;
        *)
          echo "connect key must be host:port, got: \${key}" >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --hdc-port)
      export QEMU_HDC_HOST_PORT="\${2:?missing hdc port}"
      shift 2
      ;;
    --vnc-display)
      export QEMU_VNC_DISPLAY="\${2:?missing vnc display}"
      shift 2
      ;;
    --serial-port)
      export QEMU_SERIAL_PORT="\${2:?missing serial port}"
      shift 2
      ;;
    --kernel-log-level)
      export QEMU_KERNEL_LOG_LEVEL="\${2:?missing kernel log level}"
      shift 2
      ;;
    --a11y)
      export QEMU_ACCESSIBILITY=1
      shift
      ;;
    --qmp-socket)
      export QEMU_QMP_SOCKET="\${2:?missing QMP socket path}"
      shift 2
      ;;
    --audio)
      export QEMU_AUDIO_BACKEND="\${2:?missing audio backend mode}"
      shift 2
      ;;
    --shared-dir)
      export QEMU_SHARED_DIR="\${2:?missing shared directory path}"
      shift 2
      ;;
    --usb)
      export QEMU_USB=1
      shift
      ;;
    --usb-disk)
      export QEMU_USB_DISK="\${2:?missing USB disk path}"
      shift 2
      ;;
    --usb-host)
      export QEMU_USB_HOST="\${2:?missing USB host VID:PID}"
      shift 2
      ;;
    --usb-serial)
      export QEMU_USB_SERIAL="\${2:?missing USB serial mode}"
      shift 2
      ;;
    --bt-usb)
      export QEMU_BT_USB="\${2:?missing Bluetooth USB VID:PID}"
      shift 2
      ;;
    --balloon)
      export QEMU_BALLOON=1
      shift
      ;;
    --rng)
      export QEMU_RNG="\${2:?missing RNG mode}"
      shift 2
      ;;
    --port-forward|--hostfwd)
      if [ -n "\${QEMU_PORT_FORWARD:-}" ]; then
        export QEMU_PORT_FORWARD="\${QEMU_PORT_FORWARD},\${2:?missing port-forward spec}"
      else
        export QEMU_PORT_FORWARD="\${2:?missing port-forward spec}"
      fi
      shift 2
      ;;
    --ril-modem)
      export QEMU_RIL_MODEM="\${2:?missing RIL modem mode}"
      shift 2
      ;;
    --wifi)
      export QEMU_WIFI_MODE="\${2:?missing Wi-Fi mode}"
      shift 2
      ;;
    --gps)
      export QEMU_GPS="\${2:?missing GPS coordinates}"
      shift 2
      ;;
    --sensor)
      export QEMU_SENSOR="\${2:?missing sensor values}"
      shift 2
      ;;
    --battery)
      export QEMU_BATTERY="\${2:?missing battery spec}"
      shift 2
      ;;
    --thermal)
      export QEMU_THERMAL="\${2:?missing thermal temperature}"
      shift 2
      ;;
    --sdcard)
      export QEMU_SDCARD="\${2:?missing SD card image path}"
      shift 2
      ;;
    --nvme-disk|--nvme)
      export QEMU_NVME_DISK="\${2:?missing NVMe disk image path}"
      shift 2
      ;;
    --instance)
      export QEMU_INSTANCE_ID="\${2:?missing instance ID}"
      shift 2
      ;;
    --peer)
      export QEMU_PEER_MODE="\${2:?missing peer mode}"
      shift 2
      ;;
    --userdata-file)
      export QEMU_USERDATA_FILE="\${2:?missing userdata file path}"
      shift 2
      ;;
    --rtc)
      export QEMU_RTC="\${2:?missing RTC mode}"
      shift 2
      ;;
    --watchdog)
      export QEMU_WATCHDOG="\${2:?missing watchdog model}"
      shift 2
      ;;
    --tpm)
      export QEMU_TPM="\${2:?missing TPM path}"
      shift 2
      ;;
    --clipboard)
      export QEMU_CLIPBOARD="\${2:?missing clipboard mode}"
      shift 2
      ;;
    --camera-feed|--camera)
      export QEMU_CAMERA_FEED="\${2:?missing camera feed pattern}"
      shift 2
      ;;
    -a|--accel)
      export QEMU_ACCEL="\${2:?missing accel mode}"
      shift 2
      ;;
    -q|--qemu)
      export QEMU_BIN="\${2:?missing qemu path}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      if [ "\$#" -gt 0 ]; then
        export QEMU_EXTRA_ARGS="\${*}\${QEMU_EXTRA_ARGS:+ \${QEMU_EXTRA_ARGS}}"
      fi
      break
      ;;
    -*)
      echo "unknown option: \$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      echo "unexpected argument: \$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Auto-derive HDC port and VNC display from QEMU_INSTANCE_ID when unset.
if [ -n "\${QEMU_INSTANCE_ID:-}" ] && [[ "\${QEMU_INSTANCE_ID}" =~ ^[1-9][0-9]{0,2}\$ ]]; then
  export QEMU_HDC_HOST_PORT="\${QEMU_HDC_HOST_PORT:-\$((DEFAULT_HDC_PORT + QEMU_INSTANCE_ID - 1))}"
  export QEMU_VNC_DISPLAY="\${QEMU_VNC_DISPLAY:-\$((DEFAULT_VNC_DISPLAY + QEMU_INSTANCE_ID - 1))}"
fi

# Apply defaults only when unset so environment variables still work.
export QEMU_XRES="\${QEMU_XRES:-\${DEFAULT_XRES}}"
export QEMU_YRES="\${QEMU_YRES:-\${DEFAULT_YRES}}"
export QEMU_SMP="\${QEMU_SMP:-\${DEFAULT_SMP}}"
export QEMU_MEMORY="\${QEMU_MEMORY:-\${DEFAULT_MEMORY}}"
export QEMU_CPU="\${QEMU_CPU:-\${DEFAULT_CPU}}"
export QEMU_DISPLAY="\${QEMU_DISPLAY:-\${DEFAULT_DISPLAY}}"
export QEMU_HDC_HOST_PORT="\${QEMU_HDC_HOST_PORT:-\${DEFAULT_HDC_PORT}}"
export QEMU_VNC_DISPLAY="\${QEMU_VNC_DISPLAY:-\${DEFAULT_VNC_DISPLAY}}"
export QEMU_SERIAL_PORT="\${QEMU_SERIAL_PORT:-}"
export QEMU_KERNEL_LOG_LEVEL="\${QEMU_KERNEL_LOG_LEVEL:-4}"
export QEMU_ACCESSIBILITY="\${QEMU_ACCESSIBILITY:-0}"
export QEMU_QMP_SOCKET="\${QEMU_QMP_SOCKET:-}"
export QEMU_AUDIO_BACKEND="\${QEMU_AUDIO_BACKEND:-auto}"
export QEMU_SHARED_DIR="\${QEMU_SHARED_DIR:-}"
export QEMU_USB="\${QEMU_USB:-0}"
export QEMU_USB_DISK="\${QEMU_USB_DISK:-}"
export QEMU_USB_HOST="\${QEMU_USB_HOST:-}"
export QEMU_USB_SERIAL="\${QEMU_USB_SERIAL:-off}"
export QEMU_BT_USB="\${QEMU_BT_USB:-}"
export QEMU_BALLOON="\${QEMU_BALLOON:-0}"
export QEMU_RNG="\${QEMU_RNG:-on}"
export QEMU_PORT_FORWARD="\${QEMU_PORT_FORWARD:-}"
export QEMU_RIL_MODEM="\${QEMU_RIL_MODEM:-auto}"
export QEMU_WIFI_MODE="\${QEMU_WIFI_MODE:-auto}"
export QEMU_GPS="\${QEMU_GPS:-}"
export QEMU_SENSOR="\${QEMU_SENSOR:-}"
export QEMU_BATTERY="\${QEMU_BATTERY:-}"
export QEMU_THERMAL="\${QEMU_THERMAL:-}"
export QEMU_SDCARD="\${QEMU_SDCARD:-}"
export QEMU_NVME_DISK="\${QEMU_NVME_DISK:-}"
export QEMU_INSTANCE_ID="\${QEMU_INSTANCE_ID:-}"
export QEMU_USERDATA_FILE="\${QEMU_USERDATA_FILE:-}"
export QEMU_RTC="\${QEMU_RTC:-utc}"
export QEMU_WATCHDOG="\${QEMU_WATCHDOG:-none}"
export QEMU_TPM="\${QEMU_TPM:-}"
export QEMU_CLIPBOARD="\${QEMU_CLIPBOARD:-auto}"
export QEMU_CAMERA_FEED="\${QEMU_CAMERA_FEED:-}"
export QEMU_ACCEL="\${QEMU_ACCEL:-auto}"
export QEMU_BIN="\${QEMU_BIN:-\${DEFAULT_QEMU_BIN}}"
export QEMU_RESET="\${QEMU_RESET:-0}"
export QEMU_USERDATA_SIZE="\${QEMU_USERDATA_SIZE:-}"
export QEMU_EXTRA_ARGS="\${QEMU_EXTRA_ARGS:-}"

case "\${QEMU_RESET}" in
  0|1) ;;
  *) echo "QEMU_RESET must be 0 or 1, got: \${QEMU_RESET}" >&2; exit 2 ;;
esac

if [ -n "\${QEMU_USERDATA_SIZE}" ]; then
  if [[ "\${QEMU_USERDATA_SIZE}" =~ ^([1-9][0-9]*)([MmGg]([Ii]?[Bb])?)?\$ ]]; then
    userdata_num="\${BASH_REMATCH[1]}"
    userdata_unit="\${BASH_REMATCH[2]:-M}"
    case "\${userdata_unit}" in
      [Gg]*) userdata_target_bytes=\$((userdata_num * 1024 * 1024 * 1024)) ;;
      *) userdata_target_bytes=\$((userdata_num * 1024 * 1024)) ;;
    esac
  else
    echo "invalid userdata size: \${QEMU_USERDATA_SIZE} (expected e.g. 4096, 4096M, 4G, 8G)" >&2
    exit 2
  fi
  if [ "\${QEMU_RESET}" = "1" ] && [ "\${userdata_target_bytes}" -lt 2147483648 ]; then
    echo "cannot reset userdata.img below minimum F2FS image size 2147483648 bytes (2G), got: \${QEMU_USERDATA_SIZE}" >&2
    exit 2
  fi
  if ! grep -q 'QEMU_CAPABILITIES_V1' "\${HERE}/launch/qemu_run.sh" 2>/dev/null; then
    userdata_img="\${QEMU_USERDATA_FILE:-\${OHOS_IMG}/userdata.img}"
    if [ ! -f "\${userdata_img}" ]; then
      echo "userdata.img not found at \${userdata_img}" >&2
      exit 2
    fi
    userdata_current_bytes=\$(stat -f "%z" "\${userdata_img}" 2>/dev/null || stat -c "%s" "\${userdata_img}" 2>/dev/null || wc -c < "\${userdata_img}" | tr -d "[:space:]")
    if [ "\${userdata_target_bytes}" -lt "\${userdata_current_bytes}" ]; then
      echo "cannot shrink userdata.img from \${userdata_current_bytes} bytes to \${userdata_target_bytes} bytes (\${QEMU_USERDATA_SIZE}); pass --reset --userdata-size \${QEMU_USERDATA_SIZE} or restore a smaller userdata.img first" >&2
      exit 2
    elif [ "\${userdata_target_bytes}" -gt "\${userdata_current_bytes}" ]; then
      if command -v truncate >/dev/null 2>&1; then
        truncate -s "\${userdata_target_bytes}" "\${userdata_img}"
      else
        dd if=/dev/null of="\${userdata_img}" bs=1 count=0 seek="\${userdata_target_bytes}" status=none 2>/dev/null || \\
          dd if=/dev/null of="\${userdata_img}" bs=1 count=0 seek="\${userdata_target_bytes}" 2>/dev/null
      fi
      echo "Expanded \${userdata_img} from \${userdata_current_bytes} to \${userdata_target_bytes} bytes (\${QEMU_USERDATA_SIZE}); guest init will resize F2FS /data on boot." >&2
    fi
  fi
fi

case "\${QEMU_XRES}" in
  ''|*[!0-9]*) echo "invalid width: \${QEMU_XRES}" >&2; exit 2 ;;
esac
case "\${QEMU_YRES}" in
  ''|*[!0-9]*) echo "invalid height: \${QEMU_YRES}" >&2; exit 2 ;;
esac
case "\${QEMU_SMP}" in
  ''|*[!0-9]*) echo "invalid smp: \${QEMU_SMP}" >&2; exit 2 ;;
esac
case "\${QEMU_ACCESSIBILITY}" in
  0|1) ;;
  *) echo "QEMU_ACCESSIBILITY must be 0 or 1, got: \${QEMU_ACCESSIBILITY}" >&2; exit 2 ;;
esac
case "\${QEMU_KERNEL_LOG_LEVEL}" in
  [0-8]) ;;
  *) echo "kernel log level must be 0..8" >&2; exit 2 ;;
esac

if [ "\${QEMU_ACCESSIBILITY}" = "1" ]; then
  QEMU_QMP_SOCKET="\${QEMU_QMP_SOCKET:-/tmp/openharmony-qemu-a11y-\${QEMU_HDC_HOST_PORT}.sock}"
  # qemu_run.sh registers virtio-multitouch-pci before the absolute pointer.
fi

if [ -n "\${QEMU_QMP_SOCKET}" ]; then
  case "\${QEMU_QMP_SOCKET}" in
    *[[:space:],]*)
      echo "QMP socket path cannot contain whitespace or commas: \${QEMU_QMP_SOCKET}" >&2
      exit 2
      ;;
  esac
  if [ -e "\${QEMU_QMP_SOCKET}" ]; then
    [ -S "\${QEMU_QMP_SOCKET}" ] || {
      echo "refusing to replace non-socket QMP path: \${QEMU_QMP_SOCKET}" >&2
      exit 2
    }
    rm -f "\${QEMU_QMP_SOCKET}"
  fi
  case " \${QEMU_EXTRA_ARGS} " in
    *" -qmp "*) ;;
    *) QEMU_EXTRA_ARGS="-qmp unix:\${QEMU_QMP_SOCKET},server=on,wait=off\${QEMU_EXTRA_ARGS:+ \${QEMU_EXTRA_ARGS}}" ;;
  esac
  export QEMU_QMP_SOCKET
  echo "Accessibility QMP socket: \${QEMU_QMP_SOCKET}" >&2
fi
export QEMU_EXTRA_ARGS

exec "\${HERE}/launch/qemu_run.sh"
EOF
  chmod +x "${dest}"
}

write_windows_ps1() {
  local dest="$1"
  local product="$2"
  local default_smp="$3"
  local default_mem="$4"
  local default_display="$5"
  local default_cpu="${6:-max}"
  local pointer_device="${7:-virtio-mouse-pci}"

  local win_qemu_exe="qemu-system-x86_64.exe"
  local win_qemu_env="QEMU_SYSTEM_X86_64"
  local win_kernel_file="bzImage"
  local win_blk_dev="virtio-blk-pci"
  local win_net_dev="virtio-net-pci"
  local win_machine="q35"
  case "${product}" in
    x86_64_virt)
      win_qemu_exe="qemu-system-x86_64.exe"
      win_qemu_env="QEMU_SYSTEM_X86_64"
      win_kernel_file="bzImage"
      win_blk_dev="virtio-blk-pci"
      win_net_dev="virtio-net-pci"
      win_machine="q35"
      ;;
    arm64_virt|qemu-arm64-linux-min)
      win_qemu_exe="qemu-system-aarch64.exe"
      win_qemu_env="QEMU_SYSTEM_AARCH64"
      win_kernel_file="Image"
      win_blk_dev="virtio-blk-device"
      win_net_dev="virtio-net-device"
      win_machine="virt"
      ;;
    armv7a_virt)
      win_qemu_exe="qemu-system-arm.exe"
      win_qemu_env="QEMU_SYSTEM_ARM"
      win_kernel_file="zImage"
      win_blk_dev="virtio-blk-device"
      win_net_dev="virtio-net-device"
      win_machine="virt,highmem=off"
      ;;
  esac

  cat >"${dest}" <<EOF
param(
  [Alias("r")][string]\$Resolution,
  [int]\$Width,
  [int]\$Height,
  [Alias("m")][string]\$Memory,
  [Alias("DataSize")][string]\$UserdataSize,
  [Alias("ResetUserdata")][switch]\$Reset,
  [Alias("s")][int]\$Smp,
  [string]\$Cpu,
  [Alias("d")][string]\$Display,
  [switch]\$Headless,
  [Alias("c")][string]\$Connect,
  [int]\$HdcPort,
  [int]\$VncDisplay,
  [int]\$SerialPort,
  [ValidateRange(0, 8)][int]\$KernelLogLevel,
  [switch]\$A11y,
  [int]\$QmpPort,
  [string]\$Audio,
  [string]\$SharedDir,
  [switch]\$Usb,
  [string]\$UsbDisk,
  [string]\$UsbHost,
  [string]\$UsbSerial,
  [string]\$BtUsb,
  [switch]\$Balloon,
  [string]\$Rng,
  [string]\$PortForward,
  [string]\$RilModem,
  [string]\$Wifi,
  [string]\$Gps,
  [string]\$Sensor,
  [string]\$Battery,
  [string]\$Thermal,
  [string]\$Sdcard,
  [string]\$NvmeDisk,
  [int]\$Instance,
  [string]\$Peer,
  [string]\$UserdataFile,
  [string]\$Rtc,
  [string]\$Watchdog,
  [string]\$Tpm,
  [string]\$Clipboard,
  [string]\$CameraFeed,
  [Alias("a")][string]\$Accel,
  [Alias("q")][string]\$QemuPath,
  [Parameter(ValueFromRemainingArguments = \$true)][string[]]\$ExtraArgs
)

\$ErrorActionPreference = "Stop"

\$Root = Split-Path -Parent (Split-Path -Parent \$MyInvocation.MyCommand.Path)
\$Img = Join-Path \$Root "images"
\$Product = "${product}"

\$DefaultSmp = ${default_smp}
\$DefaultMemory = "${default_mem}"
\$DefaultDisplay = "${default_display}"
\$DefaultCpu = "${default_cpu}"
\$DefaultXres = 800
\$DefaultYres = 500
\$DefaultHdcPort = 5555
\$DefaultVncDisplay = 21

if (\$Headless) {
  \$Display = "none"
}

if (\$Resolution) {
  if (\$Resolution -notmatch '^(\\d+)x(\\d+)\$') {
    throw "Resolution must be WxH, got: \$Resolution"
  }
  \$env:QEMU_XRES = \$Matches[1]
  \$env:QEMU_YRES = \$Matches[2]
}
if (\$PSBoundParameters.ContainsKey("Width")) { \$env:QEMU_XRES = "\$Width" }
if (\$PSBoundParameters.ContainsKey("Height")) { \$env:QEMU_YRES = "\$Height" }

if (\$Memory) { \$env:QEMU_MEMORY = \$Memory }
if (\$UserdataSize) { \$env:QEMU_USERDATA_SIZE = \$UserdataSize }
if (\$Reset) { \$env:QEMU_RESET = "1" }
if (\$PSBoundParameters.ContainsKey("Smp")) { \$env:QEMU_SMP = "\$Smp" }
if (\$Cpu) { \$env:QEMU_CPU = \$Cpu }
if (\$Display) { \$env:QEMU_DISPLAY = \$Display }
if (\$Connect) {
  if (\$Connect -notmatch '^[^:]+:(\\d+)\$') {
    throw "Connect must be host:port, got: \$Connect"
  }
  \$env:QEMU_HDC_HOST_PORT = \$Matches[1]
}
if (\$PSBoundParameters.ContainsKey("HdcPort")) { \$env:QEMU_HDC_HOST_PORT = "\$HdcPort" }
if (\$PSBoundParameters.ContainsKey("VncDisplay")) { \$env:QEMU_VNC_DISPLAY = "\$VncDisplay" }
if (\$PSBoundParameters.ContainsKey("SerialPort")) { \$env:QEMU_SERIAL_PORT = "\$SerialPort" }
if (\$PSBoundParameters.ContainsKey("KernelLogLevel")) { \$env:QEMU_KERNEL_LOG_LEVEL = "\$KernelLogLevel" }
if (\$A11y) { \$env:QEMU_ACCESSIBILITY = "1" }
if (\$PSBoundParameters.ContainsKey("QmpPort")) { \$env:QEMU_QMP_PORT = "\$QmpPort" }
if (\$Audio) { \$env:QEMU_AUDIO_BACKEND = \$Audio }
if (\$SharedDir) { \$env:QEMU_SHARED_DIR = \$SharedDir }
if (\$Usb) { \$env:QEMU_USB_XHCI = "1" }
if (\$UsbDisk) { \$env:QEMU_USB_STORAGE = \$UsbDisk }
if (\$UsbHost) { \$env:QEMU_USB_HOST = \$UsbHost }
if (\$UsbSerial) { \$env:QEMU_USB_SERIAL = \$UsbSerial }
if (\$BtUsb) { \$env:QEMU_BT_USB = \$BtUsb }
if (\$Balloon) { \$env:QEMU_BALLOON = "1" }
if (\$Rng) { \$env:QEMU_RNG = \$Rng }
if (\$PortForward) { \$env:QEMU_PORT_FORWARD = \$PortForward }
if (\$RilModem) { \$env:QEMU_RIL_MODEM = \$RilModem }
if (\$Wifi) { \$env:QEMU_WIFI_MODE = \$Wifi }
if (\$Gps) { \$env:QEMU_GPS = \$Gps }
if (\$Sensor) { \$env:QEMU_SENSOR = \$Sensor }
if (\$Battery) { \$env:QEMU_BATTERY = \$Battery }
if (\$Thermal) { \$env:QEMU_THERMAL = \$Thermal }
if (\$Sdcard) { \$env:QEMU_SDCARD = \$Sdcard }
if (\$NvmeDisk) { \$env:QEMU_NVME_DISK = \$NvmeDisk }
if (\$PSBoundParameters.ContainsKey("Instance")) { \$env:QEMU_INSTANCE_ID = "\$Instance" }
if (\$Peer) { \$env:QEMU_PEER_MODE = \$Peer }
if (\$UserdataFile) { \$env:QEMU_USERDATA_FILE = \$UserdataFile }
if (\$Rtc) { \$env:QEMU_RTC = \$Rtc }
if (\$Watchdog) { \$env:QEMU_WATCHDOG = \$Watchdog }
if (\$Tpm) { \$env:QEMU_TPM = \$Tpm }
if (\$Clipboard) { \$env:QEMU_CLIPBOARD = \$Clipboard }
if (\$CameraFeed) { \$env:QEMU_CAMERA_FEED = \$CameraFeed }
if (\$Accel) { \$env:QEMU_ACCEL = \$Accel }
if (\$QemuPath) { \$env:QEMU_BIN = \$QemuPath }

\$MgmtMac = if (\$env:QEMU_MGMT_MAC) { \$env:QEMU_MGMT_MAC } else { "52:54:00:12:34:56" }
\$PeerMac = if (\$env:QEMU_PEER_MAC) { \$env:QEMU_PEER_MAC } else { "52:54:00:12:35:56" }
\$GuestSerial = if (\$env:QEMU_GUEST_SERIAL) { \$env:QEMU_GUEST_SERIAL } else { "0023456789" }
\$InstanceUuid = \$env:QEMU_INSTANCE_UUID
\$SysProdImgPath = Join-Path \$Img "sys_prod.img"
\$ChipProdImgPath = Join-Path \$Img "chip_prod.img"
\$ResetRequested = (\$env:QEMU_RESET -eq "1")
if (\$env:QEMU_RESET -and \$env:QEMU_RESET -notin @("0", "1")) {
  throw "QEMU_RESET must be 0 or 1, got: \$(\$env:QEMU_RESET)"
}

\$PristineF2fsB64 = "7d3NbhvHAQfwXX5JdoRWDYwg1aW82SlqWqJkRw4KNG1yKvwCvRSgSEqWLYmqSMtuTmmBoocecs4hD9FD7z71HVrAT2AECPoBBHXhdGd3KMmGncrGOra4vx8wO/xYDsVZSeD8OZy9mESLCVBhi+1//yNNvpecyy7Xs7KQlXA5jeW/b4W95vN9/5nt8E1WaklRWrEOtz9x4/msvJOVpaLNNN71+/+sdc9/9vH5P/30z4NfffTF21eSQdJLJlkBquZiVnb3i8t3d4t6tFXUt+LtvcPtvN5dO4x1ccfu7Xh9VNR3hxt5C3d70/2K/yqrW8X+o/0741Bv7vT6od7a3sxv398rnnB8uDVtJ39AbzzJ97vVO8hvHww38np7PMrrrU+Kn+9erD8ZT4r2BrHd3+YPTyaTaV3cPrw3LF7X/u287u9N4u1Fu6PB8F6oD2Mdny652Stex81xUQ+KHyc53B3cLvYv+uk3/dHd7hn7PbixvXfnXvtweDDeHu213+8sd1bWLo8ONsaTXv/25eXl1fXly1u994fLve6gf/3q6tX2pem9H27c2d4ZDA/ea1/6aKe3t/WL7OqkaK8frh+12u12Vjqr7Us3J5P98QdXrmxtT27e2ej0R7tXdnYOi83l/YPRrWF/0snubA+vr69du7a2vjm4trK+OhxeG6z3NwYba1eXu92V1c3+5vXlbq+7svLeT9pPP/ONGx+f+vm8/iT5fMH/Ql5QIyvN+H6zoTtextt/33yYygFADiAHAOQAcgA5gBxADoAcoDI5QP7GfDFJHibLv8xv/PFcXr0V91nLyq+z8jB7Iz8XRwLh/fw3z/Bth+g0+6fpcfuNWMJzfpiV+2Es8v2T+waOIQAAAJzWgwd//EsacwAAAACqon60WYqfrIdNulR8lptvakvFh7r5pr6kz2bo6MsBAAAAKqix8FVJLZX7ffMwSE0ulDbmTcI888cltfb1dPp6KR6FzfxrOPJyAAAAAKiCPLJpygEAAACgMjlASw4AAAAAlckB5pwvAAAAACohnC8gH2yfIgf4sn4cHtSeM65/erGE8JCwisKj5+w/99T+zbTIDE6TAwAAAAAv5q//6jxOYw7QcN6IqsqPqKVCX8KZXyo0hnuNE1Va/LnHv/o0/nYUlfk3AAAwE2oxB3hyRNA8OUIEAAAAzr780716zAEAAACA2c8BGnIAAAAAqEwO0LROIAAAAFRCWCcwH3gvlrlMXHmLupXXUnlLw5WotAXmSlxcbqG0lswxAQAAeCM1WsZsAEClzOsCAKrsnByAN1tDFwAAAJTo/NM5QBpLvgxAcU6BsFmKI7I0XAjnFayFCyFFqC/pRQAAADgb3ilygLgMYPzstVlULd0DAAAAMyL/rD+NOQAAAAAw+zlATQ4AAAAAlckB6s/8XkCjuD9+PaBZXIvfEmgdPRYAAICzqH60WYoDwOlycM3pIDAsCdeajgEtCzdLGuYDAAAAyAHkAJXRkgMAAABUUGPhq5JayieMlzauDKeuSy6U1VoIO+aSxyW19nV4qaWd2/xR2Mx/90d+Tg4AAAAAVZBHNvNyAAAAAKhMDvBIDgAAAFBBvhfw4mbjewFhUYhwvL78edJ+otcXT1zO/OH+g1vPqp95/Hmuo0Pc1hcAAAC8OvXk6NyAR2P1sBZkGnOAT393PDLN73/3+HEvkgNMmWLw7TlAmvV2TRYAAADAK9JIjicvTHOAcBqImhzgteQA9ay3G3IAAAAAXpFmLCdzgHAGyLoc4LXkAM2st1tyAAAAAF6RViwnc4BGyADaxaC9/n9bqOePrE0v1o6WDgAAINOZ1h19AcCbK405wA9+dP9vIR/49INzeUlO5AZN3QQzTagH1VXXBVBZDV0A1X3/H3MAY30gfdn7fREIAADOjHrMAS7+0HwAqCrzAaDC7wN0AVSW+QBQ4b//mAMY6wPmAwAAwOxrxhzgws/MB4CqMh8Aqst8AKgu8wGguloxBzDWB8wHAACA2fc/"

function Reset-QemuUserdataImage([string]\$TargetImg, [int64]\$DesiredBytes = 2147483648L) {
  if (\$DesiredBytes -lt 2147483648L) {
    \$DesiredBytes = 2147483648L
  }
  \$ParentDir = Split-Path -Parent \$TargetImg
  if (\$ParentDir -and -not (Test-Path \$ParentDir)) {
    New-Item -ItemType Directory -Force -Path \$ParentDir | Out-Null
  }
  \$Compressed = [Convert]::FromBase64String(\$PristineF2fsB64)
  \$InputMs = New-Object System.IO.MemoryStream(,\$Compressed)
  \$Deflate = New-Object System.IO.Compression.DeflateStream(\$InputMs, [System.IO.Compression.CompressionMode]::Decompress)
  \$OutputMs = New-Object System.IO.MemoryStream
  \$Deflate.CopyTo(\$OutputMs)
  \$Deflate.Close()
  \$Payload = \$OutputMs.ToArray()
  \$Pos = 0
  \$Count = [BitConverter]::ToUInt32(\$Payload, \$Pos)
  \$Pos += 4
  if (Test-Path \$TargetImg) {
    Remove-Item -Force \$TargetImg
  }
  \$fs = [System.IO.File]::Open(\$TargetImg, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
  try {
    try {
      & fsutil sparse setflag \$TargetImg 1 *> \$null
    } catch {}
    \$fs.SetLength(\$DesiredBytes)
    for (\$i = 0; \$i -lt \$Count; \$i++) {
      \$BlkIdx = [int64][BitConverter]::ToUInt32(\$Payload, \$Pos)
      \$BlkLen = [int][BitConverter]::ToUInt32(\$Payload, \$Pos + 4)
      \$Pos += 8
      [void]\$fs.Seek(\$BlkIdx * 4096L, [System.IO.SeekOrigin]::Begin)
      \$fs.Write(\$Payload, \$Pos, \$BlkLen)
      \$Pos += \$BlkLen
    }
  } finally {
    \$fs.Close()
  }
}

if (\$env:QEMU_INSTANCE_ID) {
  \$InstId = [int]\$env:QEMU_INSTANCE_ID
  if (\$InstId -lt 1 -or \$InstId -gt 999) { throw "QEMU_INSTANCE_ID must be 1..999" }
  if (-not \$env:QEMU_HDC_HOST_PORT) { \$env:QEMU_HDC_HOST_PORT = "\$(\$DefaultHdcPort + \$InstId - 1)" }
  if (-not \$env:QEMU_VNC_DISPLAY) { \$env:QEMU_VNC_DISPLAY = "\$(\$DefaultVncDisplay + \$InstId - 1)" }
  \$InstHex = "{0:x2}" -f ((\$InstId + 85) -band 0xff)
  if (-not \$env:QEMU_MGMT_MAC) { \$MgmtMac = "52:54:00:12:34:\$InstHex" }
  if (-not \$env:QEMU_PEER_MAC) { \$PeerMac = "52:54:00:12:35:\$InstHex" }
  if (-not \$InstanceUuid) { \$InstanceUuid = ("00000000-0000-4000-8000-{0:x12}" -f \$InstId) }
  if (-not \$env:QEMU_GUEST_SERIAL) { \$GuestSerial = ("00234567{0:d2}" -f (\$InstId % 100)) }
  if (\$InstId -ne 1) {
    \$InstDir = Join-Path (Join-Path \$Img "instances") "instance-\$InstId"
    New-Item -ItemType Directory -Force -Path \$InstDir | Out-Null
    \$InstUserdata = Join-Path \$InstDir "userdata.img"
    if (-not (Test-Path \$InstUserdata)) {
      Reset-QemuUserdataImage -TargetImg \$InstUserdata -DesiredBytes 2147483648L
    }
    foreach (\$DiskName in @("sys_prod.img", "chip_prod.img")) {
      \$SrcDisk = Join-Path \$Img \$DiskName
      \$DstDisk = Join-Path \$InstDir \$DiskName
      if ((-not (Test-Path \$DstDisk) -or \$ResetRequested) -and (Test-Path \$SrcDisk)) {
        Copy-Item -Force -Path \$SrcDisk -Destination \$DstDisk
      }
    }
    if (-not \$env:QEMU_USERDATA_FILE) { \$env:QEMU_USERDATA_FILE = \$InstUserdata }
    \$SysProdImgPath = Join-Path \$InstDir "sys_prod.img"
    \$ChipProdImgPath = Join-Path \$InstDir "chip_prod.img"
  }
}

\$Xres = if (\$env:QEMU_XRES) { \$env:QEMU_XRES } else { "\$DefaultXres" }
\$Yres = if (\$env:QEMU_YRES) { \$env:QEMU_YRES } else { "\$DefaultYres" }
\$SmpValue = if (\$env:QEMU_SMP) { \$env:QEMU_SMP } else { "\$DefaultSmp" }
\$MemoryValue = if (\$env:QEMU_MEMORY) { \$env:QEMU_MEMORY } else { "\$DefaultMemory" }
\$CpuValue = if (\$env:QEMU_CPU) { \$env:QEMU_CPU } else { "\$DefaultCpu" }
\$HdcHostPort = if (\$env:QEMU_HDC_HOST_PORT) { \$env:QEMU_HDC_HOST_PORT } else { "\$DefaultHdcPort" }
\$KernelLogLevelValue = if (\$env:QEMU_KERNEL_LOG_LEVEL) { \$env:QEMU_KERNEL_LOG_LEVEL } else { "4" }
if (\$KernelLogLevelValue -notmatch '^[0-8]\$') { throw "kernel log level must be 0..8" }
\$VncDisplayValue = if (\$env:QEMU_VNC_DISPLAY) { \$env:QEMU_VNC_DISPLAY } else { "\$DefaultVncDisplay" }
\$GpuDevice = "virtio-gpu-pci,xres=\$Xres,yres=\$Yres"

function Prepare-QemuDiskImage([string]\$Spec, [string]\$Label) {
  \$ImgPath = \$Spec
  \$SizeSpec = ""
  if (\$Spec -match '^(.+):([1-9]\\d*[MmGg](?:i?[Bb])?)\$') {
    \$ImgPath = \$Matches[1]
    \$SizeSpec = \$Matches[2]
  }
  if (\$SizeSpec -match '^([1-9]\\d*)(?:([MmGg])(?:i?[Bb])?)?\$') {
    \$SNum = [int64]\$Matches[1]
    \$SUnit = if (\$Matches[2]) { \$Matches[2].ToUpperInvariant() } else { "M" }
    \$TargetBytes = if (\$SUnit -eq "G") { \$SNum * 1024L * 1024L * 1024L } else { \$SNum * 1024L * 1024L }
    \$ParentDir = Split-Path -Parent \$ImgPath
    if (\$ParentDir -and -not (Test-Path \$ParentDir)) {
      New-Item -ItemType Directory -Force -Path \$ParentDir | Out-Null
    }
    \$fs = [System.IO.File]::Open(\$ImgPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::Write)
    try {
      if (\$TargetBytes -gt \$fs.Length) { \$fs.SetLength(\$TargetBytes) }
    } finally {
      \$fs.Close()
    }
  }
  if (-not (Test-Path \$ImgPath -PathType Leaf)) {
    throw "\$Label image does not exist: \$ImgPath"
  }
  return \$ImgPath
}

\$UserdataImg = if (\$env:QEMU_USERDATA_FILE) { \$env:QEMU_USERDATA_FILE } else { Join-Path \$Img "userdata.img" }
\$TargetBytes = 0L
\$UserdataSpec = ""
if (\$env:QEMU_USERDATA_SIZE) {
  \$UserdataSpec = \$env:QEMU_USERDATA_SIZE.Trim()
  if (\$UserdataSpec -match '^([1-9]\\d*)(?:([MmGg])(?:i?[Bb])?)?\$') {
    \$SizeNum = [int64]\$Matches[1]
    \$Unit = if (\$Matches[2]) { \$Matches[2].ToUpperInvariant() } else { "M" }
    \$TargetBytes = if (\$Unit -eq "G") { \$SizeNum * 1024L * 1024L * 1024L } else { \$SizeNum * 1024L * 1024L }
  } else {
    throw "Invalid userdata size: \$UserdataSpec (expected e.g. 4096, 4096M, 4G, 8G)"
  }
  if (\$ResetRequested -and \$TargetBytes -lt 2147483648L) {
    throw "Cannot reset userdata.img below minimum F2FS image size 2147483648 bytes (2G), got: \$UserdataSpec"
  }
}

if (\$ResetRequested) {
  \$PreResetBytes = if (Test-Path \$UserdataImg) { (Get-Item \$UserdataImg).Length } else { 2147483648L }
  if (\$TargetBytes -gt 0L) {
    Reset-QemuUserdataImage -TargetImg \$UserdataImg -DesiredBytes 2147483648L
    Write-Host "Reset \$UserdataImg to clean factory F2FS image (2147483648 bytes)."
  } elseif (\$PreResetBytes -gt 2147483648L) {
    Reset-QemuUserdataImage -TargetImg \$UserdataImg -DesiredBytes \$PreResetBytes
    Write-Host "Reset \$UserdataImg to clean factory F2FS image (preserved custom size: \$PreResetBytes bytes; guest init will resize F2FS /data on boot)."
  } else {
    Reset-QemuUserdataImage -TargetImg \$UserdataImg -DesiredBytes 2147483648L
    Write-Host "Reset \$UserdataImg to clean factory F2FS image (2147483648 bytes)."
  }
}

if (\$TargetBytes -gt 0L) {
  if (-not (Test-Path \$UserdataImg)) {
    throw "userdata.img not found at \$UserdataImg"
  }
  \$CurrentBytes = (Get-Item \$UserdataImg).Length
  if (\$TargetBytes -lt \$CurrentBytes) {
    throw "Cannot shrink userdata.img from \$CurrentBytes bytes to \$TargetBytes bytes (\$UserdataSpec); pass -Reset -UserdataSize \$UserdataSpec or restore a smaller userdata.img first."
  } elseif (\$TargetBytes -gt \$CurrentBytes) {
    \$fs = [System.IO.File]::Open(\$UserdataImg, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write)
    try {
      \$fs.SetLength(\$TargetBytes)
    } finally {
      \$fs.Close()
    }
    Write-Host "Expanded \$UserdataImg from \$CurrentBytes to \$TargetBytes bytes (\$UserdataSpec); guest init will resize F2FS /data on boot."
  }
}

function Resolve-Qemu {
  if (\$env:QEMU_BIN) { return \$env:QEMU_BIN }
  \$archEnv = [Environment]::GetEnvironmentVariable("${win_qemu_env}")
  if (\$archEnv) { return \$archEnv }
  \$cmd = Get-Command "${win_qemu_exe}" -ErrorAction SilentlyContinue
  if (\$cmd) { return \$cmd.Source }
  \$defaultPath = "C:\\Program Files\\qemu\\${win_qemu_exe}"
  if (Test-Path \$defaultPath) { return \$defaultPath }
  throw "${win_qemu_exe} not found. Install QEMU for Windows or set QEMU_BIN / ${win_qemu_env}."
}

\$Qemu = Resolve-Qemu

\$RequestedAccel = if (\$env:QEMU_ACCEL) { \$env:QEMU_ACCEL.ToLowerInvariant() } else { "auto" }
\$AccelArgs = @("-accel", "tcg,thread=multi")
switch (\$RequestedAccel) {
  "tcg" { Write-Host "TCG software emulation forced by QEMU_ACCEL." }
  "whpx" {
    \$AccelArgs = @("-accel", "whpx,kernel-irqchip=off")
    Write-Host "WHPX acceleration forced by QEMU_ACCEL."
  }
  default {
    if (\$Product -eq "x86_64_virt") {
      try {
        \$AccelHelp = & \$Qemu -accel help 2>&1 | Out-String
        if (\$AccelHelp -match "whpx") {
          \$AccelArgs = @("-accel", "whpx,kernel-irqchip=off")
          Write-Host "WHPX acceleration enabled."
        } else {
          Write-Host "WHPX not available, using TCG software emulation."
        }
      } catch {
        Write-Host "Cannot query QEMU accelerators, using TCG software emulation."
      }
    } else {
      Write-Host "Using TCG software emulation for \$Product on Windows."
    }
  }
}

\$DisplayType = if (\$env:QEMU_DISPLAY) { \$env:QEMU_DISPLAY } else { "\$DefaultDisplay" }
switch (\$DisplayType) {
  "none" {
    \$DisplayArgs = @("-device", \$GpuDevice, "-display", "none", "-serial", "mon:stdio")
  }
  "vnc" {
    \$DisplayArgs = @("-device", \$GpuDevice, "-vnc", ":\${VncDisplayValue}", "-serial", "stdio")
    \$VncTcp = 5900 + [int]\$VncDisplayValue
    Write-Host "Display: VNC on 127.0.0.1:\$VncTcp"
  }
  "gtk" {
    \$DisplayArgs = @("-device", \$GpuDevice, "-display", "gtk,gl=off", "-serial", "stdio")
  }
  default {
    \$DisplayArgs = @("-device", \$GpuDevice, "-display", "sdl,gl=off", "-serial", "stdio")
  }
}

if (\$Product -eq "x86_64_virt") {
  \$KernelBootArgs = "oemmode=rd snd-ens1370.index=0 snd-aloop.index=1 snd-aloop.id=QemuCapture snd-aloop.pcm_substreams=1 loglevel=\$KernelLogLevelValue buildvariant=eng developer_mode=1 console=ttyS0,115200 sn=\$GuestSerial init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@f2fs@nosuid,nodev,noatime,usrquota,grpquota,prjquota@wait,required,reservedsize=104857600"
} else {
  \$KernelBootArgs = "oemmode=rd snd-ens1370.index=0 snd-aloop.index=1 snd-aloop.id=QemuCapture snd-aloop.pcm_substreams=1 buildvariant=eng developer_mode=1 default_boot_device=a003e00.virtio_mmio sn=\$GuestSerial ip=dhcp loglevel=\$KernelLogLevelValue console=ttyAMA0,115200 init=/bin/init ohos.boot.hardware=virt root=/dev/ram0 rw ohos.required_mount.system=/dev/block/vde@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdd@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdc@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vdb@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vda@/data@f2fs@nosuid,nodev,noatime,usrquota,grpquota,prjquota@wait,required,reservedsize=104857600"
}

\$WifiModeValue = if (\$env:QEMU_WIFI_MODE) { \$env:QEMU_WIFI_MODE.ToLowerInvariant() } else { "auto" }
if (\$WifiModeValue -notin @("auto", "hwsim", "virt_wifi", "off")) {
  throw "Invalid QEMU_WIFI_MODE: \$WifiModeValue (expected auto|hwsim|virt_wifi|off)"
}
\$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.wifi=\$WifiModeValue"

\$AccessibilityEnabled = if (\$env:QEMU_ACCESSIBILITY) { \$env:QEMU_ACCESSIBILITY } else { "0" }
if (\$AccessibilityEnabled -notin @("0", "1")) {
  throw "QEMU_ACCESSIBILITY must be 0 or 1, got: \$AccessibilityEnabled"
}
\$A11yInputArgs = if (\$AccessibilityEnabled -eq "1") { @("-device", "virtio-multitouch-pci") } else { @() }

\$AudioModeValue = if (\$env:QEMU_AUDIO_BACKEND) { \$env:QEMU_AUDIO_BACKEND } else { "auto" }
\$AudioArgs = @("-audiodev", "none,id=ohos_audio", "-device", "ES1370,audiodev=ohos_audio")
if (\$AudioModeValue -eq "auto") {
  if (\$DisplayType -notin @("none", "vnc")) {
    try {
      \$AudioHelp = & \$Qemu -audiodev help 2>&1 | Out-String
      if (\$AudioHelp -match "\\bdsound\\b") {
        \$AudioArgs = @("-audiodev", "dsound,id=ohos_audio", "-device", "ES1370,audiodev=ohos_audio")
      } elseif (\$AudioHelp -match "\\bsdl\\b") {
        \$AudioArgs = @("-audiodev", "sdl,id=ohos_audio", "-device", "ES1370,audiodev=ohos_audio")
      }
    } catch {}
  }
} elseif (\$AudioModeValue -match '^wav(?::(.+))?\$') {
  \$WavPath = if (\$Matches[1]) { \$Matches[1] } else { Join-Path \$env:TEMP "openharmony-qemu-audio.wav" }
  \$AudioArgs = @("-audiodev", "wav,id=ohos_audio,path=\$WavPath", "-device", "ES1370,audiodev=ohos_audio")
} elseif (\$AudioModeValue -in @("coreaudio", "pa", "pipewire", "alsa", "sdl", "dsound", "oss", "jack")) {
  \$AudioArgs = @("-audiodev", "\$AudioModeValue,id=ohos_audio", "-device", "ES1370,audiodev=ohos_audio")
} elseif (\$AudioModeValue -ne "none") {
  throw "Invalid QEMU_AUDIO_BACKEND: \$AudioModeValue"
}

\$CapabilityArgs = @()
if (\$InstanceUuid) {
  \$CapabilityArgs += @("-uuid", \$InstanceUuid)
}
if (\$env:QEMU_SHARED_DIR) {
  \$SharePath = \$env:QEMU_SHARED_DIR
  \$ShareTag = "hostshare"
  if (\$SharePath -match '^(.+):([A-Za-z0-9_.-]+)\$' -and (Test-Path \$Matches[1] -PathType Container)) {
    \$SharePath = \$Matches[1]
    \$ShareTag = \$Matches[2]
  }
  if (-not (Test-Path \$SharePath -PathType Container)) {
    throw "QEMU_SHARED_DIR directory does not exist: \$SharePath"
  }
  \$CapabilityArgs += @(
    "-fsdev", "local,id=fsdev_hostshare,path=\$SharePath,security_model=mapped-xattr",
    "-device", "virtio-9p-pci,fsdev=fsdev_hostshare,mount_tag=\$ShareTag"
  )
  \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.share_tag=\$ShareTag"
}
\$UsbSerialMode = if (\$env:QEMU_USB_SERIAL) { \$env:QEMU_USB_SERIAL } else { "off" }
if (\$env:QEMU_USB_XHCI -eq "1" -or \$env:QEMU_USB_STORAGE -or \$env:QEMU_USB_HOST -or \$env:QEMU_BT_USB -or (\$UsbSerialMode -notin @("off", "0", ""))) {
  \$CapabilityArgs += @("-device", "qemu-xhci,id=xhci0")
}
if (\$env:QEMU_USB_STORAGE) {
  \$UsbDiskPath = Prepare-QemuDiskImage \$env:QEMU_USB_STORAGE "USB disk"
  \$CapabilityArgs += @(
    "-drive", "if=none,id=usb_disk0,file=\$UsbDiskPath,format=raw",
    "-device", "usb-storage,bus=xhci0.0,drive=usb_disk0"
  )
}
foreach (\$UsbSpec in @(\$env:QEMU_USB_HOST, \$env:QEMU_BT_USB)) {
  if (\$UsbSpec) {
    if (\$UsbSpec -notmatch '^(?:0x)?([0-9A-Fa-f]{1,4}):(?:0x)?([0-9A-Fa-f]{1,4})\$') {
      throw "Invalid USB VID:PID specification: \$UsbSpec"
    }
    \$CapabilityArgs += @("-device", ("usb-host,bus=xhci0.0,vendorid=0x{0},productid=0x{1}" -f \$Matches[1], \$Matches[2]))
  }
}
if (\$UsbSerialMode -notin @("off", "0", "")) {
  if (\$UsbSerialMode -match '^tcp:(?:([^:]+):)?(\\d+)\$') {
    \$UsbTcpHost = if (\$Matches[1]) { \$Matches[1] } else { "127.0.0.1" }
    \$UsbTcpPort = \$Matches[2]
    \$CapabilityArgs += @(
      "-chardev", "socket,id=usb_serial_chr0,host=\$UsbTcpHost,port=\$UsbTcpPort,server=on,wait=off",
      "-device", "usb-serial,bus=xhci0.0,chardev=usb_serial_chr0,id=usb_serial0"
    )
  } else {
    \$CapabilityArgs += @(
      "-chardev", "null,id=usb_serial_chr0",
      "-device", "usb-serial,bus=xhci0.0,chardev=usb_serial_chr0,id=usb_serial0"
    )
  }
}
if (\$env:QEMU_BALLOON -eq "1") {
  \$CapabilityArgs += @("-device", "virtio-balloon-pci,id=balloon0")
}
\$RngMode = if (\$env:QEMU_RNG) { \$env:QEMU_RNG.ToLowerInvariant() } else { "on" }
if (\$RngMode -in @("auto", "on", "1")) {
  \$CapabilityArgs += @("-device", "virtio-rng-pci,id=rng0")
} elseif (\$RngMode -notin @("off", "0", "none")) {
  throw "Invalid QEMU_RNG: \$RngMode (expected auto|on|off)"
}
if (\$env:QEMU_SDCARD) {
  \$SdcardPath = Prepare-QemuDiskImage \$env:QEMU_SDCARD "SD card"
  \$CapabilityArgs += @(
    "-device", "sdhci-pci,id=sdhci0",
    "-drive", "if=none,id=sdcard_drive0,file=\$SdcardPath,format=raw",
    "-device", "sd-card,drive=sdcard_drive0"
  )
}
if (\$env:QEMU_NVME_DISK) {
  \$NvmePath = Prepare-QemuDiskImage \$env:QEMU_NVME_DISK "NVMe disk"
  \$CapabilityArgs += @(
    "-drive", "if=none,id=nvme_drive0,file=\$NvmePath,format=raw",
    "-device", "nvme,drive=nvme_drive0,serial=ohos-nvme0"
  )
}
if (\$env:QEMU_GPS) { \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.gps=\$(\$env:QEMU_GPS)" }
if (\$env:QEMU_SENSOR) { \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.sensor=\$(\$env:QEMU_SENSOR)" }
if (\$env:QEMU_BATTERY) { \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.battery=\$(\$env:QEMU_BATTERY)" }
if (\$env:QEMU_THERMAL) { \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.thermal=\$(\$env:QEMU_THERMAL)" }
if (\$env:QEMU_CAMERA_FEED) { \$KernelBootArgs = "\$KernelBootArgs ohos.boot.qemu.camera=\$(\$env:QEMU_CAMERA_FEED)" }
\$RtcMode = if (\$env:QEMU_RTC -and \$env:QEMU_RTC -in @("localtime", "host")) { "localtime" } else { "utc" }
\$CapabilityArgs += @("-rtc", "base=\$RtcMode,clock=host")
if (\$env:QEMU_WATCHDOG -and \$env:QEMU_WATCHDOG -notin @("none", "off", "0")) {
  \$WdtParts = \$env:QEMU_WATCHDOG -split ':'
  \$WdtAct = if (\$WdtParts.Length -gt 1) { \$WdtParts[1] } else { "reset" }
  \$CapabilityArgs += @("-device", "i6300esb", "-watchdog-action", \$WdtAct)
}
\$HostfwdExtras = ""
if (\$env:QEMU_PORT_FORWARD) {
  foreach (\$PfRule in (\$env:QEMU_PORT_FORWARD -split '[,\\s]+' | Where-Object { \$_ })) {
    if (\$PfRule -match '^(?:(tcp|udp):)?([1-9]\\d{0,4}):([1-9]\\d{0,4})\$') {
      \$PfProto = if (\$Matches[1]) { \$Matches[1].ToLowerInvariant() } else { "tcp" }
      \$PfHost = [int]\$Matches[2]
      \$PfGuest = [int]\$Matches[3]
      if (\$PfHost -gt 65535 -or \$PfGuest -gt 65535) { throw "Invalid port-forward port in \$PfRule" }
      \$HostfwdExtras += ",hostfwd=\${PfProto}::\${PfHost}-:\${PfGuest}"
    } else {
      throw "Invalid QEMU_PORT_FORWARD rule: \$PfRule (expected [tcp|udp:]HOST_PORT:GUEST_PORT)"
    }
  }
}
\$PeerNetArgs = @()
if (\$env:QEMU_PEER_MODE -and \$env:QEMU_PEER_MODE -ne "off") {
  if (\$env:QEMU_PEER_MODE -match '^(listen|connect)(?::(\\d+))?\$') {
    \$PeerRole = \$Matches[1]
    \$PeerPort = if (\$Matches[2]) { \$Matches[2] } elseif (\$env:QEMU_PEER_PORT) { \$env:QEMU_PEER_PORT } else { "6666" }
    \$PeerEndpoint = if (\$PeerRole -eq "listen") { "server=on" } else { "server=off,reconnect-ms=250" }
    \$PeerNetArgs = @(
      "-netdev", "stream,id=peer_lan,\$PeerEndpoint,addr.type=inet,addr.host=127.0.0.1,addr.port=\$PeerPort",
      "-device", "virtio-net-pci,id=peer_lan_nic,netdev=peer_lan,mac=\$PeerMac"
    )
  } else {
    throw "Invalid QEMU_PEER_MODE: \$(\$env:QEMU_PEER_MODE) (expected off|listen[:PORT]|connect[:PORT])"
  }
}
\$UserdataImgPath = if (\$env:QEMU_USERDATA_FILE) { \$env:QEMU_USERDATA_FILE } else { Join-Path \$Img "userdata.img" }

\$MachineArgs = @("-machine", "${win_machine}")
if (\$Product -eq "x86_64_virt") {
  \$MachineArgs += @("-global", "ICH9-LPC.disable_s3=1", "-global", "ICH9-LPC.disable_s4=1")
}

\$ArgsList = @(
  \$MachineArgs,
  \$AccelArgs,
  "-cpu", "\$CpuValue",
  "-smp", "\$SmpValue",
  "-m", "\$MemoryValue",
  "-kernel", (Join-Path \$Img "${win_kernel_file}"),
  "-initrd", (Join-Path \$Img "ramdisk.img"),
  \$DisplayArgs,
  \$AudioArgs,
  \$CapabilityArgs,
  \$A11yInputArgs,
  "-device", "${pointer_device}",
  "-device", "virtio-keyboard-pci",
  \$PeerNetArgs,
  "-netdev", "user,id=net0,hostfwd=tcp::\${HdcHostPort}-:5555\${HostfwdExtras}",
  "-device", "${win_net_dev},netdev=net0,mac=\$MgmtMac",
  "-drive", ("if=none,file={0},format=raw,id=updater,file.locking=off" -f (Join-Path \$Img "updater.img")),
  "-device", "${win_blk_dev},drive=updater,serial=updater",
  "-drive", ("if=none,file={0},format=raw,id=system,file.locking=off" -f (Join-Path \$Img "system.img")),
  "-device", "${win_blk_dev},drive=system,serial=system",
  "-drive", ("if=none,file={0},format=raw,id=vendor,file.locking=off" -f (Join-Path \$Img "vendor.img")),
  "-device", "${win_blk_dev},drive=vendor,serial=vendor",
  "-drive", ("if=none,file={0},format=raw,id=sys_prod" -f \$SysProdImgPath),
  "-device", "${win_blk_dev},drive=sys_prod,serial=sys_prod",
  "-drive", ("if=none,file={0},format=raw,id=chip_prod" -f \$ChipProdImgPath),
  "-device", "${win_blk_dev},drive=chip_prod,serial=chip_prod",
  "-drive", ("if=none,file={0},format=raw,id=userdata" -f \$UserdataImgPath),
  "-device", "${win_blk_dev},drive=userdata,serial=userdata",
  "-append", \$KernelBootArgs
)

if (\$env:QEMU_SERIAL_PORT) {
  \$ArgsList += @("-serial", "telnet:127.0.0.1:\$(\$env:QEMU_SERIAL_PORT),server,nowait")
  Write-Host "Serial telnet console: 127.0.0.1:\$(\$env:QEMU_SERIAL_PORT)"
}
\$QmpPortValue = if (\$env:QEMU_QMP_PORT) { [int]\$env:QEMU_QMP_PORT } elseif (\$AccessibilityEnabled -eq "1") { 4445 } else { 0 }
if ((\$AccessibilityEnabled -eq "1" -or \$env:QEMU_QMP_PORT) -and
    (\$QmpPortValue -lt 1 -or \$QmpPortValue -gt 65535)) {
  throw "QMP port must be between 1 and 65535"
}
if (\$QmpPortValue -gt 0) {
  \$ArgsList += @("-qmp", "tcp:127.0.0.1:\${QmpPortValue},server=on,wait=off")
  Write-Host "Accessibility QMP endpoint: tcp://127.0.0.1:\$QmpPortValue"
}
if (\$env:QEMU_EXTRA_ARGS) {
  \$ArgsList += (\$env:QEMU_EXTRA_ARGS -split '\\s+' | Where-Object { \$_ })
}
if (\$ExtraArgs) {
  \$ArgsList += \$ExtraArgs
}

& \$Qemu @ArgsList
exit \$LASTEXITCODE
EOF
}

write_package_launcher_readme() {
  local package_dir="$1"
  local package_name="$2"
  local product="$3"
  local standard_vpn="${4:-false}"
  local default_smp="$5"
  local default_mem="$6"
  local default_display="$7"
  local default_cpu="${8:-max}"
  local pointer_device="${9:-virtio-mouse-pci}"
  local cpu_example="${default_cpu}"
  if [ "${product}" = "x86_64_virt" ]; then
    cpu_example=EPYC-v5
  fi

  cat >"${package_dir}/README.md" <<EOF
# ${package_name}

This package contains an OpenHarmony standard-system QEMU image.

The manifest's capability flags record static packaging checks, not proof that
an API works. Boot and behavior results belong in a separate report bound to
this archive's SHA-256. Archive creation or the offline verifier cannot satisfy
the first-artifact behavior gate.

Install QEMU on the host first, then run one of:

- Linux: \`launch/linux.sh\`
- macOS: \`launch/macos.command\`
- Windows PowerShell: \`launch/windows.ps1\`

## Launch options

CLI flags override environment variables, which override package defaults.

| Option | Env | Default |
| --- | --- | --- |
| \`-r, --resolution WxH\` | \`QEMU_XRES\` / \`QEMU_YRES\` | \`800x500\` |
| \`--width\` / \`--height\` | \`QEMU_XRES\` / \`QEMU_YRES\` | same as above |
| \`-m, --memory SIZE\` | \`QEMU_MEMORY\` | \`${default_mem}\` |
| \`--userdata-size SIZE\` / Windows \`-UserdataSize SIZE\` | \`QEMU_USERDATA_SIZE\` | current \`userdata.img\` size (\`2G\`) |
| \`--reset\` / Windows \`-Reset\` | \`QEMU_RESET\` | \`0\` (\`1\` resets active \`userdata.img\` to clean factory F2FS image, preserving custom size) |
| \`-s, --smp N\` | \`QEMU_SMP\` | \`${default_smp}\` |
| \`--cpu MODEL\` | \`QEMU_CPU\` | \`${default_cpu}\` |
| \`-d, --display TYPE\` / \`--headless\` | \`QEMU_DISPLAY\` | \`${default_display}\` |
| \`-c, --connect host:port\` / \`--hdc-port\` | \`QEMU_HDC_HOST_PORT\` | \`5555\` |
| \`--vnc-display N\` | \`QEMU_VNC_DISPLAY\` | \`21\` (TCP 5921) |
| \`--serial-port PORT\` | \`QEMU_SERIAL_PORT\` | unset |
| \`--kernel-log-level N\` / Windows \`-KernelLogLevel N\` | \`QEMU_KERNEL_LOG_LEVEL\` | \`4\` (0..8) |
| \`--a11y\` | \`QEMU_ACCESSIBILITY\` | \`0\` |
| \`--qmp-socket PATH\` | \`QEMU_QMP_SOCKET\` | \`/tmp/openharmony-qemu-a11y-<HDC_PORT>.sock\` with \`--a11y\` |
| Windows \`-QmpPort PORT\` | \`QEMU_QMP_PORT\` | \`4445\` with \`-A11y\` |
| \`--audio MODE\` / Windows \`-Audio MODE\` | \`QEMU_AUDIO_BACKEND\` | \`auto\` (\`none\` headless, host audio windowed) |
| \`--shared-dir DIR[:TAG]\` / Windows \`-SharedDir\` | \`QEMU_SHARED_DIR\` | unset (mounts at \`/mnt/share\` and \`/data/share\`) |
| \`--usb\` / Windows \`-Usb\` | \`QEMU_USB_XHCI\` | \`0\` (auto-enabled by \`--usb-disk\`/\`--usb-host\`/\`--bt-usb\`/\`--usb-serial\`) |
| \`--usb-disk FILE[:SIZE]\` / Windows \`-UsbDisk FILE[:SIZE]\` | \`QEMU_USB_STORAGE\` | unset (mounts at \`/mnt/data/external/usb\` and \`/data/usb\`) |
| \`--usb-host VID:PID\` / Windows \`-UsbHost VID:PID\` | \`QEMU_USB_HOST\` | unset |
| \`--usb-serial MODE\` / Windows \`-UsbSerial MODE\` | \`QEMU_USB_SERIAL\` | \`off\` (\`off\`/\`auto\`/\`on\`/\`loopback\`/\`pty\`/\`unix:PATH\`/\`tcp:HOST:PORT\`) |
| \`--bt-usb VID:PID\` / Windows \`-BtUsb VID:PID\` | \`QEMU_BT_USB\` | unset (uses virtual HCI \`libbt_vendor.z.so\` by default) |
| \`--balloon\` / Windows \`-Balloon\` | \`QEMU_BALLOON\` | \`0\` |
| \`--rng MODE\` / Windows \`-Rng MODE\` | \`QEMU_RNG\` | \`on\` (\`auto\`/\`on\`/\`off\`, attaches \`virtio-rng-pci\`) |
| \`--port-forward SPEC\` / Windows \`-PortForward SPEC\` | \`QEMU_PORT_FORWARD\` | unset (\`[tcp\|udp:]HOST_PORT:GUEST_PORT\`, comma-separated or repeated) |
| \`--ril-modem MODE\` / Windows \`-RilModem MODE\` | \`QEMU_RIL_MODEM\` | \`auto\` (\`auto\`/\`on\`/\`off\`) |
| \`--wifi MODE\` / Windows \`-Wifi MODE\` | \`QEMU_WIFI_MODE\` | \`auto\` (\`auto\`/\`hwsim\`/\`virt_wifi\`/\`off\`) |
| \`--gps COORDS\` / Windows \`-Gps\` | \`QEMU_GPS\` | \`39.9042,116.4074,50\` |
| \`--sensor VALUES\` / Windows \`-Sensor\` | \`QEMU_SENSOR\` | \`0.0,9.8,0.0:0.0,0.0,0.0,1.0\` |
| \`--battery SPEC\` / Windows \`-Battery\` | \`QEMU_BATTERY\` | \`100:charging\` |
| \`--thermal TEMP_C\` / Windows \`-Thermal\` | \`QEMU_THERMAL\` | \`25.0\` |
| \`--sdcard FILE[:SIZE]\` / Windows \`-Sdcard\` | \`QEMU_SDCARD\` | unset (mounts at \`/mnt/data/external/sdcard\` and \`/data/sdcard\`) |
| \`--nvme-disk FILE[:SIZE]\` / Windows \`-NvmeDisk\` | \`QEMU_NVME_DISK\` | unset (mounts at \`/mnt/data/external/nvme\` and \`/data/nvme\`) |
| \`--instance ID\` / Windows \`-Instance\` | \`QEMU_INSTANCE_ID\` | unset (auto-isolates disks, MACs, UUID, serial, HDC port, VNC) |
| \`--peer MODE\` / Windows \`-Peer\` | \`QEMU_PEER_MODE\` | \`off\` (\`off\`/\`listen[:PORT]\`/\`connect[:PORT]\`) |
| \`--userdata-file PATH\` / Windows \`-UserdataFile\` | \`QEMU_USERDATA_FILE\` | \`images/userdata.img\` |
| \`--rtc MODE\` / Windows \`-Rtc\` | \`QEMU_RTC\` | \`utc\` (\`utc\`/\`localtime\`/\`host\`) |
| \`--watchdog MODEL\` / Windows \`-Watchdog\` | \`QEMU_WATCHDOG\` | \`none\` (\`none\`/\`i6300esb[:ACTION]\`) |
| \`--tpm PATH\` / Windows \`-Tpm\` | \`QEMU_TPM\` | unset (\`swtpm\` socket or state directory) |
| \`--clipboard MODE\` / Windows \`-Clipboard\` | \`QEMU_CLIPBOARD\` | \`auto\` (\`auto\`/\`on\`/\`off\`/\`text:...\`) |
| \`--camera-feed PAT\` / Windows \`-CameraFeed\` | \`QEMU_CAMERA_FEED\` | \`bars\` (\`bars\`/\`smpte\`/\`squares\`/\`checkers\`/\`cross\`/\`ramp\`/\`noise\`/\`moving\`) |
| \`-a, --accel MODE\` | \`QEMU_ACCEL\` | \`auto\` |
| \`-q, --qemu PATH\` | \`QEMU_BIN\` | product QEMU binary |
| \`-- ...\` | \`QEMU_EXTRA_ARGS\` | empty |

Examples:

\`\`\`bash
./launch/linux.sh -r 1280x720 -m 8G -s 8
./launch/linux.sh --userdata-size 8G
./launch/linux.sh --reset
./launch/linux.sh --reset --userdata-size 4G
./launch/linux.sh --shared-dir /tmp/ohos-share --balloon --audio auto
./launch/linux.sh --usb-serial loopback --port-forward 18080:8080 --rng on
./launch/linux.sh --gps 31.2304,121.4737,15 --battery 85:discharging --thermal 36.5 --camera-feed smpte
./launch/linux.sh --sdcard /tmp/ohos-sd.img:64M --nvme-disk /tmp/ohos-nvme.img:128M
./launch/linux.sh --instance 2 --peer connect:6666
python3 ./tools/qemu_hw_controller.py --socket /tmp/openharmony-qemu-hw-5555.ctrl.sock status
python3 ./tools/qemu_hw_controller.py --socket /tmp/openharmony-qemu-hw-5555.ctrl.sock key volup
python3 ./tools/qemu_hw_controller.py --socket /tmp/openharmony-qemu-hw-5555.ctrl.sock network offline
python3 ./tools/qemu_hw_controller.py --socket /tmp/openharmony-qemu-hw-5555.ctrl.sock light 800
python3 ./tools/qemu_hw_controller.py --socket /tmp/openharmony-qemu-hw-5555.ctrl.sock usb-serial-send "AT\r\n"
./launch/linux.sh --cpu ${cpu_example}
./launch/linux.sh --width 1080 --height 1920 --display cocoa
./launch/linux.sh --headless --vnc-display 21 --serial-port 4444
./launch/linux.sh --headless --a11y --qmp-socket /tmp/ohos-a11y.sock
QEMU_DISPLAY=none QEMU_HDC_HOST_PORT=5556 ./launch/linux.sh
\`\`\`

\`--userdata-size SIZE\` (or \`QEMU_USERDATA_SIZE\`) sparsely expands \`images/userdata.img\`
before starting QEMU (accepts MiB or \`M\`/\`G\` suffixes such as \`4096\`, \`4G\`, \`8G\`),
and guest \`init\` automatically runs \`fsck.f2fs\` and \`resize.f2fs\` on \`/data\` during boot.
\`--reset\` (or \`QEMU_RESET=1\`, Windows \`-Reset\`) resets the active \`userdata.img\`
(default \`images/userdata.img\`, per-instance \`images/instances/instance-<ID>/userdata.img\`,
or custom \`--userdata-file PATH\`) to a clean factory F2FS image before boot, automatically
preserving any previously customized \`userdata.img\` size unless \`--userdata-size SIZE\` is
explicitly specified alongside \`--reset\`.

\`QEMU_DISPLAY=vnc\` exposes VNC on \`127.0.0.1:\$((5900 + QEMU_VNC_DISPLAY))\`.
\`QEMU_DISPLAY=none\` is recommended for CI/headless hosts. On Linux hosts without
\`DISPLAY\`/\`WAYLAND_DISPLAY\`, graphical modes auto-fallback to headless.
\`QEMU_ACCEL=auto|hvf|kvm|tcg\` (and \`whpx\` on Windows) selects acceleration;
\`auto\` probes host support and falls back to TCG when needed.
\`--a11y\` adds a virtio multitouch device and starts a QMP server for
accessibility gesture injection (QEMU 8.1 or newer).
The multitouch device is registered before the pointer so mouse buttons and
absolute motion stay on the same tablet; touch-slot input remains independent.
The socket path is deterministic from the HDC port when \`--qmp-socket\` is omitted. On Windows, use
\`.\\launch\\windows.ps1 -A11y -QmpPort 4445\`.

After installing a HAP with an \`AccessibilityExtensionAbility\`, enable that
extension from a root HDC shell through the image's system CLI (replace the
example name):

\`\`\`bash
hdc smode
hdc tconn 127.0.0.1:5555
hdc shell /system/bin/cli_tool/executable/ohos-a11yManager ability-enable \\
  --name com.example.app/AccessibilityExtAbility --capabilities 7
\`\`\`

The capability mask must be a subset of the extension's declared
\`accessibilityCapabilities\`. The value \`7\` represents \`retrieve\`,
\`touchGuide\`, and \`gesture\`.

For the \`ohos-native-bindings\` accessibility E2E, point its existing hooks at
the launcher socket and the built-in CLI:

\`\`\`bash
export QEMU_QMP_SOCKET=/tmp/ohos-a11y.sock
export ACCESSIBILITY_E2E_ENABLE_COMMAND=\\
'/system/bin/cli_tool/executable/ohos-a11yManager ability-enable '\\
'--name com.richerfu.ohos_example/AccessibilityE2ETestExtension --capabilities 7'
pnpm run test:ui:accessibility -- --arch x64  # use arm64 for an ARM64 guest
\`\`\`

The runner executes the enable command after HAP installation, when the bundle
and ability are available in the guest.
EOF

  case "${product}" in
    arm64_virt|armv7a_virt|x86_64_virt)
      cat >>"${package_dir}/README.md" <<'EOF'

## Optional two-instance peer Ethernet (Linux and macOS)

The default remains one management `user` NIC. Full POSIX launchers can add a
real QEMU `stream` Ethernet NIC: use `QEMU_PEER_MODE=listen` in the first VM and
`QEMU_PEER_MODE=connect` in the second, with the same explicit `QEMU_PEER_PORT`.
The stream endpoint binds only host loopback. Each VM requires its own
`QEMU_PEER_MAC`, `QEMU_MGMT_MAC`, `QEMU_INSTANCE_UUID`, `QEMU_GUEST_SERIAL`, HDC
port, QMP socket, VNC display and independent copies of every disk image.
`QEMU_PEER_CAPTURE_FILE` optionally records actual data-NIC packets as pcap.
MACs must be distinct locally administered unicast addresses. The selected
QEMU must advertise `stream`; missing support fails instead of using user NAT.

The boot serial and UUID configure the emulated hardware. They are not proof
of independent OpenHarmony identities: compare each running guest's actual
`bm get --udid`, kernel boot UUID, and the two NIC MACs before configuring the
private data subnet. Duplicate actual UDIDs must stop peer validation. The
peer link supplies Ethernet only; static addressing, service discovery,
account/device authentication and authenticated sessions require separate
actual guest verification. Do not run two guests against shared userdata.
EOF
      ;;
  esac

  if [ "${product}" = "x86_64_virt" ]; then
    cat >>"${package_dir}/README.md" <<'EOF'

On Windows WHPX, override the CPU model when the host does not support the
default `max` feature set:

```powershell
.\launch\windows.ps1 -Cpu EPYC-v5 -Accel whpx
```
EOF
  fi

  if [ "${pointer_device}" = "virtio-tablet-pci" ]; then
    cat >>"${package_dir}/README.md" <<'EOF'

The launcher uses an absolute `virtio-tablet` pointer. OpenHarmony maps its
coordinates to the active guest framebuffer, so clicks stay synchronized when
`--resolution`, host window scaling, or HiDPI scaling changes.
EOF
  fi

  if [ "${standard_vpn}" = "true" ]; then
    cat >>"${package_dir}/README.md" <<'EOF'

## Standard VPN

This image includes OpenHarmony's standard VpnExtension service, guest TUN
support, F2FS verity/code-sign-capable writable userdata, SettingsData, and
the signed system VPN authorization dialog. No VPN application is
pre-authorized; the first request must be approved in the guest's system
dialog.
EOF
  fi
}

write_full_product_launchers() {
  local launch_out="$1"
  local product="$2"
  local package_dir="$3"
  local package_name="$4"
  local standard_vpn="${5:-false}"
  local official_qemu_run="${6:-}"
  local pointer_device="${7:-virtio-mouse-pci}"
  local device_type_profile="${8:-${DEVICE_TYPE_PROFILE:-default}}"

  launcher_defaults_for_product "${product}"

  mkdir -p "${launch_out}"

  if [ "${product}" = "x86_64_virt" ] || [ "${product}" = "arm64_virt" ] || \
     [ "${product}" = "armv7a_virt" ]; then
    if [ -n "${official_qemu_run}" ]; then
      if [ ! -f "${official_qemu_run}" ]; then
        echo "missing official qemu_run.sh: ${official_qemu_run}" >&2
        exit 1
      fi
      cp "${official_qemu_run}" "${launch_out}/qemu_run.sh"
    fi
    if [ ! -f "${launch_out}/qemu_run.sh" ]; then
      echo "qemu_run.sh not found in ${launch_out}" >&2
      exit 1
    fi
    sed_in_place_extended 's@[[:space:]]*\|[[:space:]]*grep[[:space:]]+"Accelerators supported"@@g' \
      "${launch_out}/qemu_run.sh"
    if [ "${product}" = "arm64_virt" ]; then
      if grep -q '^# Check hardware acceleration availability' "${launch_out}/qemu_run.sh"; then
        replace_arm64_acceleration_block "${launch_out}/qemu_run.sh"
      fi
    fi
    normalize_common_qemu_launcher \
      "${launch_out}/qemu_run.sh" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_QEMU_UNIX}" \
      "${LAUNCHER_DEFAULT_CPU}" \
      "${pointer_device}"
    ensure_armv7a_sceneboard_headless_scanout \
      "${launch_out}/qemu_run.sh" "${product}" "${device_type_profile}"
    ensure_x86_64_disable_acpi_suspend \
      "${launch_out}/qemu_run.sh" "${product}"
    if [ "${pointer_device}" = "virtio-tablet-pci" ] && \
       { ! grep -q 'virtio-tablet-pci' "${launch_out}/qemu_run.sh" || \
         grep -q 'virtio-mouse-pci' "${launch_out}/qemu_run.sh"; }; then
      echo "absolute-pointer guest requires an exclusive virtio-tablet launcher" >&2
      exit 1
    fi
    if ! grep -q '^QEMU_A11Y_INPUT_ARGS=' "${launch_out}/qemu_run.sh" || \
       ! grep -Fq '${QEMU_A11Y_INPUT_ARGS} -device' "${launch_out}/qemu_run.sh"; then
      echo "accessibility input must be registered before the pointer device" >&2
      exit 1
    fi
    if ! bash -n "${launch_out}/qemu_run.sh"; then
      echo "packaged launcher has invalid shell syntax: ${launch_out}/qemu_run.sh" >&2
      exit 1
    fi
    if ! grep -Eq 'ohos\.required_mount\.data=/dev/block/[^ @]+@/data@f2fs@' \
      "${launch_out}/qemu_run.sh"; then
      echo "packaged launcher does not mount userdata as F2FS: ${launch_out}/qemu_run.sh" >&2
      exit 1
    fi
    chmod +x "${launch_out}/qemu_run.sh"

    write_unix_cli_wrapper \
      "${launch_out}/linux.sh" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_QEMU_UNIX}" \
      "${LAUNCHER_DEFAULT_CPU}"
    cp "${launch_out}/linux.sh" "${launch_out}/macos.command"
    chmod +x "${launch_out}/macos.command"

    if ! grep -q -- '--a11y' "${launch_out}/linux.sh" || \
       ! grep -q -- '--userdata-size' "${launch_out}/linux.sh" || \
       ! grep -q -- '--reset' "${launch_out}/linux.sh" || \
       ! grep -q -- '--shared-dir' "${launch_out}/linux.sh" || \
       ! grep -q -- '--ril-modem' "${launch_out}/linux.sh" || \
       ! grep -q -- '--usb-serial' "${launch_out}/linux.sh" || \
       ! grep -q -- '--port-forward' "${launch_out}/linux.sh" || \
       ! grep -q -- '--rng' "${launch_out}/linux.sh" || \
       ! grep -q 'QEMU_RESET_V1' "${launch_out}/qemu_run.sh" || \
       ! grep -q 'QEMU_USERDATA_SIZE_V1' "${launch_out}/qemu_run.sh" || \
       ! grep -q 'QEMU_CAPABILITIES_V1' "${launch_out}/qemu_run.sh" || \
       ! grep -q 'virtio-multitouch-pci' "${launch_out}/linux.sh" || \
       ! grep -q 'server=on,wait=off' "${launch_out}/linux.sh"; then
      echo "packaged POSIX launcher is missing accessibility/QMP/userdata-size/capabilities support" >&2
      exit 1
    fi

    write_windows_ps1 \
      "${launch_out}/windows.ps1" \
      "${product}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_DEFAULT_CPU}" \
      "${pointer_device}"
  elif [ "${product}" = "qemu-arm64-linux-min" ]; then
    write_unix_cli_wrapper \
      "${launch_out}/linux.sh" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_QEMU_UNIX}" \
      "${LAUNCHER_DEFAULT_CPU}"
    # Minimal product embeds the QEMU command in linux.sh historically; keep a
    # dedicated qemu_run.sh that honors the same env surface.
    cat >"${launch_out}/qemu_run.sh" <<'MIN_EOF'
#!/usr/bin/env bash
set -euo pipefail
OHOS_IMG="${OHOS_IMG:-.}"
QEMU_XRES="${QEMU_XRES:-800}"
QEMU_YRES="${QEMU_YRES:-500}"
QEMU_SMP="${QEMU_SMP:-4}"
QEMU_MEMORY="${QEMU_MEMORY:-1024}"
QEMU_CPU="${QEMU_CPU:-cortex-a57}"
QEMU_BIN="${QEMU_BIN:-qemu-system-aarch64}"
QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS:-}"
exec "${QEMU_BIN}" \
  -M virt \
  -smp "${QEMU_SMP}" \
  -m "${QEMU_MEMORY}" \
  -nographic \
  -cpu "${QEMU_CPU}" \
  -kernel "${OHOS_IMG}/Image" \
  -initrd "${OHOS_IMG}/ramdisk.img" \
  -drive if=none,file="${OHOS_IMG}/userdata.img",format=raw,id=userdata,index=3 \
  -device virtio-blk-device,drive=userdata \
  -drive if=none,file="${OHOS_IMG}/vendor.img",format=raw,id=vendor,index=2 \
  -device virtio-blk-device,drive=vendor \
  -drive if=none,file="${OHOS_IMG}/system.img",format=raw,id=system,index=1 \
  -device virtio-blk-device,drive=system \
  -drive if=none,file="${OHOS_IMG}/updater.img",format=raw,id=updater,index=0 \
  -device virtio-blk-device,drive=updater \
  -append "console=ttyAMA0 init=/init hardware=qemu.arm.linux root=/dev/ram0 rw sn=0023456789 ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required" \
  ${QEMU_EXTRA_ARGS}
MIN_EOF
    chmod +x "${launch_out}/qemu_run.sh"
    cp "${launch_out}/linux.sh" "${launch_out}/macos.command"
    chmod +x "${launch_out}/macos.command"
    write_windows_ps1 \
      "${launch_out}/windows.ps1" \
      "${product}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_DEFAULT_CPU}" \
      "${pointer_device}"
  fi

  cat >"${launch_out}/windows.cmd" <<'EOF'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0windows.ps1" %*
EOF

  if [ ! -f "${launch_out}/windows.ps1" ]; then
    write_windows_ps1 \
      "${launch_out}/windows.ps1" \
      "${product}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_DEFAULT_CPU}" \
      "${pointer_device}"
  fi

  write_package_launcher_readme \
    "${package_dir}" \
    "${package_name}" \
    "${product}" \
    "${standard_vpn}" \
    "${LAUNCHER_DEFAULT_SMP}" \
    "${LAUNCHER_DEFAULT_MEMORY}" \
    "${LAUNCHER_DEFAULT_DISPLAY}" \
    "${LAUNCHER_DEFAULT_CPU}" \
    "${pointer_device}"
}

refresh_package_checksums() {
  local package_dir="$1"
  (
    cd "${package_dir}"
    # Runtime collectors bind nested source/build witnesses to this inventory,
    # including their raw logs and query receipts. Cover the whole package.
    find . -type f ! -path './SHA256SUMS' -print0 \
      | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  )
}

json_string_field() {
  local file="$1"
  local key="$2"
  # Prefer python for robust JSON parsing; fall back to sed.
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' \
      "${file}" "${key}"
  else
    sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "${file}" | head -n1
  fi
}

json_bool_field() {
  local file="$1"
  local key="$2"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
# support top-level or capabilities.*
if sys.argv[2] in d:
  print("true" if d[sys.argv[2]] else "false")
else:
  cap=d.get("capabilities",{})
  print("true" if cap.get(sys.argv[2]) else "false")
' "${file}" "${key}"
  else
    if grep -q "\"${key}\"[[:space:]]*:[[:space:]]*true" "${file}"; then
      echo true
    else
      echo false
    fi
  fi
}

replace_or_append_param() {
  local file="$1"
  local key="$2"
  local line="$3"

  if grep -q -E "^[[:space:]]*${key}[[:space:]]*=" "${file}"; then
    sed_in_place_extended "s|^[[:space:]]*${key}[[:space:]]*=.*$|${line}|" "${file}"
  else
    printf '%s\n' "${line}" >> "${file}"
  fi
}

install_qemu_virt_device_support() {
  local package_dir="$1"
  local product="$2"
  local source_root="${3:-}"
  local tools_dir="${package_dir}/tools"
  local images_dir="${package_dir}/images"
  local system_img="${images_dir}/system.img"
  local vendor_img="${images_dir}/vendor.img"

  mkdir -p "${tools_dir}"
  if [ -f "${SCRIPT_DIR}/qemu_at_modem.py" ]; then
    cp "${SCRIPT_DIR}/qemu_at_modem.py" "${tools_dir}/qemu_at_modem.py"
    chmod +x "${tools_dir}/qemu_at_modem.py"
  fi
  if [ -f "${SCRIPT_DIR}/qemu_hw_controller.py" ]; then
    cp "${SCRIPT_DIR}/qemu_hw_controller.py" "${tools_dir}/qemu_hw_controller.py"
    chmod +x "${tools_dir}/qemu_hw_controller.py"
  fi

  if [ "${product}" != "arm64_virt" ] && [ "${product}" != "x86_64_virt" ] && \
     [ "${product}" != "armv7a_virt" ]; then
    return
  fi

  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot install QEMU virt device support" >&2
    exit 1
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"

  if [ -f "${system_img}" ]; then
    debugfs -w -R "mkdir /mnt/share" "${system_img}" >/dev/null 2>&1 || true
    debugfs -w -R "mkdir /mnt/data" "${system_img}" >/dev/null 2>&1 || true
    debugfs -w -R "mkdir /mnt/data/external" "${system_img}" >/dev/null 2>&1 || true
    debugfs -w -R "mkdir /mnt/data/external/sdcard" "${system_img}" >/dev/null 2>&1 || true
    debugfs -w -R "mkdir /mnt/data/external/nvme" "${system_img}" >/dev/null 2>&1 || true
    debugfs -w -R "mkdir /mnt/data/external/usb" "${system_img}" >/dev/null 2>&1 || true
    local ohos_para_tmp="${tmpdir}/ohos.para"
    if debugfs -R "cat /etc/param/ohos.para" "${system_img}" > "${ohos_para_tmp}" 2>/dev/null && \
       [ -s "${ohos_para_tmp}" ]; then
      replace_or_append_param "${ohos_para_tmp}" \
        "const.telephony.ril.attty.path" "const.telephony.ril.attty.path=/dev/ttyRIL0"
      chmod 0644 "${ohos_para_tmp}"
      debugfs -w -R "rm /etc/param/ohos.para" "${system_img}" >/dev/null 2>&1 || true
      debugfs -w -R "write ${ohos_para_tmp} /etc/param/ohos.para" "${system_img}" >/dev/null
    fi
    local tel_para_tmp="${tmpdir}/telephony.para"
    if debugfs -R "cat /etc/param/telephony.para" "${system_img}" > "${tel_para_tmp}" 2>/dev/null && \
       [ -s "${tel_para_tmp}" ]; then
      replace_or_append_param "${tel_para_tmp}" \
        "const.telephony.ril.attty.path" "const.telephony.ril.attty.path=/dev/ttyRIL0"
      chmod 0644 "${tel_para_tmp}"
      debugfs -w -R "rm /etc/param/telephony.para" "${system_img}" >/dev/null 2>&1 || true
      debugfs -w -R "write ${tel_para_tmp} /etc/param/telephony.para" "${system_img}" >/dev/null
    fi
    if [ "${product}" = "x86_64_virt" ] && command -v python3 >/dev/null 2>&1; then
      local libuv_tmp="${tmpdir}/libuv.so"
      if debugfs -R "dump /system/lib64/platformsdk/libuv.so ${libuv_tmp}" "${system_img}" >/dev/null 2>&1 && \
         [ -s "${libuv_tmp}" ]; then
        if python3 - "${libuv_tmp}" <<'PY'
import sys
path = sys.argv[1]
data = bytearray(open(path, "rb").read())
# In third_party/libuv/BUILD.gn, USE_OHOS_DFX is omitted when is_emulator=true
# (x86_64), leaving uv__use_io_uring(0) enabled in uv__iou_init(). When appspawn
# forks child processes without uv_loop_fork(), the inherited MAP_SHARED io_uring
# epoll-batching ring races across children and aborts in uv__epoll_ctl_flush().
# Patch uv__iou_init() to jump directly to its epilogue, matching arm64/armv7a.
pat = bytes.fromhex("f6c3027454e8c0fbffff3dba0a05000f82f6010000")
repl = bytes.fromhex("e906020000e8c0fbffff3dba0a05000f82f6010000")
idx = data.find(pat)
if idx != -1:
    data[idx:idx + len(pat)] = repl
    open(path, "wb").write(data)
    sys.exit(0)
sys.exit(1)
PY
        then
          chmod 0644 "${libuv_tmp}"
          debugfs -w -R "rm /system/lib64/platformsdk/libuv.so" "${system_img}" >/dev/null 2>&1 || true
          debugfs -w -R "write ${libuv_tmp} /system/lib64/platformsdk/libuv.so" "${system_img}" >/dev/null
        fi
      fi
    fi
  fi

  if [ ! -f "${vendor_img}" ]; then
    rm -rf "${tmpdir}"
    return
  fi

  local setup_sh="${tmpdir}/qemu-init-setup.sh"
  cat >"${setup_sh}" <<'EOF'
#!/system/bin/sh
stage="${1:-boot}"

ensure_char_or_block_node() {
  sys_dir="$1"
  dev_node="$2"
  node_type="$3"
  if [ ! -e "${dev_node}" ] && [ -f "${sys_dir}/dev" ]; then
    dev_nums=""
    read -r dev_nums < "${sys_dir}/dev" 2>/dev/null || true
    major="${dev_nums%:*}"
    minor="${dev_nums#*:}"
    if [ -n "${major}" ] && [ -n "${minor}" ] && [ "${major}" != "${dev_nums}" ]; then
      mknod "${dev_node}" "${node_type}" "${major}" "${minor}" 2>/dev/null || true
    fi
  fi
}

setup_virtio_ports() {
  if [ -d /sys/class/misc/hw_random ] && [ -f /sys/class/misc/hw_random/dev ]; then
    ensure_char_or_block_node /sys/class/misc/hw_random /dev/hwrng c
    chmod 0666 /dev/hwrng 2>/dev/null || true
  fi

  if [ "${stage}" = "boot" ] && [ -d /sys/bus/usb/devices ]; then
    for udir in /sys/bus/usb/devices/*; do
      [ -f "${udir}/busnum" ] && [ -f "${udir}/devnum" ] && [ -f "${udir}/dev" ] || continue
      read -r ubus < "${udir}/busnum" 2>/dev/null || continue
      read -r udev < "${udir}/devnum" 2>/dev/null || continue
      ubus_pad="$(printf '%03d' "${ubus}" 2>/dev/null)" || continue
      udev_pad="$(printf '%03d' "${udev}" 2>/dev/null)" || continue
      mkdir -p "/dev/bus/usb/${ubus_pad}" 2>/dev/null || true
      chmod 0755 /dev/bus /dev/bus/usb "/dev/bus/usb/${ubus_pad}" 2>/dev/null || true
      ensure_char_or_block_node "${udir}" "/dev/bus/usb/${ubus_pad}/${udev_pad}" c
      chmod 0666 "/dev/bus/usb/${ubus_pad}/${udev_pad}" 2>/dev/null || true
    done
  fi

  has_real_usb_tty=0
  if [ -d /sys/class/tty/ttyUSB0 ] && [ -f /sys/class/tty/ttyUSB0/dev ]; then
    has_real_usb_tty=1
    if [ -L /dev/ttyUSB0 ]; then
      rm -f /dev/ttyUSB0 2>/dev/null || true
    fi
    ensure_char_or_block_node /sys/class/tty/ttyUSB0 /dev/ttyUSB0 c
    chmod 0666 /dev/ttyUSB0 2>/dev/null || true
    stty -F /dev/ttyUSB0 raw -echo -echoe -echok clocal -crtscts 115200 2>/dev/null || \
      stty raw -echo -echoe -echok clocal -crtscts 115200 < /dev/ttyUSB0 2>/dev/null || true
  fi

  has_virt_usb_serial=0
  for port_dir in /sys/class/virtio-ports/vport*; do
    [ -e "${port_dir}" ] || continue
    port_name=""
    [ -f "${port_dir}/name" ] && read -r port_name < "${port_dir}/name" 2>/dev/null || true
    case "${port_name}" in
      *ohos.usb.serial*) has_virt_usb_serial=1 ;;
    esac
  done

  for port_dir in /sys/class/virtio-ports/vport*; do
    [ -e "${port_dir}" ] || continue
    port_name=""
    [ -f "${port_dir}/name" ] && read -r port_name < "${port_dir}/name" 2>/dev/null || true
    dev_name="${port_dir##*/}"
    dev_node="/dev/${dev_name}"
    ensure_char_or_block_node "${port_dir}" "${dev_node}" c
    case "${port_name}" in
      *ohos.ril.at*)
        if [ -e "${dev_node}" ]; then
          chown radio:radio "${dev_node}" 2>/dev/null || chown 1001:1001 "${dev_node}" 2>/dev/null || true
          chmod 0666 "${dev_node}" 2>/dev/null || true
          stty -F "${dev_node}" raw -echo -echoe -echok 2>/dev/null || \
            stty raw -echo -echoe -echok < "${dev_node}" 2>/dev/null || true
          ln -sf "${dev_node}" /dev/ttyRIL0 2>/dev/null || true
          if [ "${has_real_usb_tty}" = "0" ] && [ "${has_virt_usb_serial}" = "0" ]; then
            ln -sf "${dev_node}" /dev/ttyUSB0 2>/dev/null || true
          fi
        fi
        ;;
      *ohos.usb.serial*)
        if [ -e "${dev_node}" ]; then
          chmod 0666 "${dev_node}" 2>/dev/null || true
          stty -F "${dev_node}" raw -echo -echoe -echok 2>/dev/null || \
            stty raw -echo -echoe -echok < "${dev_node}" 2>/dev/null || true
          ln -sf "${dev_node}" /dev/qemu_usb_serial 2>/dev/null || true
          if [ "${has_real_usb_tty}" = "0" ]; then
            ln -sf "${dev_node}" /dev/ttyUSB0 2>/dev/null || true
          fi
        fi
        ;;
      *ohos.hw.bridge*)
        if [ -e "${dev_node}" ]; then
          chmod 0666 "${dev_node}" 2>/dev/null || true
          stty -F "${dev_node}" raw -echo -echoe -echok 2>/dev/null || \
            stty raw -echo -echoe -echok < "${dev_node}" 2>/dev/null || true
          ln -sf "${dev_node}" /dev/qemu_hw_bridge 2>/dev/null || true
        fi
        ;;
    esac
  done
}

setup_battery_and_thermal_defaults() {
  [ -d /data ] || return 0
  bat_spec="100:charging"
  therm_c="25"
  for tok in $(cat /proc/cmdline 2>/dev/null); do
    case "${tok}" in
      ohos.boot.qemu.battery=*) bat_spec="${tok#ohos.boot.qemu.battery=}" ;;
      ohos.boot.qemu.thermal=*) therm_c="${tok#ohos.boot.qemu.thermal=}" ;;
    esac
  done
  bat_lvl="${bat_spec%%:*}"
  bat_state="Charging"
  case "${bat_spec}" in
    *:discharging|*:Discharging) bat_state="Discharging" ;;
    *:full|*:Full) bat_state="Full" ;;
    *:not_charging|*:not-charging) bat_state="Not charging" ;;
    *) bat_state="Charging" ;;
  esac
  case "${bat_lvl}" in
    ''|*[!0-9]*) bat_lvl=100 ;;
  esac
  [ "${bat_lvl}" -gt 100 ] 2>/dev/null && bat_lvl=100
  therm_int="${therm_c%%.*}"
  case "${therm_int}" in
    ''|*[!0-9-]*) therm_int=25 ;;
  esac
  temp_deci=$((therm_int * 10))
  temp_milli=$((therm_int * 1000))
  online=1
  [ "${bat_state}" = "Discharging" ] && online=0

  mkdir -p /data/service/el0/battery/battery /data/service/el0/battery/ohos_charger /data/service/el0/battery/ohos-fgu 2>/dev/null || true
  chmod 0755 /data/service/el0 /data/service/el0/battery /data/service/el0/battery/battery /data/service/el0/battery/ohos_charger /data/service/el0/battery/ohos-fgu 2>/dev/null || true
  echo "${bat_lvl}" > /data/service/el0/battery/battery/capacity 2>/dev/null || true
  echo "${bat_state}" > /data/service/el0/battery/battery/status 2>/dev/null || true
  echo "1" > /data/service/el0/battery/battery/present 2>/dev/null || true
  echo "${temp_deci}" > /data/service/el0/battery/battery/temp 2>/dev/null || true
  echo "4200000" > /data/service/el0/battery/battery/voltage_now 2>/dev/null || true
  echo "4200000" > /data/service/el0/battery/battery/voltage_avg 2>/dev/null || true
  echo "1000" > /data/service/el0/battery/battery/current_now 2>/dev/null || true
  echo "1000" > /data/service/el0/battery/battery/current_avg 2>/dev/null || true
  echo "Good" > /data/service/el0/battery/battery/health 2>/dev/null || true
  echo "Li-poly" > /data/service/el0/battery/battery/technology 2>/dev/null || true
  echo "fast" > /data/service/el0/battery/battery/charge_type 2>/dev/null || true
  echo "4000000" > /data/service/el0/battery/battery/charge_counter 2>/dev/null || true
  echo "${online}" > /data/service/el0/battery/ohos_charger/online 2>/dev/null || true
  echo "USB_PD" > /data/service/el0/battery/ohos_charger/type 2>/dev/null || true
  echo "Good" > /data/service/el0/battery/ohos_charger/health 2>/dev/null || true
  chmod 0664 /data/service/el0/battery/battery/* /data/service/el0/battery/ohos_charger/* 2>/dev/null || true

  if [ -d /sys/module/test_power/parameters ]; then
    echo "${bat_lvl}" > /sys/module/test_power/parameters/battery_capacity 2>/dev/null || true
    echo "${bat_state}" > /sys/module/test_power/parameters/battery_status 2>/dev/null || true
    echo "${therm_int}" > /sys/module/test_power/parameters/battery_temp 2>/dev/null || true
    if [ "${online}" = "1" ]; then
      echo "on" > /sys/module/test_power/parameters/ac_online 2>/dev/null || true
      echo "on" > /sys/module/test_power/parameters/usb_online 2>/dev/null || true
    else
      echo "off" > /sys/module/test_power/parameters/ac_online 2>/dev/null || true
      echo "off" > /sys/module/test_power/parameters/usb_online 2>/dev/null || true
    fi
  fi

  mkdir -p /data/service/el0/thermal/sensor /data/service/el0/thermal/cooling 2>/dev/null || true
  for tz in battery soc shell ambient charger pa ap; do
    mkdir -p "/data/service/el0/thermal/sensor/${tz}" 2>/dev/null || true
    echo "${tz}" > "/data/service/el0/thermal/sensor/${tz}/type" 2>/dev/null || true
    echo "${temp_milli}" > "/data/service/el0/thermal/sensor/${tz}/temp" 2>/dev/null || true
    chmod 0664 "/data/service/el0/thermal/sensor/${tz}/type" "/data/service/el0/thermal/sensor/${tz}/temp" 2>/dev/null || true
  done
}

setup_shared_dir() {
  for tag_file in /sys/bus/virtio/drivers/9pnet_virtio/virtio*/mount_tag; do
    [ -f "${tag_file}" ] || continue
    tag="hostshare"
    for tok in $(cat /proc/cmdline 2>/dev/null); do
      case "${tok}" in
        ohos.boot.qemu.share_tag=*)
          tag="${tok#ohos.boot.qemu.share_tag=}"
          ;;
      esac
    done
    [ -n "${tag}" ] || tag="hostshare"
    if [ -d /mnt/share ] && ! grep -q " /mnt/share " /proc/mounts 2>/dev/null; then
      mount -t 9p -o trans=virtio,version=9p2000.L,msize=524288 "${tag}" /mnt/share 2>/dev/null || true
    fi
    if [ -d /data ]; then
      mkdir -p /data/share 2>/dev/null || true
      chmod 0777 /data/share 2>/dev/null || true
      if [ -d /data/share ] && ! grep -q " /data/share " /proc/mounts 2>/dev/null; then
        if grep -q " /mnt/share " /proc/mounts 2>/dev/null; then
          mount -o bind /mnt/share /data/share 2>/dev/null || true
        else
          mount -t 9p -o trans=virtio,version=9p2000.L,msize=524288 "${tag}" /data/share 2>/dev/null || true
        fi
      fi
    fi
    break
  done
}

mount_external_block_dev() {
  bdev="$1"
  mnt_point="$2"
  data_point="$3"
  auto_fmt="$4"
  [ -b "${bdev}" ] || return 0
  mkdir -p "${mnt_point}" 2>/dev/null || true
  chmod 0777 "${mnt_point}" 2>/dev/null || true
  if ! grep -q " ${mnt_point} " /proc/mounts 2>/dev/null; then
    mount -t ext4 "${bdev}" "${mnt_point}" 2>/dev/null || \
      mount "${bdev}" "${mnt_point}" 2>/dev/null || {
        if [ "${auto_fmt}" = "1" ] && [ -x /system/bin/mke2fs ]; then
          /system/bin/mke2fs -t ext4 -F "${bdev}" >/dev/null 2>&1 || true
          mount -t ext4 "${bdev}" "${mnt_point}" 2>/dev/null || true
        fi
      }
  fi
  if grep -q " ${mnt_point} " /proc/mounts 2>/dev/null; then
    chmod 0777 "${mnt_point}" 2>/dev/null || true
    if [ -d /data ] && [ -n "${data_point}" ]; then
      mkdir -p "${data_point}" 2>/dev/null || true
      chmod 0777 "${data_point}" 2>/dev/null || true
      if ! grep -q " ${data_point} " /proc/mounts 2>/dev/null; then
        mount -o bind "${mnt_point}" "${data_point}" 2>/dev/null || true
      fi
    fi
  fi
}

setup_external_storage() {
  mkdir -p /mnt/data/external/sdcard /mnt/data/external/nvme /mnt/data/external/usb 2>/dev/null || true
  chmod 0777 /mnt/data /mnt/data/external /mnt/data/external/sdcard /mnt/data/external/nvme /mnt/data/external/usb 2>/dev/null || true

  # Ensure /dev/sd* and /dev/mmcblk* and /dev/nvme* block nodes exist from /sys/class/block
  for bdir in /sys/class/block/sd* /sys/class/block/mmcblk* /sys/class/block/nvme*; do
    [ -e "${bdir}" ] || continue
    bname="${bdir##*/}"
    ensure_char_or_block_node "${bdir}" "/dev/${bname}" b
    if [ -d /dev/block ]; then
      ensure_char_or_block_node "${bdir}" "/dev/block/${bname}" b
    fi
  done

  # 1. External SD card (/dev/mmcblk0 or SCSI model SDCARD0)
  sd_bdev=""
  if [ -b /dev/block/mmcblk0 ]; then
    sd_bdev="/dev/block/mmcblk0"
    [ -e /dev/mmcblk0 ] || ln -sf /dev/block/mmcblk0 /dev/mmcblk0 2>/dev/null || true
  elif [ -b /dev/mmcblk0 ]; then
    sd_bdev="/dev/mmcblk0"
  else
    for sdir in /sys/class/block/sd*; do
      [ -f "${sdir}/device/model" ] || continue
      if grep -q "SDCARD0" "${sdir}/device/model" 2>/dev/null; then
        sname="${sdir##*/}"
        sd_bdev="/dev/${sname}"
        ln -sf "${sd_bdev}" /dev/mmcblk0 2>/dev/null || true
        [ -d /dev/block ] && ln -sf "${sd_bdev}" /dev/block/mmcblk0 2>/dev/null || true
        break
      fi
    done
  fi
  if [ -n "${sd_bdev}" ]; then
    mount_external_block_dev "${sd_bdev}" "/mnt/data/external/sdcard" "/data/sdcard" "1"
  fi

  # 2. NVMe disk (/dev/nvme0n1 or SCSI model NVME0)
  nvme_bdev=""
  if [ -b /dev/block/nvme0n1 ]; then
    nvme_bdev="/dev/block/nvme0n1"
    [ -e /dev/nvme0n1 ] || ln -sf /dev/block/nvme0n1 /dev/nvme0n1 2>/dev/null || true
  elif [ -b /dev/nvme0n1 ]; then
    nvme_bdev="/dev/nvme0n1"
  else
    for sdir in /sys/class/block/sd*; do
      [ -f "${sdir}/device/model" ] || continue
      if grep -q "NVME0" "${sdir}/device/model" 2>/dev/null; then
        sname="${sdir##*/}"
        nvme_bdev="/dev/${sname}"
        ln -sf "${nvme_bdev}" /dev/nvme0n1 2>/dev/null || true
        [ -d /dev/block ] && ln -sf "${nvme_bdev}" /dev/block/nvme0n1 2>/dev/null || true
        break
      fi
    done
  fi
  if [ -n "${nvme_bdev}" ]; then
    mount_external_block_dev "${nvme_bdev}" "/mnt/data/external/nvme" "/data/nvme" "1"
  fi

  # 3. USB mass storage (any other /sys/class/block/sd* not matching SDCARD0 or NVME0)
  for sdir in /sys/class/block/sd*; do
    [ -f "${sdir}/device/model" ] || continue
    if grep -Eq "SDCARD0|NVME0" "${sdir}/device/model" 2>/dev/null; then
      continue
    fi
    sname="${sdir##*/}"
    usb_bdev="/dev/${sname}"
    if [ -b "${usb_bdev}" ]; then
      mount_external_block_dev "${usb_bdev}" "/mnt/data/external/usb" "/data/usb" "1"
      break
    fi
  done
}

start_hw_bridge() {
  if [ -x /vendor/bin/qemu-hw-bridge ]; then
    /vendor/bin/qemu-hw-bridge --daemon </dev/null >/dev/null 2>&1 &
  fi
}

case "${stage}" in
  pre-init)
    if [ -w /proc/sys/kernel/io_uring_disabled ]; then
      echo 2 > /proc/sys/kernel/io_uring_disabled 2>/dev/null || true
    fi
    mkdir -p /mnt/share /mnt/data/external/sdcard /mnt/data/external/nvme /mnt/data/external/usb 2>/dev/null || true
    chmod 0777 /mnt/share /mnt/data /mnt/data/external /mnt/data/external/sdcard /mnt/data/external/nvme /mnt/data/external/usb 2>/dev/null || true
    setup_virtio_ports
    ;;
  post-fs-data)
    setup_virtio_ports
    setup_battery_and_thermal_defaults
    setup_shared_dir
    setup_external_storage
    start_hw_bridge
    ;;
  boot)
    setup_virtio_ports
    setup_battery_and_thermal_defaults
    setup_shared_dir
    setup_external_storage
    start_hw_bridge
    (
      for _ in 1 2 3 4 5; do
        setup_virtio_ports
        setup_external_storage
        start_hw_bridge
        sleep 1
      done
    ) </dev/null >/dev/null 2>&1 &
    if [ -w /sys/module/cfg80211/parameters/ieee80211_regdom ]; then
      echo CN > /sys/module/cfg80211/parameters/ieee80211_regdom 2>/dev/null || true
    fi
    wifi_mode="auto"
    for tok in $(cat /proc/cmdline 2>/dev/null); do
      case "${tok}" in
        ohos.boot.qemu.wifi=*)
          wifi_mode="${tok#ohos.boot.qemu.wifi=}"
          ;;
      esac
    done
    case "${wifi_mode}" in
      off)
        rmmod mac80211_hwsim 2>/dev/null || true
        ;;
      virt_wifi)
        rmmod mac80211_hwsim 2>/dev/null || true
        insmod /vendor/modules/virt_wifi.ko 2>/dev/null || true
        ip link set wlan0 up 2>/dev/null || ifconfig wlan0 up 2>/dev/null || true
        ;;
      *)
        ip link set wlan0 up 2>/dev/null || ifconfig wlan0 up 2>/dev/null || true
        ;;
    esac
    ;;
esac
exit 0
EOF
  chmod 0755 "${setup_sh}"
  debugfs -w -R "rm /bin/qemu-init-setup.sh" "${vendor_img}" >/dev/null 2>&1 || true
  debugfs -w -R "write ${setup_sh} /bin/qemu-init-setup.sh" "${vendor_img}" >/dev/null

  local reg_cfg="${tmpdir}/qemu-regulatory.cfg"
  cat >"${reg_cfg}" <<'EOF'
{
    "jobs" : [{
            "name" : "pre-init",
            "cmds" : [
                "syncexec /system/bin/sh /vendor/bin/qemu-init-setup.sh pre-init"
            ]
        }, {
            "name" : "post-fs-data",
            "cmds" : [
                "syncexec /system/bin/sh /vendor/bin/qemu-init-setup.sh post-fs-data"
            ]
        }, {
            "name" : "boot",
            "cmds" : [
                "write /sys/module/cfg80211/parameters/ieee80211_regdom CN",
                "syncexec /system/bin/sh /vendor/bin/qemu-init-setup.sh boot",
                "ifup wlan0"
            ]
        }
    ]
}
EOF
  chmod 0644 "${reg_cfg}"
  debugfs -w -R "rm /etc/init/qemu-regulatory.cfg" "${vendor_img}" >/dev/null 2>&1 || true
  debugfs -w -R "write ${reg_cfg} /etc/init/qemu-regulatory.cfg" "${vendor_img}" >/dev/null

  local bt_target=""
  local bt_lib_dest=""
  case "${product}" in
    arm64_virt)
      bt_target="aarch64-linux-ohos"
      bt_lib_dest="/lib64/libbt_vendor.z.so"
      ;;
    x86_64_virt)
      bt_target="x86_64-linux-ohos"
      bt_lib_dest="/lib64/libbt_vendor.z.so"
      ;;
    armv7a_virt)
      bt_target="arm-linux-ohos"
      bt_lib_dest="/lib/libbt_vendor.z.so"
      ;;
  esac

  if [ -n "${bt_lib_dest}" ] && [ -f "${SCRIPT_DIR}/qemu_bt_vendor.c" ]; then
    local clang_bin=""
    local ohos_sysroot=""
    local candidate_root
    for candidate_root in "${source_root}" "/Volumes/PSSD/qemu/openharmony" "/Volumes/PSSD/ohos/ohos-main"; do
      if [ -z "${candidate_root}" ] || [ ! -d "${candidate_root}" ]; then
        continue
      fi
      local host_dir
      for host_dir in darwin-arm64 darwin-x86_64 linux-x86_64 linux-aarch64; do
        local candidate_clang="${candidate_root}/prebuilts/clang/ohos/${host_dir}/llvm/bin/clang"
        if [ -x "${candidate_clang}" ] && "${candidate_clang}" --version >/dev/null 2>&1; then
          clang_bin="${candidate_clang}"
          break
        fi
      done
      for sdk_sysroot in "${candidate_root}"/prebuilts/ohos-sdk/linux/*/native/sysroot; do
        if [ -d "${sdk_sysroot}" ]; then
          ohos_sysroot="${sdk_sysroot}"
          break
        fi
      done
      if [ -n "${clang_bin}" ]; then
        break
      fi
    done

    local bt_so="${tmpdir}/libbt_vendor.z.so"
    if [ -n "${clang_bin}" ]; then
      local libc_stub_c="${tmpdir}/libc_stub.c"
      local libc_stub_so="${tmpdir}/libc.so"
      cat >"${libc_stub_c}" <<'STUB_EOF'
int *__errno_location(void) { return 0; }
void *memcpy(void *d, const void *s, __SIZE_TYPE__ n) { return d; }
void *memset(void *s, int c, __SIZE_TYPE__ n) { return s; }
__PTRDIFF_TYPE__ read(int fd, void *b, __SIZE_TYPE__ c) { return 0; }
__PTRDIFF_TYPE__ write(int fd, const void *b, __SIZE_TYPE__ c) { return 0; }
int close(int fd) { return 0; }
int socketpair(int d, int t, int p, int sv[2]) { return 0; }
int shutdown(int s, int h) { return 0; }
int pthread_create(void *t, const void *a, void *(*f)(void *), void *g) { return 0; }
int pthread_join(void *t, void **r) { return 0; }
int select(int n, void *r, void *w, void *e, void *t) { return 0; }
STUB_EOF
      if [ "${bt_target}" = "arm-linux-ohos" ]; then
        "${clang_bin}" --target="${bt_target}" -march=armv7-a -mfloat-abi=softfp \
          -fPIC -ffreestanding -nostdlib -shared -Wl,-soname,libc.so \
          "${libc_stub_c}" -o "${libc_stub_so}"
        "${clang_bin}" --target="${bt_target}" -march=armv7-a -mfloat-abi=softfp \
          -O2 -fPIC -ffreestanding -nostdlib -shared -Wl,-soname,libbt_vendor.z.so \
          "${SCRIPT_DIR}/qemu_bt_vendor.c" "${libc_stub_so}" -o "${bt_so}"
      else
        "${clang_bin}" --target="${bt_target}" \
          -fPIC -ffreestanding -nostdlib -shared -Wl,-soname,libc.so \
          "${libc_stub_c}" -o "${libc_stub_so}"
        "${clang_bin}" --target="${bt_target}" \
          -O2 -fPIC -ffreestanding -nostdlib -shared -Wl,-soname,libbt_vendor.z.so \
          "${SCRIPT_DIR}/qemu_bt_vendor.c" "${libc_stub_so}" -o "${bt_so}"
      fi
      chmod 0644 "${bt_so}"
      debugfs -w -R "rm ${bt_lib_dest}" "${vendor_img}" >/dev/null 2>&1 || true
      debugfs -w -R "write ${bt_so} ${bt_lib_dest}" "${vendor_img}" >/dev/null

      if [ -f "${SCRIPT_DIR}/qemu_hw_bridge.c" ] && [ -n "${ohos_sysroot}" ]; then
        local hw_bridge_bin="${tmpdir}/qemu-hw-bridge"
        if [ "${bt_target}" = "arm-linux-ohos" ]; then
          "${clang_bin}" --target="${bt_target}" -march=armv7-a -mfloat-abi=softfp \
            --sysroot="${ohos_sysroot}" -O2 -Wall -Wextra -Werror \
            "${SCRIPT_DIR}/qemu_hw_bridge.c" -ldl -o "${hw_bridge_bin}"
        else
          "${clang_bin}" --target="${bt_target}" \
            --sysroot="${ohos_sysroot}" -O2 -Wall -Wextra -Werror \
            "${SCRIPT_DIR}/qemu_hw_bridge.c" -ldl -o "${hw_bridge_bin}"
        fi
        chmod 0755 "${hw_bridge_bin}"
        debugfs -w -R "rm /bin/qemu-hw-bridge" "${vendor_img}" >/dev/null 2>&1 || true
        debugfs -w -R "write ${hw_bridge_bin} /bin/qemu-hw-bridge" "${vendor_img}" >/dev/null
      fi
    elif ! debugfs -R "stat ${bt_lib_dest}" "${vendor_img}" 2>&1 \
           | grep -qE '(^|[[:space:]])Inode:[[:space:]]*[0-9]+'; then
      rm -rf "${tmpdir}"
      echo "OHOS clang not found and ${bt_lib_dest} is missing from ${vendor_img}" >&2
      exit 1
    fi
  fi

  rm -rf "${tmpdir}"
}

rewrite_package_launchers() {
  local package_dir="$1"
  local manifest="${package_dir}/manifest.json"
  local launch_out="${package_dir}/launch"
  local product
  local package_name
  local standard_vpn
  local absolute_pointer_sync
  local pointer_device
  local device_type_profile

  if [ ! -d "${package_dir}" ]; then
    echo "package directory not found: ${package_dir}" >&2
    exit 1
  fi
  if [ ! -f "${manifest}" ]; then
    echo "manifest.json not found in ${package_dir}" >&2
    exit 1
  fi
  if [ ! -f "${launch_out}/qemu_run.sh" ] && [ ! -f "${launch_out}/linux.sh" ]; then
    echo "no launch scripts found in ${launch_out}" >&2
    exit 1
  fi

  product="$(json_string_field "${manifest}" product)"
  if [ -z "${product}" ]; then
    echo "unable to read product from ${manifest}" >&2
    exit 1
  fi
  package_name="$(basename "${package_dir}")"
  standard_vpn="$(json_bool_field "${manifest}" standard_vpn)"
  absolute_pointer_sync="$(json_bool_field "${manifest}" absolute_pointer_sync)"
  device_type_profile="$(json_string_field "${manifest}" device_type_profile)"
  pointer_device=virtio-mouse-pci
  if [ "${absolute_pointer_sync}" = "true" ]; then
    pointer_device=virtio-tablet-pci
  fi

  install_qemu_virt_device_support "${package_dir}" "${product}" "${SOURCE_ROOT:-}"
  if [ -f "${package_dir}/images/system.img" ] && command -v python3 >/dev/null 2>&1 && command -v debugfs >/dev/null 2>&1; then
    python3 "${SCRIPT_DIR}/configure_sceneboard_runtime.py" \
      "${package_dir}/images/system.img" >/dev/null
  fi

  write_full_product_launchers \
    "${launch_out}" \
    "${product}" \
    "${package_dir}" \
    "${package_name}" \
    "${standard_vpn}" \
    "" \
    "${pointer_device}" \
    "${device_type_profile}"

  # Refresh launcher metadata in manifest.json when python is available.
  if command -v python3 >/dev/null 2>&1; then
    launcher_defaults_for_product "${product}"
    python3 - "${manifest}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_DEFAULT_CPU}" \
      "${pointer_device}" \
      "${absolute_pointer_sync}" <<'PY'
import json, sys
path, smp, mem, display, cpu, pointer_device, absolute_pointer_sync = sys.argv[1:8]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
accessibility = bool(data.get("capabilities", {}).get("accessibility_test", False))
data["display_default"] = display
data["launcher"] = {
    "resolution_default": "800x500",
    "smp_default": int(smp),
    "memory_default": mem,
    "cpu_default": cpu,
    "pointer_device_default": pointer_device,
    "accessibility": accessibility,
    "qmp_unix": accessibility,
    "cli": True,
}
data.setdefault("capabilities", {})["absolute_pointer_sync"] = absolute_pointer_sync == "true"
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  fi

  if [ "${QEMU_RESET_ON_REWRITE:-0}" = "1" ] || [ "${QEMU_RESET:-0}" = "1" ]; then
    rm -rf "${package_dir}/images/instances"
    if [ -f "${package_dir}/images/userdata.img" ] && command -v python3 >/dev/null 2>&1; then
      python3 - "${package_dir}/images/userdata.img" <<'RESET_PKG_PY'
import base64
import os
import struct
import sys
import zlib

b64 = "7d3NbhvHAQfwXX5JdoRWDYwg1aW82SlqWqJkRw4KNG1yKvwCvRSgSEqWLYmqSMtuTmmBoocecs4hD9FD7z71HVrAT2AECPoBBHXhdGd3KMmGncrGOra4vx8wO/xYDsVZSeD8OZy9mESLCVBhi+1//yNNvpecyy7Xs7KQlXA5jeW/b4W95vN9/5nt8E1WaklRWrEOtz9x4/msvJOVpaLNNN71+/+sdc9/9vH5P/30z4NfffTF21eSQdJLJlkBquZiVnb3i8t3d4t6tFXUt+LtvcPtvN5dO4x1ccfu7Xh9VNR3hxt5C3d70/2K/yqrW8X+o/0741Bv7vT6od7a3sxv398rnnB8uDVtJ39AbzzJ97vVO8hvHww38np7PMrrrU+Kn+9erD8ZT4r2BrHd3+YPTyaTaV3cPrw3LF7X/u287u9N4u1Fu6PB8F6oD2Mdny652Stex81xUQ+KHyc53B3cLvYv+uk3/dHd7hn7PbixvXfnXvtweDDeHu213+8sd1bWLo8ONsaTXv/25eXl1fXly1u994fLve6gf/3q6tX2pem9H27c2d4ZDA/ea1/6aKe3t/WL7OqkaK8frh+12u12Vjqr7Us3J5P98QdXrmxtT27e2ej0R7tXdnYOi83l/YPRrWF/0snubA+vr69du7a2vjm4trK+OhxeG6z3NwYba1eXu92V1c3+5vXlbq+7svLeT9pPP/ONGx+f+vm8/iT5fMH/Ql5QIyvN+H6zoTtextt/33yYygFADiAHAOQAcgA5gBxADoAcoDI5QP7GfDFJHibLv8xv/PFcXr0V91nLyq+z8jB7Iz8XRwLh/fw3z/Bth+g0+6fpcfuNWMJzfpiV+2Es8v2T+waOIQAAAJzWgwd//EsacwAAAACqon60WYqfrIdNulR8lptvakvFh7r5pr6kz2bo6MsBAAAAKqix8FVJLZX7ffMwSE0ulDbmTcI888cltfb1dPp6KR6FzfxrOPJyAAAAAKiCPLJpygEAAACgMjlASw4AAAAAlckB5pwvAAAAACohnC8gH2yfIgf4sn4cHtSeM65/erGE8JCwisKj5+w/99T+zbTIDE6TAwAAAAAv5q//6jxOYw7QcN6IqsqPqKVCX8KZXyo0hnuNE1Va/LnHv/o0/nYUlfk3AAAwE2oxB3hyRNA8OUIEAAAAzr780716zAEAAACA2c8BGnIAAAAAqEwO0LROIAAAAFRCWCcwH3gvlrlMXHmLupXXUnlLw5WotAXmSlxcbqG0lswxAQAAeCM1WsZsAEClzOsCAKrsnByAN1tDFwAAAJTo/NM5QBpLvgxAcU6BsFmKI7I0XAjnFayFCyFFqC/pRQAAADgb3ilygLgMYPzstVlULd0DAAAAMyL/rD+NOQAAAAAw+zlATQ4AAAAAlckB6s/8XkCjuD9+PaBZXIvfEmgdPRYAAICzqH60WYoDwOlycM3pIDAsCdeajgEtCzdLGuYDAAAAyAHkAJXRkgMAAABUUGPhq5JayieMlzauDKeuSy6U1VoIO+aSxyW19nV4qaWd2/xR2Mx/90d+Tg4AAAAAVZBHNvNyAAAAAKhMDvBIDgAAAFBBvhfw4mbjewFhUYhwvL78edJ+otcXT1zO/OH+g1vPqp95/Hmuo0Pc1hcAAAC8OvXk6NyAR2P1sBZkGnOAT393PDLN73/3+HEvkgNMmWLw7TlAmvV2TRYAAADAK9JIjicvTHOAcBqImhzgteQA9ay3G3IAAAAAXpFmLCdzgHAGyLoc4LXkAM2st1tyAAAAAF6RViwnc4BGyADaxaC9/n9bqOePrE0v1o6WDgAAINOZ1h19AcCbK405wA9+dP9vIR/49INzeUlO5AZN3QQzTagH1VXXBVBZDV0A1X3/H3MAY30gfdn7fREIAADOjHrMAS7+0HwAqCrzAaDC7wN0AVSW+QBQ4b//mAMY6wPmAwAAwOxrxhzgws/MB4CqMh8Aqst8AKgu8wGguloxBzDWB8wHAACA2fc/"
target_path = sys.argv[1]
payload = zlib.decompress(base64.b64decode(b64), -15)
pos = 0
count = struct.unpack_from("<I", payload, pos)[0]
pos += 4
tmp_path = f"{target_path}.reset.{os.getpid()}"
with open(tmp_path, "wb") as f:
    f.truncate(2147483648)
    for _ in range(count):
        blk_idx, blk_len = struct.unpack_from("<II", payload, pos)
        pos += 8
        f.seek(blk_idx * 4096)
        f.write(payload[pos : pos + blk_len])
        pos += blk_len
os.replace(tmp_path, target_path)
RESET_PKG_PY
    fi
  fi

  refresh_package_checksums "${package_dir}"
  echo "rewrote launchers in ${package_dir}"
}

if [ -n "${REWRITE_PACKAGE}" ]; then
  if [ -n "${SOURCE_ROOT}" ] || [ -n "${PRODUCT}" ] || [ -n "${OUTPUT_DIR}" ] || \
     [ -n "${REWRITE_ARM64_LAUNCHER}" ]; then
    echo "--rewrite-package cannot be combined with other package options" >&2
    exit 2
  fi
  rewrite_package_launchers "${REWRITE_PACKAGE}"
  exit 0
fi

if [ -n "${REWRITE_ARM64_LAUNCHER}" ]; then
  if [ -n "${SOURCE_ROOT}" ] || [ -n "${PRODUCT}" ] || [ -n "${OUTPUT_DIR}" ]; then
    echo "--rewrite-arm64-launcher cannot be combined with package options" >&2
    exit 2
  fi
  if [ ! -f "${REWRITE_ARM64_LAUNCHER}" ]; then
    echo "ARM64 launcher not found: ${REWRITE_ARM64_LAUNCHER}" >&2
    exit 1
  fi
  sed_in_place_extended 's@[[:space:]]*\|[[:space:]]*grep[[:space:]]+"Accelerators supported"@@g' "${REWRITE_ARM64_LAUNCHER}"
  if grep -q '^# Check hardware acceleration availability' "${REWRITE_ARM64_LAUNCHER}"; then
    replace_arm64_acceleration_block "${REWRITE_ARM64_LAUNCHER}"
  elif ! grep -q '^ACCEL_MODE="${QEMU_ACCEL:-auto}"' "${REWRITE_ARM64_LAUNCHER}"; then
    echo "ARM64 launcher has no recognized accelerator block: ${REWRITE_ARM64_LAUNCHER}" >&2
    exit 1
  fi
  normalize_common_qemu_launcher \
    "${REWRITE_ARM64_LAUNCHER}" 4 4096 qemu-system-aarch64 cortex-a57
  chmod +x "${REWRITE_ARM64_LAUNCHER}"
  exit 0
fi

seed_standard_userdata_dirs() {
  local image="$1"
  if [ "${SEED_USERDATA_DIRS:-1}" != "1" ]; then
    return
  fi
  # F2FS userdata is populated by the first-boot services. debugfs only
  # understands ext filesystems and must not be used to mutate this image.
  if [ "$(od -An -tx4 -j 1024 -N 4 "${image}" | tr -d '[:space:]')" = "f2f52010" ]; then
    return
  fi
  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot seed standard userdata directories" >&2
    exit 1
  fi

  local dirs=(
    /service
    /service/el0
    /service/el0/public
    /service/el1
    /service/el1/public
    /service/el1/public/startup
    /service/el1/public/storage_daemon
    /service/el1/public/storage_daemon/radar
    /service/el1/startup
    /service/el2
    /service/el2/public
    /service/hnp
    /storage
    /storage/el1
    /storage/el1/base
    /storage/el1/bundle
    /storage/el1/database
    /storage/el1/files
    /storage/el2
    /storage/el2/base
    /storage/el2/cloud
    /storage/el2/database
    /storage/el2/distributedfiles
    /storage/el2/group
    /storage/el2/log
    /storage/el2/media
    /storage/el2/share
    /storage/el2/files
    /storage/el3
    /storage/el3/base
    /storage/el3/database
    /storage/el3/files
    /storage/el3/group
    /storage/el4
    /storage/el4/base
    /storage/el4/database
    /storage/el4/files
    /storage/el4/group
    /storage/el5
    /storage/el5/base
    /storage/el5/database
    /storage/el5/files
    /storage/el5/group
    /app
    /app/el1
    /app/el1/bundle
    /app/el1/bundle/public
    /app/el2
    /app/el2/100
    /app/el2/100/base
    /app/el2/100/database
    /app/el2/100/log
    /chipset
    /chipset/el1
    /chipset/el1/public
    /data
    /hdcd
    /local
    /log
    /log/audiodump
    /log/bbox
    /log/crash
    /log/faultlog
    /log/hiaudit
    /log/hilog
    /log/hiperflog
    /log/hitrace
    /log/hiview
    /log/hiview/unified_collection
    /log/hiview/unified_collection/trace
    /log/hiview/unified_collection/trace/telemetry
    /log/hiview/unified_collection/trace/telemetry/share
    /log/reliability
    /log/reliability/bbox
    /log/reliability/bbox/panic_log
    /log/reliability/resource_leak
    /log/sanitizer
    /log/startup
    /nfc
    /system
    /update
    /updater
    /vendor
    /vendor/log
  )

  local dir
  for dir in "${dirs[@]}"; do
    debugfs -w -R "mkdir ${dir}" "${image}" >/dev/null 2>&1 || true
  done
}

install_standard_tun_compat() {
  local image="$1"
  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot install standard TUN compatibility path" >&2
    exit 1
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' RETURN
  local init_config="${tmpdir}/qemu-vpn-tun.cfg"
  cat >"${init_config}" <<'EOF'
{
  "jobs": [
    {
      "name": "init",
      "cmds": [
        "mkdir /dev/net 0755 root root",
        "symlink /dev/tun /dev/net/tun"
      ]
    }
  ]
}
EOF

  debugfs -w -R "rm /etc/init/qemu-vpn-tun.cfg" "${image}" >/dev/null 2>&1 || true
  debugfs -w -R "write ${init_config} /etc/init/qemu-vpn-tun.cfg" "${image}" >/dev/null
  rm -rf "${tmpdir}"
  trap - RETURN
}

inject_standard_qemu_params() {
  local image="$1"
  local product="$2"
  if [ "${INJECT_QEMU_RUNTIME_PARAMS:-1}" != "1" ]; then
    return
  fi
  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot inject QEMU runtime params" >&2
    exit 1
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' RETURN

  local ohos_para="${tmpdir}/ohos.para"
  local tel_para="${tmpdir}/telephony.para"
  local hdc_para="${tmpdir}/hdc.para"
  debugfs -R "cat /etc/param/ohos.para" "${image}" > "${ohos_para}" 2>/dev/null || : > "${ohos_para}"
  debugfs -R "cat /etc/param/telephony.para" "${image}" > "${tel_para}" 2>/dev/null || : > "${tel_para}"
  debugfs -R "cat /etc/param/hdc.para" "${image}" > "${hdc_para}" 2>/dev/null || : > "${hdc_para}"

  if [ "${INJECT_DEVELOPER_MODE_PARAM:-1}" = "1" ]; then
    replace_or_append_param "${ohos_para}" "const.security.developermode.state" "const.security.developermode.state=true"
  fi
  replace_or_append_param "${ohos_para}" "persist.sys.abilityms.maxProcessCacheNum" "persist.sys.abilityms.maxProcessCacheNum=2"
  replace_or_append_param "${ohos_para}" "const.telephony.ril.attty.path" "const.telephony.ril.attty.path=/dev/ttyRIL0"
  if [ -s "${tel_para}" ]; then
    replace_or_append_param "${tel_para}" "const.telephony.ril.attty.path" "const.telephony.ril.attty.path=/dev/ttyRIL0"
    debugfs -w -R "rm /etc/param/telephony.para" "${image}" >/dev/null 2>&1 || true
    debugfs -w -R "write ${tel_para} /etc/param/telephony.para" "${image}" >/dev/null
  fi
  if [ -n "${DEVICE_TYPE:-}" ]; then
    replace_or_append_param "${ohos_para}" \
      "const.product.devicetype" "const.product.devicetype=${DEVICE_TYPE}"
    replace_or_append_param "${ohos_para}" \
      "const.build.characteristics" "const.build.characteristics=${DEVICE_TYPE}"
  fi
  replace_or_append_param "${hdc_para}" "persist.hdc.mode.usb" 'persist.hdc.mode.usb = "disable"'
  replace_or_append_param "${hdc_para}" "persist.hdc.mode.tcp" 'persist.hdc.mode.tcp = "enable"'
  replace_or_append_param "${hdc_para}" "persist.hdc.mode.uart" 'persist.hdc.mode.uart = "disable"'
  replace_or_append_param "${hdc_para}" "persist.hdc.mode" 'persist.hdc.mode = "tcp"'
  replace_or_append_param "${hdc_para}" "persist.hdc.port" 'persist.hdc.port = "5555"'

  debugfs -w -R "rm /etc/param/ohos.para" "${image}" >/dev/null 2>&1 || true
  debugfs -w -R "write ${ohos_para} /etc/param/ohos.para" "${image}" >/dev/null
  debugfs -w -R "rm /etc/param/hdc.para" "${image}" >/dev/null 2>&1 || true
  debugfs -w -R "write ${hdc_para} /etc/param/hdc.para" "${image}" >/dev/null
  if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] || \
     [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ]; then
    python3 "${SCRIPT_DIR}/configure_sceneboard_runtime.py" "${image}"
  fi
  rm -rf "${tmpdir}"
  trap - RETURN
}

install_developer_policy() {
  local image="$1"
  local source_root="$2"
  local product="$3"

  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot install developer SELinux policy" >&2
    exit 1
  fi

  local stat_output
  stat_output="$(debugfs -R "stat /etc/selinux/targeted/policy/developer_policy" "${image}" 2>&1 || true)"
  if ! printf '%s\n' "${stat_output}" | grep -q "File not found"; then
    return
  fi

  local policy="${source_root}/out/${product}/obj/base/security/selinux_adapter/developer/policy.31"
  if [ ! -f "${policy}" ]; then
    policy="${source_root}/out/${product}/obj/base/security/selinux_adapter/developer/developer_policy"
  fi
  if [ ! -f "${policy}" ]; then
    echo "missing developer SELinux policy for ${product}" >&2
    echo "expected: ${source_root}/out/${product}/obj/base/security/selinux_adapter/developer/policy.31" >&2
    exit 1
  fi

  debugfs -w -R "write ${policy} /etc/selinux/targeted/policy/developer_policy" "${image}" >/dev/null
}

ensure_standard_system_root() {
  local image="$1"

  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot update standard system root" >&2
    exit 1
  fi

  debugfs -w -R "mkdir /data" "${image}" >/dev/null 2>&1 || true

  local log_stat
  log_stat="$(debugfs -R "stat /log" "${image}" 2>&1 || true)"
  if printf '%s\n' "${log_stat}" | grep -q "File not found"; then
    debugfs -w -R "symlink /log /data/log" "${image}" >/dev/null
  fi
}

kernel_config_for_product() {
  local source_root="$1"
  local product="$2"
  local kernel_obj
  case "${product}" in
    armv7a_virt)
      kernel_obj="arm_virt"
      ;;
    arm64_virt)
      kernel_obj="arm64_virt"
      ;;
    x86_64_virt)
      kernel_obj="x86_64_virt"
      ;;
    *)
      return 1
      ;;
  esac
  printf '%s\n' "${source_root}/out/kernel/OBJ/${kernel_obj}/.config"
}

require_kernel_config_bool() {
  local config="$1"
  local option="$2"
  if ! grep -qx "${option}=y" "${config}"; then
    echo "standard VPN requires ${option}=y in final kernel config: ${config}" >&2
    exit 1
  fi
}

require_x86_64_uapi_syscalls() {
  local source_root="$1"
  local include_root="${source_root}/out/x86_64_virt/obj/third_party/musl/usr/include/x86_64-linux-ohos/asm"
  local dispatch_header="${include_root}/unistd.h"
  local syscall_header="${include_root}/unistd_64.h"
  local key_enable="${source_root}/out/x86_64_virt/packages/phone/system/bin/key_enable"
  local objdump="${source_root}/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objdump"

  if [ ! -f "${dispatch_header}" ] || \
     ! grep -Fq '#include <asm/unistd_64.h>' "${dispatch_header}"; then
    echo "x86_64 musl sysroot is not using the native asm-x86 dispatcher: ${dispatch_header}" >&2
    exit 1
  fi
  if [ ! -f "${syscall_header}" ] || \
     ! grep -Eq '^#define[[:space:]]+__NR_statx[[:space:]]+332$' "${syscall_header}"; then
    echo "x86_64 musl sysroot has an invalid statx syscall number: ${syscall_header}" >&2
    exit 1
  fi
  for definition in \
    '__NR_add_key[[:space:]]+248' \
    '__NR_keyctl[[:space:]]+250'
  do
    if ! grep -Eq "^#define[[:space:]]+${definition}$" "${syscall_header}"; then
      echo "x86_64 musl sysroot has an invalid keyring syscall number: ${syscall_header}" >&2
      exit 1
    fi
  done

  if [ ! -x "${objdump}" ]; then
    objdump="$(command -v llvm-objdump || true)"
  fi
  if [ -z "${objdump}" ] || [ ! -x "${objdump}" ]; then
    echo "llvm-objdump not found; cannot verify x86_64 key_enable ABI" >&2
    exit 1
  fi
  if [ ! -f "${key_enable}" ]; then
    echo "x86_64 key_enable binary is missing: ${key_enable}" >&2
    exit 1
  fi

  local key_enable_disassembly
  key_enable_disassembly="$("${objdump}" -d "${key_enable}")"
  for syscall_number in 248 250; do
    if ! grep -Eq \
      "movl[[:space:]]+\\\$${syscall_number},[[:space:]]+%edi" \
      <<<"${key_enable_disassembly}"; then
      echo "x86_64 key_enable does not use syscall ${syscall_number}: ${key_enable}" >&2
      exit 1
    fi
  done
  if grep -Eq \
    'movl[[:space:]]+\$(217|219),[[:space:]]+%edi' \
    <<<"${key_enable_disassembly}"; then
    echo "x86_64 key_enable retained arm64 keyring syscalls: ${key_enable}" >&2
    exit 1
  fi
  echo "standard VPN userspace ABI: x86_64 statx/add_key/keyctl -> 332/248/250"
}

image_has_path() {
  local image="$1"
  local path="$2"
  debugfs -R "stat ${path}" "${image}" 2>&1 \
    | grep -qE '(^|[[:space:]])Inode:[[:space:]]*[0-9]+'
}

require_image_path() {
  local image="$1"
  local description="$2"
  shift 2
  local path
  for path in "$@"; do
    if image_has_path "${image}" "${path}"; then
      printf 'standard VPN artifact: %s -> %s\n' "${description}" "${path}"
      return
    fi
  done
  echo "standard VPN artifact is missing from ${image}: ${description}" >&2
  printf 'checked path: %s\n' "$@" >&2
  exit 1
}

require_image_symlink_target() {
  local image="$1"
  local description="$2"
  local expected_target="$3"
  shift 3
  local path
  local metadata
  for path in "$@"; do
    metadata="$(debugfs -R "stat ${path}" "${image}" 2>/dev/null || true)"
    if printf '%s\n' "${metadata}" \
      | grep -Fqx "Fast link dest: \"${expected_target}\""; then
      printf 'standard graphics symlink: %s -> %s/%s\n' \
        "${description}" "${path%/*}" "${expected_target}"
      return
    fi
  done
  echo "standard graphics symlink is missing or has the wrong target in ${image}: ${description}" >&2
  printf 'expected target: %s; checked path: %s\n' "${expected_target}" "$*" >&2
  exit 1
}

require_image_elf() {
  local image="$1"
  local description="$2"
  local expected_machine="$3"
  shift 3
  local tmpdir
  tmpdir="$(mktemp -d)"
  local extracted="${tmpdir}/artifact"
  local path
  for path in "$@"; do
    if ! image_has_path "${image}" "${path}"; then
      continue
    fi
    rm -f "${extracted}"
    if ! debugfs -R "dump ${path} ${extracted}" "${image}" >/dev/null 2>&1; then
      continue
    fi
    if python3 - "${extracted}" "${expected_machine}" <<'PY'
import sys
from pathlib import Path

expected_machine = int(sys.argv[2])
try:
    data = Path(sys.argv[1]).read_bytes()
except OSError:
    raise SystemExit(1)
if len(data) <= 4096 or not data.startswith(b"\x7fELF"):
    raise SystemExit(1)
byteorder = "little" if data[5] == 1 else "big" if data[5] == 2 else None
if byteorder is None:
    raise SystemExit(1)
machine = int.from_bytes(data[18:20], byteorder)
raise SystemExit(0 if machine == expected_machine else 1)
PY
    then
      printf 'standard graphics artifact: %s -> %s\n' "${description}" "${path}"
      rm -rf "${tmpdir}"
      return
    fi
  done
  rm -rf "${tmpdir}"
  echo "standard graphics ELF is missing or invalid in ${image}: ${description}" >&2
  printf 'checked path: %s\n' "$@" >&2
  exit 1
}

dump_first_image_file() {
  local image="$1"
  local destination="$2"
  shift 2
  local path
  for path in "$@"; do
    if image_has_path "${image}" "${path}" && \
       debugfs -R "dump ${path} ${destination}" "${image}" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

require_image_accessibility_cli() {
  local image="$1"
  local tmpdir
  tmpdir="$(mktemp -d)"
  local executable="${tmpdir}/ohos-a11yManager"
  if ! dump_first_image_file "${image}" "${executable}" \
    /system/bin/cli_tool/executable/ohos-a11yManager \
    /bin/cli_tool/executable/ohos-a11yManager; then
    rm -rf "${tmpdir}"
    echo "QEMU accessibility manager is missing from ${image}" >&2
    exit 1
  fi
  if ! python3 - "${executable}" <<'PY'
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
    print("missing accessibility CLI strings: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
PY
  then
    rm -rf "${tmpdir}"
    echo "QEMU accessibility manager does not support arbitrary abilities" >&2
    exit 1
  fi
  rm -rf "${tmpdir}"
  echo "QEMU accessibility management CLI verified"
}

require_image_elf_symbol() {
  local image="$1"
  local description="$2"
  local expected_machine="$3"
  local symbol="$4"
  shift 4
  local tmpdir
  tmpdir="$(mktemp -d)"
  local extracted="${tmpdir}/artifact"
  if dump_first_image_file "${image}" "${extracted}" "$@" && \
     python3 "${SCRIPT_DIR}/verify_runtime_elf_contract.py" \
       --machine "${expected_machine}" --elf "${extracted}" \
       --require-defined "${symbol}"; then
    rm -rf "${tmpdir}"
    printf 'runtime ELF contract: %s exports %s\n' "${description}" "${symbol}"
    return
  fi
  rm -rf "${tmpdir}"
  echo "runtime ELF contract failed: ${description} must export ${symbol}" >&2
  exit 1
}

require_image_jsvm_contract() {
  local image="$1"
  local expected_machine="$2"
  local tmpdir
  tmpdir="$(mktemp -d)"
  local jsvm="${tmpdir}/libjsvm.so"
  local v8="${tmpdir}/libv8_shared.so"
  if ! dump_first_image_file "${image}" "${jsvm}" \
    /system/lib64/libjsvm.so \
    /system/lib/libjsvm.so \
    /system/lib64/ndk/libjsvm.so \
    /system/lib/ndk/libjsvm.so \
    /lib64/libjsvm.so \
    /lib/libjsvm.so; then
    rm -rf "${tmpdir}"
    echo "cannot extract JSVM runtime for ABI verification" >&2
    exit 1
  fi
  if ! dump_first_image_file "${image}" "${v8}" \
    /system/lib64/libv8_shared.so \
    /system/lib/libv8_shared.so \
    /lib64/libv8_shared.so \
    /lib/libv8_shared.so; then
    rm -rf "${tmpdir}"
    echo "cannot extract v8_shared runtime for ABI verification" >&2
    exit 1
  fi
  if ! python3 "${SCRIPT_DIR}/verify_runtime_elf_contract.py" \
    --machine "${expected_machine}" --jsvm "${jsvm}" --v8 "${v8}"; then
    rm -rf "${tmpdir}"
    echo "JSVM M144 V8 runtime ABI contract failed" >&2
    exit 1
  fi
  rm -rf "${tmpdir}"
  echo "JSVM M144 V8 runtime ABI contract verified (not the ArkWeb engine)"
}

require_image_file_contains() {
  local image="$1"
  local description="$2"
  local needle="$3"
  shift 3
  local path
  local content
  for path in "$@"; do
    content="$(debugfs -R "cat ${path}" "${image}" 2>/dev/null || true)"
    if printf '%s\n' "${content}" | grep -Fq "${needle}"; then
      printf 'standard VPN artifact: %s -> %s\n' "${description}" "${path}"
      return
    fi
  done
  echo "standard VPN metadata is missing from ${image}: ${description}" >&2
  printf 'checked path: %s\n' "$@" >&2
  exit 1
}

require_f2fs_verity() {
  local image="$1"
  local description="$2"
  local magic
  magic="$(od -An -tx4 -j 1024 -N 4 "${image}" | tr -d '[:space:]')"
  if [ "${magic}" != "f2f52010" ]; then
    echo "${description} is not an F2FS image: ${image}" >&2
    exit 1
  fi

  # f2fs_super_block starts at byte 1024. Its little-endian feature field is
  # at offset 2180. Require VERITY (0x0400), QUOTA_INO (0x0080),
  # PRJQUOTA (0x0010), and EXTRA_ATTR (0x0008), not just launcher flags.
  local feature_hex
  feature_hex="$(od -An -tx4 -j 3204 -N 4 "${image}" | tr -d '[:space:]')"
  if [ -z "${feature_hex}" ] || (( (16#${feature_hex} & 16#0498) != 16#0498 )); then
    echo "${description} is missing F2FS verity or quota inode features: ${image}" >&2
    echo "F2FS feature bits: ${feature_hex:-unavailable}" >&2
    exit 1
  fi
  printf 'userdata filesystem features: %s -> f2fs+verity+quota+project_quota\n' \
    "${description}"
}

require_vpn_dialog_hap() {
  local image="$1"
  require_image_path "${image}" "system VPN authorization HAP" \
    /system/app/VpnDialog/VpnDialog.hap \
    /app/VpnDialog/VpnDialog.hap
}

verify_standard_vpn_capability() {
  local source_root="$1"
  local product="$2"
  local system_image="$3"
  local userdata_image="$4"

  if ! command -v debugfs >/dev/null 2>&1; then
    echo "debugfs not found; cannot verify standard VPN system artifacts" >&2
    exit 1
  fi

  local kernel_config
  kernel_config="$(kernel_config_for_product "${source_root}" "${product}")"
  if [ ! -f "${kernel_config}" ]; then
    echo "final kernel config not found for standard VPN verification: ${kernel_config}" >&2
    exit 1
  fi
  local option
  for option in \
    CONFIG_NAMESPACES \
    CONFIG_NET \
    CONFIG_UNIX \
    CONFIG_INET \
    CONFIG_NET_NS \
    CONFIG_NETDEVICES \
    CONFIG_TUN \
    CONFIG_IP_ADVANCED_ROUTER \
    CONFIG_IP_MULTIPLE_TABLES \
    CONFIG_IPV6 \
    CONFIG_IPV6_MULTIPLE_TABLES \
    CONFIG_SYSTEM_DATA_VERIFICATION \
    CONFIG_FS_VERITY \
    CONFIG_FS_VERITY_BUILTIN_SIGNATURES \
    CONFIG_SECURITY_CODE_SIGN \
    CONFIG_HCK \
    CONFIG_HCK_VENDOR_HOOKS \
    CONFIG_CRYPTO_ECC \
    CONFIG_CRYPTO_ECDSA \
    CONFIG_CRYPTO_SHA256 \
    CONFIG_FS_ENCRYPTION \
    CONFIG_F2FS_FS \
    CONFIG_F2FS_FS_XATTR \
    CONFIG_F2FS_FS_POSIX_ACL \
    CONFIG_F2FS_FS_SECURITY \
    CONFIG_QUOTA \
    CONFIG_QFMT_V2 \
    CONFIG_QUOTACTL
  do
    require_kernel_config_bool "${kernel_config}" "${option}"
  done
  if [ "${product}" != "armv7a_virt" ]; then
    require_kernel_config_bool \
      "${kernel_config}" CONFIG_ARCH_USES_HIGH_VMA_FLAGS
    require_kernel_config_bool "${kernel_config}" CONFIG_SECURITY_XPM
    require_kernel_config_bool \
      "${kernel_config}" CONFIG_DSMM_DEVELOPER_ENABLE
  fi
  if [ "${product}" = "x86_64_virt" ]; then
    require_x86_64_uapi_syscalls "${source_root}"
  fi

  require_f2fs_verity \
    "${userdata_image}" \
    "writable userdata code-sign support"
  local gpu_elf_machine
  case "${product}" in
    armv7a_virt) gpu_elf_machine=40 ;;
    arm64_virt) gpu_elf_machine=183 ;;
    x86_64_virt) gpu_elf_machine=62 ;;
    *) echo "unsupported product for GPU ELF verification: ${product}" >&2; exit 2 ;;
  esac
  require_image_elf "${system_image}" "Mesa kms_swrast DRI driver" \
    "${gpu_elf_machine}" \
    /system/lib64/kms_swrast_dri.so \
    /system/lib/kms_swrast_dri.so \
    /lib64/kms_swrast_dri.so \
    /lib/kms_swrast_dri.so
  require_image_symlink_target \
    "${system_image}" "Mesa virtio-gpu DRI driver alias" \
    "kms_swrast_dri.so" \
    /system/lib64/virtio_gpu_dri.so \
    /system/lib/virtio_gpu_dri.so \
    /lib64/virtio_gpu_dri.so \
    /lib/virtio_gpu_dri.so
  require_image_symlink_target \
    "${system_image}" "Mesa software-raster DRI driver alias" \
    "kms_swrast_dri.so" \
    /system/lib64/swrast_dri.so \
    /system/lib/swrast_dri.so \
    /lib64/swrast_dri.so \
    /lib/swrast_dri.so
  require_image_file_contains "${system_image}" "QEMU developer mode parameter" \
    "const.security.developermode.state=true" \
    /system/etc/param/ohos.para \
    /etc/param/ohos.para
  require_image_file_contains "${system_image}" "VPN manager System Ability 1155 profile" \
    "1155" \
    /system/profile/netmanager.json \
    /profile/netmanager.json \
    /system/profile/1155.xml \
    /profile/1155.xml
  require_image_path "${system_image}" "VPN manager service library" \
    /system/lib64/libnet_vpn_manager.z.so \
    /system/lib/libnet_vpn_manager.z.so \
    /lib64/libnet_vpn_manager.z.so \
    /lib/libnet_vpn_manager.z.so \
    /system/lib64/libnet_vpn_manager.so \
    /system/lib/libnet_vpn_manager.so
  require_image_path "${system_image}" "VpnExtension runtime module" \
    /system/lib64/module/net/libvpnextension.z.so \
    /system/lib/module/net/libvpnextension.z.so \
    /lib64/module/net/libvpnextension.z.so \
    /lib/module/net/libvpnextension.z.so \
    /system/lib64/module/net/libvpnextension.so \
    /system/lib/module/net/libvpnextension.so
  require_image_path "${system_image}" "VPN manager init configuration" \
    /system/etc/init/vpnmanager.cfg \
    /etc/init/vpnmanager.cfg
  require_image_file_contains "${system_image}" "standard /dev/net/tun compatibility path" \
    "/dev/net/tun" \
    /system/etc/init/qemu-vpn-tun.cfg \
    /etc/init/qemu-vpn-tun.cfg
  require_vpn_dialog_hap "${system_image}"
  require_image_path "${system_image}" "SettingsData authorization provider" \
    /system/app/com.ohos.settingsdata \
    /app/com.ohos.settingsdata \
    /system/app/SettingsData \
    /app/SettingsData
  require_image_file_contains "${system_image}" "VpnDialog preinstall entry" \
    "/system/app/VpnDialog" \
    /system/etc/app/install_list.json \
    /etc/app/install_list.json
  require_image_file_contains "${system_image}" "VpnDialog privileged-extension capability" \
    "com.ohos.vpndialog" \
    /system/etc/app/install_list_capability.json \
    /etc/app/install_list_capability.json

  STANDARD_VPN_VERIFIED=true
  VPN_AUTHORIZATION_MODE=system_dialog
  echo "standard VPN capability verified for ${product}"
}

verify_qemu_runtime_capabilities() {
  local source_root="$1"
  local product="$2"
  local system_image="$3"
  local vendor_image="$4"
  local expected_machine
  case "${product}" in
    armv7a_virt) expected_machine=40 ;;
    arm64_virt) expected_machine=183 ;;
    x86_64_virt) expected_machine=62 ;;
    *) echo "unsupported QEMU runtime product: ${product}" >&2; exit 2 ;;
  esac

  QOS_VERIFIED=false
  VIRTUAL_VIBRATOR_VERIFIED=false
  ACCESSIBILITY_VERIFIED=false
  JSVM_VERIFIED=false

  if [ "${QEMU_QOS_COMPONENT:-1}" = "1" ]; then
    local kernel_config
    kernel_config="$(kernel_config_for_product "${source_root}" "${product}")"
    local option
    for option in \
      CONFIG_AUTHORITY_CTRL \
      CONFIG_QOS_CTRL \
      CONFIG_QOS_AUTHORITY \
      CONFIG_SCHED_LATENCY_NICE \
      CONFIG_UCLAMP_TASK \
      CONFIG_UCLAMP_TASK_GROUP
    do
      require_kernel_config_bool "${kernel_config}" "${option}"
    done
    if ! grep -qx 'CONFIG_QOS_POLICY_MAX_NR=6' "${kernel_config}"; then
      echo "QoS policy count is missing from final kernel config: ${kernel_config}" >&2
      exit 1
    fi
    QOS_VERIFIED=true
    echo "QEMU QoS kernel capability verified for ${product}"
  fi

  if [ "${QEMU_VIBRATOR_COMPONENT:-1}" = "1" ]; then
    require_image_elf "${vendor_image}" "QEMU virtual vibrator product VDI" \
      "${expected_machine}" \
      /vendor/lib64/libhdi_product_vibrator_impl.z.so \
      /vendor/lib/libhdi_product_vibrator_impl.z.so \
      /lib64/libhdi_product_vibrator_impl.z.so \
      /lib/libhdi_product_vibrator_impl.z.so
    require_image_elf_symbol "${vendor_image}" \
      "QEMU virtual vibrator product VDI" "${expected_machine}" \
      hdfVdiDesc \
      /vendor/lib64/libhdi_product_vibrator_impl.z.so \
      /vendor/lib/libhdi_product_vibrator_impl.z.so \
      /lib64/libhdi_product_vibrator_impl.z.so \
      /lib/libhdi_product_vibrator_impl.z.so
    VIRTUAL_VIBRATOR_VERIFIED=true
    echo "QEMU virtual vibrator capability verified for ${product}"
  fi

  if [ "${QEMU_ACCESSIBILITY_COMPONENT:-1}" = "1" ]; then
    local accessibility_source="${source_root}/foundation/barrierfree/accessibility/tools/ohos-accessibilityManager/src/main.cpp"
    local accessibility_build="${source_root}/foundation/barrierfree/accessibility/tools/ohos-accessibilityManager/BUILD.gn"
    local accessibility_config="${source_root}/foundation/barrierfree/accessibility/tools/ohos-accessibilityManager/ohos-a11yManager.json"
    if [ ! -f "${accessibility_source}" ] || \
       [ ! -f "${accessibility_build}" ] || \
       [ ! -f "${accessibility_config}" ] || \
       ! grep -Fq '{"ability-enable", CommandAbilityEnable}' "${accessibility_source}" || \
       ! grep -Fq 'GetOption(args, "--name")' "${accessibility_source}" || \
       ! grep -Fq 'PrepareRootAccessibilityToken()' "${accessibility_source}" || \
       ! grep -Fq '"access_token:libnativetoken"' "${accessibility_build}" || \
       ! grep -Fq '"access_token:libtoken_setproc"' "${accessibility_build}" || \
       ! grep -Fq '"ability-enable"' "${accessibility_config}" || \
       ! grep -Fq '"ability-disable"' "${accessibility_config}"; then
      echo "QEMU generic accessibility CLI source/build/config contract is incomplete" >&2
      exit 1
    fi
    require_image_accessibility_cli "${system_image}"
    ACCESSIBILITY_VERIFIED=true
    echo "QEMU accessibility test capability verified for ${product} (token helpers linked statically)"
  fi

  if [ "${QEMU_JSVM_ENABLED:-false}" = "true" ]; then
    require_image_elf "${system_image}" "JSVM NDK runtime" \
      "${expected_machine}" \
      /system/lib64/libjsvm.so \
      /system/lib/libjsvm.so \
      /system/lib64/ndk/libjsvm.so \
      /system/lib/ndk/libjsvm.so \
      /lib64/libjsvm.so \
      /lib/libjsvm.so
    require_image_elf "${system_image}" "ArkWeb M144 V8 shared runtime" \
      "${expected_machine}" \
      /system/lib64/libv8_shared.so \
      /system/lib/libv8_shared.so \
      /lib64/libv8_shared.so \
      /lib/libv8_shared.so
    require_image_jsvm_contract "${system_image}" "${expected_machine}"
    JSVM_VERIFIED=true
    echo "QEMU JSVM M144 V8 capability verified for ${product} (not the ArkWeb engine)"
  fi
}

write_full_device_profile_evidence() {
  local source_root="$1"
  local product="$2"
  local package_dir="$3"
  local system_image="$4"
  local sys_prod_image="$5"

  case "${DEVICE_TYPE_PROFILE}" in
    qemu_2in1_full_source|qemu_phone_full_source) ;;
    *) return ;;
  esac

  python3 "${SCRIPT_DIR}/../patches/lib/permission_profile.py" \
    --source-root "${source_root}" --product "${product}" --device "${DEVICE_TYPE}" \
    --output "${package_dir}/permission-profile.json"

  python3 - "${source_root}" "${product}" "${package_dir}/device-profile.json" \
    "${DEVICE_TYPE_PROFILE}" "${SCRIPT_DIR}/../patches/lib" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[5])
from device_contract import QEMU_REQUIRED_SYSCAPS, active_official_requirements, retired_declaration_evidence

root = Path(sys.argv[1])
product = sys.argv[2]
output = Path(sys.argv[3])
profile_name = sys.argv[4]
configs = {
    "arm64_virt": "vendor/ohemu/qemu_arm64_linux_full/config.json",
    "x86_64_virt": "vendor/ohemu/qemu_x86_64_linux_full/config.json",
    "armv7a_virt": "vendor/ohemu/qemu_armv7a_linux_full/config.json",
}
profiles = {
    "qemu_2in1_full_source": {
        "device_type": "2in1",
        "effective_profile": "vendor/ohemu/virt/virt_2in1_full.json",
        "metadata": "vendor/ohemu/virt/virt_2in1_full.meta.json",
        "upstream": "productdefine/common/inherit/2in1.json",
    },
    "qemu_phone_full_source": {
        "device_type": "phone",
        "effective_profile": "vendor/ohemu/virt/virt_phone_full.json",
        "metadata": "vendor/ohemu/virt/virt_phone_full.meta.json",
        "upstream": "productdefine/common/inherit/phone.json",
    },
}
profile = profiles[profile_name]
device_type = profile["device_type"]
effective_profile = profile["effective_profile"]
metadata_path = root / profile["metadata"]
upstream_path = root / profile["upstream"]
product_param_path = root / "vendor/ohemu/virt/etc/param/product_virt.para"
parts_path = root / "out/preloader" / product / "parts.json"
features_path = root / "out/preloader" / product / "features.json"
syscap_path = root / "out/preloader" / product / "system/etc/syscap.json"
config_path = root / configs[product]
app_compatibility_parameter = "const.bms.supportAppTypes=2in1,phone,default,tablet"

for path in (
    metadata_path,
    upstream_path,
    product_param_path,
    parts_path,
    features_path,
    syscap_path,
    config_path,
):
    if not path.is_file():
        raise SystemExit(f"full {device_type} package evidence is missing: {path}")

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
config = json.loads(config_path.read_text(encoding="utf-8"))
parts_document = json.loads(parts_path.read_text(encoding="utf-8"))
features_document = json.loads(features_path.read_text(encoding="utf-8"))
syscap_document = json.loads(syscap_path.read_text(encoding="utf-8"))
inherit = config.get("inherit", [])
if effective_profile not in inherit:
    raise SystemExit(f"{config_path} does not inherit {effective_profile}")
if "productdefine/common/inherit/rich.json" not in inherit:
    raise SystemExit(f"{config_path} lost the rich base profile")
if metadata.get("profile") != profile_name:
    raise SystemExit(f"invalid full {device_type} metadata: {metadata_path}")
if metadata.get("app_compatibility_parameter") != app_compatibility_parameter:
    raise SystemExit(f"full {device_type} metadata is missing the QEMU system-app compatibility parameter")
product_params = product_param_path.read_text(encoding="utf-8").splitlines()
if app_compatibility_parameter not in product_params:
    raise SystemExit(f"{product_param_path} is missing {app_compatibility_parameter}")
upstream_sha256 = hashlib.sha256(upstream_path.read_bytes()).hexdigest()
if metadata.get("upstream_sha256") != upstream_sha256:
    raise SystemExit(f"{device_type} profile metadata does not match its current upstream profile")

parts = sorted(parts_document.get("parts", []))
required_parts = sorted(metadata.get("required_parts", []))
missing_parts = sorted(set(required_parts) - set(parts))
if missing_parts:
    raise SystemExit(f"resolved product is missing full {device_type} parts: " + ", ".join(missing_parts))

features = features_document.get("features", {})
required_features = {
    "ace_engine_feature_enable_accessibility": True,
    "ace_engine_feature_enable_web": True,
    "drivers_interface_display_community": True,
    "drivers_interface_display_vdi_default": True,
    "memmgr_purgeable_memory": True,
    "wifi_feature_non_hdf_driver": True,
    "wifi_feature_non_seperate_p2p": True,
}
for overrides in metadata["contract_feature_overrides"].values():
    required_features.update(overrides)
for name, expected in required_features.items():
    if features.get(name) is not expected:
        raise SystemExit(f"resolved {device_type} feature {name} is not {expected}")
if features.get("memmgr_hyperhold_memory") is True:
    raise SystemExit(f"resolved {device_type} profile unexpectedly enables memmgr hyperhold")
declared_caps = {cap for component in syscap_document["components"] for cap in component.get("syscap", [])}
recorded_requirements = metadata.get("explicit_qemu_requirements")
if (not isinstance(recorded_requirements, list) or
        any(not isinstance(cap, str) for cap in recorded_requirements) or
        not QEMU_REQUIRED_SYSCAPS.issubset(recorded_requirements)):
    raise SystemExit("profile metadata omits explicitly requested QEMU capabilities")
official_requirements = metadata.get("required_official_syscaps")
if (not isinstance(official_requirements, list) or not official_requirements or
        any(not isinstance(cap, str) for cap in official_requirements)):
    raise SystemExit("profile metadata has no valid official device capability requirements")
required_qemu_caps = (QEMU_REQUIRED_SYSCAPS | set(recorded_requirements) |
                      set(metadata["enabled_required_syscaps"]) | active_official_requirements(metadata))
sdk_name = "default" if device_type == "phone" else "2in1"
sdk_required = set(json.loads((root / f"interface/sdk-js/api/device-define/{sdk_name}.json").read_text())["SysCaps"])
retired = metadata.get("retired_documented_syscap_names", {})
if retired != retired_declaration_evidence(root, set(official_requirements), sdk_required):
    raise SystemExit("retired SysCap evidence does not match current source / SDK")
for cap, item in retired.items():
    if item["owning_part"] not in parts:
        raise SystemExit(f"retired SysCap name {cap} cannot hide a missing part: {item['owning_part']}")
missing_qemu_caps = sorted(required_qemu_caps - declared_caps)
if missing_qemu_caps:
    raise SystemExit("resolved profile lost requested capabilities: " + ", ".join(missing_qemu_caps))
invalid_caps = sorted(declared_caps.intersection(metadata["excluded_unsupported_syscaps"]))
if invalid_caps:
    raise SystemExit("resolved profile still declares excluded capabilities: " + ", ".join(invalid_caps))
if device_type == "2in1" and "SystemCapability.Communication.NetManager.NetFirewall" not in declared_caps:
    raise SystemExit("resolved 2in1 profile lost its required NetFirewall capability")
if device_type in {"phone", "2in1"}:
    runtime = metadata.get("sceneboard_runtime") or {}
    expected_haps = {"SceneBoard.hap", "NotificationManagement.hap", "ThemeService.hap", "ThemeComponent.hap"}
    hashes = runtime.get("hap_sha256", {})
    if (set(hashes) != expected_haps or
            any(len(digest) != 64 for digest in hashes.values()) or
            runtime.get("profile_valid_until", 0) < 1893456000):
        raise SystemExit("renewed SceneBoard runtime evidence is missing")
    for feature, expected in (("window_manager_use_sceneboard", True),):
        if features.get(feature) is not expected:
            raise SystemExit(f"resolved {device_type} feature {feature} is not {expected}")
    for parameter in (metadata["window_layout_parameter"], metadata["sceneboard_mode_parameter"]):
        if parameter not in product_params:
            raise SystemExit(f"{device_type} product parameters are missing {parameter}")
    if (metadata.get("boot_unlock_events") != [
            "usual.event.USER_UNLOCKED", "usual.event.SCREEN_UNLOCKED"] or
            metadata.get("boot_unlock_trigger") != "bootevent.boot.completed=true" or
            metadata.get("boot_unlock_user_id") != 100):
        raise SystemExit("SceneBoard boot-unlock publisher metadata is missing")

evidence = {
    "schema_version": 1,
    "device_type": device_type,
    "profile": profile_name,
    "product": product,
    "product_config": configs[product],
    "inherit": inherit,
    "upstream_profile": metadata["upstream_profile"],
    "upstream_sha256": upstream_sha256,
    "effective_profile": effective_profile,
    "strategy": metadata["strategy"],
    "qemu_adaptations": {
        "omitted_unavailable_legacy_components": metadata.get(
            "omitted_unavailable_legacy_components", []
        ),
        "mapped_components": metadata.get("mapped_components", []),
        "app_compatibility_parameter": app_compatibility_parameter,
        "jsvm_engine": metadata.get("qemu_adaptations", {}).get("jsvm_engine"),
        "window_architecture_feature": metadata.get("window_architecture_feature"),
        "pc_window_parameter": metadata.get("pc_window_parameter"),
        "pc_mode_parameter": metadata.get("pc_mode_parameter"),
        "window_layout_parameter": metadata.get("window_layout_parameter"),
        "sceneboard_mode_parameter": metadata.get("sceneboard_mode_parameter"),
        "boot_unlock_config": metadata.get("boot_unlock_config"),
        "boot_unlock_events": metadata.get("boot_unlock_events"),
        "boot_unlock_trigger": metadata.get("boot_unlock_trigger"),
        "boot_unlock_user_id": metadata.get("boot_unlock_user_id"),
        "sceneboard_runtime": metadata.get("sceneboard_runtime"),
        "official_contract_sources": metadata["official_contract_sources"],
        "required_official_syscaps": metadata["required_official_syscaps"],
        "retired_documented_syscap_names": metadata.get("retired_documented_syscap_names", {}),
        "explicit_qemu_requirements": metadata["explicit_qemu_requirements"],
        "enabled_required_syscaps": metadata["enabled_required_syscaps"],
        "excluded_unsupported_syscaps": metadata["excluded_unsupported_syscaps"],
        "contract_feature_overrides": metadata["contract_feature_overrides"],
    },
    "required_parts": required_parts,
    "resolved_parts_count": len(parts),
    "resolved_parts": parts,
    "validated_features": {name: features[name] for name in required_features},
    "resolved_syscap_sha256": hashlib.sha256(syscap_path.read_bytes()).hexdigest(),
    "memmgr_hyperhold_memory": features.get("memmgr_hyperhold_memory", False),
}
output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

  require_image_path "${system_image}" "${DEVICE_TYPE} UI appearance service" \
    /system/lib64/libui_appearance_service.z.so \
    /system/lib/libui_appearance_service.z.so \
    /lib64/libui_appearance_service.z.so \
    /lib/libui_appearance_service.z.so
  require_image_path "${system_image}" "${DEVICE_TYPE} input automation tool" \
    /system/bin/wukong \
    /bin/wukong
  require_image_path "${system_image}" "native package manager" \
    /system/bin/hnp \
    /bin/hnp
  require_image_path "${system_image}" "${DEVICE_TYPE}-compatible Launcher system application" \
    /system/app/com.ohos.launcher/Launcher.hap \
    /app/com.ohos.launcher/Launcher.hap
  require_image_path "${system_image}" "${DEVICE_TYPE}-compatible SystemUI system application" \
    /system/app/com.ohos.systemui \
    /app/com.ohos.systemui
  require_image_file_contains "${sys_prod_image}" \
    "BMS compatibility for current QEMU system applications on ${DEVICE_TYPE}" \
    "const.bms.supportAppTypes=2in1,phone,default,tablet" \
    /etc/param/product_virt.para \
    /sys_prod/etc/param/product_virt.para

  for hap in SceneBoard.hap NotificationManagement.hap ThemeService.hap ThemeComponent.hap; do
      require_image_path "${system_image}" "SceneBoard ${hap}" \
        "/system/app/SceneBoard/${hap}" "/app/SceneBoard/${hap}"
    done
    require_image_file_contains "${system_image}" "enabled SceneBoard" \
      ENABLED /system/etc/sceneboard.config /etc/sceneboard.config
    require_image_file_contains "${system_image}" "SceneBoard first-boot preinstall" \
      '/system/app/SceneBoard' /system/etc/app/install_list.json /etc/app/install_list.json
    require_image_file_contains "${system_image}" "SceneBoard privileged extension" \
      '"bundleName": "com.ohos.sceneboard"' \
      /system/etc/app/install_list_capability.json /etc/app/install_list_capability.json
  if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ]; then
    require_image_file_contains "${sys_prod_image}" "PC window layout" \
      "const.window.multiWindowUIType=FreeFormMultiWindow" \
      /etc/param/product_virt.para /sys_prod/etc/param/product_virt.para
    require_image_file_contains "${sys_prod_image}" "SceneBoard PC mode" \
      "persist.sceneboard.ispcmode=true" \
      /etc/param/product_virt.para /sys_prod/etc/param/product_virt.para
    require_image_path "${system_image}" "2in1 DLP manager application" \
      /system/app/com.ohos.dlpmanager \
      /app/com.ohos.dlpmanager
    require_image_path "${system_image}" "2in1 DLP permission service" \
      /system/lib64/libdlp_permission_service.z.so \
      /system/lib/libdlp_permission_service.z.so \
      /lib64/libdlp_permission_service.z.so \
      /lib/libdlp_permission_service.z.so
  else
    require_image_path "${system_image}" "phone Camera application" \
      /system/app/com.ohos.camera \
      /app/com.ohos.camera
    require_image_path "${system_image}" "phone Photos application" \
      /system/app/com.ohos.photos \
      /app/com.ohos.photos
    require_image_path "${system_image}" "phone Contacts application" \
      /system/app/com.ohos.contacts \
      /app/com.ohos.contacts
    require_image_path "${system_image}" "phone telephony core service" \
      /system/lib64/libtel_core_service.z.so \
      /system/lib/libtel_core_service.z.so \
      /lib64/libtel_core_service.z.so \
      /lib/libtel_core_service.z.so
  fi
  echo "full ${DEVICE_TYPE} source profile and runtime artifacts verified for ${product}"
}

case "${PRODUCT}" in
  armv7a_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/armv7a_virt/packages/phone/images"
    GUEST_ARCH="armv7a"
    DISPLAY_DEFAULT="sdl"
    KERNEL_FILE="zImage"
    QEMU_BIN_UNIX="qemu-system-arm"
    QEMU_BIN_WIN="qemu-system-arm.exe"
    OFFICIAL_QEMU_RUN="${SOURCE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full/qemu_run.sh"
    ;;
  x86_64_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/x86_64_virt/packages/phone/images"
    GUEST_ARCH="x86_64"
    DISPLAY_DEFAULT="sdl"
    KERNEL_FILE="bzImage"
    QEMU_BIN_UNIX="qemu-system-x86_64"
    QEMU_BIN_WIN="qemu-system-x86_64.exe"
    OFFICIAL_QEMU_RUN="${SOURCE_ROOT}/vendor/ohemu/qemu_x86_64_linux_full/qemu_run.sh"
    ;;
  arm64_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/arm64_virt/packages/phone/images"
    GUEST_ARCH="arm64"
    DISPLAY_DEFAULT="sdl"
    KERNEL_FILE="Image"
    QEMU_BIN_UNIX="qemu-system-aarch64"
    QEMU_BIN_WIN="qemu-system-aarch64.exe"
    OFFICIAL_QEMU_RUN="${SOURCE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/qemu_run.sh"
    ;;
  qemu-arm64-linux-min)
    IMAGE_DIR="${SOURCE_ROOT}/out/qemu-arm-linux/packages/phone/images"
    GUEST_ARCH="arm64"
    DISPLAY_DEFAULT="none"
    KERNEL_FILE="Image"
    QEMU_BIN_UNIX="qemu-system-aarch64"
    QEMU_BIN_WIN="qemu-system-aarch64.exe"
    ;;
  *)
    echo "unsupported product: ${PRODUCT}" >&2
    exit 2
    ;;
esac

if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] || \
   [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ]; then
  KERNEL_CPU="${GUEST_ARCH}"
  [ "${KERNEL_CPU}" != armv7a ] || KERNEL_CPU=arm
  python3 "${SOURCE_ROOT}/device/qemu/common/virt_full/kernel/kernel_input_evidence.py" \
    verify --source-root "${SOURCE_ROOT}" --arch "${KERNEL_CPU}" \
    --image "${IMAGE_DIR}/${KERNEL_FILE}" \
    --modules-dir "${SOURCE_ROOT}/out/${PRODUCT}/kernel_modules" \
    --certificate "${IMAGE_DIR}/kernel-inputs.json"
fi

COMMON_IMAGES=(
  "${KERNEL_FILE}"
  "ramdisk.img"
  "system.img"
  "vendor.img"
  "userdata.img"
  "updater.img"
)

FULL_ONLY_IMAGES=(
  "sys_prod.img"
  "chip_prod.img"
)

for file in "${COMMON_IMAGES[@]}"; do
  if [ ! -f "${IMAGE_DIR}/${file}" ]; then
    echo "missing required image: ${IMAGE_DIR}/${file}" >&2
    exit 1
  fi
done

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || [ "${PRODUCT}" = "armv7a_virt" ]; then
  for file in "${FULL_ONLY_IMAGES[@]}"; do
    if [ ! -f "${IMAGE_DIR}/${file}" ]; then
      echo "missing required full image: ${IMAGE_DIR}/${file}" >&2
      exit 1
    fi
  done
fi

ABSOLUTE_POINTER_SYNC_VERIFIED=false
POINTER_DEVICE_DEFAULT=virtio-mouse-pci
MMI_MOUSE_TRANSFORM_SOURCE="${SOURCE_ROOT}/foundation/multimodalinput/input/service/mouse_event_normalize/src/mouse_transform_processor.cpp"
if [ -f "${MMI_MOUSE_TRANSFORM_SOURCE}" ] && \
   grep -q 'QEMU_ABSOLUTE_POINTER_SYNC' "${MMI_MOUSE_TRANSFORM_SOURCE}" && \
   grep -q 'libinput_event_pointer_get_absolute_x_transformed' "${MMI_MOUSE_TRANSFORM_SOURCE}" && \
   grep -q 'libinput_event_pointer_get_absolute_y_transformed' "${MMI_MOUSE_TRANSFORM_SOURCE}" && \
   grep -q 'ctx.cursorX = ctx.offset.dx' "${MMI_MOUSE_TRANSFORM_SOURCE}" && \
   grep -q 'ctx.cursorY = ctx.offset.dy' "${MMI_MOUSE_TRANSFORM_SOURCE}"; then
  ABSOLUTE_POINTER_SYNC_VERIFIED=true
  POINTER_DEVICE_DEFAULT=virtio-tablet-pci
  echo "QEMU absolute pointer synchronization source verified for ${PRODUCT}"
elif [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || \
     [ "${PRODUCT}" = "armv7a_virt" ]; then
  echo "warning: guest absolute-pointer mapping is absent; retaining relative virtio-mouse" >&2
fi

PACKAGE_NAME="openharmony-qemu-${GUEST_ARCH}-${PRODUCT}"
if [ -n "${DEVICE_TYPE}" ] && [ "${DEVICE_TYPE_NAME_SUFFIX:-1}" != "0" ]; then
  PACKAGE_NAME="${PACKAGE_NAME}-${DEVICE_TYPE}"
fi
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"
IMAGES_OUT="${PACKAGE_DIR}/images"
LAUNCH_OUT="${PACKAGE_DIR}/launch"
TOOLS_OUT="${PACKAGE_DIR}/tools"
STANDARD_VPN_VERIFIED=false
VPN_AUTHORIZATION_MODE=unverified
QOS_VERIFIED=false
VIRTUAL_VIBRATOR_VERIFIED=false
ACCESSIBILITY_VERIFIED=false
JSVM_VERIFIED=false
SCENEBOARD_WINDOW_MANAGER_VERIFIED=false
MANIFEST_DEVICE_TYPE="${DEVICE_TYPE:-default}"
MANIFEST_DEVICE_TYPE_SOURCE=default
MANIFEST_DEVICE_TYPE_PARAM_ONLY=false
MANIFEST_DEVICE_TYPE_FULL=false
case "${DEVICE_TYPE_PROFILE}" in
  param_only)
    MANIFEST_DEVICE_TYPE_SOURCE=build_parameter
    MANIFEST_DEVICE_TYPE_PARAM_ONLY=true
    ;;
  qemu_2in1_full_source|qemu_phone_full_source)
    MANIFEST_DEVICE_TYPE_SOURCE=source_product_inherit
    MANIFEST_DEVICE_TYPE_FULL=true
    ;;
esac

rm -rf "${PACKAGE_DIR}"
mkdir -p "${IMAGES_OUT}" "${LAUNCH_OUT}" "${TOOLS_OUT}"
cp "${SCRIPT_DIR}/sign-hap.sh" "${TOOLS_OUT}/sign-hap.sh"
cp "${SCRIPT_DIR}/install-hap-signer.sh" "${TOOLS_OUT}/install-hap-signer.sh"
chmod +x "${TOOLS_OUT}/sign-hap.sh" "${TOOLS_OUT}/install-hap-signer.sh"

if [ -n "${QEMU_BUILD_INPUT_MANIFEST:-}" ]; then
  if [ ! -f "${QEMU_BUILD_INPUT_MANIFEST}" ]; then
    echo "build input manifest is missing: ${QEMU_BUILD_INPUT_MANIFEST}" >&2
    exit 1
  fi
  cp "${QEMU_BUILD_INPUT_MANIFEST}" "${PACKAGE_DIR}/build-inputs.json"
fi

if [ -f "${SOURCE_ROOT}/.ohos-qemu-source-baseline.json" ] && \
   [ -f "${SOURCE_ROOT}/.ohos-qemu-resolved-manifest.xml" ]; then
  cp "${SOURCE_ROOT}/.ohos-qemu-source-baseline.json" \
    "${PACKAGE_DIR}/source-baseline.json"
  cp "${SOURCE_ROOT}/.ohos-qemu-resolved-manifest.xml" \
    "${PACKAGE_DIR}/resolved-manifest.xml"
fi
if [ "${DEVICE_TYPE_PROFILE}" = qemu_2in1_full_source ] || [ "${DEVICE_TYPE_PROFILE}" = qemu_phone_full_source ]; then
  python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${SOURCE_ROOT}" \
    --resolved-manifest "${PACKAGE_DIR}/resolved-manifest.xml" \
    --evidence "${PACKAGE_DIR}/openharmony-project-heads.json"
  cp "${SCRIPT_DIR}/openharmony_7_0_release_source_lock.json" "${PACKAGE_DIR}/openharmony-project-lock.json"
fi

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || \
   [ "${PRODUCT}" = "armv7a_virt" ]; then
  FINAL_KERNEL_CONFIG="$(kernel_config_for_product "${SOURCE_ROOT}" "${PRODUCT}")"
  if [ ! -f "${FINAL_KERNEL_CONFIG}" ]; then
    echo "final kernel config is missing: ${FINAL_KERNEL_CONFIG}" >&2
    exit 1
  fi
  cp "${FINAL_KERNEL_CONFIG}" "${PACKAGE_DIR}/kernel.config"
fi

for file in "${COMMON_IMAGES[@]}"; do
  cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
done
if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] || \
   [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ]; then
  cp "${IMAGE_DIR}/kernel-inputs.json" "${PACKAGE_DIR}/kernel-inputs.json"
  cp "${SOURCE_ROOT}/.ohos-qemu-kernel-inputs.json" "${PACKAGE_DIR}/kernel-source-inputs.json"
fi

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || [ "${PRODUCT}" = "armv7a_virt" ]; then
  for file in "${FULL_ONLY_IMAGES[@]}"; do
    cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
  done
  install_developer_policy "${IMAGES_OUT}/system.img" "${SOURCE_ROOT}" "${PRODUCT}"
  inject_standard_qemu_params "${IMAGES_OUT}/system.img" "${PRODUCT}"
  ensure_standard_system_root "${IMAGES_OUT}/system.img"
  seed_standard_userdata_dirs "${IMAGES_OUT}/userdata.img"
  install_standard_tun_compat "${IMAGES_OUT}/system.img"
  install_qemu_virt_device_support "${PACKAGE_DIR}" "${PRODUCT}" "${SOURCE_ROOT}"
  verify_standard_vpn_capability \
    "${SOURCE_ROOT}" \
    "${PRODUCT}" \
    "${IMAGES_OUT}/system.img" \
    "${IMAGES_OUT}/userdata.img"
  verify_qemu_runtime_capabilities \
    "${SOURCE_ROOT}" \
    "${PRODUCT}" \
    "${IMAGES_OUT}/system.img" \
    "${IMAGES_OUT}/vendor.img"
  if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] || \
     [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ]; then
    python3 "${SCRIPT_DIR}/verify_arkweb_core_image.py" \
      --system-image "${IMAGES_OUT}/system.img" --arch "${GUEST_ARCH}" \
      --source-artifact-root "${QEMU_ARKWEB_CORE_ARTIFACTS:?full profile requires verified source core artifacts}" \
      --output "${PACKAGE_DIR}/arkweb-core-evidence.json"
    core_arch="${GUEST_ARCH}"
    if [ "${core_arch}" = armv7a ]; then core_arch=arm; fi
    cp "${QEMU_ARKWEB_CORE_ARTIFACTS}/${core_arch}/core-artifact.json" "${PACKAGE_DIR}/arkweb-source-core.json"
    python3 - "${SCRIPT_DIR}" "${QEMU_ARKWEB_CORE_ARTIFACTS}/${core_arch}" "${PACKAGE_DIR}/arkweb-source-core" <<'PY'
from pathlib import Path
import shutil
import sys
sys.path.insert(0, sys.argv[1])
from m144_core_artifacts import REPORTS
source, target = map(Path, sys.argv[2:])
target.mkdir(exist_ok=False)
for name in (*REPORTS, 'core-artifact.json'):
    shutil.copy2(source / name, target / name)
for name in ('frozen-build-inputs', 'hap-build-inputs'):
    shutil.copytree(source / name, target / name)
PY
  fi
  write_full_device_profile_evidence \
    "${SOURCE_ROOT}" \
    "${PRODUCT}" \
    "${PACKAGE_DIR}" \
    "${IMAGES_OUT}/system.img" \
    "${IMAGES_OUT}/sys_prod.img"
  if [ "${DEVICE_TYPE_PROFILE}" = "qemu_2in1_full_source" ] || \
     [ "${DEVICE_TYPE_PROFILE}" = "qemu_phone_full_source" ]; then
    SCENEBOARD_WINDOW_MANAGER_VERIFIED=true
  fi
fi

launcher_defaults_for_product "${PRODUCT}"
cat > "${PACKAGE_DIR}/manifest.json" <<EOF
{
  "product": "${PRODUCT}",
  "guest_arch": "${GUEST_ARCH}",
  "kernel": "${KERNEL_FILE}",
  "kernel_config": "kernel.config",
  "device_type": "${MANIFEST_DEVICE_TYPE}",
  "device_type_profile": "${DEVICE_TYPE_PROFILE}",
  "device_type_source": "${MANIFEST_DEVICE_TYPE_SOURCE}",
  "qemu_unix": "${QEMU_BIN_UNIX}",
  "qemu_windows": "${QEMU_BIN_WIN}",
  "display_default": "${DISPLAY_DEFAULT}",
  "network_default": "user",
  "launcher": {
    "resolution_default": "800x500",
    "smp_default": ${LAUNCHER_DEFAULT_SMP},
    "memory_default": "${LAUNCHER_DEFAULT_MEMORY}",
    "cpu_default": "${LAUNCHER_DEFAULT_CPU}",
    "pointer_device_default": "${POINTER_DEVICE_DEFAULT}",
    "accessibility": ${ACCESSIBILITY_VERIFIED},
    "qmp_unix": ${ACCESSIBILITY_VERIFIED},
    "cli": true
  },
  "validation": {
    "capability_flags_scope": "static_packaging_contract_only",
    "new_package_boot_tested": false,
    "runtime_behavior_tested": false,
    "first_artifact_behavior_gate_passed": false,
    "runtime_evidence_location": "external_report_bound_to_archive_sha256"
  },
  "capabilities": {
    "absolute_pointer_sync": ${ABSOLUTE_POINTER_SYNC_VERIFIED},
    "thread_qos": ${QOS_VERIFIED},
    "virtual_vibrator": ${VIRTUAL_VIBRATOR_VERIFIED},
    "virtual_vibrator_mode": "simulated",
    "accessibility_test": ${ACCESSIBILITY_VERIFIED},
    "accessibility_cli": ${ACCESSIBILITY_VERIFIED},
    "virtio_multitouch": ${ACCESSIBILITY_VERIFIED},
    "jsvm": ${JSVM_VERIFIED},
    "jsvm_engine": "ArkWeb M144 V8",
    "standard_vpn": ${STANDARD_VPN_VERIFIED},
    "userdata_fs_verity": ${STANDARD_VPN_VERIFIED},
    "userdata_filesystem": "f2fs",
    "userdata_code_sign_ioctl": ${STANDARD_VPN_VERIFIED},
    "developer_device": ${STANDARD_VPN_VERIFIED},
    "vpn_authorization": "${VPN_AUTHORIZATION_MODE}",
    "device_type": "${MANIFEST_DEVICE_TYPE}",
    "device_type_profile": "${DEVICE_TYPE_PROFILE}",
    "device_type_param_only": ${MANIFEST_DEVICE_TYPE_PARAM_ONLY},
    "device_type_full": ${MANIFEST_DEVICE_TYPE_FULL},
    "sceneboard_window_manager": ${SCENEBOARD_WINDOW_MANAGER_VERIFIED}
  }
}
EOF

if [ -f "${PACKAGE_DIR}/source-baseline.json" ]; then
  python3 - "${PACKAGE_DIR}/manifest.json" \
    "${PACKAGE_DIR}/source-baseline.json" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
baseline_path = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["source_baseline"] = json.loads(
    baseline_path.read_text(encoding="utf-8")
)
manifest_path.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
fi

OFFICIAL_FOR_LAUNCH="${OFFICIAL_QEMU_RUN:-}"

write_full_product_launchers \
  "${LAUNCH_OUT}" \
  "${PRODUCT}" \
  "${PACKAGE_DIR}" \
  "${PACKAGE_NAME}" \
  "${STANDARD_VPN_VERIFIED}" \
  "${OFFICIAL_FOR_LAUNCH}" \
  "${POINTER_DEVICE_DEFAULT}" \
  "${DEVICE_TYPE_PROFILE}"

chmod +x "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command" 2>/dev/null || true
if [ -f "${LAUNCH_OUT}/qemu_run.sh" ]; then
  chmod +x "${LAUNCH_OUT}/qemu_run.sh"
fi

refresh_package_checksums "${PACKAGE_DIR}"

(
  cd "${OUTPUT_DIR}"
  # Avoid macOS AppleDouble forks and prefer sparse-aware GNU tar when present.
  export COPYFILE_DISABLE=1
  # The final path must never expose an in-progress archive to validation or
  # download consumers. Keep any previously completed package until tar exits
  # successfully; publish by a same-directory atomic rename.
  archive_tmp="$(mktemp "${PACKAGE_NAME}.tar.gz.tmp.XXXXXX")"
  trap 'rm -f "${archive_tmp}"' EXIT
  if command -v gtar >/dev/null 2>&1; then
    gtar --format=gnu -Sczf "${archive_tmp}" "${PACKAGE_NAME}"
  elif tar --help 2>&1 | grep -q -- '--no-mac-metadata'; then
    tar --no-mac-metadata -czf "${archive_tmp}" "${PACKAGE_NAME}"
  else
    tar -czf "${archive_tmp}" "${PACKAGE_NAME}"
  fi
  mv -f "${archive_tmp}" "${PACKAGE_NAME}.tar.gz"
)

echo "${PACKAGE_DIR}"
