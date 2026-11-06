#!/usr/bin/env python3
"""Prevent 10s XCollie suicidal _exit(0) in allocator_host under software emulation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
CRLF_FILES = ('drivers/peripheral/display/buffer/hdi_service/dfx/display_buffer_dfx.cpp',)
FILES = (
    ('display/buffer/hdi_service/dfx/display_buffer_dfx.cpp',
     '690b828f02c62590044dc7b545d079a370c369b0345def118ea5340b44beb67a',
     '4ff42edf9fb2554e0b088885d93533e33166a0ff978364c2e25886d290c2dcc0'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
