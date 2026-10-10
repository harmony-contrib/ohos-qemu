#!/usr/bin/env bash
set -euo pipefail
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    -h|--help) echo 'usage: apply.sh --source-root OHOS_ROOT'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo '--source-root is required' >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
bash "${PATCH_ROOT}/lib/apply_patch.sh" "${SOURCE_ROOT}" \
  "${SCRIPT_DIR}/0001-register-qemu-settings-shortcut.patch"
python3 - "${SOURCE_ROOT}" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
value = json.loads((root / 'foundation/multimodalinput/input/etc/ability_launch_config.json').read_text())
expected = dict(businessId='qemu.settings', preKey=[2076], finalKey=2025,
    trigger='key_down', keyDownDuration=500, statusConfig='',
    ability=dict(bundleName='com.ohos.settings', abilityName='com.ohos.settings.MainAbility'))
if value['Shortkeys'] != [expected]:
    raise SystemExit('QEMU Settings shortcut profile changed; review actual routing before build')
PY
