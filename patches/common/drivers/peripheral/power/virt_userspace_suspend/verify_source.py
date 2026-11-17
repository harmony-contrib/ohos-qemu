#!/usr/bin/env python3
"""Keep QEMU virt guest kernel and virtio/HDC alive during power_host suspend."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILES = (
    ('power/interfaces/hdi_service/src/power_interface_impl.cpp',
     '96e0bca23a4e1537113e12ad380b1cdd6c2b87a6bd85a9219b3ba101ab3a15f5',
     '716d9475927486b039648f03a49bc08f71c9ad4c9e2ea8f690f592029642b219'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
