#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    *) echo "unknown AVC EOS argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "usage: apply.sh --source-root ROOT" >&2; exit 2; }
python3 "${COMPONENT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}"
if python3 "${COMPONENT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}" \
    --require-surface-layout >/dev/null 2>&1; then
  echo "verified AVC EOS/input stack with complete surface layout overlay"
  exit 0
fi
python3 "${PATCH_ROOT}/lib/apply_component_stack.py" --component-dir "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
python3 "${COMPONENT_DIR}/verify_source.py" --source-root "${SOURCE_ROOT}" --require-patched
