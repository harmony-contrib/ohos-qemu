#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
# Only a complete real MainAbility provider can receive the native reminders.
python3 "${PATCH_ROOT}/common/applications/standard/calendardata/calendar_main/verify_source.py" "$@" --require-patched
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
