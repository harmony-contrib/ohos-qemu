#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/powermgr/thermal_manager'
REVISION = 'dbba4e1d77e4bc2c8ff7e5a0796a36e388277461'
FILES = [
    ('frameworks/napi/thermal_manager_napi.h',
     'f7e5d86030c08d1f9ab6bcf47bd889734d66596dbae7f0424be893450a91de5e',
     'f31d49bc7ac034b0a23a845aac69aea1236ed23579a90486d27dd5b16ab98367'),
    ('frameworks/napi/thermal_manager_napi.cpp',
     '9cac2d4e2e6a749a6b4be5366ce72e3d17d0b1f72618dbdd9d69926810643557',
     '63da35b900b697d14dbc1f62b7073d47da074edb3b391ccf33111551d97f1dad'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
