#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'commonlibrary/ets_utils'
REVISION = '37cafe4c6d96858e976107d41d4f723adfde4a61'
FILES = [
    ('js_concurrent_module/taskpool/task_manager.cpp',
     '2bf43ac0898bcf527428a7e236509f463a887f33e13cf852d2478de48ca9681b',
     'c9342c3e0aaa40b9a4df160e9e7f03b4f761222712f99f517028b7a568518fcb'),
    ('js_concurrent_module/taskpool/worker.h',
     '1fb808e31b89c264d63c88932eeeea3d77c3985d75ca44a0c0adb0edde5186f3',
     '23f42f0a8a05525dbf7395dcbafc9399cf2ba77f5f27e73bbb9dd86a5d422666'),
]
CRLF_FILES = {PROJECT + '/js_concurrent_module/taskpool/worker.h'}


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
