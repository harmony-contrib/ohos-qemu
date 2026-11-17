#!/usr/bin/env python3
"""Require the complete capture-end prerequisite and exact publication input."""
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

spec = importlib.util.spec_from_file_location('capture_end_prerequisite',
    Path(__file__).resolve().parent.parent / 'capture_end/verify_source.py')
prerequisite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prerequisite)
PROJECT = prerequisite.PROJECT
REVISION = prerequisite.REVISION
FILES = prerequisite.FILES[:-1] + ((prerequisite.FILES[-1][0],
    '4a4dce6793eadaec4dda7820b61c7d00f3a44daa7847f117f067a7b9dc61f27f',
    '7cb465950888f5075fe4436c82e556ed92567cb7d6b5777152c363c6a66c065a'),)


def validate(root, require_patched=False):
    validate_component(root, PROJECT, REVISION, FILES[:-1], require_patched=True)
    return validate_component(root, PROJECT, REVISION, FILES[-1:], require_patched)
