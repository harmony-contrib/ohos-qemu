#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    -h|--help) echo "usage: apply.sh --source-root ARKWEB_WORK_ROOT"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0001-remove-v8-presubmit-gate-from-build.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0002-define-disabled-arkweb-test-flag.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0003-fix-arkweb-prepare-helper-path.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0004-fix-components-assert-no-deps-list.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0005-enable-ohos-third-party-gn-targets.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0006-configure-swiftshader-llvm-for-ohos.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0007-configure-swiftshader-llvm-headers-for-ohos.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0008-scope-components-chrome-dependency-check.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0009-disable-components-browser-boundary-check-on-ohos.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0010-scope-components-browsertest-boundary-check.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0011-scope-disallowed-extension-list-to-non-ohos.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0012-use-api26-sdk-clang-resource-version.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0013-use-selected-clang-version-for-ohos-runtime.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0014-separate-m144-compiler-from-ohos-runtime.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0015-limit-hitrace-runtime-stats-to-ohos-toolchain.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0016-link-mainline-clang-against-ohos-runtime.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0017-use-openharmony-libcxx-abi-namespace.patch"
bash "${PATCH_ROOT}/lib/apply_patch.sh" \
  "${SOURCE_ROOT}" "${SCRIPT_DIR}/0018-match-openharmony-libcxx-abi-version.patch"
