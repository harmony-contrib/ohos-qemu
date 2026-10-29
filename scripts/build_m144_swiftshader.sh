#!/usr/bin/env bash
# Prepare the complete release graph and its explicit GN prerequisites.
set -euo pipefail
main() {
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ "$#" -gt 0 ] || { echo "specify arm, arm64 and/or x86_64" >&2; exit 2; }
  for arch in "$@"; do
    case "${arch}" in arm|arm64|x86_64) ;; *) echo 'unsupported dependency architecture' >&2; exit 2 ;; esac
  done
  M144_DEPENDENCY_ARCHES="$*" bash "${script_dir}/run_m144_release_build_docker.sh" swiftshader "$1"
}
main "$@"
