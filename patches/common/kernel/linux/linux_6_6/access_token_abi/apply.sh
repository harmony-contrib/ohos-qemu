#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:?missing root}"; shift 2 ;;
    --product) shift 2 ;;
    *) echo "unknown AccessToken component argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
# The removed inline patch mutated only this header on Linux 6.6: its old
# function-table replacement never matched the actual switch dispatcher.
# Recover only that exact known cached header. Unrelated source edits remain
# untouched, and unknown drift fails in the numbered patch check below.
HEADER="${SOURCE_ROOT}/kernel/linux/linux-6.6/drivers/accesstokenid/access_tokenid.h"
HEADER_SHA="$(shasum -a 256 "${HEADER}" | awk '{print $1}')"
if [ "${HEADER_SHA}" = c958754a1075b26a28e07271b3968b06b036ad0036c69a05ccd87b9e8d7e1da9 ]; then
  git -C "${SOURCE_ROOT}" apply --check --reverse "${COMPONENT_DIR}/migration-old-header.patch"
  git -C "${SOURCE_ROOT}" apply --reverse "${COMPONENT_DIR}/migration-old-header.patch"
fi
DRIVER="${SOURCE_ROOT}/kernel/linux/linux-6.6/drivers/accesstokenid/access_tokenid.c"
if [ "$(shasum -a 256 "${DRIVER}" | awk '{print $1}')" = ec40a8d18c56f8872d30d94d013fd3ed543e11cf33c7faacb8eef70360808606 ]; then
  # Upgrade only the exact R6 root-only user-id candidate, preserving drift.
  git -C "${SOURCE_ROOT}" apply --check "${COMPONENT_DIR}/migration-userid-root-only.patch"
  git -C "${SOURCE_ROOT}" apply "${COMPONENT_DIR}/migration-userid-root-only.patch"
fi
if [ "${HEADER_SHA}" = 17990a5fd71940b2cd43179aeda009eaf06c046e13baa452193b6b9c83afe273 ] && \
   [ "$(shasum -a 256 "${DRIVER}" | awk '{print $1}')" = 0f8ec1a28b66d5c919cf6cf15cd7e2f8cacf4748d355d45803ced468d9bd94bd ]; then
  # Upgrade only the exact first bitmap candidate, never arbitrary user edits.
  git -C "${SOURCE_ROOT}" apply --check --reverse "${COMPONENT_DIR}/migration-bitmap-v1.patch"
  git -C "${SOURCE_ROOT}" apply --reverse "${COMPONENT_DIR}/migration-bitmap-v1.patch"
fi
bash "${PATCH_ROOT}/lib/apply_component_dir.sh" "${COMPONENT_DIR}" --source-root "${SOURCE_ROOT}"
# A cached marker alone must not hide a reverted/edited driver or dispatcher.
git -C "${SOURCE_ROOT}" apply --check --reverse "${COMPONENT_DIR}/0001-query-real-permission-bitmap-under-lock.patch"
