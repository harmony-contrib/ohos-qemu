#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The fixed API26 compiler/runtime and source preparation adaptations are
# shared with V8/SwiftShader. Apply them explicitly on a clean source tree;
# a previous V8 build must not be an implicit full-engine prerequisite.
bash "${COMPONENT_DIR}/../m144_v8_shared/apply.sh" "$@"
bash "${COMPONENT_DIR}/../m144_core_build/apply.sh" "$@"
bash "${COMPONENT_DIR}/../m144_angle_includes/apply.sh" "$@"
bash "${COMPONENT_DIR}/../m144_adapter_header_format/apply.sh" "$@"
bash "${COMPONENT_DIR}/../m144_webrtc_thread_id/apply.sh" "$@"
bash "${COMPONENT_DIR}/apply.sh" "$@"
bash "${COMPONENT_DIR}/../m144_private_contract/apply.sh" "$@"
