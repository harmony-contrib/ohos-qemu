#!/usr/bin/env python3
"""Exact QEMU DRM mode candidate; source validation is not runtime success."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'device/qemu'
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILES = (
    ('common/virt_full/hardware/display/src/display_device/drm_crtc.cpp',
     '1936ad7fd08ff617f7a4a2631345638479039f8369653a6a41630bce4f3b52de',
     'f6b48b1802a56ff9171c046575294d1c5d288e1075ae34292b67fc08696e2994'),
    ('common/virt_full/hardware/display/src/display_device/drm_display.cpp',
     '22a95d508dbe315850e8c4d7e0910b535f72752b9a5ce10ebd867c845873d2e1',
     '890a53d07b7e7715961f43114b7f87a2598c68fbb5a215768b7458a57b711d66'),
    ('common/virt_full/hardware/display/src/display_device/hdi_drm_composition.cpp',
     '865f8d4920ee73ad1fd4adaad93f6d8bfd8da52748465c74ceab28092fe06d89',
     '8160c065c9efc806bcbcf0f60921d0f02669b3b9094c119dd8dca67863789068'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
