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
     '4ffe715444186e09114377f8cca05295806ada38650856f1d96f82986a908006'),
    ('frameworks/js/napi/vpn/src/context/setup_context.cpp',
     '4f39d7d6493e484f4f81d8e28d24dafe486605a85088496218e6f4d3aff92b2c',
     'd429840667b8b1ec036fbb5efb9b1cb1cf6677004b3f76cf82198dcb158d0e92'),
    ('frameworks/js/napi/vpnext/src/vpn_config_utils_ext.cpp',
     '00b8e25c99f54866f3d746fe7240f847e5e6cf8afcb1f1ca5894d0d0460c5bdf',
     '51dead3bb0ad6a65ea2926834e60110216bdd8ab670a760797493174813ca5ec'),
    ('frameworks/js/napi/vpnext/src/context/setup_context_ext.cpp',
     'fbcfb639481dd687cc1d91bbe65772e8d172d1aef7476bdb7fec30263ddc0074',
     'bde27a6ea229b39acb2893ed6075dd6627175069cae30c4a91329128aff85973'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
