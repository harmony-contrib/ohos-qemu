#!/usr/bin/env bash
# Apply every numbered unified diff owned by one component directory.
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: apply_component_dir.sh COMPONENT_DIR --source-root ROOT [--product PRODUCT ...]" >&2
  exit 2
fi

COMPONENT_DIR="$1"
shift
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --product) shift 2 ;;
    -h|--help) exit 0 ;;
    *) echo "unknown component argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "${SOURCE_ROOT}" ]; then
  echo "--source-root is required" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
shopt -s nullglob
PATCH_FILES=("${COMPONENT_DIR}"/[0-9][0-9][0-9][0-9]-*.patch)
if [ "${#PATCH_FILES[@]}" -eq 0 ]; then
  echo "component has no numbered patch files: ${COMPONENT_DIR}" >&2
  exit 1
fi
for patch_file in "${PATCH_FILES[@]}"; do
  bash "${SCRIPT_DIR}/apply_patch.sh" "${SOURCE_ROOT}" "${patch_file}"
done
