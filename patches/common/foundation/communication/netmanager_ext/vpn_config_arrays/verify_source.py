"""Exact native VPN serializer source, not store/tunnel acceptance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('frameworks/js/napi/vpn/src/vpn_config_utils.cpp',
     '622d6eb21e9fedbbcd5cc79f8f9b32ff150d20fd999d39fe7db66431e711eeb6',
     '73774c408ac509ebaf35ccf7d50cbc375726882151a5929f6ddcaeff12c36b48'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
