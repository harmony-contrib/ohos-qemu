#!/usr/bin/env python3
"""Fail closed on partial or unknown system sharing edits."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/mms'
REVISION = '26df98e3738f4219aa45efe6a3e7f6b1be55c051'
FILES = (('entry/src/main/module.json5', '67c6b55f3817af6f9bfab4f8696cf18766b9e07e821b44dbe60417aa215b8b51', '67ce57d6262cffd662be30497c9bdcd60be1acef87418c04801de6623438187f'), ('entry/src/main/ets/utils/WantUtil.ets', 'e80c63b3e30ab9baa1daa4189909df523a6b65adc26a7fdf30350083983a74fa', '9c4bddf3b65cc57e909e38527f5ce92927fa4219c5141d39451f4cad5f063eda'), ('entry/src/main/ets/utils/SendDataPayload.ets', None, 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
