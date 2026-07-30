#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HAP_PROFILE_VERIFIER="${SCRIPT_DIR}/verify_hap_profile.py"

usage() {
  cat <<'USAGE'
Usage:
  package_standard_qemu.sh --source-root ROOT --product PRODUCT --output-dir DIR
  package_standard_qemu.sh --rewrite-arm64-launcher FILE

Products:
  armv7a_virt
  x86_64_virt
  arm64_virt
  qemu-arm64-linux-min

This packages already-built OpenHarmony standard-system QEMU images and
generates Linux, macOS, and Windows launchers where applicable.
USAGE
}

SOURCE_ROOT=
PRODUCT=
OUTPUT_DIR=
REWRITE_ARM64_LAUNCHER=

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
    --rewrite-arm64-launcher)
      REWRITE_ARM64_LAUNCHER="${2:-}"
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

if [ -z "${REWRITE_ARM64_LAUNCHER}" ] && \
   { [ -z "${SOURCE_ROOT}" ] || [ -z "${PRODUCT}" ] || [ -z "${OUTPUT_DIR}" ]; }; then
  usage >&2
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

normalize_common_qemu_launcher() {
  local file="$1"
  sed_in_place_extended 's|^OHOS_IMG="(out/[^"]+)"$|OHOS_IMG="${OHOS_IMG:-\1}"|' "${file}"
  if ! grep -q '^HDC_HOST_PORT=' "${file}"; then
    sed_in_place_extended 's|^(DISPLAY_TYPE=.*)$|\1\
HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"|' "${file}"
  fi
  sed_in_place_extended 's|hostfwd=tcp::5555-:5555|hostfwd=tcp::${HDC_HOST_PORT}-:5555|g' "${file}"
  sed_in_place_extended 's|init=/init|init=/bin/init|g' "${file}"
  sed_in_place_extended 's|ohos\.required_mount\.system=/dev/block/([^ @]+)@/system@ext4|ohos.required_mount.system=/dev/block/\1@/usr@ext4|g' "${file}"
  # Do not consume the trailing backslash that escapes the closing quote in
  # the ARM launchers' QEMU_CMD string.
  sed_in_place_extended 's|(ohos\.required_mount\.data=/dev/block/[^ @]+@/data)@ext4@[^ @"]+@wait[^ "\\]*|\1@f2fs@nosuid,nodev,noatime@wait,required,reservedsize=104857600|g' "${file}"
  if ! grep -q 'oemmode=rd' "${file}"; then
    sed_in_place_extended 's|-append \\"[[:space:]]*|-append \\"oemmode=rd |' "${file}"
    sed_in_place_extended 's|-append "[[:space:]]*|-append "oemmode=rd |' "${file}"
  fi
  if ! grep -q 'developer_mode=1' "${file}"; then
    sed_in_place_extended \
      's|oemmode=rd|oemmode=rd buildvariant=eng developer_mode=1|' \
      "${file}"
  fi
  # OpenHarmony's composer service still needs a display device when the host
  # frontend is disabled. Without virtio-gpu, headless boots lose
  # composer_host/render_service and the critical foundation process exits.
  sed_in_place_extended \
    's|DISPLAY_ARGS="-display none|DISPLAY_ARGS="-device virtio-gpu-pci,xres=800,yres=500 -display none|' \
    "${file}"
  sed_in_place_extended \
    's|^([[:space:]]*)-display none$|\1-device virtio-gpu-pci,xres=800,yres=500\
\1-display none|' \
    "${file}"
}

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
  normalize_common_qemu_launcher "${REWRITE_ARM64_LAUNCHER}"
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

inject_standard_qemu_params() {
  local image="$1"
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
  local hdc_para="${tmpdir}/hdc.para"
  debugfs -R "cat /etc/param/ohos.para" "${image}" > "${ohos_para}" 2>/dev/null || : > "${ohos_para}"
  debugfs -R "cat /etc/param/hdc.para" "${image}" > "${hdc_para}" 2>/dev/null || : > "${hdc_para}"

  if [ "${INJECT_DEVELOPER_MODE_PARAM:-1}" = "1" ]; then
    replace_or_append_param "${ohos_para}" "const.security.developermode.state" "const.security.developermode.state=true"
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
  # at offset 2180, and F2FS_FEATURE_VERITY is bit 0x0400.
  local feature_hex
  feature_hex="$(od -An -tx4 -j 3204 -N 4 "${image}" | tr -d '[:space:]')"
  if [ -z "${feature_hex}" ] || (( (16#${feature_hex} & 16#0400) == 0 )); then
    echo "${description} is missing F2FS verity feature: ${image}" >&2
    echo "F2FS feature bits: ${feature_hex:-unavailable}" >&2
    exit 1
  fi
  printf 'standard VPN filesystem feature: %s -> f2fs+verity\n' \
    "${description}"
}

require_vpn_dialog_hap() {
  local image="$1"
  if [ ! -x "${HAP_PROFILE_VERIFIER}" ]; then
    echo "HAP profile verifier is missing: ${HAP_PROFILE_VERIFIER}" >&2
    exit 1
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' RETURN
  local extracted="${tmpdir}/VpnDialog.hap"
  local path
  for path in \
    /system/app/VpnDialog/VpnDialog.hap \
    /app/VpnDialog/VpnDialog.hap
  do
    if ! image_has_path "${image}" "${path}"; then
      continue
    fi
    rm -f "${extracted}"
    if ! debugfs -R "dump ${path} ${extracted}" "${image}" >/dev/null 2>&1; then
      continue
    fi
    if [ ! -s "${extracted}" ]; then
      continue
    fi
    if python3 "${HAP_PROFILE_VERIFIER}" \
      "${extracted}" \
      --bundle-name com.ohos.vpndialog \
      --app-feature hos_system_app \
      --allowed-acl ohos.permission.MANAGE_SECURE_SETTINGS \
      --allowed-acl ohos.permission.GET_BUNDLE_INFO_PRIVILEGED \
      --allowed-acl ohos.permission.SYSTEM_FLOAT_WINDOW \
      --allowed-acl ohos.permission.GET_BUNDLE_RESOURCES \
      --allowed-acl ohos.permission.GET_RUNNING_INFO \
      --min-valid-seconds "${VPN_DIALOG_PROFILE_MIN_VALID_SECONDS:-31536000}"
    then
      printf 'standard VPN artifact: system VPN authorization HAP -> %s\n' \
        "${path}"
      rm -rf "${tmpdir}"
      trap - RETURN
      return
    fi
  done

  rm -rf "${tmpdir}"
  trap - RETURN
  echo "a non-empty, currently signed VpnDialog.hap is missing from ${image}" >&2
  exit 1
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

case "${PRODUCT}" in
  armv7a_virt)
    IMAGE_DIR="${SOURCE_ROOT}/out/armv7a_virt/packages/phone/images"
    GUEST_ARCH="armv7a"
    DISPLAY_DEFAULT="none"
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

PACKAGE_NAME="openharmony-qemu-${GUEST_ARCH}-${PRODUCT}"
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"
IMAGES_OUT="${PACKAGE_DIR}/images"
LAUNCH_OUT="${PACKAGE_DIR}/launch"
STANDARD_VPN_VERIFIED=false
VPN_AUTHORIZATION_MODE=unverified

rm -rf "${PACKAGE_DIR}"
mkdir -p "${IMAGES_OUT}" "${LAUNCH_OUT}"

for file in "${COMMON_IMAGES[@]}"; do
  cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
done

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || [ "${PRODUCT}" = "armv7a_virt" ]; then
  for file in "${FULL_ONLY_IMAGES[@]}"; do
    cp "${IMAGE_DIR}/${file}" "${IMAGES_OUT}/"
  done
  install_developer_policy "${IMAGES_OUT}/system.img" "${SOURCE_ROOT}" "${PRODUCT}"
  inject_standard_qemu_params "${IMAGES_OUT}/system.img"
  ensure_standard_system_root "${IMAGES_OUT}/system.img"
  seed_standard_userdata_dirs "${IMAGES_OUT}/userdata.img"
  install_standard_tun_compat "${IMAGES_OUT}/system.img"
  verify_standard_vpn_capability \
    "${SOURCE_ROOT}" \
    "${PRODUCT}" \
    "${IMAGES_OUT}/system.img" \
    "${IMAGES_OUT}/userdata.img"
fi

cat > "${PACKAGE_DIR}/manifest.json" <<EOF
{
  "product": "${PRODUCT}",
  "guest_arch": "${GUEST_ARCH}",
  "kernel": "${KERNEL_FILE}",
  "qemu_unix": "${QEMU_BIN_UNIX}",
  "qemu_windows": "${QEMU_BIN_WIN}",
  "display_default": "${DISPLAY_DEFAULT}",
  "network_default": "user",
  "capabilities": {
    "standard_vpn": ${STANDARD_VPN_VERIFIED},
    "userdata_fs_verity": ${STANDARD_VPN_VERIFIED},
    "userdata_filesystem": "f2fs",
    "userdata_code_sign_ioctl": ${STANDARD_VPN_VERIFIED},
    "developer_device": ${STANDARD_VPN_VERIFIED},
    "vpn_authorization": "${VPN_AUTHORIZATION_MODE}"
  }
}
EOF

cat > "${PACKAGE_DIR}/README.md" <<EOF
# ${PACKAGE_NAME}

This package contains an OpenHarmony standard-system QEMU image.

Install QEMU on the host first, then run one of:

- Linux: \`launch/linux.sh\`
- macOS: \`launch/macos.command\`
- Windows PowerShell: \`launch/windows.ps1\`

Set \`QEMU_DISPLAY=vnc\` to expose a VNC display on \`127.0.0.1:5921\`, or
\`QEMU_DISPLAY=none\` for headless execution. HDC/debug forwarding uses host
TCP port 5555 where supported by the guest. Set \`QEMU_HDC_HOST_PORT\` before
launch when that host port is already in use. ARM64 packages accept
\`QEMU_ACCEL=auto|hvf|kvm|tcg\`; the default \`auto\` mode probes HVF before
using it and falls back to TCG when nested virtualization is unavailable.
EOF

if [ "${STANDARD_VPN_VERIFIED}" = "true" ]; then
  cat >> "${PACKAGE_DIR}/README.md" <<'EOF'

## Standard VPN

This image includes OpenHarmony's standard VpnExtension service, guest TUN
support, F2FS verity/code-sign-capable writable userdata, SettingsData, and
the signed system VPN authorization dialog. No VPN application is
pre-authorized; the first request must be approved in the guest's system
dialog.
EOF
fi

if [ "${PRODUCT}" = "x86_64_virt" ] || [ "${PRODUCT}" = "arm64_virt" ] || [ "${PRODUCT}" = "armv7a_virt" ]; then
  if [ ! -f "${OFFICIAL_QEMU_RUN}" ]; then
    echo "missing official qemu_run.sh: ${OFFICIAL_QEMU_RUN}" >&2
    exit 1
  fi
  cp "${OFFICIAL_QEMU_RUN}" "${LAUNCH_OUT}/qemu_run.sh"
  # Some QEMU builds print accelerator names on lines following the heading.
  # Older upstream launchers grep only the heading and therefore miss hvf/kvm.
  # Normalize those launchers while preserving compatibility with QEMU builds
  # that print the accelerator list on one line.
  sed_in_place_extended 's@[[:space:]]*\|[[:space:]]*grep[[:space:]]+"Accelerators supported"@@g' "${LAUNCH_OUT}/qemu_run.sh"
  if [ "${PRODUCT}" = "arm64_virt" ]; then
    replace_arm64_acceleration_block "${LAUNCH_OUT}/qemu_run.sh"
  fi
  normalize_common_qemu_launcher "${LAUNCH_OUT}/qemu_run.sh"
  if ! bash -n "${LAUNCH_OUT}/qemu_run.sh"; then
    echo "packaged launcher has invalid shell syntax: ${LAUNCH_OUT}/qemu_run.sh" >&2
    exit 1
  fi
  if ! grep -Eq 'ohos\.required_mount\.data=/dev/block/[^ @]+@/data@f2fs@' "${LAUNCH_OUT}/qemu_run.sh"; then
    echo "packaged launcher does not mount userdata as F2FS: ${LAUNCH_OUT}/qemu_run.sh" >&2
    exit 1
  fi
  chmod +x "${LAUNCH_OUT}/qemu_run.sh"
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
export OHOS_IMG="${IMG}"
exec "${HERE}/launch/qemu_run.sh"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"
  if [ "${PRODUCT}" = "x86_64_virt" ]; then
    cat > "${LAUNCH_OUT}/windows.ps1" <<'EOF'
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Img = Join-Path $Root "images"
$HdcHostPort = if ($env:QEMU_HDC_HOST_PORT) { $env:QEMU_HDC_HOST_PORT } else { "5555" }

function Resolve-Qemu {
  if ($env:QEMU_SYSTEM_X86_64) {
    return $env:QEMU_SYSTEM_X86_64
  }
  $cmd = Get-Command "qemu-system-x86_64.exe" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $defaultPath = "C:\Program Files\qemu\qemu-system-x86_64.exe"
  if (Test-Path $defaultPath) {
    return $defaultPath
  }
  throw "qemu-system-x86_64.exe not found. Install QEMU for Windows or set QEMU_SYSTEM_X86_64."
}

$Qemu = Resolve-Qemu

$RequestedAccel = if ($env:QEMU_ACCEL) { $env:QEMU_ACCEL.ToLowerInvariant() } else { "auto" }
$AccelArgs = @("-accel", "tcg,thread=multi")
switch ($RequestedAccel) {
  "tcg" {
    Write-Host "TCG software emulation forced by QEMU_ACCEL."
  }
  "whpx" {
    $AccelArgs = @("-accel", "whpx,kernel-irqchip=off")
    Write-Host "WHPX acceleration forced by QEMU_ACCEL."
  }
  default {
    try {
      $AccelHelp = & $Qemu -accel help 2>&1 | Out-String
      if ($AccelHelp -match "whpx") {
        $AccelArgs = @("-accel", "whpx,kernel-irqchip=off")
        Write-Host "WHPX acceleration enabled."
      } else {
        Write-Host "WHPX not available, using TCG software emulation."
      }
    } catch {
      Write-Host "Cannot query QEMU accelerators, using TCG software emulation."
    }
  }
}

$DisplayType = if ($env:QEMU_DISPLAY) { $env:QEMU_DISPLAY } else { "sdl" }
switch ($DisplayType) {
  "none" {
    $DisplayArgs = @("-device", "virtio-gpu-pci,xres=800,yres=500", "-display", "none", "-serial", "mon:stdio")
  }
  "vnc" {
    $DisplayArgs = @("-device", "virtio-gpu-pci,xres=800,yres=500", "-vnc", ":21", "-serial", "stdio")
    Write-Host "Display: VNC on 127.0.0.1:5921"
  }
  "gtk" {
    $DisplayArgs = @("-device", "virtio-gpu-pci", "-display", "gtk,gl=off", "-serial", "stdio")
  }
  default {
    $DisplayArgs = @("-device", "virtio-gpu-pci", "-display", "sdl,gl=off", "-serial", "stdio")
  }
}

$KernelBootArgs = "oemmode=rd buildvariant=eng developer_mode=1 console=ttyS0,115200 sn=0023456789 init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@f2fs@nosuid,nodev,noatime@wait,required,reservedsize=104857600"

$ArgsList = @(
  "-machine", "q35",
  $AccelArgs,
  "-cpu", "max",
  "-smp", "4",
  "-m", "4096",
  "-kernel", (Join-Path $Img "bzImage"),
  "-initrd", (Join-Path $Img "ramdisk.img"),
  $DisplayArgs,
  "-device", "virtio-mouse-pci",
  "-device", "virtio-keyboard-pci",
  "-netdev", "user,id=net0,hostfwd=tcp::${HdcHostPort}-:5555",
  "-device", "virtio-net-pci,netdev=net0",
  "-drive", ("if=none,file={0},format=raw,id=updater" -f (Join-Path $Img "updater.img")),
  "-device", "virtio-blk-pci,drive=updater,serial=updater",
  "-drive", ("if=none,file={0},format=raw,id=system" -f (Join-Path $Img "system.img")),
  "-device", "virtio-blk-pci,drive=system,serial=system",
  "-drive", ("if=none,file={0},format=raw,id=vendor" -f (Join-Path $Img "vendor.img")),
  "-device", "virtio-blk-pci,drive=vendor,serial=vendor",
  "-drive", ("if=none,file={0},format=raw,id=sys_prod" -f (Join-Path $Img "sys_prod.img")),
  "-device", "virtio-blk-pci,drive=sys_prod,serial=sys_prod",
  "-drive", ("if=none,file={0},format=raw,id=chip_prod" -f (Join-Path $Img "chip_prod.img")),
  "-device", "virtio-blk-pci,drive=chip_prod,serial=chip_prod",
  "-drive", ("if=none,file={0},format=raw,id=userdata" -f (Join-Path $Img "userdata.img")),
  "-device", "virtio-blk-pci,drive=userdata,serial=userdata",
  "-append", $KernelBootArgs
)

& $Qemu @ArgsList
exit $LASTEXITCODE
EOF
  fi
elif [ "${PRODUCT}" = "qemu-arm64-linux-min" ]; then
  cat > "${LAUNCH_OUT}/linux.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${HERE}/images"
exec qemu-system-aarch64 \
  -M virt \
  -smp 4 \
  -m 1024 \
  -nographic \
  -cpu cortex-a57 \
  -kernel "${IMG}/Image" \
  -initrd "${IMG}/ramdisk.img" \
  -drive if=none,file="${IMG}/userdata.img",format=raw,id=userdata,index=3 \
  -device virtio-blk-device,drive=userdata \
  -drive if=none,file="${IMG}/vendor.img",format=raw,id=vendor,index=2 \
  -device virtio-blk-device,drive=vendor \
  -drive if=none,file="${IMG}/system.img",format=raw,id=system,index=1 \
  -device virtio-blk-device,drive=system \
  -drive if=none,file="${IMG}/updater.img",format=raw,id=updater,index=0 \
  -device virtio-blk-device,drive=updater \
  -append "console=ttyAMA0 init=/init hardware=qemu.arm.linux root=/dev/ram0 rw sn=0023456789 ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required"
EOF
  cp "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"
fi

cat > "${LAUNCH_OUT}/windows.cmd" <<'EOF'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0windows.ps1"
EOF

if [ ! -f "${LAUNCH_OUT}/windows.ps1" ]; then
  cat > "${LAUNCH_OUT}/windows.ps1" <<EOF
Write-Error "Windows launcher is not enabled for ${PRODUCT} yet. Use x86_64_virt for Windows x86_64."
exit 1
EOF
fi

chmod +x "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command"

(
  cd "${PACKAGE_DIR}"
  find images launch -type f -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
)

(
  cd "${OUTPUT_DIR}"
  tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
)

echo "${PACKAGE_DIR}"
