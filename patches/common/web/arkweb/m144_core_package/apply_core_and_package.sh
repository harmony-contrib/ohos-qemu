#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
bash "${PATCH_ROOT}/common/web/arkweb/m144_window_contract/apply_with_core_build.sh" "$@"
bash "${COMPONENT_DIR}/apply.sh" "$@"
