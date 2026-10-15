"""Exact WithEnv fallback to the owning pipeline font scale."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('frameworks/bridge/declarative_frontend/jsview/js_view.cpp', '1466048924f330c28249b723e1fb41bdebbc53c7d0d3f0cc3ed97538d7c610f5', '82543a7ac5df453694308d783b4594b3e2291dbcfa38498163394e54602da4f9'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
