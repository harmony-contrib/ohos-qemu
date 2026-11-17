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
     '74740e61aa8bb7dcb0fc6965c5aaf355a664a82d075424ca66be132e43722a80'),
    ('frameworks/js/napi/vpnext/src/vpn_config_utils_ext.cpp',
     '00b8e25c99f54866f3d746fe7240f847e5e6cf8afcb1f1ca5894d0d0460c5bdf',
     'e1dbdf174800b3a90d675f138b8b9072b4d9d4b417dc18d6dba525efa26586e9'),
    ('frameworks/js/napi/vpnext/src/context/setup_context_ext.cpp',
     'fbcfb639481dd687cc1d91bbe65772e8d172d1aef7476bdb7fec30263ddc0074',
     'e160be816a14b1e927d8ba71be8b25c2b05b8eb3e104e4b3be508d1401860796'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
