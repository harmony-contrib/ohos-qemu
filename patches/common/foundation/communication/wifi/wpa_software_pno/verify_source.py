#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
PREFIX = 'wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_scan/'
FILES = [
    (PREFIX + 'BUILD.gn',
     '1089f38f245e027b58af498ed762360530e0d5d2c86a1ae4084ff7dab9776110',
     '7df79573e17b22ca612631961d50135970ced6aec5bc2c83a715a705ec3e491c'),
    (PREFIX + 'scan_state_machine.cpp',
     'aa5d84a1c440b4ada27e225e02a1dc4f0361a279a0b2e2378f07fb42e341268b',
     '8ac791ae6473439abc8a3f73230f2a4de028a60ada272d49a9a415621b49a775'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
