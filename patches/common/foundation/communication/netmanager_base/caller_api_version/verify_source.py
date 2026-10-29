"""Pinned caller API capture; runtime error behavior still needs a new package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (('utils/napi_utils/src/base_context.cpp',
    '2ae13a50856041f4807f9a4d53f1e858ce1364843ba203c3aab4c8c5de01f7b5',
    '0310af124ad55596e34025876cbdc14ef675b668912d4164af096cc29f16a34a'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
