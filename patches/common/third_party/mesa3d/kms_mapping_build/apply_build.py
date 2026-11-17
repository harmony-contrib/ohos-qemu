#!/usr/bin/env python3
"""Skip only the exact official GN file that has no generated ARMv7 action."""
import argparse
from pathlib import Path
import subprocess
import sys

from verify_source import FILES, OFFICIAL_GNI_SHA, PROJECT, REVISION
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import digest, validate_component

MAPPING_GN_SHA = '6f009ea7e6bb37219c5a3e3adf3c46644e3915b05b45d3d0e009d05e4ee4da24'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    path = root / PROJECT / 'ohos/BUILD.gn'
    actual = digest(path.read_bytes())
    if actual == MAPPING_GN_SHA:
        validate_component(root, PROJECT, REVISION,
                           (('ohos/BUILD.gn', MAPPING_GN_SHA, MAPPING_GN_SHA),), require_patched=True)
        subprocess.run(['git', '-C', str(root), 'apply', '--check',
                        str(Path(__file__).with_name('0002-track-import-lifetime-backport-input.patch'))], check=True)
        subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn',
                        str(Path(__file__).with_name('0002-track-import-lifetime-backport-input.patch'))], check=True)
        validate_component(root, PROJECT, REVISION, FILES, require_patched=True)
    elif actual == OFFICIAL_GNI_SHA:
        validate_component(root, PROJECT, REVISION,
                           (('ohos/BUILD.gn', OFFICIAL_GNI_SHA, OFFICIAL_GNI_SHA),), require_patched=True)
        print('exact official Mesa GN has no generated ARMv7 action; no ARMv7 mapping build claim')
    else:
        subprocess.run([sys.executable, str(Path(__file__).resolve().parents[4] / 'lib/apply_exact_component.py'),
                        '--component-dir', str(Path(__file__).resolve().parent),
                        '--source-root', str(root)], check=True)
