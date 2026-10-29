#!/usr/bin/env python3
from pathlib import Path
import hashlib
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

# The capture selector runs immediately before WLAN in the complete patch
# plan. These two whole-file successors differ only by CONFIG_SND_ALOOP=y;
# keep both exact compositions so either component remains idempotent.
ALSA_CONFIG = (
    'common/virt_full/kernel/arm64_virt_defconfig',
    '9a56d9280b0b30fada5074da959b547c0df2bf905d0fe84fa034a5a8a32297a6',
    '71d4640de24b2483f26c40cd36c3d2ebb6a153a11a8d4e377d14994c51856c4c',
)


def validate(root, require_patched=False):
    config = Path(root) / PROJECT / ALSA_CONFIG[0]
    files = FILES
    if config.is_file() and hashlib.sha256(config.read_bytes()).hexdigest() in ALSA_CONFIG[1:]:
        files = [FILES[0], ALSA_CONFIG]
    return validate_component(root, PROJECT, REVISION, files, require_patched)
