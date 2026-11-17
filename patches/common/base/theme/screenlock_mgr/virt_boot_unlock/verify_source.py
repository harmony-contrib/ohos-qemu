#!/usr/bin/env python3
"""Keep display awake across TCG boot SCBScreenLock and auto-unlock unrequested no-PIN locks on QEMU virt."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/theme/screenlock_mgr'
REVISION = '0ee87e038fb5bcd7f23ea0bb0e91f23a0478a6bd'
FILES = (
    ('bundle.json',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d',
     'db1330ac17dc57220d98859ed8c89c89318e9ab46dc229665723168afc0e8566'),
    ('services/BUILD.gn',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f',
     'de654b1f702d5bb9f44047a285f532052c1293bea8e78e1a5a8710bab9f13059'),
    ('services/src/screenlock_system_ability.cpp',
     'e2adf73ca8e6b45d603fbd067124153992bc2ddaa208dff54b71ac2be3aff2a7',
     'c02969c046f2b083d7620f36a55f220a6e4c407361c9fe583d07d0f3d95268d9'),
)
LEGACY_V1_FILES = (
    ('bundle.json',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d'),
    ('services/BUILD.gn',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f'),
    ('services/src/screenlock_system_ability.cpp',
     'e2adf73ca8e6b45d603fbd067124153992bc2ddaa208dff54b71ac2be3aff2a7',
     'dade25758d8d4f859b8604bf9982b088b7a78bdf6fcc1a95ed0f6f4a4c7b0e79'),
)
LEGACY_V2_FILES = (
    ('bundle.json',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d',
     'db1330ac17dc57220d98859ed8c89c89318e9ab46dc229665723168afc0e8566'),
    ('services/BUILD.gn',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f',
     'de654b1f702d5bb9f44047a285f532052c1293bea8e78e1a5a8710bab9f13059'),
    ('services/src/screenlock_system_ability.cpp',
     'e2adf73ca8e6b45d603fbd067124153992bc2ddaa208dff54b71ac2be3aff2a7',
     '02eb708e5f45f617167821313a604e9fcb5488a6247ea38623e243138498fc64'),
)
LEGACY_V3_FILES = (
    ('bundle.json',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d',
     'db1330ac17dc57220d98859ed8c89c89318e9ab46dc229665723168afc0e8566'),
    ('services/BUILD.gn',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f',
     'de654b1f702d5bb9f44047a285f532052c1293bea8e78e1a5a8710bab9f13059'),
    ('services/src/screenlock_system_ability.cpp',
     'e2adf73ca8e6b45d603fbd067124153992bc2ddaa208dff54b71ac2be3aff2a7',
     'f0c0a1c6e7231bc3905711b6912601946758f73531bc229610bed5830c377833'),
)
LEGACY_V4_FILES = (
    ('bundle.json',
     '8bb589fec3280d9cf52eda996064ed2203cfd0b24b2cdec31b637df94b916f5d',
     'db1330ac17dc57220d98859ed8c89c89318e9ab46dc229665723168afc0e8566'),
    ('services/BUILD.gn',
     '3ab6c072bbf33c82b867ead44eaafeb8de8bf5bdd73ebfc8d37f7968a1dc130f',
     'de654b1f702d5bb9f44047a285f532052c1293bea8e78e1a5a8710bab9f13059'),
    ('services/src/screenlock_system_ability.cpp',
     'e2adf73ca8e6b45d603fbd067124153992bc2ddaa208dff54b71ac2be3aff2a7',
     '95cf4448a373b7ebb7982a0ffc15a348e677b1edbd5ca8cdadcd7b5740039eaf'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def is_legacy_v1(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V1_FILES, require_patched=True)
    except ValueError:
        return False


def is_legacy_v2(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V2_FILES, require_patched=True)
    except ValueError:
        return False


def is_legacy_v3(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V3_FILES, require_patched=True)
    except ValueError:
        return False


def is_legacy_v4(root):
    try:
        return validate_component(root, PROJECT, REVISION, LEGACY_V4_FILES, require_patched=True)
    except ValueError:
        return False
