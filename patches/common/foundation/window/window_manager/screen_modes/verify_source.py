#!/usr/bin/env python3
"""Exact pinned screen-mode IPC repair, never a guest success assertion."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/window/window_manager'
REVISION = 'c9e0c375301ef3fc5cb08d4e5ab69bc7fe04bf73'
CRLF_FILES = frozenset(PROJECT + '/' + name for name in ('utils/include/screen_info.h', 'utils/src/screen_info.cpp'))
FILES = (
    ('utils/include/screen_info.h',
     '68e94e3c5929820728957863d9d9eb9b99a257c6dab92300bf8886beb45d63a8',
     'f4c6bb1a7605a847894d00c1d78e4c7c74ea0cc922775ec078cb7190e4df7673'),
    ('utils/src/screen_info.cpp',
     'a02126e01360a581f6ce56612b9ff382a0069c7df1c7977a20b9d121f938bf63',
     '0fc398e16c501e036de356816312e21806e15c6f8d29eb51566b06343f6ec597'),
    ('window_scene/screen_session_manager/src/zidl/screen_session_manager_stub.cpp',
     'a7028d20e23f4911694e1b912f2cfb46accff301cc678b0d1ccbedec50cec225',
     '2dc74b54ae1775d1e73f6290bc02cbf7233d99b40a78148130467b50c937ecbf'),
    ('window_scene/screen_session_manager/src/zidl/screen_session_manager_proxy.cpp',
     'ee97327f7f4cfa80a88bda0b16f5949069d5b8f3ba3599daf94808a7a370130c',
     '3e815847fa6985cbfde33d83413e06acfc94d3e59608e35e0d2eb9a08792a2c9'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
