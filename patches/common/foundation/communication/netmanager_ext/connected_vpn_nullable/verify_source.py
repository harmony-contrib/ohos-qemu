"""Exact nullable connected-VPN IPC repair after the always-on component."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('interfaces/innerkits/netvpnclient/INetworkVpnService.idl', 'd2a41cae4f25ff8808b9287986a6f1785a3a9778eaf65e05f9f35945f3a8c1fc', '3c8259477599282e159352d03afd7b2e27740ff5ab0815ca9f03766b11e791c6'),
    ('frameworks/native/netvpnclient/src/networkvpn_client.cpp', '2f2494677bfa42fa5fcd2bf3f605054c67f4341ead9282b1fddccbfb406fa513', '58952fc33d04c16bb4078f5cec60acc3eab14503fe18e74ed16e8cf902a91f36'),
    ('services/vpnmanager/include/networkvpn_service.h', '296316894a3db878e4951456b8b021d9ead4c9eb15392a7f5c660b00fb8c8674', '72d1637791a4b897c4e1187380eb7490e578c4c81eefd5b026a0e86ea09edad3'),
    ('services/vpnmanager/src/networkvpn_service.cpp', '1be84d577d02d7f02ac18e880ef904fd7683cc8747cc34c7f41949db7c09bc89', '7c622df9325665c6983ad35a281364aafa5fdb16a555de2246d061c2b7689d53'),
    ('test/netmanager_ext_mock_test/mock_i_network_vpn_service.h', '6005b7b8b3a2589fc499859c1c36da0e3eba32fe5d569f4a5ed36d364283fd39', '67be9ef39636dc8cff62c37245aea4b2f7b2f7cd1a28078f660d83a79546c0f8'),
    ('test/netmanager_ext_mock_test/mock_networkvpn_service_stub_test.h', 'cbbfb8e89cfa5aded7d49e7e97faeaace2ed65def5dfa923975ac4f3ddf9033a', 'be58291258703d602a0b0b9f99dd0e3cc380ff6fb3d044fa01dadf77f65219b7'),
)
CRLF_FILES = {'foundation/communication/netmanager_ext/test/netmanager_ext_mock_test/mock_networkvpn_service_stub_test.h'}

def validate(root, require_patched=False):
    try:
        return validate_component(root, PROJECT, REVISION, FILES, require_patched)
    except ValueError as original_error:
        import importlib.util
        spec = importlib.util.spec_from_file_location('qemu_openvpn_session_following',
            Path(__file__).resolve().parent.parent / 'openvpn_session/verify_source.py')
        following = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(following)
        try:
            return following.validate_preceding(root, FILES)
        except (ValueError, FileNotFoundError):
            raise original_error
