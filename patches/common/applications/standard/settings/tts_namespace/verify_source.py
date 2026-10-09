#!/usr/bin/env python3
"""Pinned OHOS 7 Settings SDK namespace correction, preserving the old alias."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (('napi/settings/napi_settings_init.cpp',
          '82395ff1aa9bf6d6cb32cdaf971d7c75bc0c029c81aef1f8b81501cd8b641567',
          '44225247789f4e6db3f1612cd13a71eb3ea4f78164ab4d40c8927be3f412e32f'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
