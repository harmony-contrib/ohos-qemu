#!/usr/bin/env bash
# Cache the immutable Git LFS objects that the GitHub 7.0 mirrors expose as
# explanatory text stubs instead of normal LFS pointers.
set -euo pipefail
export LC_ALL=C
export LANG=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSET_MAP="${ASSET_MAP:-${SCRIPT_DIR}/../patches/common/build/github_lfs_assets/assets.tsv}"
CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
ASSET_ROOT="${OHOS_LFS_ASSET_ROOT:-${CACHE_ROOT}/artifacts/openharmony-7.0-lfs}"
LFS_JOBS="${LFS_JOBS:-10}"
GITCODE_LFS_DIRECT="${GITCODE_LFS_DIRECT:-1}"

case "${LFS_JOBS}" in
  ''|*[!0-9]*|0)
    echo "LFS_JOBS must be a positive integer" >&2
    exit 2
    ;;
esac
case "${GITCODE_LFS_DIRECT}" in 0|1) ;; *)
  echo "GITCODE_LFS_DIRECT must be 0 or 1" >&2
  exit 2
esac
[ -f "${ASSET_MAP}" ] || { echo "missing LFS asset map: ${ASSET_MAP}" >&2; exit 1; }
mkdir -p "${ASSET_ROOT}"

curl_lfs() {
  if [ "${GITCODE_LFS_DIRECT}" = "1" ]; then
    (
      unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
      curl --http1.1 -fsSL --connect-timeout 20 --retry 4 "$@"
    )
  else
    curl --http1.1 -fsSL --connect-timeout 20 --retry 4 "$@"
  fi
}

prepare_one() {
  local remote="$1"
  local oid="$2"
  local expected_size="$3"
  local object_dir="${ASSET_ROOT}/${oid:0:2}"
  local target="${object_dir}/${oid}"
  local endpoint="${remote%.git}.git/info/lfs/objects/batch"
  local actual actual_size request response href temp_file

  if [ -f "${target}" ]; then
    actual_size="$(wc -c < "${target}" | tr -d '[:space:]')"
    actual="$(shasum -a 256 "${target}" | awk '{print $1}')"
    if [ "${actual_size}" = "${expected_size}" ] && [ "${actual}" = "${oid}" ]; then
      return
    fi
    echo "replace invalid OpenHarmony LFS cache object: ${oid}" >&2
  fi

  mkdir -p "${object_dir}"
  request="{\"operation\":\"download\",\"transfers\":[\"basic\"],\"objects\":[{\"oid\":\"${oid}\",\"size\":${expected_size}}]}"
  response="$(curl_lfs \
    -H 'Accept: application/vnd.git-lfs+json' \
    -H 'Content-Type: application/vnd.git-lfs+json' \
    -d "${request}" "${endpoint}")"
  href="$(printf '%s' "${response}" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
obj = data.get("objects", [{}])[0]
if obj.get("error"):
    raise SystemExit(obj["error"].get("message", "Git LFS server error"))
print(obj["actions"]["download"]["href"])
')"

  temp_file="$(mktemp "${object_dir}/.${oid}.XXXXXX")"
  if ! curl_lfs "${href}" -o "${temp_file}"; then
    rm -f -- "${temp_file}"
    return 1
  fi
  actual_size="$(wc -c < "${temp_file}" | tr -d '[:space:]')"
  actual="$(shasum -a 256 "${temp_file}" | awk '{print $1}')"
  if [ "${actual_size}" != "${expected_size}" ] || [ "${actual}" != "${oid}" ]; then
    rm -f -- "${temp_file}"
    echo "OpenHarmony LFS object mismatch: ${oid} size=${actual_size} sha256=${actual}" >&2
    return 1
  fi
  chmod 0644 "${temp_file}"
  mv "${temp_file}" "${target}"
  echo "cached OpenHarmony LFS object: ${oid} (${expected_size} bytes)"
}

export ASSET_ROOT GITCODE_LFS_DIRECT
export -f curl_lfs prepare_one

python3 - "${ASSET_MAP}" <<'PY' \
  | sort -u \
  | xargs -n 3 -P "${LFS_JOBS}" bash -c 'prepare_one "$1" "$2" "$3"' _
import re
import sys
from pathlib import PurePosixPath

seen_paths = set()
for line_number, raw in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    if not raw.strip() or raw.startswith("#"):
        continue
    fields = raw.rstrip("\n").split("\t")
    if len(fields) != 5:
        raise SystemExit(f"invalid LFS map line {line_number}: expected five columns")
    repo_root, relative, remote, oid, size = fields
    for value, label in ((repo_root, "repo root"), (relative, "relative path")):
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"invalid {label} on LFS map line {line_number}")
    if (repo_root, relative) in seen_paths:
        raise SystemExit(f"duplicate LFS path on line {line_number}: {repo_root}/{relative}")
    seen_paths.add((repo_root, relative))
    if not remote.startswith("https://gitcode.com/openharmony/"):
        raise SystemExit(f"unexpected LFS remote on line {line_number}: {remote}")
    if not re.fullmatch(r"[0-9a-f]{64}", oid) or not size.isdigit() or int(size) <= 0:
        raise SystemExit(f"invalid LFS identity on line {line_number}")
    print(remote, oid, size)
PY

asset_count="$(awk -F '\t' '$1 !~ /^#/ && NF == 5 {count++} END {print count + 0}' "${ASSET_MAP}")"
echo "OpenHarmony 7.0 GitHub/LFS compatibility cache ready: ${ASSET_ROOT} (${asset_count} mapped assets)"
