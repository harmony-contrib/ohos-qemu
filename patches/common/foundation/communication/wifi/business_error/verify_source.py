#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
FILES = [('wifi/frameworks/js/napi/src/wifi_napi_errcode.cpp',
          '8840102de7fbba7bb43690c1988ab2b28e1fd8cde9839d05016a91ddc6c72621',
          '2436ec69abf1d1fa61f15dcd588fa88657bc4db98e7838a3a78a292ce4b45eba')]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
