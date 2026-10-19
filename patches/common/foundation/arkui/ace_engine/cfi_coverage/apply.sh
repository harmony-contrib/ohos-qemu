#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
# Keep the old two-file component independent and enforce application order.
python3 "${COMPONENT_DIR}/verify_source.py" "$@" --check-prerequisites
python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
python3 "${COMPONENT_DIR}/verify_source.py" "$@" --require-patched
