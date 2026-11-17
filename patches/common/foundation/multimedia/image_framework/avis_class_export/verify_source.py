#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/image_framework'
REVISION = '711db218c8d1c4d6546b28d8cf466059644dfa77'
FILES = [
    ('frameworks/kits/js/common/native_module_ohos_image.cpp',
     'a8e562a6a61d64f283d446f5c3f2c4c62226acee50f0675d6ad33a36fc677ab2',
     '7d4a15c150a98bbd60e7eb83b3f199db31f93e8c90f10e8984151a344ae4c62d'),
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
