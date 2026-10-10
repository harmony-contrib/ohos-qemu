#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
PREFIX = 'wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_native/'
FILES = [
    (PREFIX + 'wifi_hal_interface/wifi_supplicant_hal_interface.cpp',
     'ebbc1b8da2e8e78e3488cded0cb9bc2ae76e070b7d21436fdbf5f5a796a1c23f',
     '6a09a2c37dafea9681fe3ada9078937746bd151ebcf4ffdd55e2bf2a6ed53179'),
    (PREFIX + 'wifi_hal_interface/wifi_sta_hal_interface.cpp',
     'ea8d438ed739b20f7ed46e33cbee30e91fb4c6edff71ebe183560c243c1442d6',
     '19d34c2d976a6b0fb2fe6f4b109ff47e47f31dfa213288e8b1079210a0b646ba'),
    (PREFIX + 'client/hdi_client/wifi_hdi_wpa_callback.cpp',
     '932a256e85b3748942501a5c6fd8d2124e89b88de4ee86431a698a02f2b0bb1f',
     'b6827032f6b1a5ac6b1fbb1c18ba9cf3e65a2204c8758ad0bfba93144a8cf05c'),
    (PREFIX + 'client/hdi_client/wifi_hdi_wpa_client.cpp',
     'a3fb9be8b95c2b41d121341d14cf21a0a83fb0483e77bd4662a57f43931ee97f',
     'd3aaa9c18d169d284e4529e02c991c6d050442e2b7a2e8c20b10dcb95c5bddac'),
]
CRLF_FILES = {PROJECT + '/' + relative for relative, _, _ in FILES
              if '/client/hdi_client/' in relative}


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
