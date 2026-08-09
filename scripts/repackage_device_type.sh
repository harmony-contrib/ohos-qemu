#!/usr/bin/env bash
# Repackage existing openharmony-qemu-* packages with a forced deviceType
# (const.product.devicetype / const.build.characteristics).
#
# This does NOT rebuild OpenHarmony components for a true 2in1 inherit set.
# It only changes the system-parameter deviceType that BMS / deviceInfo use.
# Full component rebuild still requires Linux Docker + build.sh --device-type.
set -euo pipefail
export LC_ALL=C
export LANG=C
# Prevent macOS AppleDouble (._*) resource forks when copying/tarring.
export COPYFILE_DISABLE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGER="${SCRIPT_DIR}/package_standard_qemu.sh"

usage() {
  cat <<'USAGE'
Usage:
  repackage_device_type.sh \
    --device-type TYPE \
    --output-dir DIR \
    --input-package DIR [--input-package DIR ...]

  repackage_device_type.sh \
    --device-type TYPE \
    --output-dir DIR \
    --input-tarball FILE.tar.gz [--input-tarball FILE ...]

  repackage_device_type.sh \
    --device-type TYPE \
    --output-dir DIR \
    --input-root ROOT

Options:
  --device-type TYPE       Target deviceType (e.g. 2in1, phone, default).
  --output-dir DIR         Directory for new packages and tar.gz archives.
  --input-package DIR      Existing package directory (repeatable).
  --input-tarball FILE     Existing package .tar.gz (repeatable; preferred:
                           clean release tarballs avoid dirty userdata).
  --input-root ROOT        Scan ROOT for openharmony-qemu-* package dirs.
  --kernel-from DIR        Optional package dir whose images/{Image,bzImage,zImage}
                           replace the input kernels (e.g. jitfix kernels on a
                           clean userdata base).
  --rewrite-launchers      Also refresh launch/ via package_standard_qemu.sh.
  --name-suffix SUFFIX     Package name suffix (default: -<device-type>).
  --allow-dirty-userdata   Permit runtime-dirtied userdata.img (archives bloat).
                           Default is to refuse userdata gzip-1 > 200MB so
                           shippable packages stay near clean-release size.
  --keep-workdir           Keep extracted/work dirs under output for debug.
  -h, --help               Show this help.

Requires debugfs (e2fsprogs). On macOS:
  brew install e2fsprogs
  export PATH="$(brew --prefix e2fsprogs)/sbin:$PATH"
USAGE
}

DEVICE_TYPE=
OUTPUT_DIR=
NAME_SUFFIX_SET=0
NAME_SUFFIX=
REWRITE_LAUNCHERS=0
KEEP_WORKDIR=0
ALLOW_DIRTY_USERDATA=0
KERNEL_FROM=
INPUT_PACKAGES=()
INPUT_TARBALLS=()
INPUT_ROOT=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --device-type)
      DEVICE_TYPE="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --input-package)
      INPUT_PACKAGES+=("${2:-}")
      shift 2
      ;;
    --input-tarball)
      INPUT_TARBALLS+=("${2:-}")
      shift 2
      ;;
    --input-root)
      INPUT_ROOT="${2:-}"
      shift 2
      ;;
    --kernel-from)
      KERNEL_FROM="${2:-}"
      shift 2
      ;;
    --rewrite-launchers)
      REWRITE_LAUNCHERS=1
      shift
      ;;
    --name-suffix)
      NAME_SUFFIX_SET=1
      NAME_SUFFIX="${2-}"
      shift 2
      ;;
    --keep-workdir)
      KEEP_WORKDIR=1
      shift
      ;;
    --allow-dirty-userdata)
      ALLOW_DIRTY_USERDATA=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${DEVICE_TYPE}" ] || [ -z "${OUTPUT_DIR}" ]; then
  usage >&2
  exit 2
fi

case "${DEVICE_TYPE}" in
  default|phone|tablet|2in1|tv|wearable|car|liteWearable) ;;
  *)
    echo "unsupported device type: ${DEVICE_TYPE}" >&2
    echo "expected one of: default phone tablet 2in1 tv wearable car liteWearable" >&2
    exit 2
    ;;
esac

if [ "${NAME_SUFFIX_SET}" -eq 0 ]; then
  NAME_SUFFIX="-${DEVICE_TYPE}"
fi

if [ -n "${INPUT_ROOT}" ]; then
  while IFS= read -r -d '' dir; do
    INPUT_PACKAGES+=("${dir}")
  done < <(find "${INPUT_ROOT}" -mindepth 1 -maxdepth 1 -type d -name 'openharmony-qemu-*' -print0 | sort -z)
fi

if [ "${#INPUT_PACKAGES[@]}" -eq 0 ] && [ "${#INPUT_TARBALLS[@]}" -eq 0 ]; then
  echo "no input packages or tarballs specified" >&2
  usage >&2
  exit 2
fi

# Prefer Homebrew e2fsprogs on macOS (sbin is often not on PATH).
if ! command -v debugfs >/dev/null 2>&1; then
  for candidate in \
    /opt/homebrew/opt/e2fsprogs/sbin/debugfs \
    /usr/local/opt/e2fsprogs/sbin/debugfs
  do
    if [ -x "${candidate}" ]; then
      export PATH="$(dirname "${candidate}"):${PATH}"
      break
    fi
  done
  # Cellar wildcard
  for path in /opt/homebrew/Cellar/e2fsprogs/*/sbin/debugfs /usr/local/Cellar/e2fsprogs/*/sbin/debugfs; do
    if [ -x "${path}" ]; then
      export PATH="$(dirname "${path}"):${PATH}"
      break
    fi
  done
fi

if ! command -v debugfs >/dev/null 2>&1; then
  echo "debugfs not found; install e2fsprogs first" >&2
  exit 1
fi

if [ ! -x "${PACKAGER}" ]; then
  echo "missing packager: ${PACKAGER}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"
WORKDIR="${OUTPUT_DIR}/.repackage-work-$$"
mkdir -p "${WORKDIR}"
cleanup() {
  if [ "${KEEP_WORKDIR}" -eq 0 ]; then
    rm -rf "${WORKDIR}"
  fi
}
trap cleanup EXIT

replace_or_append_param() {
  local file="$1"
  local key="$2"
  local line="$3"
  if grep -q -E "^[[:space:]]*${key}[[:space:]]*=" "${file}"; then
    if sed --version >/dev/null 2>&1; then
      sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*$|${line}|" "${file}"
    else
      sed -i '' -E "s|^[[:space:]]*${key}[[:space:]]*=.*$|${line}|" "${file}"
    fi
  else
    printf '%s\n' "${line}" >> "${file}"
  fi
}

inject_device_type() {
  local image="$1"
  local device_type="$2"
  local tmpdir
  local ohos_para
  local path
  local wrote=0

  tmpdir="$(mktemp -d)"
  ohos_para="${tmpdir}/ohos.para"

  for path in /etc/param/ohos.para /system/etc/param/ohos.para; do
    if ! debugfs -R "stat ${path}" "${image}" 2>&1 | grep -q 'Inode:'; then
      continue
    fi
    debugfs -R "cat ${path}" "${image}" > "${ohos_para}" 2>/dev/null || : > "${ohos_para}"
    if grep -q '^const\.' "${ohos_para}" 2>/dev/null; then
      grep -E '^(#|const\.|persist\.|[[:space:]]*$)' "${ohos_para}" > "${ohos_para}.clean" || true
      mv "${ohos_para}.clean" "${ohos_para}"
    fi
    replace_or_append_param "${ohos_para}" \
      "const.product.devicetype" "const.product.devicetype=${device_type}"
    replace_or_append_param "${ohos_para}" \
      "const.build.characteristics" "const.build.characteristics=${device_type}"
    debugfs -w -R "rm ${path}" "${image}" >/dev/null 2>&1 || true
    debugfs -w -R "write ${ohos_para} ${path}" "${image}" >/dev/null
    wrote=1
    echo "  updated ${path} -> deviceType=${device_type}"
  done

  rm -rf "${tmpdir}"

  if [ "${wrote}" -ne 1 ]; then
    echo "unable to locate ohos.para in ${image}" >&2
    exit 1
  fi
}

verify_device_type() {
  local image="$1"
  local device_type="$2"
  local path
  local content
  for path in /etc/param/ohos.para /system/etc/param/ohos.para; do
    if ! debugfs -R "stat ${path}" "${image}" 2>&1 | grep -q 'Inode:'; then
      continue
    fi
    content="$(debugfs -R "cat ${path}" "${image}" 2>/dev/null || true)"
    if ! printf '%s\n' "${content}" | grep -qx "const.product.devicetype=${device_type}"; then
      echo "verify failed: const.product.devicetype!=${device_type} in ${path}" >&2
      printf '%s\n' "${content}" | grep 'devicetype\|characteristics' >&2 || true
      exit 1
    fi
    if ! printf '%s\n' "${content}" | grep -qx "const.build.characteristics=${device_type}"; then
      echo "verify failed: const.build.characteristics!=${device_type} in ${path}" >&2
      exit 1
    fi
    echo "  verified ${path}"
    return 0
  done
  echo "verify failed: ohos.para missing after inject" >&2
  exit 1
}

update_manifest_device_type() {
  local manifest="$1"
  local device_type="$2"
  local base_product="$3"
  local notes="$4"
  python3 - "${manifest}" "${device_type}" "${base_product}" "${notes}" <<'PY'
import json, sys
path, device_type, base_product, notes = sys.argv[1:5]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["device_type"] = device_type
data["device_type_source"] = "repackage_param_inject"
data["device_type_profile"] = "param_only"
data["base_product"] = data.get("product") or base_product
if notes:
    data["repackage_notes"] = notes
caps = data.setdefault("capabilities", {})
caps["device_type"] = device_type
# Param injection does not change or prove the source product profile.
caps["device_type_param_only"] = True
caps["device_type_full"] = False
caps["device_type_profile"] = "param_only"
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
}

warn_if_userdata_dirty() {
  local userdata="$1"
  # Heuristic: pristine empty-ish F2FS userdata gzips under ~20–180MB at -1.
  # Dirty runtime userdata often exceeds ~250MB compressed and bloated tar.gz
  # from ~620MB to ~1GB. Refuse by default for shippable packages.
  local gz
  gz="$(gzip -c -1 "${userdata}" | wc -c | tr -d ' ')"
  echo "  userdata.img gzip -1 size: ${gz} bytes"
  if [ "${gz}" -gt 200000000 ]; then
    echo "  ERROR: userdata.img looks dirty/runtime-used (poor compression)." >&2
    echo "         Prefer --input-tarball of a clean release package." >&2
    echo "         Or pass --allow-dirty-userdata for debug-only packages." >&2
    if [ "${ALLOW_DIRTY_USERDATA}" -eq 1 ]; then
      echo "  continuing because --allow-dirty-userdata was set" >&2
    else
      exit 1
    fi
  fi
}

copy_package_tree() {
  local src="$1"
  local dst="$2"
  rm -rf "${dst}"
  mkdir -p "${dst}"
  # Stream through tar to avoid cloning xattrs / resource forks.
  # macOS BSD tar: --no-mac-metadata when available.
  local tar_create=(tar -C "${src}" -cf -)
  local tar_extract=(tar -C "${dst}" -xf -)
  if tar --help 2>&1 | grep -q -- '--no-mac-metadata'; then
    tar_create=(tar -C "${src}" --no-mac-metadata -cf -)
    tar_extract=(tar -C "${dst}" --no-mac-metadata -xf -)
  fi
  "${tar_create[@]}" . | "${tar_extract[@]}"
  find "${dst}" \( -name '._*' -o -name '.DS_Store' \) -delete 2>/dev/null || true
}

maybe_overlay_kernels() {
  local out_images="$1"
  if [ -z "${KERNEL_FROM}" ]; then
    return
  fi
  local src_images="${KERNEL_FROM}/images"
  if [ ! -d "${src_images}" ]; then
    echo "kernel-from package missing images/: ${KERNEL_FROM}" >&2
    exit 1
  fi
  local k
  for k in Image bzImage zImage; do
    if [ -f "${src_images}/${k}" ]; then
      cp -f "${src_images}/${k}" "${out_images}/${k}"
      echo "  overlaid kernel ${k} from $(basename "${KERNEL_FROM}")"
    fi
  done
}

create_archive() {
  local output_dir="$1"
  local package_name="$2"
  (
    cd "${output_dir}"
    rm -f "${package_name}.tar.gz"
    # Prefer GNU tar sparse if present; else plain tar with COPYFILE_DISABLE.
    if command -v gtar >/dev/null 2>&1; then
      gtar --format=gnu -Sczf "${package_name}.tar.gz" "${package_name}"
    elif tar --help 2>&1 | grep -q -- '--no-mac-metadata'; then
      tar --no-mac-metadata -czf "${package_name}.tar.gz" "${package_name}"
    else
      COPYFILE_DISABLE=1 tar -czf "${package_name}.tar.gz" "${package_name}"
    fi
  )
}

repackage_one_dir() {
  local input_dir="$1"
  local base_name
  local product
  local out_name
  local out_dir
  local notes=""

  if [ ! -d "${input_dir}" ]; then
    echo "input package not found: ${input_dir}" >&2
    exit 1
  fi
  if [ ! -f "${input_dir}/images/system.img" ]; then
    echo "missing images/system.img in ${input_dir}" >&2
    exit 1
  fi
  if [ ! -f "${input_dir}/manifest.json" ]; then
    echo "missing manifest.json in ${input_dir}" >&2
    exit 1
  fi

  input_dir="$(cd "${input_dir}" && pwd)"
  base_name="$(basename "${input_dir}")"
  # Strip prior -2in1/-phone style suffix before re-applying.
  base_name="${base_name%-2in1}"
  base_name="${base_name%-phone}"
  base_name="${base_name%-default}"
  if [ -n "${NAME_SUFFIX}" ] && [[ "${base_name}" == *"${NAME_SUFFIX}" ]]; then
    out_name="${base_name}"
  else
    out_name="${base_name}${NAME_SUFFIX}"
  fi
  out_dir="${OUTPUT_DIR}/${out_name}"

  echo "==> repackage $(basename "${input_dir}") -> ${out_name} (deviceType=${DEVICE_TYPE})"

  copy_package_tree "${input_dir}" "${out_dir}"
  maybe_overlay_kernels "${out_dir}/images"
  if [ -n "${KERNEL_FROM}" ]; then
    notes="kernels_from=$(basename "${KERNEL_FROM}")"
  fi

  if [ -f "${out_dir}/images/userdata.img" ]; then
    warn_if_userdata_dirty "${out_dir}/images/userdata.img"
  fi

  product="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("product",""))' \
    "${out_dir}/manifest.json")"
  if [ -z "${product}" ]; then
    echo "unable to read product from manifest" >&2
    exit 1
  fi

  inject_device_type "${out_dir}/images/system.img" "${DEVICE_TYPE}"
  verify_device_type "${out_dir}/images/system.img" "${DEVICE_TYPE}"
  update_manifest_device_type "${out_dir}/manifest.json" "${DEVICE_TYPE}" "${product}" "${notes}"

  if [ "${REWRITE_LAUNCHERS}" -eq 1 ]; then
    bash "${PACKAGER}" --rewrite-package "${out_dir}"
  fi

  (
    cd "${out_dir}"
    find images launch -type f -print0 2>/dev/null | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  )

  create_archive "${OUTPUT_DIR}" "${out_name}"

  echo "    wrote ${out_dir}"
  echo "    wrote ${OUTPUT_DIR}/${out_name}.tar.gz ($(du -h "${OUTPUT_DIR}/${out_name}.tar.gz" | awk '{print $1}'))"
}

# Expand tarballs into workdir packages then process.
if [ "${#INPUT_TARBALLS[@]}" -gt 0 ]; then
  for tb in "${INPUT_TARBALLS[@]}"; do
    if [ ! -f "${tb}" ]; then
      echo "tarball not found: ${tb}" >&2
      exit 1
    fi
    echo "==> extract $(basename "${tb}")"
    extract_dir="${WORKDIR}/$(basename "${tb}" .tar.gz)-src"
    rm -rf "${extract_dir}"
    mkdir -p "${extract_dir}"
    if tar --help 2>&1 | grep -q -- '--no-mac-metadata'; then
      tar --no-mac-metadata -xzf "${tb}" -C "${extract_dir}"
    else
      COPYFILE_DISABLE=1 tar -xzf "${tb}" -C "${extract_dir}"
    fi
    # Expect a single top-level package directory (bash 3.2 compatible).
    found_count=0
    found_dir=
    while IFS= read -r -d '' d; do
      found_count=$((found_count + 1))
      found_dir="${d}"
    done < <(find "${extract_dir}" -mindepth 1 -maxdepth 1 -type d -name 'openharmony-qemu-*' -print0)
    if [ "${found_count}" -ne 1 ]; then
      echo "expected exactly one openharmony-qemu-* dir in ${tb}, found ${found_count}" >&2
      exit 1
    fi
    INPUT_PACKAGES+=("${found_dir}")
  done
fi

if [ "${#INPUT_PACKAGES[@]}" -eq 0 ]; then
  echo "no packages to process after resolving inputs" >&2
  exit 1
fi

for pkg in "${INPUT_PACKAGES[@]}"; do
  repackage_one_dir "${pkg}"
done

echo "done: processed package(s) with deviceType=${DEVICE_TYPE} in ${OUTPUT_DIR}"
