#!/usr/bin/env bash
# Apply one unified diff to an OpenHarmony checkout, with a strict idempotence
# check. Callers keep one patch file per component so upstream drift is easy to
# diagnose and review.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: apply_patch.sh OHOS_ROOT PATCH_FILE" >&2
  exit 2
fi

OHOS_ROOT="$1"
PATCH_FILE="$2"

if [ ! -d "${OHOS_ROOT}" ]; then
  echo "OpenHarmony root not found: ${OHOS_ROOT}" >&2
  exit 1
fi
if [ ! -f "${PATCH_FILE}" ]; then
  echo "component patch not found: ${PATCH_FILE}" >&2
  exit 1
fi

PATCH_ID="$(python3 - "${PATCH_FILE}" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
MARKER_DIR="${OHOS_ROOT}/.ohos-qemu-patches"
MARKER_FILE="${MARKER_DIR}/${PATCH_ID}.applied"
if [ -f "${MARKER_FILE}" ]; then
  echo "component patch already applied: ${PATCH_FILE}"
  exit 0
fi

if git -C "${OHOS_ROOT}" apply --check "${PATCH_FILE}" >/dev/null 2>&1; then
  git -C "${OHOS_ROOT}" apply --whitespace=nowarn "${PATCH_FILE}"
  mkdir -p "${MARKER_DIR}"
  printf '%s\n' "${PATCH_FILE}" > "${MARKER_FILE}"
  echo "applied component patch: ${PATCH_FILE}"
elif git -C "${OHOS_ROOT}" apply --check --ignore-space-change \
  "${PATCH_FILE}" >/dev/null 2>&1; then
  git -C "${OHOS_ROOT}" apply --ignore-space-change --whitespace=nowarn \
    "${PATCH_FILE}"
  mkdir -p "${MARKER_DIR}"
  printf '%s\n' "${PATCH_FILE}" > "${MARKER_FILE}"
  echo "applied component patch (line-ending tolerant): ${PATCH_FILE}"
elif git -C "${OHOS_ROOT}" apply --check --reverse \
  "${PATCH_FILE}" >/dev/null 2>&1 || \
  git -C "${OHOS_ROOT}" apply --check --reverse --ignore-space-change \
  "${PATCH_FILE}" >/dev/null 2>&1; then
  mkdir -p "${MARKER_DIR}"
  printf '%s\n' "${PATCH_FILE}" > "${MARKER_FILE}"
  echo "component patch already applied: ${PATCH_FILE}"
else
  echo "component patch does not apply cleanly and is not already applied: ${PATCH_FILE}" >&2
  git -C "${OHOS_ROOT}" apply --check "${PATCH_FILE}" >&2 || true
  exit 1
fi
