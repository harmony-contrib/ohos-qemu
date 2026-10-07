#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_LIB="${COMPONENT_DIR}/../../../../../lib/apply_component_dir.sh"
python3 "${COMPONENT_DIR}/check.py" "$@"
bash "${PATCH_LIB}" "${COMPONENT_DIR}" "$@"
python3 "${COMPONENT_DIR}/check.py" "$@" --require-patched
