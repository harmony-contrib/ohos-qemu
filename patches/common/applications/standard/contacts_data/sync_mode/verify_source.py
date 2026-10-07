#!/usr/bin/env python3
"""Reject unknown ContactsData source states before the API26 enum repair."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/contacts_data'
REVISION = 'c73bd27daa3fcd8ed6099b17cbffbd7021e3873e'
FILES = (('contacts/src/contacts_api.cpp',
          '018501eb1fe4ac1792a7150004512c45238ef9a38b1b2e98d468de9c87b827e7',
          '1e695abbda171e24ba756d670f635ff5ee3cad748b5cdfe05a29f14002d85303'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('ContactSyncMode repair present: ' + str(validate(args.source_root, args.require_patched)))
