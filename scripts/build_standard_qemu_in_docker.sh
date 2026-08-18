#!/usr/bin/env bash
set -euo pipefail

# Ruby-based Ark compiler generators inherit the process locale. Ubuntu's
# empty/POSIX locale makes Ruby treat UTF-8 source as US-ASCII.
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

usage() {
  cat <<'USAGE'
Usage:
  build_standard_qemu_in_docker.sh [armv7a_virt] [arm64_virt] [x86_64_virt]

Default products:
  arm64_virt x86_64_virt

Environment:
  CACHE_ROOT          Persistent mount root, default: /Volumes/PSSD/qemu
  OHOS_ROOT           OpenHarmony checkout, default: $CACHE_ROOT/openharmony
  PACKAGE_ROOT        Package output dir, default: $CACHE_ROOT/packages
  CONTAINER_HOME      Persistent HOME, default: $CACHE_ROOT/home
  OHOS_BRANCH         Manifest branch/tag, default: master
  MANIFEST_URL        Manifest repo, default: https://github.com/openharmony/manifest.git
  MANIFEST_GROUPS     Repo groups, default includes standard/full system groups
  REPO_URL            Repo tool mirror, default:
                       https://github.com/GerritCodeReview/git-repo.git
  REPO_LAUNCHER_URL   Repo launcher, default:
                       https://raw.githubusercontent.com/GerritCodeReview/git-repo/main/repo
  REPO_JOBS           repo sync jobs, default: 8
  REPO_CHECKOUT_JOBS  repo checkout jobs, default: 1
  REPO_SYNC_RETRIES   repo sync retry attempts, default: 3
  BUILD_JOBS          build jobs, default: nproc
  KERNEL_BUILD_JOBS   nested kernel make jobs, default: BUILD_JOBS
  CCACHE_MAXSIZE      ccache size limit, default: 100G
  CCACHE_DIR          ccache directory, default: $CACHE_ROOT/ccache
  QEMU_CCACHE_ON_OUT_VOLUME
                      Put ccache and its temp files under out/.ccache. Use 1
                      when out/ is a native Linux volume, default: 0.
  GIT_USER_NAME       Global git user.name, default: richerfu
  GIT_USER_EMAIL      Global git user.email, default: southorange0929@foxmail.com
  NPM_REGISTRY        npm registry, default: https://repo.huaweicloud.com/repository/npm/
  PREBUILTS_RETRY     Retry prebuilts_download.sh after cleaning JS deps, default: 1
  PREBUILTS_CLEAN     Clean JS deps before prebuilts_download.sh, default: 0
  CLEAN_KERNEL_OBJ    Remove out/KERNEL_OBJ before each product build, default: 0
  NO_PREBUILT_SDK     Pass --no-prebuilt-sdk=true to build.sh, default: 0
  BUILD_ONLY_LOAD     Pass --build-only-load=true to build.sh, default: 0
  SKIP_APT            Skip apt dependency installation, default: 0
  SKIP_REPO_SYNC      Reuse existing checkout without repo sync, default: 0
  SKIP_PREBUILTS      Reuse existing prebuilts, default: 0
  SKIP_GIT_LFS        Skip git lfs pull, default: 0
  ALLOW_NON_DOCKER    Allow an isolated Ubuntu 22.04 VM instead of Docker,
                      default: 0
  GIT_LFS_PATHS       Space-separated paths to fetch with Git LFS, default:
                       applications/standard/hap base/web/webview
                       foundation/arkui/ace_engine third_party/icu
                       third_party/libphonenumber
  QEMU_FIX_ACCESS_TOKENID_ABI
                       Backport access_tokenid ABI used by current userspace, default: 1
  QEMU_FIX_SYSTEM_COMPAT_SYMLINKS
                       Map ramdisk /system to /usr/system, add
                       /bin/init -> /system/bin/init, and add
                       /chipset -> /vendor for QEMU, default: 1
  QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION
                       Avoid libselinux/VERSION shadowing libc++ <version>
                       when the checkout is mounted from a case-insensitive
                       host filesystem, default: 1
  QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN
                       Keep XMP Endian.h out of public system-header lookup
                       and suppress private path-case diagnostics on a
                       case-insensitive host filesystem, default: 1
  QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK
                       Restore uniquely named iptables match/target sources
                       and combined headers when upstream case-distinct files
                       alias each other on a case-insensitive host filesystem,
                       default: 1
  QEMU_FIX_MINDSPORE_NON_ARM_HWCAP
                       Keep MindSpore's ARM-only asm/hwcap.h include out of
                       x86_64 OHOS builds, default: 1
  QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY
                       Copy ArkGuard node_modules launchers as regular files
                       when staging across shared filesystems, default: 1
  QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR
                       Serialize Arkoala npm install/code generation because
                       it writes node_modules in the shared source tree,
                       default: 1
  QEMU_FIX_VIRTIOFS_KERNEL_COPY
                       Copy the kernel worktree without dereferencing the
                       repo-tool .git symlink on shared filesystems,
                       default: 1
  QEMU_ABSOLUTE_POINTER_OVERLAY
                       Map virtio-tablet absolute events to the active guest
                       display dimensions, default: 1
  ARMV7A_FULL_OVERLAY Apply experimental armv7a_virt full overlay, default: 1
  STANDARD_VPN_OVERLAY
                       Enable and validate the standard VpnExtension stack,
                       default: 1
  QEMU_2IN1_FULL_OVERLAY
                       For DEVICE_TYPE=2in1, add the source component/feature
                       profile derived from productdefine 2in1.json. Values:
                       auto (default), 1, or 0. A value of 0 produces only a
                       parameter-level device type and is not a full profile.
  QEMU_PHONE_FULL_OVERLAY
                       For DEVICE_TYPE=phone, add the source component/feature
                       profile derived from productdefine phone.json. Values:
                       auto (default), 1, or 0.
  PRUNE_PRODUCT_OUT_AFTER_PACKAGE
                       Remove out/<product> after its verified package is
                       archived. Useful for six-package matrix builds on a
                       space-constrained Docker disk, default: 0.
  DEVICE_TYPE         Pass --device-type to build.sh and packaging
                       (default|phone|tablet|2in1|...), default: empty
                       (OpenHarmony default remains "default"). When set to
                       e.g. 2in1, packaged names gain a -2in1 suffix.

Build environment:
  This script is intended to run inside a Docker container based on
  ubuntu:22.04. It refuses other environments before touching the OpenHarmony
  checkout.

This script keeps OpenHarmony changes narrow and repeatable: full QEMU products
keep SELinux, seccomp, screen, and critical-service behavior enabled by default.
The default source-side changes are limited to the QEMU rootfs /system
compatibility path and the access_tokenid kernel ABI that current OpenHarmony
userspace expects from the QEMU kernels.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGER="${SCRIPT_DIR}/package_standard_qemu.sh"
ARMV7A_OVERLAY="${SCRIPT_DIR}/../overlays/armv7a_virt_full/apply.sh"
VPN_OVERLAY="${SCRIPT_DIR}/../overlays/standard_qemu_vpn/apply.sh"
QEMU_2IN1_OVERLAY="${SCRIPT_DIR}/../overlays/qemu_2in1_full/apply.sh"
QEMU_PHONE_OVERLAY="${SCRIPT_DIR}/../overlays/qemu_phone_full/apply.sh"
QEMU_ABSOLUTE_POINTER_OVERLAY_SCRIPT="${SCRIPT_DIR}/../overlays/qemu_absolute_pointer/apply.sh"

if [ ! -x "${PACKAGER}" ]; then
  echo "missing executable packager: ${PACKAGER}" >&2
  exit 1
fi

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
OHOS_ROOT="${OHOS_ROOT:-${CACHE_ROOT}/openharmony}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages}"
CONTAINER_HOME="${CONTAINER_HOME:-${CACHE_ROOT}/home}"
OHOS_BRANCH="${OHOS_BRANCH:-master}"
MANIFEST_URL="${MANIFEST_URL:-https://github.com/openharmony/manifest.git}"
MANIFEST_GROUPS="${MANIFEST_GROUPS:-default,ohos:mini,ohos:small,ohos:standard,ohos:system,ohos:chipset}"
REPO_URL="${REPO_URL:-https://github.com/GerritCodeReview/git-repo.git}"
REPO_LAUNCHER_URL="${REPO_LAUNCHER_URL:-https://raw.githubusercontent.com/GerritCodeReview/git-repo/main/repo}"
REPO_NO_BUNDLE="${REPO_NO_BUNDLE:-1}"
REPO_NO_TAGS="${REPO_NO_TAGS:-0}"
REPO_FORCE_SYNC="${REPO_FORCE_SYNC:-1}"
REPO_JOBS="${REPO_JOBS:-8}"
REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS:-1}"
REPO_SYNC_RETRIES="${REPO_SYNC_RETRIES:-3}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS:-${BUILD_JOBS}}"
CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-100G}"
CCACHE_DIR="${CCACHE_DIR:-${CACHE_ROOT}/ccache}"
GIT_USER_NAME="${GIT_USER_NAME:-richerfu}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-southorange0929@foxmail.com}"
NPM_REGISTRY="${NPM_REGISTRY:-https://repo.huaweicloud.com/repository/npm/}"
PREBUILTS_RETRY="${PREBUILTS_RETRY:-1}"
PREBUILTS_CLEAN="${PREBUILTS_CLEAN:-0}"
CLEAN_KERNEL_OBJ="${CLEAN_KERNEL_OBJ:-0}"
NO_PREBUILT_SDK="${NO_PREBUILT_SDK:-0}"
BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD:-0}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_REPO_SYNC="${SKIP_REPO_SYNC:-0}"
SKIP_PREBUILTS="${SKIP_PREBUILTS:-0}"
SKIP_GIT_LFS="${SKIP_GIT_LFS:-0}"
ALLOW_NON_DOCKER="${ALLOW_NON_DOCKER:-0}"
GIT_LFS_PATHS="${GIT_LFS_PATHS:-applications/standard/hap base/web/webview foundation/arkui/ace_engine third_party/icu third_party/libphonenumber}"
QEMU_FIX_ACCESS_TOKENID_ABI="${QEMU_FIX_ACCESS_TOKENID_ABI:-${QEMU_FIX_ACCESS_TOKENID_SPM:-1}}"
QEMU_FIX_SYSTEM_COMPAT_SYMLINKS="${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS:-1}"
QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION="${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION:-1}"
QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN="${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN:-1}"
QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK="${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK:-1}"
QEMU_FIX_MINDSPORE_NON_ARM_HWCAP="${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP:-1}"
QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY="${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY:-1}"
QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR="${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR:-1}"
QEMU_FIX_VIRTIOFS_KERNEL_COPY="${QEMU_FIX_VIRTIOFS_KERNEL_COPY:-1}"
QEMU_ABSOLUTE_POINTER_OVERLAY="${QEMU_ABSOLUTE_POINTER_OVERLAY:-1}"
QEMU_CCACHE_ON_OUT_VOLUME="${QEMU_CCACHE_ON_OUT_VOLUME:-0}"
ARMV7A_FULL_OVERLAY="${ARMV7A_FULL_OVERLAY:-1}"
STANDARD_VPN_OVERLAY="${STANDARD_VPN_OVERLAY:-1}"
QEMU_2IN1_FULL_OVERLAY="${QEMU_2IN1_FULL_OVERLAY:-auto}"
QEMU_PHONE_FULL_OVERLAY="${QEMU_PHONE_FULL_OVERLAY:-auto}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-0}"
DEVICE_TYPE="${DEVICE_TYPE:-}"
DEVICE_TYPE_BUILD_PROFILE="${DEVICE_TYPE_BUILD_PROFILE:-}"
PRODUCTS=("$@")

if [ "${#PRODUCTS[@]}" -eq 0 ]; then
  PRODUCTS=(arm64_virt x86_64_virt)
fi

for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt|arm64_virt|x86_64_virt) ;;
    *)
      echo "unsupported product for this no-patch build script: ${product}" >&2
      exit 2
      ;;
  esac
done

if [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" != "0" ] && \
   [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" != "1" ]; then
  echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE must be 0 or 1" >&2
  exit 2
fi

require_docker_ubuntu_2204() {
  if [ "$(uname -s)" != "Linux" ]; then
    echo "this script must run inside Docker on Ubuntu 22.04" >&2
    exit 1
  fi
  if [ ! -r /etc/os-release ]; then
    echo "missing /etc/os-release; expected Docker image ubuntu:22.04" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_ID:-}" != "22.04" ]; then
    echo "unsupported build OS: ${PRETTY_NAME:-unknown}; expected ubuntu:22.04" >&2
    exit 1
  fi
  if [ ! -f /.dockerenv ] &&
     ! grep -qaE '/(docker|containerd|kubepods)(/|$)' /proc/1/cgroup 2>/dev/null &&
     [ "${ALLOW_NON_DOCKER}" != "1" ]; then
    echo "this build must run inside Docker, not directly on the host" >&2
    exit 1
  fi
  if [ ! -f /.dockerenv ] &&
     ! grep -qaE '/(docker|containerd|kubepods)(/|$)' /proc/1/cgroup 2>/dev/null; then
    echo "running in an explicitly allowed isolated Ubuntu 22.04 VM"
  fi
}

require_docker_ubuntu_2204

install_deps() {
  if [ "${SKIP_APT}" = "1" ]; then
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found; set SKIP_APT=1 if dependencies are already installed" >&2
    return
  fi
  if [ "$(id -u)" != "0" ]; then
    echo "not root; skip apt dependency installation" >&2
    return
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update

  # Host-arch package set. x86 multilib packages only exist on amd64 images.
  local host_arch
  host_arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  local -a apt_packages=(
    autoconf
    automake
    bc
    bison
    build-essential
    ca-certificates
    ccache
    cmake
    cpio
    curl
    default-jdk
    dosfstools
    e2fsprogs
    file
    flex
    g++
    gcc
    gcc-arm-none-eabi
    genext2fs
    git
    git-lfs
    gettext
    gperf
    libelf-dev
    libfl-dev
    libgmp-dev
    libmpc-dev
    libmpfr-dev
    libncurses5
    libncurses5-dev
    libncursesw5-dev
    libssl-dev
    libxml2-utils
    libtool
    make
    mtd-utils
    mtools
    ninja-build
    openssh-client
    openssl
    pkg-config
    python-is-python3
    python3
    python3-pip
    python3-setuptools
    python3-venv
    rsync
    ruby
    scons
    unzip
    u-boot-tools
    wget
    zip
    zlib1g-dev
  )
  case "${host_arch}" in
    amd64|x86_64|i386)
      apt_packages+=(
        lib32stdc++6
        lib32z1
        libc6-dev-i386
      )
      ;;
    *)
      echo "host architecture ${host_arch}: skipping x86 multilib apt packages"
      ;;
  esac

  apt-get install -y --no-install-recommends "${apt_packages[@]}"

  command -v git >/dev/null
  command -v ssh >/dev/null
  if [ ! -f /usr/include/FlexLexer.h ]; then
    echo "missing /usr/include/FlexLexer.h; install libfl-dev in the Docker image" >&2
    exit 1
  fi

  git lfs install --system >/dev/null 2>&1 || true
}

verify_armv7_kernel_host_deps() {
  local product
  local needs_armv7=0
  for product in "${PRODUCTS[@]}"; do
    if [ "${product}" = "armv7a_virt" ]; then
      needs_armv7=1
      break
    fi
  done
  if [ "${needs_armv7}" != "1" ]; then
    return
  fi

  # Linux 6.6 enables an ARM GCC host plugin whose GCC-provided headers
  # include <gmp.h>.  Most OHOS targets do not exercise this path, so a stale
  # dependency image can otherwise fail hours into an armv7 build.
  if ! printf '#include <gmp.h>\n' | c++ -E -x c++ - >/dev/null 2>&1; then
    echo "armv7a_virt kernel build requires the host GMP header (libgmp-dev)" >&2
    echo "rerun with SKIP_APT=0 or refresh the Docker dependency image" >&2
    exit 1
  fi
}

ensure_python_module() {
  local python_bin="$1"
  local module="$2"
  local package="$3"
  if ! command -v "${python_bin}" >/dev/null 2>&1 && [ ! -x "${python_bin}" ]; then
    return
  fi
  # Skip host-prebuilt interpreters that cannot actually execute on this
  # container (e.g. linux-x86 python on a pure arm64 image without multiarch).
  if ! "${python_bin}" -c 'import sys' >/dev/null 2>&1; then
    echo "skip unusable python interpreter: ${python_bin}"
    return
  fi
  if "${python_bin}" - "${module}" <<'PY' >/dev/null 2>&1
import importlib
import sys
importlib.import_module(sys.argv[1])
PY
  then
    return
  fi

  echo "install missing python module for ${python_bin}: ${package}"
  local pip_scope_args=()
  if [ "$(id -u)" != "0" ]; then
    pip_scope_args+=(--user)
  fi
  if ! "${python_bin}" -m pip install \
    "${pip_scope_args[@]}" \
    --trusted-host repo.huaweicloud.com \
    -i https://repo.huaweicloud.com/repository/pypi/simple \
    "${package}"; then
    "${python_bin}" -m pip install \
      "${pip_scope_args[@]}" \
      --break-system-packages \
      --trusted-host repo.huaweicloud.com \
      -i https://repo.huaweicloud.com/repository/pypi/simple \
      "${package}"
  fi
}

ensure_python_modules() {
  ensure_python_module python3 typing_extensions "typing_extensions>=4.12.2"
  ensure_python_module python3 json5 json5
  ensure_python_module python3 yaml PyYAML
  ensure_python_module python3 mesonbuild "meson>=1.1,<2"
  ensure_python_module python3 mako "mako>=0.8"

  local python_bin
  for python_bin in \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/current/bin/python3" \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/3.12.10/bin/python3"; do
    if [ -x "${python_bin}" ]; then
      ensure_python_module "${python_bin}" typing_extensions "typing_extensions>=4.12.2"
      ensure_python_module "${python_bin}" json5 json5
      ensure_python_module "${python_bin}" yaml PyYAML
      ensure_python_module "${python_bin}" mako "mako>=0.8"
    fi
  done
}

raise_nofile_limit() {
  local wanted="${NOFILE_LIMIT:-1048576}"
  local current
  current="$(ulimit -n)"
  if [ "${current}" != "unlimited" ] && [ "${current}" -lt "${wanted}" ]; then
    ulimit -n "${wanted}" >/dev/null 2>&1 || true
  fi
}

configure_user_tools() {
  mkdir -p "${CONTAINER_HOME}" "${CACHE_ROOT}/npm-cache" "${CACHE_ROOT}/logs"
  export HOME="${CONTAINER_HOME}"
  export PATH="${CONTAINER_HOME}/.local/bin:${PATH}"
  export npm_config_cache="${CACHE_ROOT}/npm-cache"
  export NPM_CONFIG_CACHE="${CACHE_ROOT}/npm-cache"
  export NPM_CONFIG_REGISTRY="${NPM_REGISTRY}"
  export NPM_CONFIG_FETCH_RETRIES="${NPM_CONFIG_FETCH_RETRIES:-10}"
  export NPM_CONFIG_FETCH_RETRY_MINTIMEOUT="${NPM_CONFIG_FETCH_RETRY_MINTIMEOUT:-20000}"
  export NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT="${NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT:-120000}"
  export NPM_CONFIG_FETCH_TIMEOUT="${NPM_CONFIG_FETCH_TIMEOUT:-600000}"
  export NPM_CONFIG_PROGRESS=false
  export NPM_CONFIG_AUDIT=false
  export NPM_CONFIG_FUND=false

  {
    echo "registry=${NPM_REGISTRY}"
    echo "cache=${CACHE_ROOT}/npm-cache"
    echo "fetch-retries=${NPM_CONFIG_FETCH_RETRIES}"
    echo "fetch-retry-mintimeout=${NPM_CONFIG_FETCH_RETRY_MINTIMEOUT}"
    echo "fetch-retry-maxtimeout=${NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT}"
    echo "fetch-timeout=${NPM_CONFIG_FETCH_TIMEOUT}"
    echo "progress=false"
    echo "audit=false"
    echo "fund=false"
    if [ -n "${HTTP_PROXY:-${http_proxy:-}}" ]; then
      echo "proxy=${HTTP_PROXY:-${http_proxy:-}}"
    fi
    if [ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]; then
      echo "https-proxy=${HTTPS_PROXY:-${https_proxy:-}}"
    elif [ -n "${HTTP_PROXY:-${http_proxy:-}}" ]; then
      echo "https-proxy=${HTTP_PROXY:-${http_proxy:-}}"
    fi
  } > "${CONTAINER_HOME}/.npmrc"

  git config --global --add safe.directory '*' >/dev/null 2>&1 || true
  git config --global user.name "${GIT_USER_NAME}"
  git config --global user.email "${GIT_USER_EMAIL}"
  git config --global checkout.workers 1
  git config --global index.threads 1
  git config --global http.version HTTP/1.1

  # compile_app.py launches ohpm with a minimal environment, so Node falls
  # back to the passwd home instead of CONTAINER_HOME. Keep both paths on the
  # persistent cache without changing OpenHarmony sources.
  local passwd_home
  passwd_home="$(getent passwd "$(id -u)" | cut -d: -f6)"
  local persistent_ohpm="${CONTAINER_HOME}/.ohpm"
  local passwd_ohpm="${passwd_home}/.ohpm"
  mkdir -p "${persistent_ohpm}"
  if [ "${passwd_ohpm}" != "${persistent_ohpm}" ]; then
    if [ -d "${passwd_ohpm}" ] && [ ! -L "${passwd_ohpm}" ]; then
      if [ -d "${passwd_ohpm}/cache" ]; then
        mkdir -p "${persistent_ohpm}/cache"
        cp -an "${passwd_ohpm}/cache/." "${persistent_ohpm}/cache/"
      fi
      if [ -f "${passwd_ohpm}/.ohpmrc" ] && [ ! -e "${persistent_ohpm}/.ohpmrc" ]; then
        cp -p "${passwd_ohpm}/.ohpmrc" "${persistent_ohpm}/.ohpmrc"
      fi
      rm -rf "${passwd_ohpm}"
    fi
    ln -sfn "${persistent_ohpm}" "${passwd_ohpm}"
  fi
}

ensure_host_tools() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "install missing host tool: uv"
    python3 -m pip install --user \
      --trusted-host repo.huaweicloud.com \
      -i https://repo.huaweicloud.com/repository/pypi/simple \
      uv
  fi
  command -v uv >/dev/null
}

ensure_repo_tool() {
  if command -v repo >/dev/null 2>&1; then
    return
  fi
  if [ "$(id -u)" != "0" ]; then
    echo "repo command not found; install repo or rerun as root without SKIP_APT=1" >&2
    exit 1
  fi
  curl -fsSL "${REPO_LAUNCHER_URL}" -o /usr/local/bin/repo
  chmod +x /usr/local/bin/repo
}

prepare_checkout() {
  mkdir -p "${CACHE_ROOT}" "${OHOS_ROOT}" "${PACKAGE_ROOT}" "${CACHE_ROOT}/logs" "${CCACHE_DIR}"
  cd "${OHOS_ROOT}"
  if [ "${SKIP_REPO_SYNC}" = "1" ] && [ -d .repo ]; then
    echo "skip repo init/sync; reusing existing checkout at ${OHOS_ROOT}"
    return
  fi

  local repo_init_args=(
    init
    -u "${MANIFEST_URL}"
    -b "${OHOS_BRANCH}"
    -g "${MANIFEST_GROUPS}"
    --repo-url="${REPO_URL}"
    --no-repo-verify
  )
  if [ "${REPO_NO_BUNDLE}" = "1" ]; then
    repo_init_args+=(--no-clone-bundle)
  fi
  repo "${repo_init_args[@]}"

  local repo_sync_args=(
    sync
    -c
    -j"${REPO_JOBS}"
  )
  if [ "${REPO_NO_TAGS}" = "1" ]; then
    repo_sync_args+=(--no-tags)
  fi
  if [ "${REPO_FORCE_SYNC}" = "1" ]; then
    repo_sync_args+=(--force-sync)
  fi
  if [ "${REPO_NO_BUNDLE}" = "1" ]; then
    repo_sync_args+=(--no-clone-bundle)
  fi
  if repo sync -h 2>&1 | grep -q -- '--jobs-checkout'; then
    repo_sync_args+=(--jobs-checkout="${REPO_CHECKOUT_JOBS}")
  fi

  local attempt=1
  while true; do
    if repo "${repo_sync_args[@]}"; then
      break
    fi
    if [ "${attempt}" -ge "${REPO_SYNC_RETRIES}" ]; then
      echo "repo sync failed after ${attempt} attempts" >&2
      exit 1
    fi
    echo "repo sync failed; retry ${attempt}/${REPO_SYNC_RETRIES} after 20s"
    sleep 20
    attempt=$((attempt + 1))
  done
}

configure_out_volume_ccache() {
  if [ "${QEMU_CCACHE_ON_OUT_VOLUME}" != "1" ]; then
    return
  fi

  # hb's --ccache resolver intentionally replaces CCACHE_DIR with
  # $CCACHE_BASE/$CCACHE_LOCAL_DIR. On a macOS bind mount this eventually
  # exhausts VirtioFS file handles even when the container nofile limit is
  # high. Keep both the cache and temporary files on the native Linux out
  # volume used by the full 2in1 build.
  local native_ccache="${OHOS_ROOT}/out/.ccache"
  local native_tmp="${OHOS_ROOT}/out/.ccache-tmp"
  local seed_marker="${native_ccache}/.ohos-qemu-host-cache-seeded"
  mkdir -p "${native_ccache}" "${native_tmp}"

  if [ ! -f "${seed_marker}" ]; then
    local source_cache
    for source_cache in "${CONTAINER_HOME}/.ccache" "${CCACHE_DIR}"; do
      if [ -d "${source_cache}" ] && [ "${source_cache}" != "${native_ccache}" ]; then
        echo "seed native Linux ccache from ${source_cache}"
        rsync -a --ignore-existing "${source_cache}/" "${native_ccache}/"
      fi
    done
    touch "${seed_marker}"
  fi

  CCACHE_BASE="${OHOS_ROOT}/out"
  CCACHE_LOCAL_DIR=.ccache
  CCACHE_TEMPDIR="${native_tmp}"
  CCACHE_DIR="${native_ccache}"
  export CCACHE_BASE CCACHE_LOCAL_DIR CCACHE_TEMPDIR CCACHE_DIR
  echo "ccache native volume: ${CCACHE_DIR} (temp: ${CCACHE_TEMPDIR})"
}

sync_git_lfs_objects() {
  if [ "${SKIP_GIT_LFS}" = "1" ]; then
    echo "skip git lfs pull"
    return
  fi
  if [ ! -d "${OHOS_ROOT}/.repo" ]; then
    return
  fi
  if ! git lfs version >/dev/null 2>&1; then
    echo "git-lfs not found; install git-lfs or set SKIP_GIT_LFS=1 only if LFS objects are already present" >&2
    exit 1
  fi

  cd "${OHOS_ROOT}"
  echo "sync Git LFS objects: ${GIT_LFS_PATHS}"
  local path
  for path in ${GIT_LFS_PATHS}; do
    if [ ! -e "${OHOS_ROOT}/${path}/.git" ]; then
      echo "skip git lfs path without git metadata: ${path}"
      continue
    fi
    echo "git lfs pull: ${path}"
    git -C "${OHOS_ROOT}/${path}" lfs pull
  done
}

verify_git_lfs_objects() {
  if ! git lfs version >/dev/null 2>&1; then
    echo "git-lfs not found; cannot verify cached LFS objects" >&2
    exit 1
  fi

  local path
  local relative_path
  local object_path
  local first_line
  local missing=0
  for path in ${GIT_LFS_PATHS}; do
    if [ ! -e "${OHOS_ROOT}/${path}/.git" ]; then
      continue
    fi
    while IFS= read -r relative_path; do
      [ -n "${relative_path}" ] || continue
      object_path="${OHOS_ROOT}/${path}/${relative_path}"
      if [ ! -f "${object_path}" ]; then
        echo "missing Git LFS worktree file: ${path}/${relative_path}" >&2
        missing=1
        continue
      fi
      IFS= read -r first_line < "${object_path}" || true
      if [ "${first_line}" = "version https://git-lfs.github.com/spec/v1" ]; then
        echo "unresolved Git LFS pointer: ${path}/${relative_path}" >&2
        missing=1
      fi
    done < <(git -C "${OHOS_ROOT}/${path}" lfs ls-files --name-only)
  done

  if [ "${missing}" -ne 0 ]; then
    echo "cached checkout has unresolved Git LFS objects; rerun without SKIP_GIT_LFS=1" >&2
    exit 1
  fi
}

remove_under_ohos_root() {
  local path="$1"
  case "${path}" in
    "${OHOS_ROOT}"/*) rm -rf "${path}" ;;
    *)
      echo "refusing to remove path outside OHOS_ROOT: ${path}" >&2
      exit 1
      ;;
  esac
}

remove_under_cache_root() {
  local path="$1"
  case "${path}" in
    "${CACHE_ROOT}"/*) rm -rf "${path}" ;;
    *)
      echo "refusing to remove path outside CACHE_ROOT: ${path}" >&2
      exit 1
      ;;
  esac
}

clean_js_prebuilts_state() {
  echo "clean JS dependency/prebuilt state left by interrupted npm installs"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/jsframework/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/parse5/packages/parse5/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/weex-loader/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/arkcompiler/ets_frontend/legacy_bin/api8/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/prebuilts/build-tools/common/js-framework/node_modules"
  remove_under_cache_root "${CACHE_ROOT}/npm-cache"
  remove_under_cache_root "${CONTAINER_HOME}/.npm/_cacache/jsframework"
}

ETS12_PREBUILTS_CONFIG_BACKUP=""
ETS12_SEPARATE_NPM_INSTALL=0

restore_ets12_prebuilts_config() {
  if [ -z "${ETS12_PREBUILTS_CONFIG_BACKUP}" ]; then
    return
  fi
  local config="${OHOS_ROOT}/build/prebuilts_config.json"
  if [ -f "${ETS12_PREBUILTS_CONFIG_BACKUP}" ]; then
    cp -p "${ETS12_PREBUILTS_CONFIG_BACKUP}" "${config}"
    rm -f "${ETS12_PREBUILTS_CONFIG_BACKUP}"
  fi
  ETS12_PREBUILTS_CONFIG_BACKUP=""
}

prepare_ets12_separate_npm_install() {
  if [ "${SKIP_PREBUILTS}" = "1" ]; then
    return
  fi

  local config="${OHOS_ROOT}/build/prebuilts_config.json"
  local package_json="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2/package.json"
  if [ ! -f "${config}" ] || [ ! -f "${package_json}" ]; then
    return
  fi

  ETS12_PREBUILTS_CONFIG_BACKUP="$(mktemp "${CACHE_ROOT}/prebuilts_config.ets12.XXXXXX.json")"
  cp -p "${config}" "${ETS12_PREBUILTS_CONFIG_BACKUP}"
  if ! python3 - "${config}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = "${code_dir}/developtools/ace_ets2bundle/ets1.2"
data = json.loads(path.read_text())
removed = 0

def remove_target(value):
    global removed
    if isinstance(value, dict):
        for child in value.values():
            remove_target(child)
    elif isinstance(value, list):
        before = len(value)
        value[:] = [item for item in value if item != target]
        removed += before - len(value)
        for child in value:
            remove_target(child)

remove_target(data)
if removed != 1:
    raise SystemExit(f"expected one ets1.2 npm entry, removed {removed}")
path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n")
PY
  then
    restore_ets12_prebuilts_config
    return 1
  fi

  ETS12_SEPARATE_NPM_INSTALL=1
  echo "install ets1.2 separately to avoid npm 6 local-package staging collision"
}

install_ets12_node_modules() {
  if [ "${ETS12_SEPARATE_NPM_INSTALL}" != "1" ]; then
    return
  fi

  local root="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2"
  local npm_tool="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin/npm"
  if [ ! -x "${npm_tool}" ]; then
    echo "missing OpenHarmony npm tool: ${npm_tool}" >&2
    exit 1
  fi

  remove_under_ohos_root "${root}/node_modules"
  (
    cd "${root}"
    PATH="$(dirname "${npm_tool}"):${PATH}" \
      "${npm_tool}" install \
      --registry "${NPM_REGISTRY}" \
      --cache "${CONTAINER_HOME}/.npm/_cacache/ets1.2" \
      --package-lock=false \
      --unsafe-perm
  ) 2>&1 | tee "${CACHE_ROOT}/logs/npm_install_ets12.log"
}

download_prebuilts() {
  cd "${OHOS_ROOT}"
  if [ "${SKIP_PREBUILTS}" = "1" ]; then
    echo "skip prebuilts_download.sh; reusing existing prebuilts"
    return
  fi
  if [ ! -x build/prebuilts_download.sh ]; then
    echo "missing build/prebuilts_download.sh under ${OHOS_ROOT}" >&2
    exit 1
  fi
  if [ "${PREBUILTS_CLEAN}" = "1" ]; then
    clean_js_prebuilts_state
  fi

  set +e
  bash build/prebuilts_download.sh 2>&1 | tee "${CACHE_ROOT}/logs/prebuilts_download.log"
  local rc="${PIPESTATUS[0]}"
  set -e
  if [ "${rc}" = "0" ] || [ "${PREBUILTS_RETRY}" != "1" ]; then
    return "${rc}"
  fi

  clean_js_prebuilts_state
  set +e
  bash build/prebuilts_download.sh 2>&1 | tee "${CACHE_ROOT}/logs/prebuilts_download.retry.log"
  rc="${PIPESTATUS[0]}"
  set -e
  return "${rc}"
}

configure_ohos_node_path() {
  local node_root="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs"
  local node_bin=""
  local candidate
  for candidate in \
    "${node_root}"/node-v18*-linux-x64/bin \
    "${node_root}/current/bin"; do
    if [ -x "${candidate}/node" ] && [ -x "${candidate}/npm" ]; then
      node_bin="${candidate}"
      break
    fi
  done
  if [ -z "${node_bin}" ]; then
    echo "missing OpenHarmony Node.js 18 prebuilt under ${node_root}" >&2
    exit 1
  fi

  export PATH="${node_bin}:${PATH}"
  hash -r
  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
  if [ "${node_major}" -lt 18 ]; then
    echo "OpenHarmony build requires Node.js 18+, found $(node --version)" >&2
    exit 1
  fi
  echo "OpenHarmony build Node.js: $(node --version) from $(command -v node)"
}

repair_ets12_node_modules() {
  local root="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2"
  local npm_tool=(
    "${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin/npm"
  )
  if [ ! -d "${root}/node_modules" ]; then
    return
  fi
  if [ ! -x "${npm_tool[0]}" ]; then
    echo "missing OpenHarmony npm tool: ${npm_tool[0]}" >&2
    exit 1
  fi

  # npm 6 resolves nested file: dependencies relative to the top-level
  # node_modules symlink. Repair those generated links at their physical
  # package locations so TypeScript project references resolve normally.
  local package
  local dependency
  for package in common compat interop libarkts; do
    mkdir -p "${root}/${package}/node_modules/@koalaui"
  done
  for dependency in build-common compat; do
    ln -sfn "../../../${dependency}" \
      "${root}/common/node_modules/@koalaui/${dependency}"
  done
  ln -sfn "../../../build-common" \
    "${root}/compat/node_modules/@koalaui/build-common"
  for dependency in build-common common compat; do
    ln -sfn "../../../${dependency}" \
      "${root}/interop/node_modules/@koalaui/${dependency}"
  done
  for dependency in build-common common compat interop; do
    ln -sfn "../../../${dependency}" \
      "${root}/libarkts/node_modules/@koalaui/${dependency}"
  done
  if [ -d "${root}/interop/node_modules/@types/node" ]; then
    mkdir -p "${root}/node_modules/@types"
    ln -sfn "../../interop/node_modules/@types/node" \
      "${root}/node_modules/@types/node"
  fi

  if [ ! -x "${root}/node_modules/.bin/arktscgen" ]; then
    echo "restore ets1.2 npm executable links"
    (
      cd "${root}"
      "${npm_tool[@]}" rebuild \
        --registry "${NPM_REGISTRY}" \
        --cache "${CACHE_ROOT}/npm-cache" \
        --unsafe-perm
    )
  fi
}

build_product() {
  local product="$1"
  local kernel_obj="${product}"
  local kernel_image="Image"
  if [ "${product}" = "armv7a_virt" ]; then
    kernel_obj="arm_virt"
    kernel_image="zImage"
  elif [ "${product}" = "x86_64_virt" ]; then
    kernel_image="bzImage"
  fi
  cd "${OHOS_ROOT}"
  export CCACHE_DIR
  export OHOS_KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS}"
  ccache -M "${CCACHE_MAXSIZE}" >/dev/null 2>&1 || true

  # A component-profile change must not reuse a target graph or case-collided
  # Taihe outputs from an earlier build. The host runner mounts out/ on a
  # case-sensitive Linux volume; this stamp also makes profile switches safe.
  local profile_stamp="${OHOS_ROOT}/out/.ohos-qemu-build-profile-${product}"
  local previous_profile=""
  if [ -f "${profile_stamp}" ]; then
    previous_profile="$(<"${profile_stamp}")"
  fi
  if [ -n "${previous_profile}" ] && [ "${previous_profile}" != "${DEVICE_TYPE_BUILD_PROFILE}" ]; then
    echo "device profile changed for ${product}: ${previous_profile} -> ${DEVICE_TYPE_BUILD_PROFILE}; clean product output"
    rm -rf "${OHOS_ROOT}/out/${product}" "${OHOS_ROOT}/out/preloader/${product}"
  fi
  mkdir -p "${OHOS_ROOT}/out"
  printf '%s\n' "${DEVICE_TYPE_BUILD_PROFILE}" > "${profile_stamp}"

  # Recent hb versions persist list-valued arguments in out/hb_args and append
  # the next invocation's values. Without clearing the generated default here,
  # sequential product builds can execute Ninja with multiple conflicting -j
  # values (for example, "-j2 -j8").
  python3 - "${OHOS_ROOT}/out/hb_args/buildargs.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_file():
    data = json.loads(path.read_text(encoding="utf-8"))
    ninja_args = data.get("ninja_args")
    if isinstance(ninja_args, dict) and ninja_args.get("argDefault"):
        ninja_args["argDefault"] = []
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
PY

  if [ "${CLEAN_KERNEL_OBJ}" = "1" ]; then
    rm -rf "${OHOS_ROOT}/out/KERNEL_OBJ"
    rm -rf "${OHOS_ROOT}/out/kernel/OBJ/${kernel_obj}"
    rm -f "${OHOS_ROOT}/out/${product}/packages/phone/images/${kernel_image}"
  fi

  local build_args=(
    ./build.sh
    --product-name "${product}"
    --ccache
    "--ninja-args=-j${BUILD_JOBS}"
    --load-test-config=false
    --deps-guard=false
  )
  if [ -n "${DEVICE_TYPE}" ]; then
    # Ensure GN sees device_type at compile time (init ohos.para generation).
    # --device-type is a post-image rewrite in hb and cannot run in
    # --build-only-load mode because packages/phone/.../ohos.para does not yet
    # exist.  The packager performs the same final-image rewrite as a verified
    # step, while this GN arg keeps the compile-time device type available.
    build_args+=(--gn-args "device_type=${DEVICE_TYPE}")
    if [ "${BUILD_ONLY_LOAD}" != "1" ]; then
      build_args+=(--device-type "${DEVICE_TYPE}")
    fi
  fi
  if [ "${NO_PREBUILT_SDK}" = "1" ]; then
    build_args+=(--no-prebuilt-sdk=true)
  fi
  if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
    build_args+=(--build-only-load=true)
  fi
  "${build_args[@]}" 2>&1 | tee "${CACHE_ROOT}/logs/build_${product}_${DEVICE_TYPE:-default}.log"
}

package_product() {
  local product="$1"
  validate_prebuilt_haps "${product}"
  local package_args=(
    bash "${PACKAGER}"
    --source-root "${OHOS_ROOT}"
    --product "${product}"
    --output-dir "${PACKAGE_ROOT}"
  )
  if [ -n "${DEVICE_TYPE}" ]; then
    package_args+=(--device-type "${DEVICE_TYPE}")
  fi
  package_args+=(--device-type-profile "${DEVICE_TYPE_BUILD_PROFILE}")
  "${package_args[@]}" 2>&1 | tee "${CACHE_ROOT}/logs/package_${product}_${DEVICE_TYPE:-default}.log"
}

validate_prebuilt_haps() {
  local product="$1"
  local image_dir="${OHOS_ROOT}/out/${product}/packages/phone/images"
  local system_app_dir="${OHOS_ROOT}/out/${product}/packages/phone/system/app"
  local pointer_list="${CACHE_ROOT}/logs/lfs_pointer_haps_${product}.txt"

  if [ ! -d "${system_app_dir}" ]; then
    return
  fi

  : > "${pointer_list}"
  while IFS= read -r -d '' hap; do
    if head -c 64 "${hap}" | grep -q 'version https://git-lfs.github.com/spec'; then
      printf '%s\n' "${hap}" >> "${pointer_list}"
    fi
  done < <(find "${system_app_dir}" -type f -name '*.hap' -print0)

  if [ -s "${pointer_list}" ]; then
    echo "Git LFS pointer HAPs found in ${system_app_dir}; run git lfs pull for applications/standard/hap and rebuild ${product}." >&2
    cat "${pointer_list}" >&2
    exit 1
  fi

  if [ -d "${image_dir}" ]; then
    find "${image_dir}" -maxdepth 1 -type f -name '*.img' -size 0 -print -quit | grep -q . && {
      echo "empty image artifact found under ${image_dir}" >&2
      exit 1
    }
  fi

  return 0
}

product_list_contains() {
  local expected="$1"
  local product
  for product in "${PRODUCTS[@]}"; do
    if [ "${product}" = "${expected}" ]; then
      return 0
    fi
  done
  return 1
}

configure_qemu_device_profile() {
  local profile_args=()
  local product
  for product in "${PRODUCTS[@]}"; do
    profile_args+=(--product "${product}")
  done

  for overlay in "${QEMU_2IN1_OVERLAY}" "${QEMU_PHONE_OVERLAY}"; do
    if [ ! -f "${overlay}" ]; then
      echo "missing QEMU device profile overlay: ${overlay}" >&2
      exit 1
    fi
  done

  case "${QEMU_2IN1_FULL_OVERLAY}" in auto|0|1) ;; *)
    echo "unsupported QEMU_2IN1_FULL_OVERLAY=${QEMU_2IN1_FULL_OVERLAY}; expected auto, 1, or 0" >&2
    exit 2
  esac
  case "${QEMU_PHONE_FULL_OVERLAY}" in auto|0|1) ;; *)
    echo "unsupported QEMU_PHONE_FULL_OVERLAY=${QEMU_PHONE_FULL_OVERLAY}; expected auto, 1, or 0" >&2
    exit 2
  esac
  if [ "${QEMU_2IN1_FULL_OVERLAY}" = "1" ] && [ "${DEVICE_TYPE}" != "2in1" ]; then
    echo "QEMU_2IN1_FULL_OVERLAY=1 requires DEVICE_TYPE=2in1" >&2
    exit 2
  fi
  if [ "${QEMU_PHONE_FULL_OVERLAY}" = "1" ] && [ "${DEVICE_TYPE}" != "phone" ]; then
    echo "QEMU_PHONE_FULL_OVERLAY=1 requires DEVICE_TYPE=phone" >&2
    exit 2
  fi

  # A product may inherit only one generated device profile. Disable both for
  # the selected products before enabling the requested source profile.
  bash "${QEMU_2IN1_OVERLAY}" --source-root "${OHOS_ROOT}" --disable \
    "${profile_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/disable_qemu_2in1_full_overlay.log"
  bash "${QEMU_PHONE_OVERLAY}" --source-root "${OHOS_ROOT}" --disable \
    "${profile_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/disable_qemu_phone_full_overlay.log"

  if [ "${DEVICE_TYPE}" = "2in1" ] && [ "${QEMU_2IN1_FULL_OVERLAY}" != "0" ]; then
    DEVICE_TYPE_BUILD_PROFILE=qemu_2in1_full_source
    bash "${QEMU_2IN1_OVERLAY}" --source-root "${OHOS_ROOT}" \
      "${profile_args[@]}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_2in1_full_overlay.log"
  elif [ "${DEVICE_TYPE}" = "phone" ] && [ "${QEMU_PHONE_FULL_OVERLAY}" != "0" ]; then
    DEVICE_TYPE_BUILD_PROFILE=qemu_phone_full_source
    bash "${QEMU_PHONE_OVERLAY}" --source-root "${OHOS_ROOT}" \
      "${profile_args[@]}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_phone_full_overlay.log"
  elif [ -n "${DEVICE_TYPE}" ]; then
    DEVICE_TYPE_BUILD_PROFILE=param_only
  else
    DEVICE_TYPE_BUILD_PROFILE=default
  fi
  export DEVICE_TYPE_BUILD_PROFILE
}

apply_armv7a_full_overlay() {
  if ! product_list_contains armv7a_virt; then
    return
  fi
  if [ "${ARMV7A_FULL_OVERLAY}" != "1" ]; then
    echo "armv7a_virt selected but ARMV7A_FULL_OVERLAY=${ARMV7A_FULL_OVERLAY}; skip overlay"
    return
  fi
  if [ ! -f "${ARMV7A_OVERLAY}" ]; then
    echo "missing armv7a overlay: ${ARMV7A_OVERLAY}" >&2
    exit 1
  fi
  bash "${ARMV7A_OVERLAY}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_armv7a_virt_full_overlay.log"
}

apply_standard_vpn_overlay() {
  if [ "${STANDARD_VPN_OVERLAY}" != "1" ]; then
    echo "STANDARD_VPN_OVERLAY=${STANDARD_VPN_OVERLAY}; skip standard VPN configuration"
    return
  fi
  if [ ! -f "${VPN_OVERLAY}" ]; then
    echo "missing standard VPN overlay: ${VPN_OVERLAY}" >&2
    exit 1
  fi

  local vpn_args=()
  local product
  for product in "${PRODUCTS[@]}"; do
    vpn_args+=(--product "${product}")
  done
  bash "${VPN_OVERLAY}" \
    --source-root "${OHOS_ROOT}" \
    "${vpn_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_standard_qemu_vpn_overlay.log"
}

apply_qemu_absolute_pointer_overlay() {
  if [ "${QEMU_ABSOLUTE_POINTER_OVERLAY}" != "1" ]; then
    echo "QEMU_ABSOLUTE_POINTER_OVERLAY=${QEMU_ABSOLUTE_POINTER_OVERLAY}; skip absolute pointer configuration"
    return
  fi
  if [ ! -f "${QEMU_ABSOLUTE_POINTER_OVERLAY_SCRIPT}" ]; then
    echo "missing QEMU absolute-pointer overlay: ${QEMU_ABSOLUTE_POINTER_OVERLAY_SCRIPT}" >&2
    exit 1
  fi
  bash "${QEMU_ABSOLUTE_POINTER_OVERLAY_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_absolute_pointer_overlay.log"
}

fix_case_insensitive_selinux_version_header() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
selinux_root = source_root / "third_party/selinux/libselinux"
version_file = selinux_root / "VERSION"
lowercase_alias = selinux_root / "version"
compat_version_file = selinux_root / "LIBSELINUX_VERSION"
build_file = source_root / "third_party/selinux/BUILD.gn"
make_file = selinux_root / "src/Makefile"

entry_names = {entry.name for entry in selinux_root.iterdir()}
has_version_file = "VERSION" in entry_names
has_compat_version_file = "LIBSELINUX_VERSION" in entry_names
case_insensitive_alias = has_version_file and lowercase_alias.exists()
already_configured = has_compat_version_file
if not case_insensitive_alias and not already_configured:
    print("libselinux VERSION does not alias lowercase <version>; no compatibility fix needed")
    raise SystemExit(0)

quote_only_config = '''config("third_party_selinux_config") {
  include_dirs = [ "$LIBSELINUX_ROOT_DIR/include" ]
  cflags = [
    "-iquote" + rebase_path("$LIBSELINUX_ROOT_DIR", root_build_dir),
  ]
}
'''
original_config = '''config("third_party_selinux_config") {
  include_dirs = [
    "$LIBSELINUX_ROOT_DIR/include",
    "$LIBSELINUX_ROOT_DIR",
  ]
}
'''
text = build_file.read_text()
if original_config in text:
    build_file.write_text(text.replace(original_config, quote_only_config, 1))
elif quote_only_config not in text:
    raise SystemExit(f"unexpected third_party_selinux_config layout in {build_file}")

if has_compat_version_file:
    if has_version_file and version_file.read_bytes() != compat_version_file.read_bytes():
        raise SystemExit(f"conflicting libselinux version files: {version_file} and {compat_version_file}")
    if not has_version_file:
        compat_version_file.rename(version_file)
    else:
        compat_version_file.unlink()

make_text = make_file.read_text()
updated_make_text = make_text.replace("../LIBSELINUX_VERSION", "../VERSION")
if updated_make_text != make_text:
    make_file.write_text(updated_make_text)
elif "../VERSION" not in make_text:
    raise SystemExit(f"unexpected libselinux VERSION reference layout in {make_file}")

if "VERSION" in {entry.name for entry in selinux_root.iterdir()}:
    print(
        "configured case-insensitive libselinux compatibility: "
        f"quote-only private headers in {build_file}; preserved {version_file}"
    )
else:
    raise SystemExit(f"missing libselinux version file: {version_file}")
PY
}

fix_case_insensitive_xmp_endian_header() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
xmp_root = source_root / "third_party/xmp_toolkit_sdk"
source_dir = xmp_root / "source"
endian_header = source_dir / "Endian.h"
lowercase_alias = source_dir / "endian.h"
build_file = xmp_root / "BUILD.gn"
warning_flag = '"-Wno-nonportable-include-path"'

entry_names = {entry.name for entry in source_dir.iterdir()}
case_insensitive_alias = "Endian.h" in entry_names and lowercase_alias.exists()
text = build_file.read_text()
public_original = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
'''
public_intermediate = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
  include_dirs -= [ "source" ]
'''
public_duplicate = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
  include_dirs -= [ "source" ]
  include_dirs -= [ "source" ]
'''
public_replacement = ''']

_xmpsdk_public_include_dirs = _xmpsdk_include_dirs
_xmpsdk_public_include_dirs -= [ "source" ]

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_public_include_dirs
'''
already_configured = warning_flag in text and public_replacement in text
if not case_insensitive_alias and not already_configured:
    print("XMP Endian.h does not alias endian.h; no compatibility fix needed")
    raise SystemExit(0)

if public_duplicate in text:
    text = text.replace(public_duplicate, public_replacement, 1)
elif public_intermediate in text:
    text = text.replace(public_intermediate, public_replacement, 1)
elif public_original in text:
    text = text.replace(public_original, public_replacement, 1)
elif public_replacement not in text:
    raise SystemExit(f"unexpected xmpsdk_public_config layout in {build_file}")

original = '''    "-Wno-tautological-overlap-compare",
    "-Wno-int-to-void-pointer-cast",
  ]
}
'''
replacement = '''    "-Wno-tautological-overlap-compare",
    "-Wno-int-to-void-pointer-cast",
    "-Wno-nonportable-include-path",
  ]
}
'''
if original in text:
    text = text.replace(original, replacement, 1)
elif replacement not in text:
    raise SystemExit(f"unexpected xmpsdk_config cflags_cc layout in {build_file}")
build_file.write_text(text)

if not endian_header.exists():
    raise SystemExit(f"missing XMP endian header: {endian_header}")
print(
    "configured case-insensitive XMP compatibility: "
    f"removed source/ from public include lookup and suppressed "
    f"private path-case diagnostics in {build_file}"
)
PY
}

fix_case_insensitive_iptables_variants() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}" != "1" ]; then
    return
  fi

  python3 "${SCRIPT_DIR}/fix_case_insensitive_iptables.py" \
    --source-root "${OHOS_ROOT}"
}

fix_case_insensitive_kernel_netfilter() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}" != "1" ]; then
    return
  fi

  python3 "${SCRIPT_DIR}/fix_case_insensitive_kernel_netfilter.py" \
    --source-root "${OHOS_ROOT}"
}

fix_mindspore_non_arm_hwcap_header() {
  if [ "${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
source = source_root / (
    "third_party/mindspore/mindspore-src/source/mindspore-lite/"
    "src/common/utils.cc"
)
text = source.read_text()
original = """#if defined(__ANDROID__) || defined(MS_COMPILE_OHOS)
#include <sys/auxv.h>
#include <asm/hwcap.h>
#endif
"""
replacement = """#if defined(__ANDROID__) || defined(MS_COMPILE_OHOS)
#include <sys/auxv.h>
#ifdef ENABLE_ARM64
#include <asm/hwcap.h>
#endif
#endif
"""
if original in text:
    source.write_text(text.replace(original, replacement, 1))
elif replacement not in text:
    raise SystemExit(f"unexpected MindSpore hwcap include layout in {source}")
print(f"configured non-ARM MindSpore hwcap compatibility in {source}")
PY
}

fix_virtiofs_node_symlink_copy() {
  if [ "${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
import re
from pathlib import Path

source_root = Path(sys.argv[1])
scripts = [
    source_root / "arkcompiler/ets_frontend/arkguard/compile_arkguard.py",
    source_root / "arkcompiler/ets_frontend/ets2panda/driver/build_system/build_build_system.py",
]
pattern = re.compile(
    r"shutil\.copytree\(source_path,\s*dest_path,\s*"
    r"dirs_exist_ok=True,\s*symlinks=True\)"
)
replacement = (
    "shutil.copytree(source_path, dest_path, "
    "dirs_exist_ok=True, symlinks=False)"
)
for script in scripts:
    text = script.read_text()
    original_text = text
    restore_marker = "Restore symlinks without copying unsupported VirtioFS metadata."
    updated, count = pattern.subn(replacement, text, count=1)
    if count:
        text = updated
    elif replacement not in text and not (
            script.name == "build_build_system.py" and restore_marker in text):
        raise SystemExit(f"unexpected copytree layout in {script}")
    if script.name == "build_build_system.py":
        restore_block = '''shutil.copytree(source_path, dest_path, dirs_exist_ok=True, symlinks=False)
            # Restore symlinks without copying unsupported VirtioFS metadata.
            for source_dir, dirnames, filenames in os.walk(
                    source_path, topdown=False):
                for name in dirnames + filenames:
                    source_entry = os.path.join(source_dir, name)
                    if not os.path.islink(source_entry):
                        continue
                    relative_entry = os.path.relpath(source_entry, source_path)
                    dest_entry = os.path.join(dest_path, relative_entry)
                    if os.path.lexists(dest_entry):
                        if os.path.isdir(dest_entry) and not os.path.islink(
                                dest_entry):
                            shutil.rmtree(dest_entry)
                        else:
                            os.unlink(dest_entry)
                    os.symlink(os.readlink(source_entry), dest_entry)'''
        if restore_marker not in text:
            if replacement not in text:
                raise SystemExit(f"missing copytree call in {script}")
            text = text.replace(replacement, restore_block, 1)
    if text != original_text:
        script.write_text(text)
    print(f"configured shared-filesystem Node launcher copy in {script}")
PY
}

serialize_shared_arkoala_generator() {
  if [ "${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
script = source_root / (
    "foundation/arkui/ace_engine/frameworks/bridge/arkts_frontend/"
    "arkoala_generator/gn/command/generation.py"
)
text = script.read_text()
original_text = text
if "import fcntl\n" not in text:
    import_marker = "import argparse\n"
    if import_marker not in text:
        raise SystemExit(f"unexpected import layout in {script}")
    text = text.replace(import_marker, import_marker + "import fcntl\n", 1)

lock_marker = "Waiting for shared Arkoala generator lock:"
if lock_marker not in text:
    original = '''    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, "../../")
'''
    replacement = '''    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, "../../")

    lock_path = os.environ.get(
        "OHOS_ARKOALA_GENERATOR_LOCK",
        "/tmp/openharmony-arkoala-generator.lock",
    )
    print(f"Waiting for shared Arkoala generator lock: {lock_path}")
    generator_lock = open(lock_path, "w", encoding="utf-8")
    fcntl.flock(generator_lock, fcntl.LOCK_EX)
    print(f"Acquired shared Arkoala generator lock: {lock_path}")
'''
    if original not in text:
        raise SystemExit(f"unexpected main layout in {script}")
    text = text.replace(original, replacement, 1)

if text != original_text:
    script.write_text(text)
print(f"serialized shared-source Arkoala generation in {script}")
PY
}

fix_virtiofs_kernel_source_copy() {
  if [ "${QEMU_FIX_VIRTIOFS_KERNEL_COPY}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
script = source_root / "device/qemu/common/virt_full/kernel/build_kernel.sh"
text = script.read_text()
original_text = text
# Prefer rsync over tar/cp -rL: VirtioFS + tar can hit EMFILE ("Too many open
# files") when packing the full kernel tree. rsync streams file-by-file.
rsync_replacement = '''    rm -rf "${KERNEL_BUILD_ROOT}"
    mkdir -p "${KERNEL_BUILD_ROOT}"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --copy-links --exclude='.git' \\
            "${KERNEL_SOURCE_DIR}/" "${KERNEL_BUILD_ROOT}/"
    else
        tar --exclude='./.git' --exclude='.git' \\
            -C "${KERNEL_SOURCE_DIR}" -chf - . \\
            | tar -C "${KERNEL_BUILD_ROOT}" -xf -
    fi
'''
legacy_cp = '''    rm -rf ${KERNEL_BUILD_ROOT}
    mkdir -p ${OHOS_SOURCE_ROOT}/out/kernel/OBJ
    cp -rL ${KERNEL_SOURCE_DIR}  ${KERNEL_BUILD_ROOT}
'''
legacy_tar = '''    rm -rf "${KERNEL_BUILD_ROOT}"
    mkdir -p "${KERNEL_BUILD_ROOT}"
    tar --exclude='./.git' --exclude='.git' \\
        -C "${KERNEL_SOURCE_DIR}" -chf - . \\
        | tar -C "${KERNEL_BUILD_ROOT}" -xf -
'''
if rsync_replacement in text:
    pass
elif legacy_tar in text:
    text = text.replace(legacy_tar, rsync_replacement, 1)
elif legacy_cp in text:
    text = text.replace(legacy_cp, rsync_replacement, 1)
else:
    raise SystemExit(f"unexpected kernel copy layout in {script}")
old_jobs = "    make ${MAKE_OPTIONS} -j$(nproc)\n"
new_jobs = '    make ${MAKE_OPTIONS} -j"${OHOS_KERNEL_BUILD_JOBS:-$(nproc)}"\n'
if old_jobs in text:
    text = text.replace(old_jobs, new_jobs, 1)
elif new_jobs not in text:
    raise SystemExit(f"unexpected kernel jobs layout in {script}")
reuse_marker = "reuse complete external kernel outputs:"
if reuse_marker not in text:
    main_marker = """##main
# Always refresh the kernel copy."""
    reuse_block = """##main
if [ "${OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE:-0}" = "1" ]; then
    FINAL_KERNEL_IMAGE="${OHOS_IMAGES_DIR}/$(basename "${KERNEL_OUT_IMAGE}")"
    COMPLETE_KERNEL_OUTPUTS=1
    for OUTPUT in \\
        "${FINAL_KERNEL_IMAGE}" \\
        "${KERNEL_MODULES_OUT}/rtw89_core.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_pci.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_8852a.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_8852ae.ko" \\
        "${KERNEL_MODULES_OUT}/mt7601u.ko" \\
        "${KERNEL_MODULES_OUT}/mac80211_hwsim.ko" \\
        "${KERNEL_MODULES_OUT}/virt_wifi.ko" \\
        "${KERNEL_MODULES_OUT}/libarc4.ko" \\
        "${KERNEL_MODULES_OUT}/mac80211.ko" \\
        "${KERNEL_MODULES_OUT}/cfg80211.ko" \\
        "${KERNEL_MODULES_OUT}/iwlwifi.ko" \\
        "${KERNEL_MODULES_OUT}/iwlmvm.ko"; do
        if [ ! -s "${OUTPUT}" ]; then
            COMPLETE_KERNEL_OUTPUTS=0
            break
        fi
    done
    if [ "${COMPLETE_KERNEL_OUTPUTS}" = "1" ]; then
        echo "reuse complete external kernel outputs: ${FINAL_KERNEL_IMAGE}"
        popd
        exit 0
    fi
fi

# Always refresh the kernel copy."""
    if main_marker not in text:
        raise SystemExit(f"unexpected kernel main layout in {script}")
    text = text.replace(main_marker, reuse_block, 1)
if text != original_text:
    script.write_text(text)
print(f"configured shared-filesystem kernel worktree copy in {script}")
PY
}

configure_qemu_product_features() {
  if [ "${QEMU_FIX_ACCESS_TOKENID_ABI}" != "1" ] && [ "${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}" != "1" ]; then
    return
  fi

  cd "${OHOS_ROOT}"
  QEMU_FIX_ACCESS_TOKENID_ABI="${QEMU_FIX_ACCESS_TOKENID_ABI}" \
    QEMU_FIX_SYSTEM_COMPAT_SYMLINKS="${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}" \
    python3 - <<'PY'
import os
from pathlib import Path

fix_access_tokenid_abi = os.environ.get("QEMU_FIX_ACCESS_TOKENID_ABI") == "1"
fix_system_compat_symlinks = os.environ.get("QEMU_FIX_SYSTEM_COMPAT_SYMLINKS") == "1"

if fix_system_compat_symlinks:
    path = Path("build/ohos/images/build_image.py")
    if path.exists():
        text = path.read_text()
        original = text
        text = text.replace("os.symlink('/usr', _system_path)", "os.symlink('/usr/system', _system_path)")
        text = text.replace("os.makedirs(_system_path, exist_ok=True)", "os.symlink('/usr/system', _system_path)")
        if "def _prepare_system_seccomp_compat(" not in text:
            marker = '''def _prepare_updater(updater_path: str, target_cpu: str):
'''
            helper = '''def _prepare_system_seccomp_compat(system_path: str, target_cpu: str):
    if target_cpu not in ('arm64', 'x86_64', 'riscv64'):
        return
    _lib64_seccomp = os.path.join(system_path, 'lib64', 'seccomp')
    _lib_seccomp = os.path.join(system_path, 'lib', 'seccomp')
    if not os.path.isdir(_lib64_seccomp) or os.path.lexists(_lib_seccomp):
        return
    os.makedirs(os.path.dirname(_lib_seccomp), exist_ok=True)
    os.symlink('../lib64/seccomp', _lib_seccomp)


'''
            text = text.replace(marker, helper + marker, 1)
        text = text.replace(
            "    if args.image_name == 'system':\n        _prepare_root(args.input_path, args.target_cpu)\n",
            "    if args.image_name == 'system':\n        _prepare_root(args.input_path, args.target_cpu)\n        _prepare_system_seccomp_compat(args.input_path, args.target_cpu)\n",
            1,
        )
        old = '''def _prepare_ramdisk(ramdisk_path: str):
    _dir_list = ['bin', 'dev', 'etc', 'lib', 'proc', 'sys', 'system', 'usr', 'mnt', 'storage']
    for _dir_name in _dir_list:
        _path = os.path.join(ramdisk_path, _dir_name)
        if os.path.exists(_path):
            continue
        os.makedirs(_path, exist_ok=True)
    if not os.path.exists(os.path.join(ramdisk_path, 'init')):
        os.symlink('bin/init_early', os.path.join(ramdisk_path, 'init'))
'''
        new = '''def _prepare_ramdisk(ramdisk_path: str):
    _dir_list = ['bin', 'dev', 'etc', 'lib', 'proc', 'sys', 'system', 'usr', 'mnt', 'storage']
    for _dir_name in _dir_list:
        _path = os.path.join(ramdisk_path, _dir_name)
        if os.path.exists(_path):
            continue
        os.makedirs(_path, exist_ok=True)
    _system_path = os.path.join(ramdisk_path, 'system')
    if os.path.lexists(_system_path):
        if not os.path.islink(_system_path) or os.readlink(_system_path) != '/usr/system':
            if os.path.isdir(_system_path) and not os.path.islink(_system_path):
                os.rmdir(_system_path)
            else:
                os.unlink(_system_path)
    if not os.path.lexists(_system_path):
        os.symlink('/usr/system', _system_path)
    _chipset_path = os.path.join(ramdisk_path, 'chipset')
    if not os.path.exists(_chipset_path):
        os.symlink('/vendor', _chipset_path)
    _bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')
    if os.path.lexists(_bin_init_path):
        if not os.path.islink(_bin_init_path) or os.readlink(_bin_init_path) != '/system/bin/init':
            if os.path.isdir(_bin_init_path) and not os.path.islink(_bin_init_path):
                os.rmdir(_bin_init_path)
            else:
                os.unlink(_bin_init_path)
    if not os.path.lexists(_bin_init_path):
        os.symlink('/system/bin/init', _bin_init_path)
    if not os.path.exists(os.path.join(ramdisk_path, 'init')):
        os.symlink('bin/init_early', os.path.join(ramdisk_path, 'init'))
'''
        if old in text:
            text = text.replace(old, new, 1)
        elif "_bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')" not in text:
            marker = """    _chipset_path = os.path.join(ramdisk_path, 'chipset')
    if not os.path.exists(_chipset_path):
        os.symlink('/vendor', _chipset_path)
"""
            insert = marker + """    _bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')
    if os.path.lexists(_bin_init_path):
        if not os.path.islink(_bin_init_path) or os.readlink(_bin_init_path) != '/system/bin/init':
            if os.path.isdir(_bin_init_path) and not os.path.islink(_bin_init_path):
                os.rmdir(_bin_init_path)
            else:
                os.unlink(_bin_init_path)
    if not os.path.lexists(_bin_init_path):
        os.symlink('/system/bin/init', _bin_init_path)
"""
            text = text.replace(marker, insert, 1)
        if text != original:
            path.write_text(text)
            print(f"configured {path}: map QEMU /system to /usr/system and add QEMU init/chipset symlinks")

if fix_access_tokenid_abi:
    for version in ["5.10", "6.6"]:
        header = Path(f"kernel/linux/linux-{version}/drivers/accesstokenid/access_tokenid.h")
        source = Path(f"kernel/linux/linux-{version}/drivers/accesstokenid/access_tokenid.c")
        if not header.exists() or not source.exists():
            continue

        text = header.read_text()
        original = text
        old = '''enum {
\tGET_TOKEN_ID = 1,
\tSET_TOKEN_ID,
\tGET_FTOKEN_ID,
\tSET_FTOKEN_ID,
\tADD_PERMISSIONS,
\tREMOVE_PERMISSIONS,
\tGET_PERMISSION,
\tSET_PERMISSION,
\tACCESS_TOKENID_MAX_NR
};
'''
        new = '''enum {
\tGET_TOKEN_ID = 1,
\tSET_TOKEN_ID,
\tGET_FTOKEN_ID,
\tSET_FTOKEN_ID,
\tADD_PERMISSIONS,
\tREMOVE_PERMISSIONS,
\tGET_PERMISSION,
\tSET_PERMISSION,
\tGET_CLOSEST_HAP_TOKENID,
\tGET_FAMILY_TOKENIDS,
\tGET_ALL_PERMISSIONS = 11,
\tSET_USERID,
\tGET_USERID,
\tADD_SPM_ENTRIES = 16,
\tSET_SPM_ENTRIES,
\tGET_SPM_ENTRY,
\tREMOVE_SPM_ENTRY,
\tSET_REFCNT_UID,
\tGET_REFCNT_UID,
\tSET_REFCNT_TOKENID,
\tGET_REFCNT_TOKENID,
\tCLEAR_REFCNT_SPAWNID,
\tGET_SPM_VERSION,
\tSET_HAP_PTOKENID = 0x1A,
\tACCESS_TOKENID_MAX_NR
};
'''
        if old in text:
            text = text.replace(old, new, 1)
        if "\tSET_USERID," not in text:
            text = text.replace(
                "\tGET_ALL_PERMISSIONS = 11,\n\tADD_SPM_ENTRIES = 16,\n",
                "\tGET_CLOSEST_HAP_TOKENID,\n\tGET_FAMILY_TOKENIDS,\n\tGET_ALL_PERMISSIONS = 11,\n\tSET_USERID,\n\tGET_USERID,\n\tADD_SPM_ENTRIES = 16,\n",
                1,
            )
        if "\tSET_HAP_PTOKENID = 0x1A," not in text:
            text = text.replace(
                "\tGET_SPM_VERSION,\n\tACCESS_TOKENID_MAX_NR\n",
                "\tGET_SPM_VERSION,\n\tSET_HAP_PTOKENID = 0x1A,\n\tACCESS_TOKENID_MAX_NR\n",
                1,
            )
        if "ioctl_get_all_perm_data" not in text:
            marker = '''typedef struct {
\tuint32_t token;
\tuint32_t perm[MAX_PERM_GROUP_NUM];
} ioctl_add_perm_data;
'''
            replacement = marker + '''
typedef struct {
\tuint32_t token;
\tuint32_t perm[MAX_PERM_GROUP_NUM];
} ioctl_get_all_perm_data;

typedef struct {
\tuint32_t uid;
\tuint64_t refcnt;
} ioctl_spm_uid_ref;

typedef struct {
\tuint32_t tokenid;
\tuint64_t refcnt;
} ioctl_spm_tokenid_ref;
'''
            if marker in text:
                text = text.replace(marker, replacement, 1)
        if "ACCESS_TOKENID_GET_ALL_PERMISSIONS" not in text:
            marker = '''#define\tACCESS_TOKENID_SET_PERMISSION \\
\t_IOW(ACCESS_TOKEN_ID_IOCTL_BASE, SET_PERMISSION, ioctl_set_get_perm_data)
'''
            replacement = marker + '''#define\tACCESS_TOKENID_GET_ALL_PERMISSIONS \\
\t_IOW(ACCESS_TOKEN_ID_IOCTL_BASE, GET_ALL_PERMISSIONS, ioctl_get_all_perm_data)
#define\tACCESS_TOKENID_GET_SPM_VERSION \\
\t_IOR(ACCESS_TOKEN_ID_IOCTL_BASE, GET_SPM_VERSION, uint32_t)
'''
            if marker in text:
                text = text.replace(marker, replacement, 1)
        if text != original:
            header.write_text(text)
            print(f"configured {header}: extend access_tokenid ioctl command numbers for SPM")

        text = source.read_text()
        original = text
        if "int access_tokenid_get_all_permissions(" not in text:
            marker = "typedef int (*access_token_id_func)(struct file *file, void __user *arg);"
            helper_funcs = '''
int access_tokenid_get_all_permissions(struct file *file, void __user *uarg)
{
\tioctl_get_all_perm_data get_all_perm_data;
\tstruct token_perm_node *target_node = NULL;
\tstruct token_perm_node *parent_node = NULL;

\tif (copy_from_user(&get_all_perm_data, uarg, sizeof(get_all_perm_data)))
\t\treturn -EFAULT;

\tread_lock(&token_rwlock);
\tfind_node_by_token(g_token_perm_root, get_all_perm_data.token, &target_node, &parent_node);
\tif (target_node != NULL)
\t\tmemcpy(get_all_perm_data.perm, target_node->perm_data.perm, sizeof(get_all_perm_data.perm));
\telse
\t\tmemset(get_all_perm_data.perm, 0, sizeof(get_all_perm_data.perm));
\tread_unlock(&token_rwlock);

\treturn copy_to_user(uarg, &get_all_perm_data, sizeof(get_all_perm_data)) ? -EFAULT : 0;
}

int access_tokenid_spm_success(struct file *file, void __user *uarg)
{
\treturn 0;
}

int access_tokenid_get_spm_refcnt_uid(struct file *file, void __user *uarg)
{
\tioctl_spm_uid_ref ref = {0};

\tif (copy_from_user(&ref, uarg, sizeof(ref)))
\t\treturn -EFAULT;
\tref.refcnt = 0;
\treturn copy_to_user(uarg, &ref, sizeof(ref)) ? -EFAULT : 0;
}

int access_tokenid_get_spm_refcnt_tokenid(struct file *file, void __user *uarg)
{
\tioctl_spm_tokenid_ref ref = {0};

\tif (copy_from_user(&ref, uarg, sizeof(ref)))
\t\treturn -EFAULT;
\tref.refcnt = 0;
\treturn copy_to_user(uarg, &ref, sizeof(ref)) ? -EFAULT : 0;
}

int access_tokenid_get_spm_version(struct file *file, void __user *uarg)
{
\tuint32_t version = 1;

\treturn copy_to_user(uarg, &version, sizeof(version)) ? -EFAULT : 0;
}

int access_tokenid_set_userid(struct file *file, void __user *uarg)
{
\tuint32_t user_id = 0;

\tif (copy_from_user(&user_id, uarg, sizeof(user_id)))
\t\treturn -EFAULT;
\tcurrent->user_id = user_id;
\treturn 0;
}

int access_tokenid_get_userid(struct file *file, void __user *uarg)
{
\treturn copy_to_user(uarg, &current->user_id, sizeof(current->user_id)) ? -EFAULT : 0;
}

int access_tokenid_set_hap_ptokenid(struct file *file, void __user *uarg)
{
\tuint64_t tokenid = 0;

\tif (copy_from_user(&tokenid, uarg, sizeof(tokenid)))
\t\treturn -EFAULT;
\tcurrent->ftoken = tokenid;
\treturn 0;
}
'''
            if marker in text:
                text = text.replace(marker, helper_funcs + "\n" + marker, 1)
        if "int access_tokenid_set_userid(" not in text:
            marker = "typedef int (*access_token_id_func)(struct file *file, void __user *arg);"
            helper_funcs = '''
int access_tokenid_set_userid(struct file *file, void __user *uarg)
{
\tuint32_t user_id = 0;

\tif (copy_from_user(&user_id, uarg, sizeof(user_id)))
\t\treturn -EFAULT;
\tcurrent->user_id = user_id;
\treturn 0;
}

int access_tokenid_get_userid(struct file *file, void __user *uarg)
{
\treturn copy_to_user(uarg, &current->user_id, sizeof(current->user_id)) ? -EFAULT : 0;
}

int access_tokenid_set_hap_ptokenid(struct file *file, void __user *uarg)
{
\tuint64_t tokenid = 0;

\tif (copy_from_user(&tokenid, uarg, sizeof(tokenid)))
\t\treturn -EFAULT;
\tcurrent->ftoken = tokenid;
\treturn 0;
}
'''
            if marker in text:
                text = text.replace(marker, helper_funcs + "\n" + marker, 1)
        old = '''static access_token_id_func g_func_array[ACCESS_TOKENID_MAX_NR] = {
\tNULL, /* reserved */
\taccess_tokenid_get_tokenid,
\taccess_tokenid_set_tokenid,
\taccess_tokenid_get_ftokenid,
\taccess_tokenid_set_ftokenid,
\taccess_tokenid_add_permission,
\taccess_tokenid_remove_permission,
\taccess_tokenid_get_permission,
\taccess_tokenid_set_permission,
};
'''
        new = '''static access_token_id_func g_func_array[ACCESS_TOKENID_MAX_NR] = {
\t[GET_TOKEN_ID] = access_tokenid_get_tokenid,
\t[SET_TOKEN_ID] = access_tokenid_set_tokenid,
\t[GET_FTOKEN_ID] = access_tokenid_get_ftokenid,
\t[SET_FTOKEN_ID] = access_tokenid_set_ftokenid,
\t[ADD_PERMISSIONS] = access_tokenid_add_permission,
\t[REMOVE_PERMISSIONS] = access_tokenid_remove_permission,
\t[GET_PERMISSION] = access_tokenid_get_permission,
\t[SET_PERMISSION] = access_tokenid_set_permission,
\t[GET_ALL_PERMISSIONS] = access_tokenid_get_all_permissions,
\t[SET_USERID] = access_tokenid_set_userid,
\t[GET_USERID] = access_tokenid_get_userid,
\t[ADD_SPM_ENTRIES] = access_tokenid_spm_success,
\t[SET_SPM_ENTRIES] = access_tokenid_spm_success,
\t[GET_SPM_ENTRY] = access_tokenid_spm_success,
\t[REMOVE_SPM_ENTRY] = access_tokenid_spm_success,
\t[SET_REFCNT_UID] = access_tokenid_spm_success,
\t[GET_REFCNT_UID] = access_tokenid_get_spm_refcnt_uid,
\t[SET_REFCNT_TOKENID] = access_tokenid_spm_success,
\t[GET_REFCNT_TOKENID] = access_tokenid_get_spm_refcnt_tokenid,
\t[CLEAR_REFCNT_SPAWNID] = access_tokenid_spm_success,
\t[GET_SPM_VERSION] = access_tokenid_get_spm_version,
\t[SET_HAP_PTOKENID] = access_tokenid_set_hap_ptokenid,
};
'''
        if old in text:
            text = text.replace(old, new, 1)
        if "\t[SET_USERID] = access_tokenid_set_userid," not in text:
            text = text.replace(
                "\t[GET_ALL_PERMISSIONS] = access_tokenid_get_all_permissions,\n\t[ADD_SPM_ENTRIES] = access_tokenid_spm_success,\n",
                "\t[GET_ALL_PERMISSIONS] = access_tokenid_get_all_permissions,\n\t[SET_USERID] = access_tokenid_set_userid,\n\t[GET_USERID] = access_tokenid_get_userid,\n\t[ADD_SPM_ENTRIES] = access_tokenid_spm_success,\n",
                1,
            )
        if "\t[SET_HAP_PTOKENID] = access_tokenid_set_hap_ptokenid," not in text:
            text = text.replace(
                "\t[GET_SPM_VERSION] = access_tokenid_get_spm_version,\n};\n",
                "\t[GET_SPM_VERSION] = access_tokenid_get_spm_version,\n\t[SET_HAP_PTOKENID] = access_tokenid_set_hap_ptokenid,\n};\n",
                1,
            )
        if text != original:
            source.write_text(text)
            print(f"configured {source}: add access_tokenid userspace ABI compatibility for QEMU")

        sched = Path(f"kernel/linux/linux-{version}/include/linux/sched.h")
        fork = Path(f"kernel/linux/linux-{version}/kernel/fork.c")
        if sched.exists():
            text = sched.read_text()
            original = text
            old = '''#ifdef CONFIG_ACCESS_TOKENID
\tu64\t\t\t\ttoken;
\tu64\t\t\t\tftoken;
#endif
'''
            new = '''#ifdef CONFIG_ACCESS_TOKENID
\tu64\t\t\t\ttoken;
\tu64\t\t\t\tftoken;
\tu32\t\t\t\tuser_id;
#endif
'''
            if old in text:
                text = text.replace(old, new, 1)
            if text != original:
                sched.write_text(text)
                print(f"configured {sched}: add access_tokenid user_id task field")
        if fork.exists():
            text = fork.read_text()
            original = text
            old = '''#ifdef CONFIG_ACCESS_TOKENID
\ttsk->token = orig->token;
\ttsk->ftoken = 0;
#endif
'''
            new = '''#ifdef CONFIG_ACCESS_TOKENID
\ttsk->token = orig->token;
\ttsk->ftoken = 0;
\ttsk->user_id = orig->user_id;
#endif
'''
            if old in text:
                text = text.replace(old, new, 1)
            if text != original:
                fork.write_text(text)
                print(f"configured {fork}: inherit access_tokenid user_id on fork")

PY
}

ensure_flexlexer_header() {
  local src="/usr/include/FlexLexer.h"
  local dst="${OHOS_ROOT}/base/update/updater/services/script/script_interpreter/FlexLexer.h"

  if [ -f "${dst}" ]; then
    return
  fi
  if [ ! -f "${src}" ]; then
    echo "missing ${src}; install libfl-dev in the Docker image" >&2
    exit 1
  fi
  if [ ! -d "$(dirname "${dst}")" ]; then
    echo "missing updater script include dir: $(dirname "${dst}")" >&2
    exit 1
  fi
  if [ ! -f "${dst}" ] || ! cmp -s "${src}" "${dst}"; then
    cp "${src}" "${dst}"
    echo "configured ${dst}: copied Docker FlexLexer.h for updater yacc build"
  fi
}

clean_corrupt_hvigor_state() {
  cd "${OHOS_ROOT}"
  python3 - <<'PY'
from pathlib import Path
import shutil

removed = []
excluded_roots = {".repo", "out", "prebuilts"}
for source_root in Path(".").iterdir():
    if not source_root.is_dir() or source_root.name in excluded_roots:
        continue
    for dep_map in source_root.rglob(".hvigor/dependencyMap/oh-package.json5"):
        try:
            if dep_map.stat().st_size != 0:
                continue
        except FileNotFoundError:
            continue
        hvigor_dir = dep_map.parents[1]
        shutil.rmtree(hvigor_dir, ignore_errors=True)
        removed.append(str(hvigor_dir))

for path in removed:
    print(f"removed corrupt hvigor state: {path}")
PY
}

ensure_hvigor_sdkmanager_common() {
  local version="2.26.3"
  local registry="https://repo.harmonyos.com/npm/"
  local node_bin="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin"
  local npm="${node_bin}/npm"
  local target="${OHOS_ROOT}/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/@ohos/sdkmanager-common"
  if [ ! -x "${npm}" ] || [ ! -d "$(dirname "${target}")" ]; then
    return
  fi

  local installed=""
  if [ -f "${target}/package.json" ]; then
    installed="$(python3 - "${target}/package.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream).get("version", ""))
PY
)"
  fi
  if [ "${installed}" = "${version}" ]; then
    return
  fi

  local workdir archive
  workdir="$(mktemp -d "${CACHE_ROOT}/sdkmanager-common.XXXXXX")"
  archive="$({
    cd "${workdir}"
    PATH="${node_bin}:${PATH}" "${npm}" pack \
      "@ohos/sdkmanager-common@${version}" \
      --registry "${registry}" \
      --cache "${CACHE_ROOT}/npm-cache" \
      --silent
  } | tail -n 1)"
  tar -xzf "${workdir}/${archive}" -C "${workdir}"
  rm -rf "${target}"
  mv "${workdir}/package" "${target}"
  rm -rf "${workdir}"
  echo "updated Hvigor sdkmanager-common: ${installed:-missing} -> ${version}"
}

ensure_ohos_sdk_ets_loader_modules() {
  local sdk_root="${OHOS_ROOT}/prebuilts/ohos-sdk/linux"
  local node_bin="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin"
  local npm="${node_bin}/npm"
  if [ ! -x "${npm}" ] || [ ! -d "${sdk_root}" ]; then
    return
  fi

  local bundled_modules_source=""
  local candidate
  for candidate in \
    "${sdk_root}/23/ets/build-tools/ets-loader/node_modules" \
    "${OHOS_ROOT}/developtools/ace_ets2bundle/compiler/node_modules"; do
    if [ -f "${candidate}/typescript/package.json" ] && \
      [ -f "${candidate}/arkguard/package.json" ]; then
      bundled_modules_source="${candidate}"
      break
    fi
  done

  local loader
  while IFS= read -r loader; do
    if [ ! -f "${loader}/node_modules/json5/package.json" ]; then
      echo "install SDK ets-loader modules: ${loader}"
      (
        cd "${loader}"
        PATH="${node_bin}:${PATH}" "${npm}" ci \
          --registry "${NPM_REGISTRY}" \
          --cache "${CACHE_ROOT}/npm-cache" \
          --ignore-scripts \
          --unsafe-perm
      )
    fi

    local module
    for module in typescript arkguard declgen hypium @ohos/hypium; do
      if [ -f "${loader}/node_modules/${module}/package.json" ]; then
        continue
      fi
      if [ -z "${bundled_modules_source}" ] || \
        [ ! -f "${bundled_modules_source}/${module}/package.json" ]; then
        echo "missing OpenHarmony ${module} prebuilt for SDK ets-loader" >&2
        return 1
      fi

      local module_parent="${loader}/node_modules/${module%/*}"
      local module_name="${module##*/}"
      local module_tmp="${module_parent}/.${module_name}.tmp.$$"
      if [ "${module_parent}" = "${loader}/node_modules/${module}" ]; then
        module_parent="${loader}/node_modules"
        module_tmp="${module_parent}/.${module_name}.tmp.$$"
      fi
      echo "install SDK ets-loader ${module} from: ${bundled_modules_source}"
      mkdir -p "${module_parent}"
      rm -rf "${module_tmp}"
      cp -a "${bundled_modules_source}/${module}" "${module_tmp}"
      rm -rf "${loader}/node_modules/${module}"
      mv "${module_tmp}" "${loader}/node_modules/${module}"
    done

    test -f "${loader}/node_modules/json5/package.json"
    test -f "${loader}/node_modules/typescript/package.json"
    test -f "${loader}/node_modules/arkguard/package.json"
  done < <(
    find "${sdk_root}" -mindepth 5 -maxdepth 5 -type f \
      -path '*/ets/build-tools/ets-loader/package-lock.json' \
      -print \
      | sed 's#/package-lock.json$##' \
      | sort
  )
}

main() {
  echo "cache root: ${CACHE_ROOT}"
  echo "home: ${CONTAINER_HOME}"
  echo "OpenHarmony root: ${OHOS_ROOT}"
  echo "package root: ${PACKAGE_ROOT}"
  echo "manifest: ${MANIFEST_URL} ${OHOS_BRANCH} groups=${MANIFEST_GROUPS}"
  echo "repo tool: ${REPO_URL}"
  echo "repo jobs: network=${REPO_JOBS} checkout=${REPO_CHECKOUT_JOBS}"
  echo "npm registry: ${NPM_REGISTRY}"
  echo "skip repo sync: ${SKIP_REPO_SYNC}"
  echo "allow non-Docker Ubuntu VM: ${ALLOW_NON_DOCKER}"
  echo "ccache max size: ${CCACHE_MAXSIZE}"
  echo "ccache dir: ${CCACHE_DIR}"
  echo "kernel build jobs: ${KERNEL_BUILD_JOBS}"
  echo "skip prebuilts: ${SKIP_PREBUILTS}"
  echo "no prebuilt sdk: ${NO_PREBUILT_SDK}"
  echo "build only load: ${BUILD_ONLY_LOAD}"
  echo "skip git lfs: ${SKIP_GIT_LFS}"
  echo "git lfs paths: ${GIT_LFS_PATHS}"
  echo "qemu fix access_tokenid abi: ${QEMU_FIX_ACCESS_TOKENID_ABI}"
  echo "qemu fix system compat symlinks: ${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}"
  echo "qemu fix case-insensitive selinux VERSION: ${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION}"
  echo "qemu fix case-insensitive XMP Endian.h: ${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN}"
  echo "qemu fix case-insensitive iptables variants: ${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}"
  echo "qemu fix MindSpore non-ARM hwcap include: ${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP}"
  echo "qemu fix VirtioFS node symlink copy: ${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY}"
  echo "qemu serialize shared Arkoala generator: ${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR}"
  echo "qemu fix VirtioFS kernel worktree copy: ${QEMU_FIX_VIRTIOFS_KERNEL_COPY}"
  echo "QEMU absolute pointer overlay: ${QEMU_ABSOLUTE_POINTER_OVERLAY}"
  echo "ccache on native out volume: ${QEMU_CCACHE_ON_OUT_VOLUME}"
  echo "armv7a full overlay: ${ARMV7A_FULL_OVERLAY}"
  echo "standard VPN overlay: ${STANDARD_VPN_OVERLAY}"
  echo "QEMU full 2in1 overlay: ${QEMU_2IN1_FULL_OVERLAY}"
  echo "device type: ${DEVICE_TYPE:-default (unset)}"
  echo "products: ${PRODUCTS[*]}"
  echo "source changes: system_compat_symlinks=${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS} access_tokenid_abi=${QEMU_FIX_ACCESS_TOKENID_ABI} mindspore_non_arm_hwcap=${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP} standard_vpn=${STANDARD_VPN_OVERLAY} absolute_pointer=${QEMU_ABSOLUTE_POINTER_OVERLAY}"

  raise_nofile_limit
  install_deps
  verify_armv7_kernel_host_deps
  ensure_python_modules
  configure_user_tools
  ensure_host_tools
  ensure_repo_tool
  prepare_checkout
  configure_out_volume_ccache
  sync_git_lfs_objects
  verify_git_lfs_objects
  prepare_ets12_separate_npm_install
  trap restore_ets12_prebuilts_config EXIT
  download_prebuilts
  restore_ets12_prebuilts_config
  trap - EXIT
  configure_ohos_node_path
  install_ets12_node_modules
  repair_ets12_node_modules
  ensure_python_modules
  ensure_hvigor_sdkmanager_common
  ensure_ohos_sdk_ets_loader_modules
  # armv7a_virt is generated from the arm64 product template. Generate it
  # before applying the managed phone/2in1 inheritance; otherwise the armv7
  # overlay recreates config.json and silently drops the selected profile.
  apply_armv7a_full_overlay
  configure_qemu_device_profile
  apply_standard_vpn_overlay
  apply_qemu_absolute_pointer_overlay
  fix_case_insensitive_selinux_version_header
  fix_case_insensitive_xmp_endian_header
  fix_case_insensitive_iptables_variants
  fix_case_insensitive_kernel_netfilter
  fix_mindspore_non_arm_hwcap_header
  fix_virtiofs_node_symlink_copy
  serialize_shared_arkoala_generator
  fix_virtiofs_kernel_source_copy
  configure_qemu_product_features
  ensure_flexlexer_header
  clean_corrupt_hvigor_state

  local product
  for product in "${PRODUCTS[@]}"; do
    build_product "${product}"
    if [ "${BUILD_ONLY_LOAD}" != "1" ]; then
      package_product "${product}"
      if [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" = "1" ]; then
        echo "prune packaged product output to conserve disk: out/${product}"
        remove_under_ohos_root "${OHOS_ROOT}/out/${product}"
      fi
    fi
  done

  echo
  if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
    echo "done. load-only validation completed for: ${PRODUCTS[*]}"
  else
    echo "done. packages:"
    find "${PACKAGE_ROOT}" -maxdepth 1 \( -name '*.tar.gz' -o -name '*.zip' \) -print | sort
  fi
}

main "$@"
