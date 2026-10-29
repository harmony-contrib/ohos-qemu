#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "$0")" && pwd)"
python3 "$component_dir/verify_source.py" "$@"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
