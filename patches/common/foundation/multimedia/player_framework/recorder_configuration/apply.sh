#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$component_dir/apply.py" "$@"
