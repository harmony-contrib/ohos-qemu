"""Exact OpenVPN session follow-up after connected_vpn_nullable/openvpn_lifecycle."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (('services/vpnmanager/include/open_vpn_ctl.h', '83d31736f01a61c2a939a4e3fd6aa29410b98d40b9e893d4cbab3da280eca2c5', '65affa18146d3a3c23f0895b11bd81ef63abe279e2eb2afe6ca8e1af13ddbb25'), ('services/vpnmanager/src/open_vpn_ctl.cpp', '676dd2fd56c126c153f42e5e0d170676fa05fa600cf31a3bd05f80e1c297ae24', '62c9b1162ba13c0eac3cf5eaf2051c171ab9d76d1acd735a54cf3d03264545f0'), ('services/vpnmanager/src/networkvpn_service.cpp', '7c622df9325665c6983ad35a281364aafa5fdb16a555de2246d061c2b7689d53', '694b0c90fe01e43c9ec89f5363b3009f0e895b3c3bcc2d874e248829f9c95e05'), ('services/vpnmanager/src/net_vpn_impl.cpp', '2c8bb47f05336ce57fa4b0630b14d5fa0840aac08fe3527aa499ef58e8c21cb0', '3416dcb8df5b7e707599819979a620b08d2356bb68d62fc15192b261bbe1b4f7'))
CRLF_FILES = ('foundation/communication/netmanager_ext/services/vpnmanager/include/open_vpn_ctl.h', 'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp')

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def validate_preceding(root, files):
    """Accept only this complete follow-up plus every unaffected preceding file."""
    validate(root, True)
    repaired = {name: final for name, _, final in FILES}
    expected = tuple((name, original, repaired.get(name, final)) for name, original, final in files)
    return validate_component(root, PROJECT, REVISION, expected, True)
