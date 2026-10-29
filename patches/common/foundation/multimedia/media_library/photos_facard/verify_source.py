#!/usr/bin/env python3
"""Guard the native-to-real-Photos FA event target; do not attest delivery."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (
    ('services/media_facard/src/operation/medialibrary_facard_operations.cpp',
     '774b0c400113ba803b1fa3c0f1cf6fa54102adc07ad011f4c3fa90562886efae',
     'e0d88078b6a0bdb45f227b1de77914a32c0145d87263e1cbe25da5ecf768cbc5'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
