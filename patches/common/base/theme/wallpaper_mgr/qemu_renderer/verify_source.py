#!/usr/bin/env python3
"""Require the complete fixed-source wallpaper component; no runtime claim."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'base/theme/wallpaper_mgr'
REVISION = '42256bdeaa504da4ae4d038c24d42a4601e3a6cf'
FILES = (('services/BUILD.gn', '16c6df2d65364e8a54582a1736d950053d41abe3e945b04fda3caff8ac0b97dd', '3308963b13350d8ab5d19965a94d244a1ab98dda7141d518b4225ac8ca74d824'), ('services/src/wallpaper_service.cpp', '3271676807142d4b03664db0850c0d58d11ec0258941f98bd5658d57003038ac', '5590864bd8e51f2223e03bc709207c1a1619d36abcf0b812f31ec67e0c47f1c4'))


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
