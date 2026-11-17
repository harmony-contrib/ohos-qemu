"""Exact prepared 7.0 vpn_openvpn_fields follow-up; no guest acceptance claim."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('frameworks/native/netvpnclient/src/vpn_data_bean.cpp', '9803f79ba3c19a7133255a95ac0e72857e37360ba72311c7cb959497edd34ae3', '11a8895cfc7d8c4ea546e8044c1ba2dd2763dce04abbff524736c02c4ea7ef67'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
