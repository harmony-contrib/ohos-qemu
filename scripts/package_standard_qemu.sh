#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export LANG=C

usage() {
  cat <<'USAGE'
Usage:
  package_standard_qemu.sh --source-root ROOT --product PRODUCT --output-dir DIR

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

if [ -z "${SOURCE_ROOT}" ] || [ -z "${PRODUCT}" ] || [ -z "${OUTPUT_DIR}" ]; then
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

seed_standard_userdata_dirs() {
  local image="$1"
  if [ "${SEED_USERDATA_DIRS:-1}" != "1" ]; then
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

  if [ "${INJECT_DEVELOPER_MODE_PARAM:-0}" = "1" ]; then
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
fi

cat > "${PACKAGE_DIR}/manifest.json" <<EOF
{
  "product": "${PRODUCT}",
  "guest_arch": "${GUEST_ARCH}",
  "kernel": "${KERNEL_FILE}",
  "qemu_unix": "${QEMU_BIN_UNIX}",
  "qemu_windows": "${QEMU_BIN_WIN}",
  "display_default": "${DISPLAY_DEFAULT}",
  "network_default": "user"
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
launch when that host port is already in use.
EOF

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
  sed_in_place_extended 's|^OHOS_IMG="(out/[^"]+)"$|OHOS_IMG="${OHOS_IMG:-\1}"|' "${LAUNCH_OUT}/qemu_run.sh"
  sed_in_place_extended 's|^(DISPLAY_TYPE=.*)$|\1\
HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"|' "${LAUNCH_OUT}/qemu_run.sh"
  sed_in_place_extended 's|hostfwd=tcp::5555-:5555|hostfwd=tcp::${HDC_HOST_PORT}-:5555|g' "${LAUNCH_OUT}/qemu_run.sh"
  sed_in_place_extended 's|init=/init|init=/bin/init|g' "${LAUNCH_OUT}/qemu_run.sh"
  sed_in_place_extended 's|ohos\.required_mount\.system=/dev/block/([^ @]+)@/system@ext4|ohos.required_mount.system=/dev/block/\1@/usr@ext4|g' "${LAUNCH_OUT}/qemu_run.sh"
  if [ "${PRODUCT}" = "armv7a_virt" ]; then
    sed_in_place_extended 's|(ohos\.required_mount\.data=/dev/block/[^ @]+@/data@ext4@[^"]*@wait),reservedsize=|\1,required,reservedsize=|g' "${LAUNCH_OUT}/qemu_run.sh"
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

$KernelBootArgs = "console=ttyS0,115200 sn=0023456789 init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@ext4@nosuid,nodev,noatime,barrier=1,data=ordered,noauto_da_alloc@wait,reservedsize=104857600"

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
