#!/usr/bin/env python3
"""Scale developer-mode UnlockScreenManager::UnlockScreen wait timeout by persist.sys.abilityms.timeout_unit_time_ratio."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (
    ('services/abilitymgr/src/screen_lock/unlock_screen_manager.cpp',
     'b2571e74c6f5b2a03f35433da18fa59403c57d7bb041b32f16b3ccf30d306abb',
     'f6aef245b047b27843b1416d3df41d4be798c9f088ff0f266e91f8993a9a2455'),
)
LEGACY_V1_FILES = (
    ('services/abilitymgr/src/screen_lock/unlock_screen_manager.cpp',
     'b2571e74c6f5b2a03f35433da18fa59403c57d7bb041b32f16b3ccf30d306abb',
     '226a35322e20da8a9ca62ddc22c921d288ce27b100fd33048409c82c65e83479'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def is_legacy_v1(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V1_FILES, require_patched=True)
    except ValueError:
        return False
