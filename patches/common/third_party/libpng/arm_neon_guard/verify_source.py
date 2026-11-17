#!/usr/bin/env python3
"""Exact third_party/libpng ARM64-only PNG_ARM_NEON define guard."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'third_party/libpng'
REVISION = '55ccafd48dabf5355887765faa6e92568622a9a6'
FILES = (
    ('BUILD.gn',
     '5bed71a5842ff3d05588c5fe8d957c21b450cfdf70a1f105ccda85dea67ece18',
     '4fe30ea667dc4779670ed951516f42e21bc914a43d5e2cb2aca42a20d78e3bc8'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
