"""Exact prepared 7.0 ethernet_business_error follow-up; no guest acceptance claim."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('frameworks/js/napi/ethernet/ethernet_module.cpp', '52fc36a712e6b4d44fdbaff188416de2c2049d7728abd132c06a96844ca40bc6', '52c1f930b495f2dc11f601c5e6beae8b2ef6237e55143d29fcd41908bb689990'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
