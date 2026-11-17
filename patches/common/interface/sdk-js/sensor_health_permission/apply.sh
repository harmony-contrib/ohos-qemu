#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
args=("$@")
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" "${args[@]}"
python3 "${COMPONENT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}"
