#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --product) shift 2 ;;
    *) echo "unknown VPN dialog argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${SOURCE_ROOT}" ] || { echo "--source-root is required" >&2; exit 2; }
python3 - "${COMPONENT_DIR}/assets/vpndialog.p7b.b64" \
  "${SOURCE_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/signature/vpndialog.p7b" <<'PY'
import base64
import hashlib
import sys
from pathlib import Path

source, target = map(Path, sys.argv[1:])
payload = base64.b64decode("".join(source.read_text(encoding="ascii").split()), validate=True)
expected = "ae9c5803dd72143810aa1c87d306e7b04d7e1854924161e9bcd8a8de0c623022"
actual = hashlib.sha256(payload).hexdigest()
if actual != expected:
    raise SystemExit(f"VpnDialog profile checksum mismatch: {actual}")
target.parent.mkdir(parents=True, exist_ok=True)
if not target.is_file() or target.read_bytes() != payload:
    target.write_bytes(payload)
print(f"installed VpnDialog profile: {target}")
PY
