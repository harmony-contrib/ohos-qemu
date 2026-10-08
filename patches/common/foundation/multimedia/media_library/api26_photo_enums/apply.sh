#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    *) echo "unknown API26 photo enum argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
# A later exact overlay extends this helper and wrapper. Verify its complete
# files and the unchanged cover getter instead of reverse-checking stale hunks.
if python3 "${COMPONENT_DIR}/../api26_photo_search_enums/verify_source.py" \
    --source-root "${SOURCE_ROOT}" --require-patched >/dev/null 2>&1; then
  python3 "${COMPONENT_DIR}/../fusion_asset_type/verify_source.py" \
    --source-root "${SOURCE_ROOT}" --require-patched
  echo 'verified complete exact Photo/Fusion/source/search enum composition'
  exit 0
fi
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
git -C "${SOURCE_ROOT}" apply --check --reverse "${COMPONENT_DIR}/0001-register-public-photo-enums-and-normalize-cover-source.patch"
git -C "${SOURCE_ROOT}" apply --check --reverse "${COMPONENT_DIR}/0002-forward-public-cover-and-thumbnail-enums.patch"
