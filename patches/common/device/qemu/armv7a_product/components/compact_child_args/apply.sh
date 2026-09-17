#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ] || [ "$1" != --source-root ]; then
  echo "usage: apply.sh --source-root OHOS_ROOT" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../../../.." && pwd)"
bash "${PATCH_ROOT}/lib/apply_patch.sh" "$2" "${SCRIPT_DIR}/0001-use-utf8-for-armv7-child-arguments.patch"
