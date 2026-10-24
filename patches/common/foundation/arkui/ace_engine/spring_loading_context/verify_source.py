#!/usr/bin/env python3
"""Pinned real frontend class export; reject unknown or partial source edits."""
from pathlib import Path
import hashlib
import importlib.util
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
    files = FILES
    target = Path(root) / PROJECT / FILES[0][0]
    if target.is_file():
        spec = importlib.util.spec_from_file_location('pixel_map_napi_cfi_successor',
            Path(__file__).resolve().parent.parent / 'pixel_map_napi_cfi/verify_source.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        successor = next(after for name, _, after in guard.FILES if name == FILES[0][0])
        if hashlib.sha256(target.read_bytes()).hexdigest() == successor:
            guard.validate(root, require_patched=True)
            files = ((FILES[0][0], FILES[0][1], successor),)
    return validate_component(root, PROJECT, REVISION, files, require_patched)
