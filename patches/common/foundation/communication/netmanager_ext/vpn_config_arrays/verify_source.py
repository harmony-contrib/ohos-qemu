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
     'b4c92df4a80d6c8d781de9047c9fc1ddb5e86e4c38a12eb8e7922ff7dd8b5ea8'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
