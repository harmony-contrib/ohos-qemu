#!/usr/bin/env bash
# No host seed or previous master build is required.
set -euo pipefail
main() {
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ "$#" -gt 0 ] || { echo "usage: build_m144_v8.sh arm|arm64|x86_64" >&2; exit 2; }
  for arch in "$@"; do
    case "${arch}" in arm|arm64|x86_64) ;; *) echo 'unsupported V8 architecture' >&2; exit 2 ;; esac
  done
  M144_V8_ARCHES="$*" bash "${script_dir}/run_m144_release_build_docker.sh" v8 "$1"
}
main "$@"
