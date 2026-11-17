#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = [('frameworks/bridge/declarative_frontend/engine/jsStateManagement.js',
          '122f8ed56b2f1a6da12b21975724bd2ec8796b599f6617dfeb9ec2a9e9185c4e',
          '69e473e7b11073a454d8830d0fa223e72860f65cd10e8715c2e8f592deaaaf5f')]

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
