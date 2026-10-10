#!/usr/bin/env python3
"""Exact renderer registration ordering; no caller identity or IPC changes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (
    ("services/appmgr/include/app_mgr_service_inner.h",
     '082a672bae9b675059a2647db74815066e4ec0965ef6caa65793d02f68fcc987',
     'cd8b6385ad6d6819a865ce458a6b98f1903ec739088c35bc8b3912641bd613a8'),
    ("services/appmgr/src/app_mgr_service_inner.cpp",
     '38cc45f30bcb6d95ffe4e2f0455716e705bc96db1845b2c060a9bec285b55569',
     'bce841624c35a439283ac691112407ba209219eba1b52aefe0ff06fbf2ac2bd1'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
