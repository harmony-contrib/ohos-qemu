"""Exact pinned native RPC abstract-base implementation, never an export alias."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/ipc'
REVISION = 'b8d3e96cfcf382c8fae54502679ac8b3d827b428'
FILES = (
    ('ipc/native/src/napi_common/source/napi_remote_object.cpp',
     '72156365960c22912e519d53cb8f763f8554769cf8e0f324e783ab0e322af776',
     'ec544cb78def0dc7717a2cc25aba0185def889a1417289382fddc7288984800d'),
    ('ipc/native/src/napi/src/napi_rpc_native_module.cpp',
     'ec339aed373817e2a20d73e5e7af0ab579d6308ce7228961d8883d241ef9fe24',
     '593406695a92b74b387013dec667ffc64305158981b5181c1c14e15e5e31eebe'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
