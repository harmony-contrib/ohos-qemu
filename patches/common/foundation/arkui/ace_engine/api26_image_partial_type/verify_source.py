#!/usr/bin/env python3
"""Exact fixed-release image-generation enum registration; not provider proof."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('interfaces/napi/kits/intelligence/image_generation/js_image_generation.cpp',
          '08a5e5975ea95073f5997c2b25b94f85bcc3c424e8461f4f3a37fb1e2e7e78b9',
          'ea25367bfee8a77d369b22497745d0d57663c64c26261a39efc11acfa4c3d25f'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
