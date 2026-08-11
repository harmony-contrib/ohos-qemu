#!/usr/bin/env bash
set -euo pipefail

HDC="${HDC:-hdc}"
HDC_TARGET="${HDC_TARGET:-}"
HILOG_PATH="${HILOG_PATH:-}"
VPN_ADDRESS="${VPN_ADDRESS:-fdfe:dcba:9876::1}"
VPN_PREFIX_LENGTH="${VPN_PREFIX_LENGTH:-126}"
QEMU_IPV6_GATEWAY="${QEMU_IPV6_GATEWAY:-fec0::2}"

usage() {
  cat <<'EOF'
Usage: ci/standard-vpn/verify-paws-ipv6.sh [--target HDC_TARGET] [--hilog PATH]

Verifies a running Paws IPv6 VPN on an OpenHarmony QEMU guest. Start Paws
with ci/standard-vpn/ipv6-direct.yaml and approve the first-use VPN dialog
before running this command.

Environment overrides:
  HDC, HDC_TARGET, HILOG_PATH, VPN_ADDRESS, VPN_PREFIX_LENGTH,
  QEMU_IPV6_GATEWAY
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      HDC_TARGET="${2:?missing HDC target}"
      shift 2
      ;;
    --hilog)
      HILOG_PATH="${2:?missing hilog path}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v "${HDC}" >/dev/null 2>&1; then
  echo "Missing hdc command: ${HDC}" >&2
  exit 127
fi

hdc_cmd() {
  if [ -n "${HDC_TARGET}" ]; then
    "${HDC}" -t "${HDC_TARGET}" "$@"
  else
    "${HDC}" "$@"
  fi
}

require_match() {
  local content="$1"
  local pattern="$2"
  local description="$3"
  if ! grep -Eq "${pattern}" <<<"${content}"; then
    echo "Missing ${description}; expected /${pattern}/" >&2
    exit 1
  fi
}

version="$(hdc_cmd shell param get const.product.software.version 2>&1)"
interface="$(hdc_cmd shell ifconfig vpn-tun 2>&1)"
ipv6_addresses="$(hdc_cmd shell cat /proc/net/if_inet6 2>&1)"
vpn_state="$(hdc_cmd shell hidumper -s VPNManager 2>&1)"
processes="$(hdc_cmd shell ps -ef 2>&1)"

require_match "${version}" 'OpenHarmony' 'OpenHarmony version'
require_match "${interface}" "inet6 addr: ${VPN_ADDRESS}/${VPN_PREFIX_LENGTH} Scope: Global" \
  'global VPN IPv6 address'
require_match "${interface}" 'UP POINTOPOINT RUNNING' 'running TUN interface'
require_match "${ipv6_addresses}" '[[:space:]]vpn-tun$' 'vpn-tun entry in /proc/net/if_inet6'
require_match "${vpn_state}" 'interface: vpn-tun' 'VPNManager tunnel interface'
require_match "${vpn_state}" 'state: connected' 'connected VPNManager state'
require_match "${processes}" 'com\.richerfu\.paws:vpn' 'Paws VPN extension process'

if [ -n "${HILOG_PATH}" ]; then
  if [ ! -f "${HILOG_PATH}" ]; then
    echo "Hilog file not found: ${HILOG_PATH}" >&2
    exit 1
  fi
  logs="$(<"${HILOG_PATH}")"
  require_match "${logs}" "Add address:.*prefixLength\\[${VPN_PREFIX_LENGTH}\\]" \
    'VPN IPv6 address installation log'
  require_match "${logs}" 'Add Route:.*destination\[::/0\]' 'VPN IPv6 default route log'
  require_match "${logs}" 'created tun fd [0-9]+' 'Paws TUN creation log'
  require_match "${logs}" 'protected process network' 'Paws network protection log'
  require_match "${logs}" 'VPN started in [0-9]+ ms' 'Paws VPN startup completion log'
fi

ping_output="$(hdc_cmd shell ping6 -c 3 -W 2 "${QEMU_IPV6_GATEWAY}" 2>&1)"
require_match "${ping_output}" '3 packets transmitted, 3 received, 0% packet loss' \
  'QEMU IPv6 underlay connectivity'

printf '%s\n' "${version}"
printf '%s\n' "${interface}"
printf '%s\n' "${vpn_state}"
printf '%s\n' "${ping_output}"
echo "Paws IPv6 VPN verification passed."
