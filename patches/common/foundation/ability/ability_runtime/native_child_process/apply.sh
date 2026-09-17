#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing source root}"; shift 2 ;;
    -h|--help) echo "usage: apply.sh --source-root ROOT"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
for patch_file in \
  0001-share-child-process-args-across-dsos.patch \
  0002-budget-child-process-parameter-parcels.patch; do
  bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" "${SCRIPT_DIR}/${patch_file}"
done

python3 - "${SCRIPT_DIR}" "${SOURCE_ROOT}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

component, source = map(Path, sys.argv[1:])
patches = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(component.glob('*.patch'))
}
(source / '.ohos-qemu-native-child-process.json').write_text(
    json.dumps({'schema_version': 1, 'patches': patches}, indent=2) + '\n'
)
PY

echo "Native child-process shared arguments and 150 KiB transport configured"
