#!/usr/bin/env python3
"""Preserve the actual MMI held-button set in the existing ArkUI bitmask."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('adapter/ohos/entrance/mmi_event_convertor.cpp',
     '41d1324cdc8c914dcb25114f8b4972f2e1fe0f3f76d40d0f6cbd48b106c9edfe',
     '56b7d1d7c8eef8c7d43b41d310f8d7dd1d3ee04692889cb23f139ccd58f36445'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
