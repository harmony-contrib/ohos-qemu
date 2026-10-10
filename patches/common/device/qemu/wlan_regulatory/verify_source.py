#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'device/qemu'
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILES = [
    ('common/virt_full/kernel/firmware/BUILD.gn',
     '4ae128c41f78e4f204a4f8ed87294aa2d9430be28bc7f1fe7f9789628dd41e05',
     '5c6468ae1f62a49602574ccf3297c2c3808bc4780f9a62f91f2533fdfd4d3ad9'),
    ('common/virt_full/kernel/firmware/qemu-regulatory.cfg', None,
     '56b498abd8e41b6d85c99c3bafb47abbe5b7139514aafe3a19f605d9fa677020'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
