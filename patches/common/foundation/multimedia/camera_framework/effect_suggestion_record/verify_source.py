#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/camera_framework'
REVISION = 'a421fc5b11593deb06a1b3928ebdf81b2655870b'
FILES = [('frameworks/js/camera_napi/src/native_module_ohos_camera.cpp',
          '44af18bee2757a7018c9606e86cf4c55c2e4072be417e848d763cd4ea3f7f8db',
          '0151807f91b3ce18575490858620eeb060d1f76e09eac16e87de9c3bf41054da')]

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
