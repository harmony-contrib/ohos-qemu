#!/usr/bin/env python3
"""Exact reminder viewer after the complete editor/native dispatch predecessor."""
from pathlib import Path
import importlib.util
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/calendardata'
REVISION = 'f922427ca0dc20895a0e254ae41382e5b03299a4'
FILES = (('entry/src/main/module.json5', 'ff618ccd9b045e512e190e65724cff864e7e91307404e6cd0a7ba10d778b3ab7', '84d6be601eefbe875e88aa96cc437cf15c71d3dc342f32117db85b1b6d78564c'), ('entry/src/main/ets/MainAbility/MainAbility.ets', '92ab40a10c351035ab221f0d84661c835c17aa7ac45c3bd2c9c75492fa88d007', '6c9672bae7f76ecd955083a371542950203db89efdd7dde1db8358ddd87ec51e'), ('entry/src/main/ets/pages/index.ets', '7f36cf0eedf8a185afdf32e854b8c8d3b3c46d47ea395f7d59672ebe0ee26b4e', 'ab1e7f11adb58e9b07d49a05d57901d3319d84cea6fb5b63180e268b1c4a3b98'), ('entry/src/main/ets/reminder/CalendarReminderReader.ets', None, '560395625990d7172e2bfd2643d0f14acbca05b19a4ae267160ef6e12a13b246'), ('datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets', '0e33529d17fb86a1761e6745a41f46e03317108502ec4890ef50f69c4d514e8b', '64d26c8147ce850cb7cdc3f82b7a031e68ba4f9cb6daa6fdeeb1e113cbd5b131'))

def load(name):
    path = Path(__file__).resolve().parent.parent / name / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('calendar_main_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate(root, require_patched=False):
    # These exact predecessor files are prerequisites even for an idempotent
    # replay. A valid viewer cannot disguise missing/different native callbacks.
    dispatch = load('editor_callback_dispatch')
    dispatch.validate(root, require_patched=True)
    editor = load('event_editor')
    owned = {row[0] for row in FILES} | {row[0] for row in dispatch.FILES}
    remaining = tuple(row for row in editor.FILES if row[0] not in owned)
    validate_component(root, PROJECT, REVISION, remaining, require_patched=True)
    validate_component(root, PROJECT, REVISION, (
        ('AppScope/app.json5', None, '6c470e0a9ba23bee5bbdad0b335bf91ad3225da0e68e0d9a72f287520867b1b8'),
    ), require_patched=True)
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
