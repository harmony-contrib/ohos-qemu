#!/usr/bin/env python3
"""Validate the fixed-release service source before applying its lifecycle repair."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (
    ('product/phone/src/main/ets/Setting/Accessibility/service/IgnoreRepeatClickService.ets',
     'b0e94b08aaaba4414d41a175f047252e5b50be93e284a5ace50cc15592972d1f',
     'f97a094aeb689abb6d26470db61e4048690d3060d5ecfe0e94528ac8d730a825'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
