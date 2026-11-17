#!/usr/bin/env python3
"""Guard the pinned shared common-type output naming rule, not interface names."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'build'
REVISION = '5c0623072ed9c2ee93ab909a7a01f428fee95082'
FILES = (
    ('config/components/idl_tool/idl.gni',
     'a4787050abbcf6e8fe2b84c5de0a373fa8eb2c544872cc5b2b216ddd76e476dc',
     '8246760b8cc70805fdbd0ff31fd8b85f854f2673d957d0b76b83d18edb14784f'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('verified common-type IDL output rule: ' + str(validate(args.source_root, args.require_patched)))
