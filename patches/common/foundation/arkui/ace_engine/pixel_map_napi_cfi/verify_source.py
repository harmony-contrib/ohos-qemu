#!/usr/bin/env python3
"""Exact source states required by the existing component apply helper."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "lib"))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('frameworks/bridge/js_frontend/engine/common/js_engine.cpp',
     '768261d8819b795dbdc27538604db58d0d6f9a0b2ebeb1f664fd0ce387b8aec1',
     '582661a058395e6679bbd65a7a33a6701bb5460844fbe68b19cf112161b1c48b'),
    ('frameworks/bridge/js_frontend/engine/common/js_engine.h',
     'a924caf8c08e447c02e9aa9571381561ea0865723298bfb10a04d57c1388a793',
     '21eb88e8514b9c119b97f2fa7698ffda7d975d728154d56b8b98cfcd34d63012'),
    ('interfaces/napi/kits/drag_controller/js_drag_controller.cpp',
     '6642e2054e1dc116f1b99fe4ed14476684f8e00bd21c5becb79ae7225a3e5dc4',
     'a191463f3363276a669590b68127cdc16e7f218b8f555cd419245d32cae223f7'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--require-final", action="store_true")
    args = parser.parse_args()
    validate(args.source_root, require_patched=args.require_final)
