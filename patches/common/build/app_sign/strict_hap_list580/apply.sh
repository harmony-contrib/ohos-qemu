#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
patch_root="$(cd "${component_dir}/../../../.." && pwd)"
exec python3 "${patch_root}/lib/apply_exact_component.py" --component-dir "${component_dir}" "$@"
