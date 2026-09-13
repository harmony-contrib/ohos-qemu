#!/usr/bin/env bash
# Restore pinned binary assets that are text stubs in the GitHub mirrors.
set -euo pipefail
export LC_ALL=C
export LANG=C

SOURCE_ROOT=
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSET_MAP="${ASSET_MAP:-${SCRIPT_DIR}/assets.tsv}"
ASSET_ROOT="${OHOS_LFS_ASSET_ROOT:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --asset-root) ASSET_ROOT="${2:-}"; shift 2 ;;
    --asset-map) ASSET_MAP="${2:-}"; shift 2 ;;
    -h|--help)
      echo "usage: apply.sh --source-root OHOS_ROOT --asset-root CACHE [--asset-map TSV]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
[ -n "${ASSET_ROOT}" ] || { echo "--asset-root is required" >&2; exit 2; }
[ -f "${ASSET_MAP}" ] || { echo "missing LFS asset map: ${ASSET_MAP}" >&2; exit 1; }

verified=0
restored=0
while IFS=$'\t' read -r repo_root relative remote oid expected_size extra; do
  [ -n "${repo_root}" ] || continue
  case "${repo_root}" in \#*) continue ;; esac
  [ -z "${extra:-}" ] || { echo "invalid extra LFS map column for ${repo_root}/${relative}" >&2; exit 1; }
  case "${repo_root}/${relative}" in
    /*|*'/../'*|../*|*/..)
      echo "unsafe LFS asset path: ${repo_root}/${relative}" >&2
      exit 1
      ;;
  esac
  case "${oid}" in ''|*[!0-9a-f]*) echo "invalid LFS oid for ${repo_root}/${relative}" >&2; exit 1 ;; esac
  [ "${#oid}" -eq 64 ] || { echo "invalid LFS oid length for ${repo_root}/${relative}" >&2; exit 1; }
  case "${expected_size}" in ''|*[!0-9]*) echo "invalid LFS size for ${repo_root}/${relative}" >&2; exit 1 ;; esac

  target="${SOURCE_ROOT}/${repo_root}/${relative}"
  object="${ASSET_ROOT}/${oid:0:2}/${oid}"
  [ -f "${target}" ] || { echo "missing pinned source asset: ${repo_root}/${relative}" >&2; exit 1; }
  [ -f "${object}" ] || { echo "missing cached LFS object ${oid} for ${repo_root}/${relative}" >&2; exit 1; }

  object_size="$(wc -c < "${object}" | tr -d '[:space:]')"
  object_sha="$(sha256sum "${object}" | awk '{print $1}')"
  if [ "${object_size}" != "${expected_size}" ] || [ "${object_sha}" != "${oid}" ]; then
    echo "invalid cached LFS object ${oid} for ${repo_root}/${relative}" >&2
    exit 1
  fi

  target_sha="$(sha256sum "${target}" | awk '{print $1}')"
  if [ "${target_sha}" != "${oid}" ]; then
    marker_oid="$(sed -n 's/^oid sha256://p' "${target}")"
    marker_size="$(sed -n 's/^size //p' "${target}")"
    if ! grep -Fq 'This file was originally tracked by Git LFS' "${target}" || \
       [ "${marker_oid}" != "${oid}" ] || [ "${marker_size}" != "${expected_size}" ]; then
      echo "source asset does not match its pinned LFS stub: ${repo_root}/${relative}" >&2
      exit 1
    fi
    temp="${target}.ohos-qemu-lfs.$$"
    cp -p "${object}" "${temp}"
    mv "${temp}" "${target}"
    restored=$((restored + 1))
  fi

  case "${relative}" in
    *.tgz) tar -tzf "${target}" >/dev/null ;;
    *.hap|*.zip|*.jar) unzip -tq "${target}" >/dev/null ;;
  esac
  verified=$((verified + 1))
done < "${ASSET_MAP}"

echo "OpenHarmony GitHub/LFS assets verified: ${verified} (restored: ${restored})"
