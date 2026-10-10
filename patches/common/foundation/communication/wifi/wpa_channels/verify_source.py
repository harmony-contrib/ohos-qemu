#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
PREFIX = 'wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_common/'
FILES = [
    (PREFIX + 'BUILD.gn',
     'bb0ec45866273220b618d61a2569c211469b203b1587a8b37e3532a23406a14c',
     '3312a2fc0149224b5b68dd86aa11317ad6e3425e46a14680fb4fa8ec937caa67'),
    (PREFIX + 'wifi_channel_helper.cpp',
     '8f94ae3e9bf0537eeb6954186285e7ca49183ff12572972ce40bda1d0146cbd0',
     '534d2ae3f401a22382ca0add7b879b6b2a768dae659c4b164a58f5c3351e7545'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
