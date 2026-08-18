#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  apply.sh --source-root OHOS_ROOT

Patch OpenHarmony's multimodal input service so QEMU absolute pointer events
are mapped to the current guest display dimensions instead of being treated as
relative mouse deltas. The operation is idempotent.
USAGE
}

SOURCE_ROOT=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${SOURCE_ROOT}" ]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/apply.py" "${SOURCE_ROOT}"
