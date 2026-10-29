#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    *) echo "unknown API26 Bluetooth OPP enum argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
# The pinned OPP TU uses CRLF. Match only its line-ending/space variant.
git -C "${SOURCE_ROOT}" apply --check --reverse --ignore-space-change "${COMPONENT_DIR}/0001-register-opp-transfer-wire-enums.patch"
