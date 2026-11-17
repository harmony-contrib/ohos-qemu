#!/usr/bin/env python3
"""Exact enum exports only; start/stop blinking still require real providers."""
from pathlib import Path
import hashlib
import importlib.util
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/barrierfree/accessibility'
REVISION = 'c593c7e1a6149a2c13e5931b2114d3c2d0bf20ea'
FILES = (('interfaces/kits/napi/accessibility_config/src/native_module.cpp',
          '0eb75f5d775fc0ffc707270e05f8e81287f77559823792617ccc98db43ca1fea',
          'faa573b972a9ad98ae8316b669aa73cbf40c57bf740f354bd492589a6fa641e3'),)

def validate(root, require_patched=False):
    target = Path(root) / PROJECT / FILES[0][0]
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == (
            '9c4481936d1145c7e4796cf4a90faed44bf98b81e750e57418b8f3283867bcaa'):
        spec = importlib.util.spec_from_file_location('screen_blink_successor',
            Path(__file__).resolve().parent.parent / 'screen_blink/verify_source.py')
        successor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(successor)
        # A matching native initializer alone cannot authorize a partial stack.
        return successor.validate(root, require_patched=True)
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
