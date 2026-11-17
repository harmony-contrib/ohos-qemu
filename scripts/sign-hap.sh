#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PREFIX="${OHOS_QEMU_PREFIX:-${HOME}/.ohos-qemu}"

find_signer() {
  if [ -n "${OHOS_HAP_SIGNER:-}" ]; then
    printf '%s\n' "${OHOS_HAP_SIGNER}"
    return
  fi
  for candidate in \
    "${PACKAGE_ROOT}/bin/hap-sign" \
    "${PACKAGE_ROOT}/bin/hap-sign.exe" \
    "${PREFIX}/bin/hap-sign" \
    "${PREFIX}/bin/hap-sign.exe"
  do
    if [ -x "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
  if command -v hap-sign >/dev/null 2>&1; then
    command -v hap-sign
    return
  fi
  if command -v hap-sign.exe >/dev/null 2>&1; then
    command -v hap-sign.exe
    return
  fi
  return 1
}

if ! signer="$(find_signer)"; then
  echo "hap-sign is not installed" >&2
  echo "run ${SCRIPT_DIR}/install-hap-signer.sh first" >&2
  exit 1
fi

for arg in "$@"; do
  if [ "${arg}" = "-h" ] || [ "${arg}" = "--help" ]; then
    "${signer}" sign --help
    cat <<'ENV_HELP'

Environment variables supported by sign-hap.sh (overridden by CLI options):
  OHOS_HAP_SIGNER                       Path to hap-sign binary
  OHOS_HAP_INPUT / HAP_SIGN_INPUT       Input unsigned HAP path
  OHOS_HAP_OUTPUT / HAP_SIGN_OUTPUT     Output signed HAP path (-o / --output)
  OHOS_HAP_BUNDLE_NAME / HAP_SIGN_BUNDLE_NAME
                                        Bundle name (--bundle-name)
  OHOS_HAP_DEVICE_ID / OHOS_QEMU_UDID / HAP_SIGN_DEVICE_ID
                                        Comma/space-separated device UDIDs (--device-id)
  OHOS_HAP_ACL / OHOS_HAP_ACLS / HAP_SIGN_ACLS
                                        Comma/space-separated profile ACLs (--acl)
  OHOS_HAP_RESTRICTED_PERMISSIONS / HAP_SIGN_RESTRICTED_PERMISSIONS
                                        Comma/space-separated restricted permissions (--restricted-permission)
  OHOS_HAP_APL / HAP_SIGN_APL           APL level (--apl)
  OHOS_HAP_APP_FEATURE / HAP_SIGN_APP_FEATURE
                                        App feature (--app-feature)
  OHOS_HAP_VALID_DAYS / HAP_SIGN_VALID_DAYS
                                        Profile validity days (--valid-days)
  OHOS_HAP_FORCE / HAP_SIGN_FORCE       Overwrite output file (1/true -> --force)
ENV_HELP
    exit 0
  fi
done

has_output=0
has_bundle_name=0
has_apl=0
has_app_feature=0
has_acl=0
has_restricted=0
has_device_id=0
has_valid_days=0
has_force=0
has_positional_input=0

cli_args=("$@")
i=0
while [ "${i}" -lt "${#cli_args[@]}" ]; do
  arg="${cli_args[${i}]}"
  case "${arg}" in
    -o|--output|--output=*)
      has_output=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --bundle-name|--bundle-name=*)
      has_bundle_name=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --apl|--apl=*)
      has_apl=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --app-feature|--app-feature=*)
      has_app_feature=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --acl|--acl=*)
      has_acl=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --restricted-permission|--restricted-permission=*)
      has_restricted=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --device-id|--device-id=*)
      has_device_id=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --valid-days|--valid-days=*)
      has_valid_days=1
      [[ "${arg}" != *=* ]] && i=$((i + 1))
      ;;
    --force)
      has_force=1
      ;;
    --)
      has_positional_input=1
      break
      ;;
    -*)
      ;;
    *)
      has_positional_input=1
      ;;
  esac
  i=$((i + 1))
done

env_args=()
env_output="${OHOS_HAP_OUTPUT:-${HAP_SIGN_OUTPUT:-}}"
env_bundle="${OHOS_HAP_BUNDLE_NAME:-${HAP_SIGN_BUNDLE_NAME:-}}"
env_apl="${OHOS_HAP_APL:-${HAP_SIGN_APL:-}}"
env_feature="${OHOS_HAP_APP_FEATURE:-${HAP_SIGN_APP_FEATURE:-}}"
env_acls="${OHOS_HAP_ACLS:-${OHOS_HAP_ACL:-${HAP_SIGN_ACLS:-}}}"
env_restricted="${OHOS_HAP_RESTRICTED_PERMISSIONS:-${OHOS_HAP_RESTRICTED_PERMISSION:-${HAP_SIGN_RESTRICTED_PERMISSIONS:-}}}"
env_devices="${OHOS_HAP_DEVICE_ID:-${OHOS_QEMU_UDID:-${HAP_SIGN_DEVICE_ID:-}}}"
env_valid_days="${OHOS_HAP_VALID_DAYS:-${HAP_SIGN_VALID_DAYS:-}}"
env_force="${OHOS_HAP_FORCE:-${HAP_SIGN_FORCE:-0}}"
env_input="${OHOS_HAP_INPUT:-${HAP_SIGN_INPUT:-}}"

[ "${has_output}" = 0 ] && [ -n "${env_output}" ] && env_args+=(--output "${env_output}")
[ "${has_bundle_name}" = 0 ] && [ -n "${env_bundle}" ] && env_args+=(--bundle-name "${env_bundle}")
[ "${has_apl}" = 0 ] && [ -n "${env_apl}" ] && env_args+=(--apl "${env_apl}")
[ "${has_app_feature}" = 0 ] && [ -n "${env_feature}" ] && env_args+=(--app-feature "${env_feature}")
[ "${has_valid_days}" = 0 ] && [ -n "${env_valid_days}" ] && env_args+=(--valid-days "${env_valid_days}")

if [ "${has_acl}" = 0 ] && [ -n "${env_acls}" ]; then
  for item in ${env_acls//,/ }; do
    [ -n "${item}" ] && env_args+=(--acl "${item}")
  done
fi
if [ "${has_restricted}" = 0 ] && [ -n "${env_restricted}" ]; then
  for item in ${env_restricted//,/ }; do
    [ -n "${item}" ] && env_args+=(--restricted-permission "${item}")
  done
fi
if [ "${has_device_id}" = 0 ] && [ -n "${env_devices}" ]; then
  for item in ${env_devices//,/ }; do
    [ -n "${item}" ] && env_args+=(--device-id "${item}")
  done
fi
if [ "${has_force}" = 0 ]; then
  case "$(printf '%s' "${env_force}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) env_args+=(--force) ;;
  esac
fi
if [ "${has_positional_input}" = 0 ] && [ -n "${env_input}" ]; then
  env_args+=("${env_input}")
fi

if [ "${#env_args[@]}" -gt 0 ]; then
  exec "${signer}" sign "${env_args[@]}" "$@"
else
  exec "${signer}" sign "$@"
fi
