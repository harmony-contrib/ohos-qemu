#!/usr/bin/env bash
# Isolated host-tool fallback only. The pinned GN executable is unchanged.
set -euo pipefail
GN_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/qemu-x86_64-static -cpu max "${GN_DIRECTORY}/gn.pinned-executable" "$@"
