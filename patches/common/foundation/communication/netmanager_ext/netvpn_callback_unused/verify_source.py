"""Exact no-behavior-change native client callback warning fix."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (('interfaces/innerkits/netvpnclient/include/networkvpn_client.h', '216228f506b663d8d9006ce63505eaee183ab1e247a00828bccb9adbf925d701', '25e8a07f1c75b27090c508022515a03c8659704a53c1b6d4cc0bcf107a8d59bc'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
