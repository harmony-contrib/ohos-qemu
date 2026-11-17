#!/usr/bin/env python3
"""Exact pinned route-table states; not guest presentation evidence."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (
    ('napi/settings/open_network_settings/napi_open_settings_page_util.cpp',
     '45ca1dc44ad6e5fdc1f586047ec2034cf28dfcd1b87d5008f0a3a3b289efa121',
     '055ad2e78d2e97be9266ad93f29515d0d970376019dd897d908b23cfee3ec8ee'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
