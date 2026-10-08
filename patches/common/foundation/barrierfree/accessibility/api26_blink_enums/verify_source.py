#!/usr/bin/env python3
"""Exact enum exports only; start/stop blinking still require real providers."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/barrierfree/accessibility'
REVISION = 'c593c7e1a6149a2c13e5931b2114d3c2d0bf20ea'
FILES = (('interfaces/kits/napi/accessibility_config/src/native_module.cpp',
          '0eb75f5d775fc0ffc707270e05f8e81287f77559823792617ccc98db43ca1fea',
          'faa573b972a9ad98ae8316b669aa73cbf40c57bf740f354bd492589a6fa641e3'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
