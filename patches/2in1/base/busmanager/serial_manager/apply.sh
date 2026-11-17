#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${COMPONENT_DIR}/import_source.py" "$@"
exec python3 "${COMPONENT_DIR}/apply_stack.py" "$@"
