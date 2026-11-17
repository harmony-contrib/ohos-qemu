#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  apply.sh --source-root ROOT [--product PRODUCT ...] [--disable]

Enable (default) derives a current-tree-compatible QEMU phone profile from
productdefine/common/inherit/phone.json and adds it after rich.json for the
selected standard QEMU products. --disable removes that generated inherit.
USAGE
}

SOURCE_ROOT=
ACTION=enable
PRODUCTS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --product)
      PRODUCTS+=("${2:-}")
      shift 2
      ;;
    --disable)
      ACTION=disable
      shift
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
python3 "${SCRIPT_DIR}/apply.py" "${SOURCE_ROOT}" "${ACTION}" "${PRODUCTS[@]}"
