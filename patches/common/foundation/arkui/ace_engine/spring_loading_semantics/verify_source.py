#!/usr/bin/env python3
"""SDK BEGIN-only configuration and CANCEL optional fields."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('frameworks/bridge/declarative_frontend/engine/functions/js_drag_function.cpp',
     '96e1ab76603d03a906aa64f75bf5aa15a32cfcb4d74fa2ab7723c9a248a096d2',
     '739d78a71a5a73efd7eb6d4732a9e9e5cd6e122b2a8ccf6660cc46c1628696cd'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
