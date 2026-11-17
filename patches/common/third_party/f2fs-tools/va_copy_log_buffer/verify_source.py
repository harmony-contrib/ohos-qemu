#!/usr/bin/env python3
"""Exact x86_64 va_copy and 2048-byte log buffer fix in libf2fs_log.c (Issue #27)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'third_party/f2fs-tools'
REVISION = '680fef46e9f6208ee4e7c2c1bf284606a8b3e954'
FILES = (
    ('lib/libf2fs_log.c',
     'ba08cedc1c2bc48e7a10497959806e32de907d734922a025ddf5e3daefa8fe07',
     '1fbb4ce58d183dbbda7494ada7095de5d9481429ae2c1e393cc9ea8e7b013e8b'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
