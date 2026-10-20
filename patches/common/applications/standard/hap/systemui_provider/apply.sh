#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
exec python3 "${PATCH_ROOT}/lib/systemui_provider.py" --apply-hap "$@"
