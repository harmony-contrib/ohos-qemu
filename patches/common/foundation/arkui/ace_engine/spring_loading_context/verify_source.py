#!/usr/bin/env python3
"""Pinned real frontend class export; reject unknown or partial source edits."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('interfaces/napi/kits/drag_controller/js_drag_controller.cpp',
     'b06fa3a72773f9f4a8b07f7a8b3317b8b50aa6f33cf6725031b58238a7d2acc9',
     '6642e2054e1dc116f1b99fe4ed14476684f8e00bd21c5becb79ae7225a3e5dc4'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
