#!/usr/bin/env bash
set -euo pipefail
component_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 "$component_dir/upgrade_legacy.py" "$@"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
