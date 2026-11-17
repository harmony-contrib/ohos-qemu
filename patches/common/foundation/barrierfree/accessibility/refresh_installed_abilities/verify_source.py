#!/usr/bin/env python3
"""Refresh installed accessibility extension abilities from BMS on EnableAbility miss or empty ChangeAbility."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/barrierfree/accessibility'
REVISION = 'c593c7e1a6149a2c13e5931b2114d3c2d0bf20ea'
FILES = (
    ('services/aams/src/accessibility_account_data.cpp',
     '68c7a04741e7259f3ec55bada082ad02bb32cbca75c371604df27689bed0c522',
     '7b74c87ed45c833bc200308cfef85532427b7cf3af80ab5b0baf1cc8b850e021'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
