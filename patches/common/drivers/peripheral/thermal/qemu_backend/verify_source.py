#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILES = [
    ('thermal/interfaces/hdi_service/profile/BUILD.gn',
     'c2d340c2f353dbbd03ca27e56ee402abcae86e68c484271053326642977b45cf',
     '05a2afec01f23b2c37b7b0f6b45aa0be7835c5790ddb907e8f642d732172f5c5'),
    ('thermal/interfaces/hdi_service/profile/qemu_thermal_hdi_config.xml', None,
     '31231293c6e337a0e2942584742d1808acae66e2f97c8289ae4e265432d833a8'),
]

PREVIOUS = (
    (FILES[0][0], None, FILES[0][2]),
    (FILES[1][0], None, '4483da57ab7ab01edb6a0277d5727b9bb02b12ac8ae1c69cacfe6c08a76b8d25'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
