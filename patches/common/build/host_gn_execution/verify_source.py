#!/usr/bin/env python3
"""Only accept the complete fixed build-system before/after CPU adapter."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'build'
REVISION = '5c0623072ed9c2ee93ab909a7a01f428fee95082'
FILES = (
    ('scripts/util/file_utils.py',
     '898eba0639bbc91c47a5ef966ba12e154a110e4986a5cf5d128567b3fadd022d',
     '75d3688c12a75f0f7aa6c71a15a7aaca66f5b3558594a76800371eeb81c7d9a5'),
    ('hb/util/system_util.py',
     '9e5887c8dd2cf1ef19f015198fd918abb1302a6829a061516e60a0d6192bb415',
     'ba3f51c12ba137df261032518768535a86ad2b896a8e77b55f547db6514d260d'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('verified complete host GN CPU adapter: ' + str(validate(args.source_root, args.require_patched)))
