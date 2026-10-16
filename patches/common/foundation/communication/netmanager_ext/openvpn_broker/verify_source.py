"""Exact private broker integration after the reviewed session/callback components."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (('services/vpnmanager/include/net_vpn_impl.h', '5aaf595c3027660a3b5cdc837022258dc20b321a4afae063d4666d0dd3941594', '680a36586cf9984a2096b95c72c6ac972cd567d19217e58babd1b84ea6eab45d'), ('services/vpnmanager/include/networkvpn_service.h', 'c436f184fdd8c7cb10d4962ab06e730e71d1dbd3160357edd379d733a13d9494', '85cac22f1146b7fc67b2dba3b23d065cf9301e2a598d7d604406c18530fd137b'), ('services/vpnmanager/include/open_vpn_ctl.h', '65affa18146d3a3c23f0895b11bd81ef63abe279e2eb2afe6ca8e1af13ddbb25', '2338830aa4b631a95a85e2ee1d71e9b49f275622153ae68a8eea5e9eaab6304d'), ('services/vpnmanager/src/multi_vpn_helper.cpp', '1e7dc12025c5d2b6917d25c786738ad778f5e69e7079a7a9be8fc133a35eb5d2', 'cb35c05e7b3dc8ae95b2f534cb05c9c99a4754657f7987bbecb5d83aa8b12ad0'), ('services/vpnmanager/src/net_vpn_impl.cpp', '3416dcb8df5b7e707599819979a620b08d2356bb68d62fc15192b261bbe1b4f7', 'eec73daafb888793b09158657d551ced4aebae22edb8ca00e5de9b86ecfca950'), ('services/vpnmanager/src/networkvpn_service.cpp', '88adc2dd0c24ff157c2a98ee7fe84ce6dd81c98ddb787f0edd550907756fc29c', 'e27f6ee7307c80cea972030c83ea3680f98c8c4921668e24d72540a3c66b74d4'), ('services/vpnmanager/src/open_vpn_ctl.cpp', '62c9b1162ba13c0eac3cf5eaf2051c171ab9d76d1acd735a54cf3d03264545f0', '145584763fb092e40c77242bb75281842bd6be0f105fb1381fc56d551dbf9b78'))
CRLF_FILES = ('foundation/communication/netmanager_ext/services/vpnmanager/include/open_vpn_ctl.h', 'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp')

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

def validate_preceding(root, files):
    validate(root, True)
    repaired = {name: final for name, _, final in FILES}
    expected = tuple((name, original, repaired.get(name, final)) for name, original, final in files)
    return validate_component(root, PROJECT, REVISION, expected, True)
