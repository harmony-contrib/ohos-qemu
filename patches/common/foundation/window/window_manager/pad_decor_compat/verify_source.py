#!/usr/bin/env python3
"""Exact 2in1 Pad-mode window decor compatibility in libwm.z.so (Issue #35)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/window/window_manager'
REVISION = 'c9e0c375301ef3fc5cb08d4e5ab69bc7fe04bf73'
FILES = (
    ('wm/src/window_session_impl.cpp',
     'cd6ca5540c8a4f79cc8fda3df81e6af7c688bb9a22e13454a95041fab475c1b8',
     'a80ead737ff68abdedfcde4c68325ce386cf1f24ee57d99e6d23e4a9210e280a'),
    ('wm/src/window_scene_session_impl.cpp',
     '774cb24d3690e28cdf47a757595cf252f21f3487d8dbfb245125cc54765dda76',
     'ab48f986e35200dfc65b461e02a82ed7dc095739cb5b77de455a9ce95e08c873'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
