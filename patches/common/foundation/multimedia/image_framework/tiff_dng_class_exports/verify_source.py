#!/usr/bin/env python3
"""Record-class NAPI repair reached through the existing Avis initializer."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/image_framework'
REVISION = '711db218c8d1c4d6546b28d8cf466059644dfa77'
FILES = (
    ('frameworks/kits/js/common/metadata_napi.cpp',
     '97a45fd4a907595077e56ee61f9f31d7a6181b680920b8cb7a42263e15706fd0',
     '2bd2940612b39595200896681548d5645d7301a5f49054a760ba3c2e2a8cda5f'),
    ('interfaces/kits/js/common/include/metadata_napi.h',
     'd5b05d36b7441ea97012e5a3d0c6cc0b751f2deaf8a29dd74ed2d15f7ce88709',
     'c1f5bc1f409430b3083f5bfc91b05d481588b9f5aeae2d7592b2eb5100827552'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
