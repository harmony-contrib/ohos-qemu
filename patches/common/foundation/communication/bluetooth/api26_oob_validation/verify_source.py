"""Exact API26 OOB entrypoint candidate, without claiming adapter support."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/bluetooth'
REVISION = '1727fa05c457f697f7cf80f290c82c663f1c3aab'
FILES = (('frameworks/js/napi/src/connection/napi_bluetooth_connection.cpp', '491a97b9d083a197b216965ada159da1824694e025fc0721421469f91fe9a5be', 'afb340e6a38e4bf75ebe94079ecc001002cbba6a35275c79fabd34ae9dba262c'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
