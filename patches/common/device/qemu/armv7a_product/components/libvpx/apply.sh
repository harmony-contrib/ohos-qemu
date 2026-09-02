#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../../.." && pwd)"
exec bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" "$@"
