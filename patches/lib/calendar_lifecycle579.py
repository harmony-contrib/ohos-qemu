"""Prepare the exact Calendar successor and retain its strict ancestor guards.

The temporary view is used only by existing read-only source guards. Compilation,
signing and packaging always consume the real final source tree.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from guarded_source_vector579 import apply, heads, load, target, vector

PATCHES = Path(__file__).resolve().parents[1]
COMPONENT = PATCHES / 'common/applications/standard/calendardata/lifecycle579'
MANIFEST_SHA256 = '077e60e7ca1c7bf1c69de9380e43e4185de002f29f9b52f8bcc9544b2d1d935e'


def manifest():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('complete Calendar lifecycle source vector changed')
    value = load(COMPONENT)
    if len(value['files']) != 18 or len(value['projects']) != 2:
        raise ValueError('exact eighteen-file Calendar successor required')
    return value


def rewind_if_final(root):
    value = manifest()
    heads(root, value)
    try:
        state = vector(root, value)
    except ValueError:
        # Preserve pristine/earlier/unknown bytes for the original component
        # machinery. The final hook still requires the full exact predecessor.
        return
    if state == 'final':
        inverse = dict(value, files={name: list(reversed(pair)) for name, pair in value['files'].items()})
        apply(root, COMPONENT, inverse, reverse=True)


def guard_module(relative):
    path = PATCHES / 'common' / relative / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('calendar579_' + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ancestor_paths():
    names = set()
    for relative in (
            'applications/standard/calendardata/event_editor',
            'applications/standard/calendardata/editor_callback_dispatch',
            'applications/standard/calendardata/main_ui',
            'base/notification/distributed_notification_service/calendar_owner'):
        module = guard_module(relative)
        names.update(module.PROJECT + '/' + row[0] for row in module.FILES)
    module = guard_module('applications/standard/calendardata/filter_async_lifetime')
    names.update(module.PROJECT + '/' + name for name in module.MANIFEST['files'])
    names.update(module.PROJECT + '/' + name for name in module.MANIFEST['dependencies'])
    names.add('applications/standard/calendardata/AppScope/app.json5')
    return names


@contextmanager
def ancestor_view(root):
    root = Path(root).resolve(strict=True)
    value = manifest()
    heads(root, value)
    if vector(root, value) != 'final':
        raise ValueError('complete actual Calendar successor required before ancestor projection')
    observed = {}
    projected = {}
    for name in sorted(ancestor_paths()):
        path = target(root, name)
        data = path.read_bytes() if path.exists() else None
        observed[name] = data
        if name in value['files']:
            before = value['files'][name][0]
            data = target(COMPONENT / 'before', name).read_bytes() if before is not None else None
            if (hashlib.sha256(data).hexdigest() if data is not None else None) != before:
                raise ValueError('exact retained Calendar ancestor payload changed: ' + name)
        projected[name] = data
    with tempfile.TemporaryDirectory(prefix='calendar579-ancestor-readonly-') as directory:
        view = Path(directory)
        for name, data in projected.items():
            if data is not None:
                path = view / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        try:
            yield view
        finally:
            heads(root, value)
            if vector(root, value) != 'final':
                raise ValueError('actual final Calendar vector changed during ancestor checks')
            for name, before in observed.items():
                path = target(root, name)
                if (path.read_bytes() if path.exists() else None) != before:
                    raise ValueError('actual ancestor dependency changed during source checks: ' + name)
