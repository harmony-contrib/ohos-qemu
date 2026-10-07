#!/usr/bin/env python3
"""Exact Vivid photo timestamp fix for the pinned Camera peripheral source."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILES = [
    ('camera/vdi_base/usb_camera/pipeline_core/src/node/fork_node.cpp',
     '44f820e4818930fe59ef6c603226322f43fc21a80186c4eb126546954e1c82e3',
     '5469b7485daf9a50feab197401122a8c4502bc13901390613649f0d45368613f'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
