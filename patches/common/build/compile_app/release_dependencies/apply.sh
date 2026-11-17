#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: apply.sh --source-root ROOT" >&2
}

SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
if [ -z "${SOURCE_ROOT}" ]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0001-skip-dev-only-install-for-release-haps.patch"

echo "release HAP dependency handling configured"
