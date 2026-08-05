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
  package_standard_qemu.sh --rewrite-package DIR

Products:
  armv7a_virt
  x86_64_virt
  arm64_virt
  qemu-arm64-linux-min

This packages already-built OpenHarmony standard-system QEMU images and
generates Linux, macOS, and Windows launchers where applicable.

--rewrite-package rewrites launch scripts inside an existing package directory
without re-copying guest images (useful when only launchers changed).
USAGE
}

SOURCE_ROOT=
PRODUCT=
OUTPUT_DIR=
REWRITE_ARM64_LAUNCHER=
REWRITE_PACKAGE=

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
      LAUNCHER_DEFAULT_DISPLAY=none
      LAUNCHER_QEMU_UNIX=qemu-system-arm
      LAUNCHER_QEMU_WIN=qemu-system-arm.exe
      ;;
    x86_64_virt)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_QEMU_UNIX=qemu-system-x86_64
      LAUNCHER_QEMU_WIN=qemu-system-x86_64.exe
      ;;
    arm64_virt)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
      LAUNCHER_QEMU_UNIX=qemu-system-aarch64
      LAUNCHER_QEMU_WIN=qemu-system-aarch64.exe
      ;;
    qemu-arm64-linux-min)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=1024
      LAUNCHER_DEFAULT_DISPLAY=none
      LAUNCHER_QEMU_UNIX=qemu-system-aarch64
      LAUNCHER_QEMU_WIN=qemu-system-aarch64.exe
      ;;
    *)
      LAUNCHER_DEFAULT_SMP=4
      LAUNCHER_DEFAULT_MEMORY=4096
      LAUNCHER_DEFAULT_DISPLAY=sdl
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
  local block
  local tmp

  # Upgrade previously-normalized launchers that already have resolution vars.
  if grep -q '^QEMU_XRES=' "${file}"; then
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

normalize_common_qemu_launcher() {
  local file="$1"
  local default_smp="${2:-4}"
  local default_mem="${3:-4096}"
  local default_qemu_bin="${4:-qemu-system-x86_64}"

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
    "${file}" "${default_smp}" "${default_mem}" "${default_qemu_bin}"

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

  # CPU / memory.
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

  # Auto headless when no host display is available (Linux SSH, CI).
  ensure_auto_headless_support "${file}"

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

write_unix_cli_wrapper() {
  local dest="$1"
  local default_smp="$2"
  local default_mem="$3"
  local default_display="$4"
  local default_qemu_bin="$5"

  cat >"${dest}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

HERE="\$(cd "\$(dirname "\$0")/.." && pwd)"
export OHOS_IMG="\${HERE}/images"

DEFAULT_SMP="${default_smp}"
DEFAULT_MEMORY="${default_mem}"
DEFAULT_DISPLAY="${default_display}"
DEFAULT_QEMU_BIN="${default_qemu_bin}"
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
  -s, --smp N            Virtual CPUs (default: \${DEFAULT_SMP})
  -d, --display TYPE     none|vnc|sdl|gtk|cocoa|auto (default: \${DEFAULT_DISPLAY})
      --headless         Alias for --display none
  -c, --connect HOST:PORT  HDC forward address (default: 127.0.0.1:\${DEFAULT_HDC_PORT})
      --hdc-port PORT    HDC host TCP port (default: \${DEFAULT_HDC_PORT})
      --vnc-display N    VNC display number (default: \${DEFAULT_VNC_DISPLAY} => TCP \$((5900 + DEFAULT_VNC_DISPLAY)))
      --serial-port PORT Expose guest serial on telnet 127.0.0.1:PORT
  -a, --accel MODE       auto|hvf|kvm|tcg|whpx (default: auto)
  -q, --qemu PATH        Path to the qemu-system-* binary (default: \${DEFAULT_QEMU_BIN})
  -h, --help             Show this help

CLI flags override environment variables, which override the defaults above.
Supported environment variables:
  QEMU_DISPLAY QEMU_XRES QEMU_YRES QEMU_SMP QEMU_MEMORY
  QEMU_HDC_HOST_PORT QEMU_VNC_DISPLAY QEMU_SERIAL_PORT
  QEMU_ACCEL QEMU_BIN QEMU_EXTRA_ARGS
USAGE
}

while [ "\$#" -gt 0 ]; do
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
    -s|--smp)
      export QEMU_SMP="\${2:?missing smp value}"
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

# Apply defaults only when unset so environment variables still work.
export QEMU_XRES="\${QEMU_XRES:-\${DEFAULT_XRES}}"
export QEMU_YRES="\${QEMU_YRES:-\${DEFAULT_YRES}}"
export QEMU_SMP="\${QEMU_SMP:-\${DEFAULT_SMP}}"
export QEMU_MEMORY="\${QEMU_MEMORY:-\${DEFAULT_MEMORY}}"
export QEMU_DISPLAY="\${QEMU_DISPLAY:-\${DEFAULT_DISPLAY}}"
export QEMU_HDC_HOST_PORT="\${QEMU_HDC_HOST_PORT:-\${DEFAULT_HDC_PORT}}"
export QEMU_VNC_DISPLAY="\${QEMU_VNC_DISPLAY:-\${DEFAULT_VNC_DISPLAY}}"
export QEMU_SERIAL_PORT="\${QEMU_SERIAL_PORT:-}"
export QEMU_ACCEL="\${QEMU_ACCEL:-auto}"
export QEMU_BIN="\${QEMU_BIN:-\${DEFAULT_QEMU_BIN}}"
export QEMU_EXTRA_ARGS="\${QEMU_EXTRA_ARGS:-}"

case "\${QEMU_XRES}" in
  ''|*[!0-9]*) echo "invalid width: \${QEMU_XRES}" >&2; exit 2 ;;
esac
case "\${QEMU_YRES}" in
  ''|*[!0-9]*) echo "invalid height: \${QEMU_YRES}" >&2; exit 2 ;;
esac
case "\${QEMU_SMP}" in
  ''|*[!0-9]*) echo "invalid smp: \${QEMU_SMP}" >&2; exit 2 ;;
esac

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

  if [ "${product}" != "x86_64_virt" ]; then
    cat >"${dest}" <<EOF
Write-Error "Windows launcher is not enabled for ${product} yet. Use x86_64_virt for Windows x86_64."
exit 1
EOF
    return
  fi

  cat >"${dest}" <<EOF
param(
  [Alias("r")][string]\$Resolution,
  [int]\$Width,
  [int]\$Height,
  [Alias("m")][string]\$Memory,
  [Alias("s")][int]\$Smp,
  [Alias("d")][string]\$Display,
  [switch]\$Headless,
  [Alias("c")][string]\$Connect,
  [int]\$HdcPort,
  [int]\$VncDisplay,
  [int]\$SerialPort,
  [Alias("a")][string]\$Accel,
  [Alias("q")][string]\$QemuPath,
  [Parameter(ValueFromRemainingArguments = \$true)][string[]]\$ExtraArgs
)

\$ErrorActionPreference = "Stop"

\$Root = Split-Path -Parent (Split-Path -Parent \$MyInvocation.MyCommand.Path)
\$Img = Join-Path \$Root "images"

\$DefaultSmp = ${default_smp}
\$DefaultMemory = "${default_mem}"
\$DefaultDisplay = "${default_display}"
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
if (\$PSBoundParameters.ContainsKey("Smp")) { \$env:QEMU_SMP = "\$Smp" }
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
if (\$Accel) { \$env:QEMU_ACCEL = \$Accel }
if (\$QemuPath) { \$env:QEMU_BIN = \$QemuPath }

\$Xres = if (\$env:QEMU_XRES) { \$env:QEMU_XRES } else { "\$DefaultXres" }
\$Yres = if (\$env:QEMU_YRES) { \$env:QEMU_YRES } else { "\$DefaultYres" }
\$SmpValue = if (\$env:QEMU_SMP) { \$env:QEMU_SMP } else { "\$DefaultSmp" }
\$MemoryValue = if (\$env:QEMU_MEMORY) { \$env:QEMU_MEMORY } else { "\$DefaultMemory" }
\$HdcHostPort = if (\$env:QEMU_HDC_HOST_PORT) { \$env:QEMU_HDC_HOST_PORT } else { "\$DefaultHdcPort" }
\$VncDisplayValue = if (\$env:QEMU_VNC_DISPLAY) { \$env:QEMU_VNC_DISPLAY } else { "\$DefaultVncDisplay" }
\$GpuDevice = "virtio-gpu-pci,xres=\$Xres,yres=\$Yres"

function Resolve-Qemu {
  if (\$env:QEMU_BIN) { return \$env:QEMU_BIN }
  if (\$env:QEMU_SYSTEM_X86_64) { return \$env:QEMU_SYSTEM_X86_64 }
  \$cmd = Get-Command "qemu-system-x86_64.exe" -ErrorAction SilentlyContinue
  if (\$cmd) { return \$cmd.Source }
  \$defaultPath = "C:\\Program Files\\qemu\\qemu-system-x86_64.exe"
  if (Test-Path \$defaultPath) { return \$defaultPath }
  throw "qemu-system-x86_64.exe not found. Install QEMU for Windows or set QEMU_BIN / QEMU_SYSTEM_X86_64."
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

\$KernelBootArgs = "oemmode=rd buildvariant=eng developer_mode=1 console=ttyS0,115200 sn=0023456789 init=/bin/init hardware=virt root=/dev/ram0 rw ip=dhcp ohos.boot.hardware=virt ohos.required_mount.system=/dev/block/vdb@/usr@ext4@ro,barrier=1@wait,required ohos.required_mount.vendor=/dev/block/vdc@/vendor@ext4@ro,barrier=1@wait,required ohos.required_mount.sys_prod=/dev/block/vdd@/sys_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.chip_prod=/dev/block/vde@/chip_prod@ext4@rw,barrier=1@wait,required ohos.required_mount.data=/dev/block/vdf@/data@f2fs@nosuid,nodev,noatime@wait,required,reservedsize=104857600"

\$ArgsList = @(
  "-machine", "q35",
  \$AccelArgs,
  "-cpu", "max",
  "-smp", "\$SmpValue",
  "-m", "\$MemoryValue",
  "-kernel", (Join-Path \$Img "bzImage"),
  "-initrd", (Join-Path \$Img "ramdisk.img"),
  \$DisplayArgs,
  "-device", "virtio-mouse-pci",
  "-device", "virtio-keyboard-pci",
  "-netdev", "user,id=net0,hostfwd=tcp::\${HdcHostPort}-:5555",
  "-device", "virtio-net-pci,netdev=net0",
  "-drive", ("if=none,file={0},format=raw,id=updater" -f (Join-Path \$Img "updater.img")),
  "-device", "virtio-blk-pci,drive=updater,serial=updater",
  "-drive", ("if=none,file={0},format=raw,id=system" -f (Join-Path \$Img "system.img")),
  "-device", "virtio-blk-pci,drive=system,serial=system",
  "-drive", ("if=none,file={0},format=raw,id=vendor" -f (Join-Path \$Img "vendor.img")),
  "-device", "virtio-blk-pci,drive=vendor,serial=vendor",
  "-drive", ("if=none,file={0},format=raw,id=sys_prod" -f (Join-Path \$Img "sys_prod.img")),
  "-device", "virtio-blk-pci,drive=sys_prod,serial=sys_prod",
  "-drive", ("if=none,file={0},format=raw,id=chip_prod" -f (Join-Path \$Img "chip_prod.img")),
  "-device", "virtio-blk-pci,drive=chip_prod,serial=chip_prod",
  "-drive", ("if=none,file={0},format=raw,id=userdata" -f (Join-Path \$Img "userdata.img")),
  "-device", "virtio-blk-pci,drive=userdata,serial=userdata",
  "-append", \$KernelBootArgs
)

if (\$env:QEMU_SERIAL_PORT) {
  \$ArgsList += @("-serial", "telnet:127.0.0.1:\$(\$env:QEMU_SERIAL_PORT),server,nowait")
  Write-Host "Serial telnet console: 127.0.0.1:\$(\$env:QEMU_SERIAL_PORT)"
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

  cat >"${package_dir}/README.md" <<EOF
# ${package_name}

This package contains an OpenHarmony standard-system QEMU image.

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
| \`-s, --smp N\` | \`QEMU_SMP\` | \`${default_smp}\` |
| \`-d, --display TYPE\` / \`--headless\` | \`QEMU_DISPLAY\` | \`${default_display}\` |
| \`-c, --connect host:port\` / \`--hdc-port\` | \`QEMU_HDC_HOST_PORT\` | \`5555\` |
| \`--vnc-display N\` | \`QEMU_VNC_DISPLAY\` | \`21\` (TCP 5921) |
| \`--serial-port PORT\` | \`QEMU_SERIAL_PORT\` | unset |
| \`-a, --accel MODE\` | \`QEMU_ACCEL\` | \`auto\` |
| \`-q, --qemu PATH\` | \`QEMU_BIN\` | product QEMU binary |
| \`-- ...\` | \`QEMU_EXTRA_ARGS\` | empty |

Examples:

\`\`\`bash
./launch/linux.sh -r 1280x720 -m 8G -s 8
./launch/linux.sh --width 1080 --height 1920 --display cocoa
./launch/linux.sh --headless --vnc-display 21 --serial-port 4444
QEMU_DISPLAY=none QEMU_HDC_HOST_PORT=5556 ./launch/linux.sh
\`\`\`

\`QEMU_DISPLAY=vnc\` exposes VNC on \`127.0.0.1:\$((5900 + QEMU_VNC_DISPLAY))\`.
\`QEMU_DISPLAY=none\` is recommended for CI/headless hosts. On Linux hosts without
\`DISPLAY\`/\`WAYLAND_DISPLAY\`, graphical modes auto-fallback to headless.
\`QEMU_ACCEL=auto|hvf|kvm|tcg\` (and \`whpx\` on Windows) selects acceleration;
\`auto\` probes host support and falls back to TCG when needed.
EOF

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
      "${LAUNCHER_QEMU_UNIX}"
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
      "${LAUNCHER_QEMU_UNIX}"
    cp "${launch_out}/linux.sh" "${launch_out}/macos.command"
    chmod +x "${launch_out}/macos.command"

    write_windows_ps1 \
      "${launch_out}/windows.ps1" \
      "${product}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}"
  elif [ "${product}" = "qemu-arm64-linux-min" ]; then
    write_unix_cli_wrapper \
      "${launch_out}/linux.sh" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" \
      "${LAUNCHER_QEMU_UNIX}"
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
QEMU_BIN="${QEMU_BIN:-qemu-system-aarch64}"
QEMU_EXTRA_ARGS="${QEMU_EXTRA_ARGS:-}"
exec "${QEMU_BIN}" \
  -M virt \
  -smp "${QEMU_SMP}" \
  -m "${QEMU_MEMORY}" \
  -nographic \
  -cpu cortex-a57 \
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
      "${LAUNCHER_DEFAULT_DISPLAY}"
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
      "${LAUNCHER_DEFAULT_DISPLAY}"
  fi

  write_package_launcher_readme \
    "${package_dir}" \
    "${package_name}" \
    "${product}" \
    "${standard_vpn}" \
    "${LAUNCHER_DEFAULT_SMP}" \
    "${LAUNCHER_DEFAULT_MEMORY}" \
    "${LAUNCHER_DEFAULT_DISPLAY}"
}

refresh_package_checksums() {
  local package_dir="$1"
  (
    cd "${package_dir}"
    find images launch -type f -print0 2>/dev/null | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
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

rewrite_package_launchers() {
  local package_dir="$1"
  local manifest="${package_dir}/manifest.json"
  local launch_out="${package_dir}/launch"
  local product
  local package_name
  local standard_vpn

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

  write_full_product_launchers \
    "${launch_out}" \
    "${product}" \
    "${package_dir}" \
    "${package_name}" \
    "${standard_vpn}" \
    ""

  # Refresh launcher metadata in manifest.json when python is available.
  if command -v python3 >/dev/null 2>&1; then
    launcher_defaults_for_product "${product}"
    python3 - "${manifest}" \
      "${LAUNCHER_DEFAULT_SMP}" \
      "${LAUNCHER_DEFAULT_MEMORY}" \
      "${LAUNCHER_DEFAULT_DISPLAY}" <<'PY'
import json, sys
path, smp, mem, display = sys.argv[1:5]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["display_default"] = display
data["launcher"] = {
    "resolution_default": "800x500",
    "smp_default": int(smp),
    "memory_default": mem,
    "cli": True,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
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
    "${REWRITE_ARM64_LAUNCHER}" 4 4096 qemu-system-aarch64
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

launcher_defaults_for_product "${PRODUCT}"
cat > "${PACKAGE_DIR}/manifest.json" <<EOF
{
  "product": "${PRODUCT}",
  "guest_arch": "${GUEST_ARCH}",
  "kernel": "${KERNEL_FILE}",
  "qemu_unix": "${QEMU_BIN_UNIX}",
  "qemu_windows": "${QEMU_BIN_WIN}",
  "display_default": "${DISPLAY_DEFAULT}",
  "network_default": "user",
  "launcher": {
    "resolution_default": "800x500",
    "smp_default": ${LAUNCHER_DEFAULT_SMP},
    "memory_default": "${LAUNCHER_DEFAULT_MEMORY}",
    "cli": true
  },
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

OFFICIAL_FOR_LAUNCH="${OFFICIAL_QEMU_RUN:-}"
write_full_product_launchers \
  "${LAUNCH_OUT}" \
  "${PRODUCT}" \
  "${PACKAGE_DIR}" \
  "${PACKAGE_NAME}" \
  "${STANDARD_VPN_VERIFIED}" \
  "${OFFICIAL_FOR_LAUNCH}"

chmod +x "${LAUNCH_OUT}/linux.sh" "${LAUNCH_OUT}/macos.command" 2>/dev/null || true
if [ -f "${LAUNCH_OUT}/qemu_run.sh" ]; then
  chmod +x "${LAUNCH_OUT}/qemu_run.sh"
fi

refresh_package_checksums "${PACKAGE_DIR}"

(
  cd "${OUTPUT_DIR}"
  tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
)

echo "${PACKAGE_DIR}"
