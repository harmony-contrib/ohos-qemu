#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'third_party/wpa_supplicant'
REVISION = '966df143fda86a2ef75ca2a182d853d5fa480495'
PREFIX = 'wpa_supplicant-2.9_standard/'
FILES = [
    (PREFIX + 'BUILD.gn',
     '30d6750ac848db77a100e4eedff18569e0143c16a03647ff8a7d4d61b78892a8',
     'e5a9f413f446f79c876f2f7468cbab4c4f12519352ea0603cd9b91701cd2e428'),
    (PREFIX + 'src/utils/common.h',
     'daa3e8ce600640db67040fa3de0b5b5f78995caf1135576535e545bc4db6c005',
     '85fb9692595636734cfa8b074bf7207df09c943240209aa315bf8ba2f6069833'),
    (PREFIX + 'wpa_supplicant/events.c',
     '25d91da4cd97953b2118ce820737e36fbc5dec1c41f987b650bcbd47c02b3981',
     'd6dc5d207d43ee31e2575b22f8e11219008c04c1f4adc2e5caa0035a9b082902'),
    (PREFIX + 'wpa_supplicant/scan.c',
     '1d5853f3f3c5e5365233d4ff992e8062f255496b7a0c40f2715b931bfe2fb311',
     '4c212de57c461b37ee471014b73b18ef9370cd7c8ce9616389d308c6c89bfb5f'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
