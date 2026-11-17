#!/usr/bin/env bash
# Install only exact new whitelist DATA; original TE/checkers/global baseline stay untouched.
set -euo pipefail
fail() { printf '%s\n' "qemu_sh_baseline: $*" >&2; exit 2; }
source_root=''
profile=''
seen_source=0
seen_profile=0
while (($#)); do
  case "$1" in
    --source-root)
      [[ "$seen_source" == 0 && $# -ge 2 && -n "$2" ]] || fail 'one explicit --source-root is required'
      source_root="$2"
      seen_source=1
      shift 2
      ;;
    --profile)
      [[ "$seen_profile" == 0 && $# -ge 2 && -n "$2" ]] || fail 'one explicit --profile is required'
      profile="$2"
      seen_profile=1
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ "$seen_source" == 1 && "$seen_profile" == 1 ]] || fail 'required: --source-root ABSOLUTE --profile phone|2in1|none'
case "$profile" in phone|2in1|none) ;; *) fail 'profile must be phone, 2in1 or none' ;; esac
[[ "$source_root" == /* && -d "$source_root" && ! -L "$source_root" ]] || fail 'absolute unaliased source directory required'
physical_root="$(cd -P -- "$source_root" && pwd -P)"
[[ "$physical_root" == "$source_root" ]] || fail 'source-root spelling must equal its physical absolute path'
component_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
patch_root="$(cd -P -- "$component_dir/../../../../.." && pwd -P)"
vector="$patch_root/lib/guarded_source_vector579.py"
# A read-only whole-byte guard. Ancestor links are rejected before reading.
guard_file() {
  local path="$1" expected_sha="$2" expected_bytes="$3" probe="$1" observed_sha observed_bytes
  while [[ "$probe" != / ]]; do
    [[ ! -L "$probe" ]] || fail "linked guard input: $path"
    probe="${probe%/*}"
    [[ -n "$probe" ]] || probe=/
  done
  [[ -f "$path" ]] || fail "regular guard input required: $path"
  observed_bytes="$(wc -c < "$path")"
  [[ "$observed_bytes" -eq "$expected_bytes" ]] || fail "guard input size differs: $path"
  observed_sha="$(sha256sum < "$path")"
  [[ "${observed_sha%% *}" == "$expected_sha" ]] || fail "guard input SHA256 differs: $path"
}
readonly_sources() {
  guard_file "$source_root/base/security/selinux_adapter/sepolicy/whitelist/sh.baseline" "e4b1f859f82eb247e0a033442283080760ea9d2228dd3fc1031a50da6da9f3e2" 11899
  guard_file "$source_root/base/security/selinux_adapter/scripts/selinux_check/check_baseline.py" "cf43aa4a900d964d17096834b03824f20d1389d7b38ba31f62477a2405c3b421" 6864
  guard_file "$source_root/base/security/selinux_adapter/scripts/selinux_check/check_common.py" "7efca845d36318b5af877e0f98a621a270c8a07b102899d5204b9bf116910b7e" 3146
  guard_file "$source_root/base/security/selinux_adapter/scripts/selinux_check/config/glb_def.txt" "5defed5e05372310b48affac73aac5d1fbe00f57b6d251db393d7edbf485b3fc" 661
}
guard_file "$vector" "afb7560daa888493878e6d107baf1487f48c09fb6fe028fd89b331842e2b83ee" 9914
guard_file "$component_dir/cpu/source_states.json" "d245ed5ce77bdede663c0ffc6202faf382d2fa7a47e5fe7f835506f30cabffaf" 343
guard_file "$component_dir/cpu/0001-product-source.patch" "2b7347b029654d8400923644fcf36be92584ed787e827be95c69a16c0efd2581" 988
guard_file "$component_dir/usb/source_states.json" "0d28a046cbe418e499d0dc79e5f2e915407737664da7a1dd7291b521fa287b26" 343
guard_file "$component_dir/usb/0001-product-source.patch" "66172681d1a4b65706b37aedce88d936176f75ea69ea5ea499ff1c83fbc93efb" 872
readonly_sources
python3 "$vector" --component-dir "$component_dir/cpu" --source-root "$source_root"
python3 "$vector" --component-dir "$component_dir/cpu" --source-root "$source_root" --require-final
case "$profile" in
  phone|2in1)
    python3 "$vector" --component-dir "$component_dir/usb" --source-root "$source_root"
    python3 "$vector" --component-dir "$component_dir/usb" --source-root "$source_root" --require-final
    ;;
  none)
    python3 "$vector" --component-dir "$component_dir/usb" --source-root "$source_root" --rewind
    [[ ! -e "$source_root/base/security/selinux_adapter/sepolicy/whitelist/qemu_usb_sh.baseline" &&
       ! -L "$source_root/base/security/selinux_adapter/sepolicy/whitelist/qemu_usb_sh.baseline" ]] ||
      fail 'none profile must retain the exact absent USB baseline preimage'
    ;;
esac
readonly_sources
printf '%s\n' 'Exact QEMU shell baseline DATA prepared; newly packaged QEMU acceptance remains pending.'
