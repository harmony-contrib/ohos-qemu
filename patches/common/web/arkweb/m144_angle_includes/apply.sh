#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    *) echo "unknown M144 ANGLE include argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
for patch_file in "${COMPONENT_DIR}"/[0-9][0-9][0-9][0-9]-*.patch; do
  git -C "${SOURCE_ROOT}" apply --check --reverse "${patch_file}"
done
