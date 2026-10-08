#!/usr/bin/env python3
"""Skip only the exact official GN file that has no generated ARMv7 action."""
import argparse
from pathlib import Path
import subprocess
import sys

from verify_source import FILES, OFFICIAL_GNI_SHA, PROJECT, REVISION
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import digest, validate_component

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    path = root / PROJECT / 'ohos/BUILD.gn'
    if digest(path.read_bytes()) == OFFICIAL_GNI_SHA:
        validate_component(root, PROJECT, REVISION,
                           (('ohos/BUILD.gn', OFFICIAL_GNI_SHA, OFFICIAL_GNI_SHA),), require_patched=True)
        print('exact official Mesa GN has no generated ARMv7 action; no ARMv7 mapping build claim')
    else:
        subprocess.run([sys.executable, str(Path(__file__).resolve().parents[4] / 'lib/apply_exact_component.py'),
                        '--component-dir', str(Path(__file__).resolve().parent),
                        '--source-root', str(root)], check=True)
