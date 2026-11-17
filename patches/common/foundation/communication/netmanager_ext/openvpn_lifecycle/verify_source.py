"""Exact fixed-source QEMU OpenVPN control candidate; runtime acceptance pending."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (('services/vpnmanager/include/open_vpn_ctl.h', '620adda4312c23320de817089464effbd57a41f5a7c24b8bee8496e726722a85', '83d31736f01a61c2a939a4e3fd6aa29410b98d40b9e893d4cbab3da280eca2c5'), ('services/vpnmanager/src/open_vpn_ctl.cpp', '1328fbca1e7c431b6d67cd1fd54e2f0887f9f5c95ad571b42830dc49c0b87218', '676dd2fd56c126c153f42e5e0d170676fa05fa600cf31a3bd05f80e1c297ae24'))
CRLF_FILES = ('foundation/communication/netmanager_ext/services/vpnmanager/include/open_vpn_ctl.h', 'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp')

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
