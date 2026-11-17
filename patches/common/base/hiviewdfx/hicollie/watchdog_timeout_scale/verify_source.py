#!/usr/bin/env python3
"""Scale HiCollie Watchdog / XCollie / FFRT system-service timeouts by persist.sys.abilityms.timeout_unit_time_ratio."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/hiviewdfx/hicollie'
REVISION = '13daf4a2e18b570ff22813c192a1ffa252dfd2d2'
FILES = (
    ('frameworks/native/watchdog_inner.cpp',
     '6e8e60019d8c43a2616279c2ce9d6ab4bd1fa8e47db5844943855648e515cb5b',
     '5d63754cb6c05da1e19a24b2c949ba3320656fcac5cf363f0cf38d6b2670928d'),
    ('frameworks/native/watchdog_task.cpp',
     'db226ff5732490c05d7b934208d93da123beb5def212dd4b00574216aa05387b',
     '3eef9115fc306d2b6fb7eb3b4d16c5a317a542d42451f2aab86793a8409aae31'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print(validate(args.source_root.resolve(), require_patched=args.require_patched))
