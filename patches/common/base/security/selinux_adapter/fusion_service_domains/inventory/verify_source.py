#!/usr/bin/env python3
"""Register precisely the new domains; no permission or checker exemptions."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/security/selinux_adapter'
REVISION = 'cfc1d5b31a7438dbc87763f9222f00337221cf21'
FILES = (('sepolicy/whitelist/flex/domain_baseline.json',
          '16a6dfa37363eaa23ba4c886e7c6c2f939310017c0a804cdf2b72b9f17d04f52',
          'b3f841ff67559ee13c4e6745eb7344268815bd0302c99c82f5c85f19d287b9b8'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Exact Fusion SA domain inventory: ' + str(validate(args.source_root, args.require_patched)))
