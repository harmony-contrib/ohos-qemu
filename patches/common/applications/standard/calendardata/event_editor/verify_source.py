#!/usr/bin/env python3
"""Exact CalendarData editor source composition after source_provider preparation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/calendardata'
REVISION = 'f922427ca0dc20895a0e254ae41382e5b03299a4'
FILES = (('calendarmanager/napi/src/calendar_manager_napi.cpp', 'c5916ba82058f0f5af4ed3c00e74f671b3db2763d023820d221e9bad266e8d80', '72662beb41d84ad4c1495c945c7de5ffface89ad429e0d2cfea5e0faabc604d2'), ('calendarmanager/napi/include/calendar_manager_napi.h', 'd9d594ecf1b3a25d47fc02edcc65896c04407c89d9cf2bc9b4fc5021e241bdf4', 'ed18774b7833582490af121f2a02d69481cbac276f4c29636479017c0b4c1b10'), ('entry/src/main/module.json5', '2be9cdaa75fa46a08c82d56e9a8da2571b9550e1af9a6268875f33cacc7a3610', 'ff618ccd9b045e512e190e65724cff864e7e91307404e6cd0a7ba10d778b3ab7'), ('entry/src/main/resources/base/profile/main_pages.json', 'ed151c09ec9351c32a3a7652342b01457c6ef3ef5ea2821a3385b94a78b29685', '0b970b526b5b8f85df45fe6190e6f6343965d9c533614bd997bf0625a234ead7'), ('entry/src/main/ets/editor/EventEditorController.ets', None, 'bbb821e311fdbfb0deb1ddd3e436ec632f58e08127518a8da90473b27420a463'), ('entry/src/main/ets/EditorUIExtensionAbility.ets', None, 'a11b7906d7f22282935aceff9d23272d7d9ccaab314ba6eb5043063fb68682c2'), ('entry/src/main/ets/pages/EventEditor.ets', None, '4da0af1e1f4aeb77edc2916e1d7cd487d0ae68541277a9ef012a6740f715f843'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
