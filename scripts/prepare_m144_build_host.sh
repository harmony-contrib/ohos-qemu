#!/usr/bin/env bash
# Real Linux host tools/cache for every release stage; no SDK or source mutation.
set -euo pipefail
case "${M144_RELEASE_STAGE:-native}" in
  native|hap) skip_apt="${M144_CORE_SKIP_APT:-0}" ;;
  *) skip_apt="${M144_SKIP_APT:-0}" ;;
esac
if [ "${skip_apt}" != 1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates git git-lfs \
    python3 python3-pip python3-setuptools python3-dev curl wget xz-utils zip unzip \
    build-essential gcc-multilib g++-multilib pkg-config ninja-build bison flex \
    gperf perl file binutils jq openjdk-17-jdk-headless util-linux \
    libglib2.0-dev libnss3-dev libdbus-1-dev libatk1.0-dev libatk-bridge2.0-dev \
    libcups2-dev libx11-dev libxcomposite-dev libxdamage-dev libxext-dev \
    libxfixes-dev libxrandr-dev libgbm-dev libasound2-dev libpango1.0-dev \
    libdrm-dev libxkbcommon-dev
fi
for required_tool in git git-lfs python3 flock curl tar unzip zip c++ pkg-config java readelf; do
  command -v "${required_tool}" >/dev/null || { echo "missing M144 host tool: ${required_tool}" >&2; exit 1; }
done
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/prepare_m144_host_cache.py"
pkg-config --exists glib-2.0 gmodule-2.0 gobject-2.0 gthread-2.0 nss dbus-1
printf '#include <asm/errno.h>\n' | c++ -m32 -E -x c++ - >/dev/null
