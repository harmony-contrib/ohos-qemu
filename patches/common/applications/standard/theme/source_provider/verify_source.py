#!/usr/bin/env python3
"""Exact source packaging metadata; not SDK, signature or guest acceptance."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/theme'
REVISION = 'a436a43f1c0948fa12df6d520ec695ae4388a057'
FILES = (
    ('BUILD.gn', None, '8540390751f1ce9af524b18fa4c56b754daedfe9fe3c37e618c45dca147f2189'),
    ('build-profile.json5', '7eeee1053b4edb92f079c04b0d11e3ed9533a1ac3af6263ea03b1613983d6481', 'c04f0d01df54b1aa237b4f5a964f43afc5d82b2a45bdb2c635a37f0a8b5a53a4'),
    ('oh-package.json5', None, '56098c75618b559c50ec6c97c5358e448b29a548cdcb685d98bed460aae2eb83'),
    ('hvigor/hvigor-config.json5', None, '19fd4e493f941f2dc8d7f4d0da03cbe22fcd2f7fe3adc099cbbb2bdc2656e88b'),
    ('product/phone/oh-package.json5', None, 'c3e4f0dab9b0ea195e33141cb8d6d0f2637b29da23c8671cfafc436c32fadf18'),
    ('product/pad/oh-package.json5', None, 'c3e4f0dab9b0ea195e33141cb8d6d0f2637b29da23c8671cfafc436c32fadf18'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
