#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  apply.sh --source-root OHOS_ROOT

Create or refresh the experimental armv7a_virt full QEMU product in an
OpenHarmony checkout.
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
