#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$component_dir/apply_runtime.py" "$@"
