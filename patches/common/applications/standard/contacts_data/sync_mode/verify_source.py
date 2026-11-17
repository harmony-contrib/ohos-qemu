#!/usr/bin/env python3
"""Reject unknown ContactsData source states before the API26 enum repair."""
import argparse
import hashlib
import importlib.util
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
    files = FILES
    path = Path(root) / PROJECT / FILES[0][0]
    final = 'e4d8a123de6ba2e943c6fda5e0258960376998f54fd61565e81e8b224beeb4d8'
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == final:
        spec = importlib.util.spec_from_file_location('contacts_picker_protocol_successor',
            Path(__file__).parent.parent / 'picker_result_protocol/verify_source.py')
        guard = importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        guard.validate(root, require_patched=True)
        files = ((FILES[0][0], FILES[0][1], final),)
    return validate_component(root, PROJECT, REVISION, files, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('ContactSyncMode repair present: ' + str(validate(args.source_root, args.require_patched)))
