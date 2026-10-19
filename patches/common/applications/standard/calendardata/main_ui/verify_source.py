#!/usr/bin/env python3
"""Exact reminder viewer after the complete editor/native dispatch predecessor."""
from pathlib import Path
import importlib.util
import json
import hashlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/calendardata'
REVISION = 'f922427ca0dc20895a0e254ae41382e5b03299a4'
FILES = (('entry/src/main/module.json5', 'ff618ccd9b045e512e190e65724cff864e7e91307404e6cd0a7ba10d778b3ab7', '5c6cd28e95b3ff48d97157b263ff49b87a8eeb1fda44487b403145d43b0a3874'), ('entry/src/main/ets/MainAbility/MainAbility.ets', '92ab40a10c351035ab221f0d84661c835c17aa7ac45c3bd2c9c75492fa88d007', 'ada4728994501933eda37db97b7d75cf5c989394db6e39b3ebbe3c40f5db328b'), ('entry/src/main/ets/pages/index.ets', '7f36cf0eedf8a185afdf32e854b8c8d3b3c46d47ea395f7d59672ebe0ee26b4e', 'fa7dff6f63d47401de32869f69d95c23ba4040dac0951156c1072474e9240709'), ('entry/src/main/ets/reminder/CalendarReminderReader.ets', None, '560395625990d7172e2bfd2643d0f14acbca05b19a4ae267160ef6e12a13b246'), ('datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets', '0e33529d17fb86a1761e6745a41f46e03317108502ec4890ef50f69c4d514e8b', '64d26c8147ce850cb7cdc3f82b7a031e68ba4f9cb6daa6fdeeb1e113cbd5b131'), ('entry/src/main/ets/calendar/CalendarBusinessController.ets', None, 'e0cc534fc0f8a90eca0e2ff87a48bd5e8ea23f86729bff4a361aae77cde49619'))
MANIFEST_SHA256 = '31f94cb0a324680a81230c91b07b14ec16096a3ab77c7a364a568c3562d2dddc'

def load(name):
    path = Path(__file__).resolve().parent.parent / name / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('calendar_main_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def source_state(root):
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
    manifest = Path(__file__).resolve().parent / 'source_states.json'
    if manifest.is_symlink() or hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Calendar exact source manifest drift')
    states = json.loads(manifest.read_text())['states']
    keys = set(states['final'])
    if any(set(state) != keys for state in states.values()):
        raise ValueError('incomplete Calendar whole-state manifest')
    observed = {}
    for relative in sorted(keys):
        path = Path(root).resolve() / PROJECT / relative
        cursor = path
        while cursor != Path(root).resolve():
            if cursor.is_symlink():
                raise ValueError('symlink Calendar source input: ' + relative)
            cursor = cursor.parent
        observed[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    for name, expected in states.items():
        if observed == expected:
            return name
    raise ValueError('unknown or mixed Calendar UI source; preserving source')


def validate(root, require_patched=False):
    state = source_state(root)
    if require_patched and state != 'final':
        raise ValueError('complete shared-local-storage Calendar business/viewer successor required')
    return state == 'final'
