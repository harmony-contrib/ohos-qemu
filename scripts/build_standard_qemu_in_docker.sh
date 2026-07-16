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
  CCACHE_MAXSIZE      ccache size limit, default: 100G
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
  ARMV7A_FULL_OVERLAY Apply experimental armv7a_virt full overlay, default: 1

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
CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-100G}"
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
GIT_LFS_PATHS="${GIT_LFS_PATHS:-applications/standard/hap base/web/webview foundation/arkui/ace_engine third_party/icu third_party/libphonenumber}"
QEMU_FIX_ACCESS_TOKENID_ABI="${QEMU_FIX_ACCESS_TOKENID_ABI:-${QEMU_FIX_ACCESS_TOKENID_SPM:-1}}"
QEMU_FIX_SYSTEM_COMPAT_SYMLINKS="${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS:-1}"
ARMV7A_FULL_OVERLAY="${ARMV7A_FULL_OVERLAY:-1}"
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
  if [ ! -f /.dockerenv ] && ! grep -qaE '/(docker|containerd|kubepods)(/|$)' /proc/1/cgroup 2>/dev/null; then
    echo "this build must run inside Docker, not directly on the host" >&2
    exit 1
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
  apt-get install -y --no-install-recommends \
    autoconf \
    automake \
    bc \
    bison \
    build-essential \
    ca-certificates \
    ccache \
    cmake \
    cpio \
    curl \
    default-jdk \
    dosfstools \
    e2fsprogs \
    file \
    flex \
    g++ \
    gcc \
    gcc-arm-none-eabi \
    genext2fs \
    git \
    git-lfs \
    gettext \
    gperf \
    lib32stdc++6 \
    lib32z1 \
    libc6-dev-i386 \
    libelf-dev \
    libfl-dev \
    libgmp-dev \
    libmpc-dev \
    libmpfr-dev \
    libncurses5 \
    libncurses5-dev \
    libncursesw5-dev \
    libssl-dev \
    libxml2-utils \
    libtool \
    make \
    mtd-utils \
    mtools \
    ninja-build \
    openssh-client \
    openssl \
    pkg-config \
    python-is-python3 \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-venv \
    rsync \
    ruby \
    scons \
    unzip \
    u-boot-tools \
    wget \
    zip \
    zlib1g-dev

  command -v git >/dev/null
  command -v ssh >/dev/null
  if [ ! -f /usr/include/FlexLexer.h ]; then
    echo "missing /usr/include/FlexLexer.h; install libfl-dev in the Docker image" >&2
    exit 1
  fi

  git lfs install --system >/dev/null 2>&1 || true
}

ensure_python_module() {
  local python_bin="$1"
  local module="$2"
  local package="$3"
  if ! command -v "${python_bin}" >/dev/null 2>&1 && [ ! -x "${python_bin}" ]; then
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
  if ! "${python_bin}" -m pip install \
    --trusted-host repo.huaweicloud.com \
    -i https://repo.huaweicloud.com/repository/pypi/simple \
    "${package}"; then
    "${python_bin}" -m pip install \
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
  mkdir -p "${CACHE_ROOT}" "${OHOS_ROOT}" "${PACKAGE_ROOT}" "${CACHE_ROOT}/logs" "${CACHE_ROOT}/ccache"
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
  export CCACHE_DIR="${CACHE_ROOT}/ccache"
  ccache -M "${CCACHE_MAXSIZE}" >/dev/null 2>&1 || true
  if [ "${CLEAN_KERNEL_OBJ}" = "1" ]; then
    rm -rf "${OHOS_ROOT}/out/KERNEL_OBJ"
    rm -rf "${OHOS_ROOT}/out/kernel/OBJ/${kernel_obj}"
    rm -f "${OHOS_ROOT}/out/${product}/packages/phone/images/${kernel_image}"
  fi

  local build_args=(
    ./build.sh
    --product-name "${product}"
    --ccache
    --jobs "${BUILD_JOBS}"
    --load-test-config=false
    --deps-guard=false
  )
  if [ "${NO_PREBUILT_SDK}" = "1" ]; then
    build_args+=(--no-prebuilt-sdk=true)
  fi
  if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
    build_args+=(--build-only-load=true)
  fi
  "${build_args[@]}" 2>&1 | tee "${CACHE_ROOT}/logs/build_${product}.log"
}

package_product() {
  local product="$1"
  validate_prebuilt_haps "${product}"
  bash "${PACKAGER}" \
    --source-root "${OHOS_ROOT}" \
    --product "${product}" \
    --output-dir "${PACKAGE_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/package_${product}.log"
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
for dep_map in Path(".").rglob(".hvigor/dependencyMap/oh-package.json5"):
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
  echo "ccache max size: ${CCACHE_MAXSIZE}"
  echo "skip prebuilts: ${SKIP_PREBUILTS}"
  echo "no prebuilt sdk: ${NO_PREBUILT_SDK}"
  echo "build only load: ${BUILD_ONLY_LOAD}"
  echo "skip git lfs: ${SKIP_GIT_LFS}"
  echo "git lfs paths: ${GIT_LFS_PATHS}"
  echo "qemu fix access_tokenid abi: ${QEMU_FIX_ACCESS_TOKENID_ABI}"
  echo "qemu fix system compat symlinks: ${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}"
  echo "armv7a full overlay: ${ARMV7A_FULL_OVERLAY}"
  echo "products: ${PRODUCTS[*]}"
  echo "source changes: system_compat_symlinks=${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS} access_tokenid_abi=${QEMU_FIX_ACCESS_TOKENID_ABI}"

  raise_nofile_limit
  install_deps
  ensure_python_modules
  configure_user_tools
  ensure_host_tools
  ensure_repo_tool
  prepare_checkout
  sync_git_lfs_objects
  prepare_ets12_separate_npm_install
  trap restore_ets12_prebuilts_config EXIT
  download_prebuilts
  restore_ets12_prebuilts_config
  trap - EXIT
  install_ets12_node_modules
  repair_ets12_node_modules
  ensure_python_modules
  ensure_hvigor_sdkmanager_common
  ensure_ohos_sdk_ets_loader_modules
  apply_armv7a_full_overlay
  configure_qemu_product_features
  ensure_flexlexer_header
  clean_corrupt_hvigor_state

  local product
  for product in "${PRODUCTS[@]}"; do
    build_product "${product}"
    if [ "${BUILD_ONLY_LOAD}" != "1" ]; then
      package_product "${product}"
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
