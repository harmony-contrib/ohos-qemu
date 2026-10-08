#!/usr/bin/env python3
"""Pinned ARMv7 historical-Mesa action dependency contract."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'third_party/mesa3d'
REVISION = '952a438c56ce20610d88f0c4d8c673485aefeff7'
OFFICIAL_GNI_SHA = 'bd0108443d310e70fc5be312240b244de6dc1973439029f5cecf51391bd978fc'
FILES = (
    ('ohos/BUILD.gn',
     'cf448776cd41ac7180d9f699e6fd7d30ff5b455e365b55f4c214118b7572f465',
     '6f009ea7e6bb37219c5a3e3adf3c46644e3915b05b45d3d0e009d05e4ee4da24'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('verified ARMv7 Mesa mapping build inputs: ' + str(validate(args.source_root, args.require_patched)))
