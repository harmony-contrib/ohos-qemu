#!/usr/bin/env python3
"""Fail closed on partial or unknown system sharing edits."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (('product/phone/src/main/module.json5', 'f347664ff4039db0970d58b72ebe28c668d8ab62d950100b8925df68b6351b70', 'fc6383796f603062cd0cba5e5078e28e3b567f95356d09d7014c2c27b52d9a62'), ('product/phone/src/main/resources/base/profile/main_pages.json', '0a3e4a1f4856400dfaef882375159a053caa1f3e45e70cc68570c2e000f70906', '021ce6f5057f629e37236b634dcecc7e963c44ed15d35f9de02a7bbb0d90389d'), ('product/phone/src/main/ets/Setting/SharePicker/SharePickerController.ets', None, '656e4cdb114361a0ea640b2a500157b5e8c61f74efe75b123e83bca3bdeb008d'), ('product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets', None, 'bc80e70c97241c06594c3ba80b9668d3117dfba3d3b97cc451fefbd68a964758'), ('product/phone/src/main/ets/pages/SharePicker.ets', None, '0b0f93e792995546b831c67980b80717c16067591c3a22b269fdca36c51379dd'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
