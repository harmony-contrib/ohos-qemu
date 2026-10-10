#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
PREFIX = 'wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_native/'
FILES = [
    ('wifi/bundle.json',
     'b4f898dee44d3511dc9a3ff538555e24e7c94d4db97b00259a56399a5b042663',
     'e332c36c87abbb4dedbf13cfce874a308bd78c8798d5e9485e3bbbad6fd98572'),
    (PREFIX + 'BUILD.gn',
     '6bac12cbcd000dd3f6b4c8818915b3a4190e985a568c2ceef30643f8c327f499',
     '58296eadc02493d94be6e92a7369c3f85aaf9bc4195655cdae38ce76cf89766d'),
    (PREFIX + 'wifi_hal_interface/wifi_ap_hal_interface.cpp',
     'bfd785605df8f70bfdb3547d43e2eef46263590d7725c534e4622c6ca9715157',
     'a8fdad25c62c4f2d960e77791c5dee25daf355d234289e19b855a5a64acdfa14'),
    (PREFIX + 'wifi_hal_interface/wifi_software_regulatory.h', None,
     '93d0a61fd0c48eba2f7cfcaa79c5b6e3db32b3c0c9713ceac3cb54977671f291'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
