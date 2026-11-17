#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/contacts_data'
REVISION = 'c73bd27daa3fcd8ed6099b17cbffbd7021e3873e'
FILES = [
    ('contacts/src/native_module.cpp',
     '62ee0c5c18d0ebdf3c3b3b9caaff2e246713eb975d3712be00151eced6618379',
     '994663de97eaa8835bd5fbb6e11d569b8a117e0dbe02d25d1a8ae217c3fb4e50'),
    ('contacts/include/contacts_record_classes.h', None,
     '08ffca19368e55398ab59060e35db617cc4d91be7391d2a18aa12c5792de8546'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
