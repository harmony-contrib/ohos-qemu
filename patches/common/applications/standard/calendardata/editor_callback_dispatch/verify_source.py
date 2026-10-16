#!/usr/bin/env python3
"""Exact native callback delta; must follow event_editor, without HAP source changes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/calendardata'
REVISION = 'f922427ca0dc20895a0e254ae41382e5b03299a4'
FILES = (('calendarmanager/napi/src/calendar_manager_napi.cpp', '72662beb41d84ad4c1495c945c7de5ffface89ad429e0d2cfea5e0faabc604d2', '49f933bc39c943f6aee6beecb1a24a89d5d9933048dfe7b73117393746934b2b'), ('calendarmanager/napi/include/calendar_manager_napi.h', 'ed18774b7833582490af121f2a02d69481cbac276f4c29636479017c0b4c1b10', '578ce09c60602e04cd46c55f8a4a6b56d1f81ea47333d4be75ff4d19dfce8c3e'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
