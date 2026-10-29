#!/usr/bin/env python3
"""Exact JPEG capture component, after the USB generated-config component."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILES = [
    ('camera/vdi_base/usb_camera/device_manager/BUILD.gn',
     '029f5a2bfb0689277fe73f104548894c95d0063aab494fc4558efc42202f4248',
     'bf774fbb15250666d4a2a448eb2c8436e77680354cee3bf4596c37aab54be4a6'),
    ('camera/vdi_base/usb_camera/adapter/platform/v4l2/src/device_manager/v4l2_device_manager.cpp',
     'ac434a84f3bee05d5e41a8aad64438ec539e2331c02e046e7b81938702ec1914',
     'f05c0c4e232787d286641f469e06e57d5f5bab43d645b4c7d968017ac8ee8087'),
    ('camera/vdi_base/usb_camera/pipeline_core/BUILD.gn',
     '274ed2eba3892cd9d64e86cfa0bab6868c40a3f1a7a4a96bfcc7ec8f3946cd3f',
     '58e71f433a1d0c6425aab75d101e41283e045bb44cc4e25319686210132f9eed'),
    ('camera/vdi_base/usb_camera/adapter/platform/v4l2/src/pipeline_core/nodes/uvc_node/uvc_node.cpp',
     'fcb5853c938e273b222df586c9c80fd1bbf9af7fedb23d8a8b56455708e3badd',
     '13766098fbd8d83e9fd8c0dc9c6d6dd3c14fb85fccee02669bb3cae2b1f53c45'),
    ('camera/vdi_base/usb_camera/pipeline_core/src/node/codec_node.cpp',
     'f18c171cd503703567ceb86ebd7017cc26205d1df481a92df2423ac1b87dc0d6',
     'd7cef95e6edebb4f6d50f93b4be103d6c23158c34c3624468123458b48c10b23'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
