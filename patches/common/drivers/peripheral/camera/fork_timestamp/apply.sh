#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${COMPONENT_DIR}/../../../../../lib/apply_exact_component.py" \
  --component-dir "${COMPONENT_DIR}" "$@"
