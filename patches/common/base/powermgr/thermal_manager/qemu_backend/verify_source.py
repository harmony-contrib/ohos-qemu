#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/powermgr/thermal_manager'
REVISION = 'dbba4e1d77e4bc2c8ff7e5a0796a36e388277461'
FILES = [
    ('services/native/profile/BUILD.gn',
     '9b9a6bd71f9daa4e42e562eae5472a5eaedfd3d335d499dc04e2887f047b2ae2',
     '92a5a7c608556b58674d8cf48973fece92eb75c95d583ae67c4ec7be8676e724'),
    ('services/native/profile/qemu_thermal_service_config.xml', None,
     '1ba15e293fdc83f933b94f3cfa0a3311137d3b1075d770d828eaa1086454abfd'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
