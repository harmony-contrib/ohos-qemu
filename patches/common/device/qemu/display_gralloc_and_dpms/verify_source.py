#!/usr/bin/env python3
"""Fix QEMU GBM gralloc DMA-BUF sync/mmap/refcount, DRM master retry, and virtual DPMS/backlight."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'device/qemu'
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILES = (
    ('common/virt_full/hardware/display/src/display_gralloc/display_gralloc_gbm.cpp',
     'ec2d5404688e38779580462fcfc518708e9b213b54844f0e0df21b3ceaef6ae2',
     '355c1389568a76694cbb1e18d2da5a4cf48c25b749118881e2dc2e9de9ca1e30'),
    ('common/virt_full/hardware/display/src/display_device/drm_connector.h',
     '4710ba9d9362c812f0d3681dc2f6e5c2d6c31b563d6e75ca306decd1a6f1e580',
     'fee4dc09de7ff740e0706be10b8a5069038552f93db097bfa9b2da5bec6b4a3d'),
    ('common/virt_full/hardware/display/src/display_device/drm_connector.cpp',
     '7c190b2ff1e7061b9332934da5590bb97e51ff6a9b42b1399f22956ed5a1f57e',
     '03aecba724046859d93f5e2ae01e0fba67ef438ae819d10e7e5c9315a8df0ca1'),
    ('common/virt_full/hardware/display/src/display_device/drm_device.cpp',
     '6fcf3197722e4d46be91e1936b0b01f8f978186c63f0d1ff0cfd51ca7372c421',
     'fa19dc02928a5d4a61236e683799821554dfe6b03b96ba0f58935c0490c5e541'),
)
LEGACY_V1_FILES = (
    ('common/virt_full/hardware/display/src/display_gralloc/display_gralloc_gbm.cpp',
     'ec2d5404688e38779580462fcfc518708e9b213b54844f0e0df21b3ceaef6ae2',
     '355c1389568a76694cbb1e18d2da5a4cf48c25b749118881e2dc2e9de9ca1e30'),
    ('common/virt_full/hardware/display/src/display_device/drm_connector.h',
     '4710ba9d9362c812f0d3681dc2f6e5c2d6c31b563d6e75ca306decd1a6f1e580',
     'fee4dc09de7ff740e0706be10b8a5069038552f93db097bfa9b2da5bec6b4a3d'),
    ('common/virt_full/hardware/display/src/display_device/drm_connector.cpp',
     '7c190b2ff1e7061b9332934da5590bb97e51ff6a9b42b1399f22956ed5a1f57e',
     '59624e8e45e0c1f6837f4db54645659f5625d438b38f098684990b9a36a89460'),
    ('common/virt_full/hardware/display/src/display_device/drm_device.cpp',
     '6fcf3197722e4d46be91e1936b0b01f8f978186c63f0d1ff0cfd51ca7372c421',
     '6fcf3197722e4d46be91e1936b0b01f8f978186c63f0d1ff0cfd51ca7372c421'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def is_legacy_v1(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V1_FILES, require_patched=True)
    except ValueError:
        return False
