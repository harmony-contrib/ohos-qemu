#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../.." && pwd)"
python3 - "${COMPONENT_DIR}" "$@" <<'PY'
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

component = Path(sys.argv[1]).resolve()
parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
args, _ = parser.parse_known_args(sys.argv[2:])
root = args.source_root.resolve()

spec = importlib.util.spec_from_file_location('display_modes_baseline', component / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

if baseline.is_legacy_v1(root):
    patch_v1 = component / '0001-accept-only-advertised-drm-modes-and-own-atomic-requests.patch'
    subprocess.run(['git', '-C', str(root), 'apply', '-R', '--check', str(patch_v1)], check=True)
    subprocess.run(['git', '-C', str(root), 'apply', '-R', '--whitespace=nowarn', str(patch_v1)], check=True)
    if baseline.validate(root):
        raise RuntimeError('expected pristine baseline after reversing legacy display_modes v1')
PY
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
