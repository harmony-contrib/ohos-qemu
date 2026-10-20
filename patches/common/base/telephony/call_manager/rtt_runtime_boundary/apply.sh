#!/usr/bin/env bash
set -euo pipefail
component="$(cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$component/apply_runtime.py" "$@"
