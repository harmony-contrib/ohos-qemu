#!/usr/bin/env python3
"""Exact 32-bit HiLog format cast in netfirewall_intercept_recorder.cpp."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('services/netfirewallmanager/src/netfirewall_intercept_recorder.cpp',
     'c97677a1f5d5a10652a16f86bf9fe9984dc6f6ae14c1cc6129a594a09025c693',
     'beca770621b6b811199c6083c40ae3d072fbb35cde89621ec739169a997334ef'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
