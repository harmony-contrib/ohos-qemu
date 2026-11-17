#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
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

spec = importlib.util.spec_from_file_location('virt_boot_unlock_baseline', component / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

if baseline.is_legacy_v1(root) or baseline.is_legacy_v2(root) or baseline.is_legacy_v3(root) or baseline.is_legacy_v4(root):
    proj_dir = root / baseline.PROJECT
    rel_files = [entry[0] for entry in baseline.FILES]
    subprocess.run(['git', '-C', str(proj_dir), 'checkout', '--', *rel_files], check=True)
    if baseline.validate(root):
        raise RuntimeError('expected pristine baseline after resetting legacy virt_boot_unlock')
PY
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
