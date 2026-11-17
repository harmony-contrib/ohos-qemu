#!/usr/bin/env python3
"""Exact public Attribute export and database input-boundary repair."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/contacts_data'
REVISION = 'c73bd27daa3fcd8ed6099b17cbffbd7021e3873e'
FILES = (
    ('contacts/include/contacts_napi_object.h',
     '383f0c8028924bb6f1f15368e67a91a3faa279514fe931b9790949c64a3f04ab',
     'bdc17782c1e19d44da4c93e942fd75eeea10f500b7fa2c95e24d98d908f93f46'),
    ('contacts/src/contacts_build.cpp',
     'af29778abb078a59a2164d9033ae475274085a5537d4eef6045ae3d1e4f0f155',
     '14ffa0847c8d374215fd63f5986ac412530fef0a302fd9298f3495969899231f'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Contact Attribute repair present: ' + str(validate(args.source_root, args.require_patched)))
