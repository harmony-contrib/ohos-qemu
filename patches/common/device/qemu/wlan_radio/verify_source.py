#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'device/qemu'
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILES = [
    ('common/virt_full/cfg/init.virt.cfg',
     '6dc3c6b3325f4033394482f2ae6943064a1489406b69198d0fd3d3d58d1dba54',
     'b2245565897863750d27d4e9726f752de0dbb22912b20213c236f6cd4f4db2d3'),
    ('common/virt_full/kernel/arm64_virt_defconfig',
     'b5a3259581cf663f7c918ff845de8c2e9a524e07b26f64185aca9961df2ecf54',
     '75f2656b45f6bd905ed2556ed40d4b010075403e439895e17baf48d4e58b4b1e'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
