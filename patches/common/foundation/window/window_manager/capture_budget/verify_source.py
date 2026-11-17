#!/usr/bin/env python3
"""Exact QEMU-only bounded capture budget; never a guest success assertion."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/window/window_manager'
REVISION = 'c9e0c375301ef3fc5cb08d4e5ab69bc7fe04bf73'
FILES = (
    ('window_scene/screen_session_manager/BUILD.gn',
     '1e06c492765335f04c88206cdcbe873543d2dc74bbb2b62affb71c9bf12942bf',
     'aa2cdbf6a7f05fd4798e9003084adbbe73f1b3037bab032fb23eb558235e5366'),
    ('window_scene/screen_session_manager/src/screen_session_manager.cpp',
     '92666410b08746b07bd38138a3240d6213a957a07e0311ff3990dd8c5f9ffad9',
     '12786c624fea2e3bcdf5aeaa27d485a1acaaefae1b53870206b65701cc1277f2'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
