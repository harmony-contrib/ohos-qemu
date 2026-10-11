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
     'd90168fc7ba43ecfa1c9fe0e6bb63c397d4814794ac5c68bbe9bd2e0d256cbfe'),
    ('frameworks/js/napi/vpn/src/context/setup_context.cpp',
     '4f39d7d6493e484f4f81d8e28d24dafe486605a85088496218e6f4d3aff92b2c',
     '27bbc5dadf3aad40e158e27b9b00f2492f06d683ea036fb4ae319917f6558c7c'),
    ('frameworks/js/napi/vpnext/src/vpn_config_utils_ext.cpp',
     '00b8e25c99f54866f3d746fe7240f847e5e6cf8afcb1f1ca5894d0d0460c5bdf',
     '7999ff4510cac17ae6bc0ded81f3b838d81a081f9415fba936213ad4e32bba04'),
    ('frameworks/js/napi/vpnext/src/context/setup_context_ext.cpp',
     'fbcfb639481dd687cc1d91bbe65772e8d172d1aef7476bdb7fec30263ddc0074',
     '297aff0727166eb0924734c5da5d09ea2e25829d4c48c3431fd8662c7b0c459f'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
