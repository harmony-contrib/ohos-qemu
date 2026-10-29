#!/usr/bin/env python3
"""Exact pinned source build inputs; no runtime acceptance claim."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/mms'
REVISION = '26df98e3738f4219aa45efe6a3e7f6b1be55c051'
FILES = (('BUILD.gn', None, 'ff3a2fde79e76a3dc126f4898800f4e1a0459c96d73a13a1bf8f9a14f9d60d2f'), ('build-profile.json5', 'da0d89f4b562e98c816bf2ad0793f2704700db22edb15310956c3c2ff85491aa', '3c6cae55eb0e01133e8bad7af37d35eee0163a337dd40cc0d3416da5627e1aa8'), ('oh-package.json5', '648bd2c3d9ed022f4e14d5cde43197ddd842ba38c037739fc696e4d0e0ebca12', 'c7b6d942a923f3203c8e46a2c379bca931b80392aed24f6301960555f46a525c'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
