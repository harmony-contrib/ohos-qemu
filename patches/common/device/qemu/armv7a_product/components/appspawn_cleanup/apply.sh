#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ] || [ "$1" != --source-root ]; then
  echo "usage: apply.sh --source-root OHOS_ROOT" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../../../.." && pwd)"
for patch_file in \
  0001-avoid-armv7-native-spawn-cleanup-log-crash.patch \
  0002-skip-native-spawn-lock-reference-cleanup.patch; do
  bash "${PATCH_ROOT}/lib/apply_patch.sh" "$2" "${SCRIPT_DIR}/${patch_file}"
done
