"""Exact Calendar prefix/legacy72/typed successor with original ancestor guards.

The source lock and full eighteen-file vectors precede any write. Verification
never migrates; ordinary build prefix rewind and forward remain explicit.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

from guarded_source_vector579 import apply, heads, identity, load, matches, replace, target

PATCHES = Path(__file__).resolve().parents[1]
COMPONENT = PATCHES / 'common/applications/standard/calendardata/lifecycle579'
MANIFEST_SHA256 = '049a833f2595205f6f58d001fdf62ea10243f3c200b2f361c2822fd9659faffa'
CHANGED = frozenset((
    'applications/standard/calendardata/entry/src/main/ets/calendar/CalendarChangeSubscription.ets',
    'applications/standard/calendardata/datamanager/src/main/ets/utils/CalendarDataHelper.ets',
    'applications/standard/calendardata/datamanager/src/main/ets/processor/events/ConditionalEventMutation.ets',
    'applications/standard/calendardata/datamanager/src/main/ets/processor/events/EventsProcessor.ets',
    'applications/standard/calendardata/entry/src/main/ets/pages/index.ets',
))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink() or digest(path.read_bytes()) != MANIFEST_SHA256:
        raise ValueError('complete Calendar lifecycle source vector changed')
    value = load(COMPONENT)
    legacy = value.get('legacy72_final')
    if (len(value['files']) != 18 or len(value['projects']) != 2 or type(legacy) is not dict or
            legacy.keys() != value['files'].keys() or
            {n for n, pair in value['files'].items() if legacy[n] != pair[1]} != CHANGED or
            any(not isinstance(h, str) or len(h) != 64 or any(c not in 'abcdef0123456789' for c in h)
                for h in legacy.values())):
        raise ValueError('exact full eighteen-file Calendar legacy72/typed successor required')
    return value


def state(root, value):
    actual = {name: digest(path.read_bytes()) if path.exists() else None
              for name in value['files'] for path in (target(root, name),)}
    if actual == {n: pair[1] for n, pair in value['files'].items()}:
        return 'final'
    if actual == value['legacy72_final']:
        return 'legacy72'
    if actual == {n: pair[0] for n, pair in value['files'].items()}:
        return 'before'
    raise ValueError('unknown or mixed complete Calendar source vector preserved')


@contextmanager
def source_lock(root):
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink() or marker.exists() and not marker.is_dir():
        raise ValueError('source lock directory is linked or not a directory')
    marker.mkdir(exist_ok=True)
    # Same canonical component path/key as the original generic applicator.
    name = digest(str(COMPONENT).encode()) + '.lock'
    fd = os.open(marker / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def legacy_value(value):
    return dict(value, files={n: [pair[0], value['legacy72_final'][n]]
                              for n, pair in value['files'].items()})


def migrate_legacy72(root, value):
    if state(root, value) != 'legacy72':
        raise ValueError('complete actual Calendar legacy72 vector required')
    originals = {}
    for name in value['files']:
        path = target(root, name)
        originals[name] = {'bytes': path.read_bytes(), 'identity': identity(path)}
    if state(root, value) != 'legacy72':
        raise ValueError('complete Calendar legacy changed during snapshot')
    with tempfile.TemporaryDirectory(prefix='calendar-typed579-stage-') as directory:
        staged = Path(directory)
        for name, original in originals.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original['bytes'])
        subprocess.run(['patch', '--binary', '--batch', '--forward', '--fuzz=0', '-p1', '-i',
            str(COMPONENT / '0002-legacy72-to-typed-arkts.patch')], cwd=staged, check=True)
        if state(staged, value) != 'final' or {p.relative_to(staged).as_posix()
                for p in staged.rglob('*') if p.is_file()} != set(value['files']):
            raise ValueError('complete exact eighteen-file staged Calendar successor required')
        finals = {name: (staged / name).read_bytes() for name in value['files']}
    heads(root, value)
    for name, original in originals.items():
        if not matches(target(root, name), original):
            raise ValueError('Calendar source inode changed before migration: ' + name)
    installed = {}
    try:
        for name in sorted(CHANGED):
            path = target(root, name)
            if not matches(path, originals[name]):
                raise ValueError('Calendar source raced during migration: ' + name)
            replace(path, finals[name], originals[name]['identity'], installed, name)
        for name in value['files']:
            if name not in CHANGED and not matches(target(root, name), originals[name]):
                raise ValueError('unchanged Calendar source raced during migration: ' + name)
        heads(root, value)
        if state(root, value) != 'final':
            raise ValueError('complete typed Calendar final vector required')
    except BaseException as error:
        failures = []
        for name in reversed(sorted(CHANGED)):
            try:
                path = target(root, name)
                if matches(path, originals[name]):
                    continue
                if (name not in installed or not path.exists() or identity(path) != installed[name] or
                        path.read_bytes() != finals[name]):
                    raise ValueError('unknown concurrent Calendar source preserved: ' + name)
                replace(path, originals[name]['bytes'], originals[name]['identity'], {}, name)
            except BaseException as rollback_error:
                failures.append(str(rollback_error))
        if failures:
            raise RuntimeError('owned Calendar migration rollback incomplete: ' + '; '.join(failures)) from error
        if state(root, value) != 'legacy72':
            raise RuntimeError('prior full Calendar state changed; foreign bytes preserved') from error
        raise


def rewind_if_final(root):
    """Early source prefix only: unrecognized bytes are not declared valid."""
    root = Path(root).resolve(strict=True)
    value = manifest()
    with source_lock(root):
        heads(root, value)
        try:
            epoch = state(root, value)
        except ValueError:
            # Pristine/earlier/unknown are untouched. Original normal hooks and
            # final strict eighteen-file source gate are still mandatory.
            return 'defer_to_original_normal_hooks_NOT_verified'
        if epoch in ('final', 'legacy72'):
            current = value if epoch == 'final' else legacy_value(value)
            inverse = dict(current, files={n: list(reversed(pair)) for n, pair in current['files'].items()})
            patch = '0001-product-source.patch' if epoch == 'final' else '0001-legacy72-source.patch'
            apply(root, COMPONENT, inverse, reverse=True, patch_name=patch)
            if state(root, value) != 'before':
                raise ValueError('exact Calendar prefix restoration required')
        return 'exact_prefix_before_NOT_runtime_acceptance'


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
    if state(root, value) != 'final':
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
            if state(root, value) != 'final':
                raise ValueError('actual final Calendar vector changed during ancestor checks')
            for name, before in observed.items():
                path = target(root, name)
                if (path.read_bytes() if path.exists() else None) != before:
                    raise ValueError('actual ancestor dependency changed during source checks: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--require-final', action='store_true')
    modes.add_argument('--rewind', action='store_true')
    modes.add_argument('--migrate', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve(strict=True)
    if args.rewind:
        print(rewind_if_final(root))
        return 0
    value = manifest()
    with source_lock(root):
        heads(root, value)
        epoch = state(root, value)
        if args.require_final:
            if epoch != 'final':
                raise ValueError('complete typed Calendar final required; verification never migrates')
        elif epoch == 'legacy72':
            migrate_legacy72(root, value)
        elif epoch == 'before':
            if args.migrate:
                raise ValueError('standalone migration requires complete legacy72 or final')
            apply(root, COMPONENT, value)
        if state(root, value) != 'final':
            raise ValueError('complete typed eighteen-file Calendar successor required')
    print('Calendar product source prepared; compilation and QEMU acceptance pending')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
