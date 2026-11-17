#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
# Parse the fixed source CLI and reject unknown/partial/alias inputs before writes.
python3 "${COMPONENT_DIR}/verify_source.py" "$@" >/dev/null
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
