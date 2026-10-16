#!/usr/bin/env python3
"""Fail closed on drift or mixed business lifecycle patches."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/theme'
REVISION = 'a436a43f1c0948fa12df6d520ec695ae4388a057'
FILES = (
    ('product/phone/src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts', '12ebd3016fc3825cd277c12ff2e51b1300c35df34a6ffdec6b8f6d43cf722905', '84cde2fbed244e1e6e3562096f66d5948d9124c4030e7d1bd54b3fa39e761dac'),
    ('product/pad/src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts', '12ebd3016fc3825cd277c12ff2e51b1300c35df34a6ffdec6b8f6d43cf722905', '84cde2fbed244e1e6e3562096f66d5948d9124c4030e7d1bd54b3fa39e761dac'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
