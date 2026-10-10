#!/usr/bin/env bash
# Repository-owned local runtime gate. Never starts a second package build.
set -euo pipefail
main() {
  local script_dir python cache_root environment_root
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cache_root="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
  environment_root="${QEMU_TEST_PYTHON_ENV:-${cache_root}/tools/qemu-runtime-validation-python}"
  if [ "$(uname -s)" = Darwin ]; then
    export LC_ALL=en_US.UTF-8 LC_CTYPE=en_US.UTF-8 LANG=en_US.UTF-8
  else
    export LC_ALL=C.UTF-8 LC_CTYPE=C.UTF-8 LANG=C.UTF-8
  fi
  python="${environment_root}/bin/python"
  if [ ! -x "${python}" ]; then
    [ ! -e "${environment_root}" ] || {
      echo 'incomplete validation Python environment; select a fresh QEMU_TEST_PYTHON_ENV' >&2; return 1;
    }
    mkdir -p "$(dirname "${environment_root}")"
    python3 -m venv "${environment_root}"
  fi
  "${python}" -m pip install --disable-pip-version-check \
    -r "${script_dir}/../ci/capability-audit/requirements-test.txt"
  exec "${python}" "${script_dir}/../ci/capability-audit/run_with_owned_hdc.py" "$@"
}
main "$@"
