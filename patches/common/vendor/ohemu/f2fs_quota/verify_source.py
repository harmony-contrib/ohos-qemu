#!/usr/bin/env python3
"""Exact QEMU userdata format after the shared F2FS/VPN component."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'vendor/ohemu'
REVISION = 'b56c5a95ec590543691278b85afe9fe228744163'
FILES = (('virt/image_conf/userdata_image_conf.txt',
          'ccf600e440eb585a70c8209f3be4021db8a4e520c2c831076acb975409713157',
          'acfa8845bf7b86931afd00b17182202e805f7cedbacb42d46c714e148eb58d31'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
