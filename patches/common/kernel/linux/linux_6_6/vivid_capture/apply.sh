#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${COMPONENT_DIR}/check.py" "$@"
bash "${COMPONENT_DIR}/../../../../../lib/apply_component_dir.sh" "${COMPONENT_DIR}" "$@"
python3 "${COMPONENT_DIR}/check.py" "$@" --require-patched
