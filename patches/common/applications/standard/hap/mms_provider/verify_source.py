#!/usr/bin/env python3
"""Exact pinned source build inputs; no runtime acceptance claim."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/hap'
REVISION = 'f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
FILES = (('BUILD.gn', 'f53e1d7c537ec63ef5c7ebb37b16bcd4a95e1d4a8a17fe68a034b0d65955b9d2', 'd35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
