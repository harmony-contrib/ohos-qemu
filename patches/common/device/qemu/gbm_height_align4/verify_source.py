#!/usr/bin/env python3
"""Exact QEMU display_gralloc 4-row GBM height alignment (Issue #35)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'device/qemu'
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILES = (
    ('common/virt_full/hardware/display/src/display_gralloc/hi_gbm_internal.h',
     '01cc1be0d1d8e8ece4e99de9b01eb34a90b491050908357d8c84ab0b83e0b42f',
     '00766e695247c1bab5e972c922fff0aaa1a95b5f189413a6d2c8333c7a216fe2'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
