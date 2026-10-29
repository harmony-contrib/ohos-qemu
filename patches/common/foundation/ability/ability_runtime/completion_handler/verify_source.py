#!/usr/bin/env python3
"""Exact SDK-declared completion callback class export, not service success."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (
    ('frameworks/js/napi/completion_handler_for_abilitystartcallback/'
     'completion_handler_for_abilitystartcallback_module.cpp',
     'c700db058f2d61f9e77cd293aa8dd029c7e391242f4d314e9e1f155cc478cdd3',
     'eb1da0d5affdb82b560d025ee8a770c3ff3da4242fda8ea48987426c3c3974cc'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
