#!/usr/bin/env python3
"""Exempt remaining SystemAbilityLoadCallbackStub cross-DSO dispatch methods from CFI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/systemabilitymgr/samgr'
REVISION = 'e8c6b7007c0898a552db5eca1018c21b126ec27a'
FILES = (
    ('frameworks/native/source/system_ability_load_callback_stub.cpp',
     '0b1e7268fb0205c3ca8389a7e9c8a17aad49a4ad5a8fde90eb0b275ae858f7d1',
     '4f77c77f7e7d57b3ed2bae0d73b6734e159e991e6706be17ebcae1e3a34a7fdd'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
