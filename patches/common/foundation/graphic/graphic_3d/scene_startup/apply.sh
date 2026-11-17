#!/usr/bin/env bash
set -euo pipefail
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing source root}"; shift 2 ;;
    -h|--help) echo "usage: apply.sh --source-root ROOT"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
python3 "${SCRIPT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}"
bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
  "${SCRIPT_DIR}/0001-retry-real-scene-plugins-and-report-engine-init-failures.patch"
python3 "${SCRIPT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}" --require-patched
echo "Scene plugin loading, initialization failure propagation and queue lifetime configured"
