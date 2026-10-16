"""Exact owner-bound callback dispatch after the complete OpenVPN session component."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (('services/vpnmanager/src/networkvpn_service.cpp', '694b0c90fe01e43c9ec89f5363b3009f0e895b3c3bcc2d874e248829f9c95e05', '88adc2dd0c24ff157c2a98ee7fe84ce6dd81c98ddb787f0edd550907756fc29c'), ('services/vpnmanager/include/networkvpn_service.h', '72d1637791a4b897c4e1187380eb7490e578c4c81eefd5b026a0e86ea09edad3', 'c436f184fdd8c7cb10d4962ab06e730e71d1dbd3160357edd379d733a13d9494'))

def following():
    import importlib.util
    spec = importlib.util.spec_from_file_location('openvpn_broker_following',
        Path(__file__).resolve().parent.parent / 'openvpn_broker/verify_source.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def validate(root, require_patched=False):
    try:
        return validate_component(root, PROJECT, REVISION, FILES, require_patched)
    except ValueError as original_error:
        try:
            return following().validate_preceding(root, FILES)
        except (ValueError, FileNotFoundError):
            raise original_error

def validate_preceding(root, files):
    repaired = {name: final for name, _, final in FILES}
    expected = tuple((name, original, repaired.get(name, final)) for name, original, final in files)
    try:
        validate_component(root, PROJECT, REVISION, FILES, True)
        return validate_component(root, PROJECT, REVISION, expected, True)
    except ValueError as original_error:
        try:
            return following().validate_preceding(root, expected)
        except (ValueError, FileNotFoundError):
            raise original_error
