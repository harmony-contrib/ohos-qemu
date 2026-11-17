#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
for argument in "$@"; do
  if [ "${argument}" = --require-final ]; then
    exec python3 "${COMPONENT_DIR}/verify_source.py" "$@"
  fi
done
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
