#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  build_standard_qemu_in_docker.sh [arm64_virt] [x86_64_virt]

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
  REPO_URL            Repo tool mirror, default: https://gitee.com/oschina/repo.git
  REPO_JOBS           repo sync jobs, default: 8
  REPO_CHECKOUT_JOBS  repo checkout jobs, default: 1
  REPO_SYNC_RETRIES   repo sync retry attempts, default: 3
  BUILD_JOBS          build jobs, default: nproc
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
  GIT_LFS_PATHS       Space-separated paths to fetch with Git LFS, default: foundation/arkui/ace_engine

This script intentionally does not patch the OpenHarmony source tree. It builds
the official master full QEMU products and delegates launch command details to
vendor/ohemu qemu_run.sh through the packager.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGER="${SCRIPT_DIR}/package_standard_qemu.sh"

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
REPO_URL="${REPO_URL:-https://gitee.com/oschina/repo.git}"
REPO_NO_BUNDLE="${REPO_NO_BUNDLE:-1}"
REPO_NO_TAGS="${REPO_NO_TAGS:-0}"
REPO_FORCE_SYNC="${REPO_FORCE_SYNC:-1}"
REPO_JOBS="${REPO_JOBS:-8}"
REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS:-1}"
REPO_SYNC_RETRIES="${REPO_SYNC_RETRIES:-3}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
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
GIT_LFS_PATHS="${GIT_LFS_PATHS:-foundation/arkui/ace_engine}"
PRODUCTS=("$@")

if [ "${#PRODUCTS[@]}" -eq 0 ]; then
  PRODUCTS=(arm64_virt x86_64_virt)
fi

for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    arm64_virt|x86_64_virt) ;;
    *)
      echo "unsupported product for this no-patch build script: ${product}" >&2
      exit 2
      ;;
  esac
done

if [ "$(uname -s)" != "Linux" ]; then
  echo "this script must run inside a Linux container or host" >&2
  exit 1
fi

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
    repo \
    rsync \
    ruby \
    scons \
    unzip \
    u-boot-tools \
    wget \
    zip \
    zlib1g-dev
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

  local python_bin
  for python_bin in \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/current/bin/python3" \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/3.12.10/bin/python3"; do
    if [ -x "${python_bin}" ]; then
      ensure_python_module "${python_bin}" typing_extensions "typing_extensions>=4.12.2"
      ensure_python_module "${python_bin}" json5 json5
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
}

ensure_repo_tool() {
  if command -v repo >/dev/null 2>&1; then
    return
  fi
  if [ "$(id -u)" != "0" ]; then
    echo "repo command not found; install repo or rerun as root without SKIP_APT=1" >&2
    exit 1
  fi
  curl -fsSL https://gitee.com/oschina/repo/raw/fork_flow/repo-py3 -o /usr/local/bin/repo
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
    if [ ! -d "${OHOS_ROOT}/${path}/.git" ]; then
      echo "skip git lfs path without git metadata: ${path}"
      continue
    fi
    if git -C "${OHOS_ROOT}/${path}" lfs ls-files 2>/dev/null | grep -q .; then
      echo "git lfs pull: ${path}"
      git -C "${OHOS_ROOT}/${path}" lfs pull
    fi
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

build_product() {
  local product="$1"
  cd "${OHOS_ROOT}"
  export CCACHE_DIR="${CACHE_ROOT}/ccache"
  ccache -M 100G >/dev/null 2>&1 || true
  if [ "${CLEAN_KERNEL_OBJ}" = "1" ]; then
    rm -rf "${OHOS_ROOT}/out/KERNEL_OBJ"
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
  bash "${PACKAGER}" \
    --source-root "${OHOS_ROOT}" \
    --product "${product}" \
    --output-dir "${PACKAGE_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/package_${product}.log"
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
  echo "skip prebuilts: ${SKIP_PREBUILTS}"
  echo "no prebuilt sdk: ${NO_PREBUILT_SDK}"
  echo "build only load: ${BUILD_ONLY_LOAD}"
  echo "skip git lfs: ${SKIP_GIT_LFS}"
  echo "git lfs paths: ${GIT_LFS_PATHS}"
  echo "products: ${PRODUCTS[*]}"
  echo "source patches: none"

  raise_nofile_limit
  install_deps
  ensure_python_modules
  configure_user_tools
  ensure_repo_tool
  prepare_checkout
  sync_git_lfs_objects
  download_prebuilts
  ensure_python_modules

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
