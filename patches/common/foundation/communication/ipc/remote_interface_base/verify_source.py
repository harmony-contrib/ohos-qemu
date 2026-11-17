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
     'c0b9c5a213dd815870ff894b8700c4eba264835cf23cbb10fa8c42cee85730e1'),
    ('ipc/native/src/napi/src/napi_rpc_native_module.cpp',
     'ec339aed373817e2a20d73e5e7af0ab579d6308ce7228961d8883d241ef9fe24',
     '593406695a92b74b387013dec667ffc64305158981b5181c1c14e15e5e31eebe'),
    ('ipc/native/src/napi_common/include/napi_remote_object_internal.h',
     '513b3d6cdbafc375826a4c487614e8b455281e4c4fb5463381588b95145f28e9',
     '3f781d87cf9e1baebcd0d0b6b9224ddbb388760488b629f2ed16cef021742091'),
    ('ipc/native/src/napi_common/source/napi_rpc_error.cpp',
     'b7bb2cc93c3c0f7d2ffa3a24c149b3882dfc3c39f3a5de8628c99650ed5f6c4e',
     '5473671e3fe169bda40491d85e13c694550c8a5a3620d7462c28e9b84dff0e2b'),
    ('ipc/native/src/napi/src/napi_remote_proxy.cpp',
     'c38074f2c170765e13924d90634fa7be36506af2dd10a87d52081d75c436e6ad',
     '9d08a15d910766b17f4522cf08288059147628620d5dd977110c2d43f46a3605'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
