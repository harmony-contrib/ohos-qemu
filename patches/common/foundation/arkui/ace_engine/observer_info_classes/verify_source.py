#!/usr/bin/env python3
"""Exact dynamic observer info classes and the required real density context."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('interfaces/napi/kits/observer/js_ui_observer.cpp',
     'ad8f5701e880c5d12539ec9059677e80e5677a8aeeb8bc8920546ab4484b27a4',
     '4dc7b5ac9ceb04e38fb4e16de9549e523e0614d136142ce85c61abca6ed49045'),
    ('interfaces/napi/kits/observer/ui_observer.cpp',
     '9befbe92003a92075d43385b9c3726e9ec1b52f1bd7e424f959d296e2132aa3f',
     '5ea24270c568a6a2f9766385112ef7dacaa9a6c6579ba240a21804897925745c'),
    ('interfaces/napi/kits/observer/ui_observer_listener.cpp',
     'ffb04de9b7941833c64581f9dd266ce3dbfdcae86c6fa1c5aea324ccca571eb0',
     'c175d8aee25a010921f1ddab7c46d2572c26c403ca8ecc9160d2fca858a43740'),
    ('interfaces/napi/kits/observer/ui_observer_listener.h',
     '61370e6e49ea525da88f749f5c96ccc58810e3b683095a8736309bfbf5652ae7',
     '7fd15639c45684508f3ba4c0dc7147236f77e792d41dfcd896991c470cf89b3e'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
