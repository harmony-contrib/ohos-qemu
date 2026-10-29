#!/usr/bin/env python3
"""Accept only the whole pinned build strict-HAP-list before/after vector."""
import argparse
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'build'
REVISION = '5c0623072ed9c2ee93ab909a7a01f428fee95082'
FILES = (
    ('ohos/app/app.gni',
     '9ab0a880c5881d85e1ff14ebfb22b516bf53aa06402f8516f61ed05b8dd70845',
     '46c6db1d5028d9a4b9fb194af7e8c47453288a6fd3dae3491dc819a80412c2cd'),
    ('ohos/app/app_internal.gni',
     'efcc75e1463b6bd9920e8f25d84028b81cb066f5c50fd8006e425c87910b3426',
     'ed4adffda69a58f996e8729c392f78bdc32d5baf205f45a5fda97ffeb739ade3'),
    ('scripts/app_sign.py',
     '27b5d201b187e0bceac512944df8f1bbd3b8e67a4af8aa19d3e811e7c2d30b45',
     'c31459e346387c724eeadcc2be6ca9017f0592dc8372856811ed2e82159d7e23'),
)
MODES = (('ohos/app/app.gni', 420), ('ohos/app/app_internal.gni', 420), ('scripts/app_sign.py', 493))


def validate(root, require_patched=False):
    result = validate_component(root, PROJECT, REVISION, FILES, require_patched)
    for relative, expected_mode in MODES:
        target = Path(root).resolve() / PROJECT / relative
        if stat.S_IMODE(target.stat().st_mode) != expected_mode:
            raise ValueError('strict HAP component requires the pinned source mode: ' + relative)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('verified complete strict HAP list component: ' +
          str(validate(args.source_root, args.require_patched)))
