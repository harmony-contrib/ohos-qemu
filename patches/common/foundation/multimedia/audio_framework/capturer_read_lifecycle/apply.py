#!/usr/bin/env python3
"""Install only an exact complete component state; rollback an interrupted publication."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / 'manifest.json').read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def path_for(root, name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('unsafe component target')
    path = root / name
    for cursor in (path, *path.parents):
        if cursor == root:
            break
        if cursor.is_symlink():
            raise ValueError('linked component target: ' + name)
    return path


def inspect(root):
    root = Path(root).resolve()
    for name, revision in MANIFEST['projects'].items():
        project = root / name
        if (project / '.git').exists():
            actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != revision:
                raise ValueError('component requires fixed project revision: ' + name)
    observed = {}
    for name in MANIFEST['files']:
        path = path_for(root, name)
        if path.exists() and not path.is_file():
            raise ValueError('regular component target required: ' + name)
        observed[name] = sha(path.read_bytes()) if path.exists() else None
    states = {
        'before': {name: row['before'] for name, row in MANIFEST['files'].items()},
        'after': {name: row['after'] for name, row in MANIFEST['files'].items()},
    }
    previous = HERE / 'previous-state.json'
    if previous.exists():
        value = json.loads(previous.read_text())
        if set(value['files']) != set(observed):
            raise ValueError('previous complete-state membership differs')
        states['previous'] = value['files']
    # Compare complete vectors, never accept independently valid old/new members.
    for state in ('after', 'previous', 'before'):
        if state in states and observed == states[state]:
            return state
    raise ValueError('unknown or partial component state; preserving source')


def validate(root, require_patched=False):
    state = inspect(root)
    if require_patched and state != 'after':
        raise ValueError('complete patched component required')
    return state == 'after'


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.capturer-read-lifecycle-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(root):
    root = Path(root).resolve()
    if validate(root):
        return
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('linked component lock directory')
    marker.mkdir(exist_ok=True)
    descriptor = os.open(marker / 'capturer-read-lifecycle.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if validate(root):
            return
        snapshots, outputs = {}, {}
        for name, entry in MANIFEST['files'].items():
            path = path_for(root, name)
            stat = path.stat() if path.exists() else None
            snapshots[name] = (path.read_bytes() if stat else None,
                               stat.st_mode & 0o777 if stat else 0o644,
                               (stat.st_atime_ns, stat.st_mtime_ns) if stat else None)
            data = (HERE / 'files' / entry['payload']).read_bytes()
            if sha(data) != entry['after']:
                raise ValueError('component payload differs from manifest: ' + name)
            outputs[name] = data
        for name, (original, _, _) in snapshots.items():
            path = path_for(root, name)
            if (path.read_bytes() if path.exists() else None) != original:
                raise ValueError('component source changed during preparation')
        attempted = []
        try:
            for name, data in outputs.items():
                attempted.append(name)
                atomic_write(path_for(root, name), data, snapshots[name][1])
            validate(root, True)
        except BaseException:
            rollback_errors = []
            for name in reversed(attempted):
                try:
                    path = path_for(root, name)
                    original, mode, times = snapshots[name]
                    current = path.read_bytes() if path.exists() else None
                    if current != original:
                        if original is None:
                            path.unlink()
                        else:
                            atomic_write(path, original, mode)
                            os.utime(path, ns=times)
                except BaseException as error:
                    rollback_errors.append(name + ': ' + str(error))
            if rollback_errors:
                raise RuntimeError('component publication failed; rollback unproven: ' + repr(rollback_errors))
            for name, (original, _, _) in snapshots.items():
                path = path_for(root, name)
                if (path.read_bytes() if path.exists() else None) != original:
                    raise RuntimeError('component rollback differs: ' + name)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    parser.add_argument('--product')
    args = parser.parse_args()
    if args.require_patched:
        validate(args.source_root, True)
    else:
        run(args.source_root)
    print('verified complete capturer-read-lifecycle component')
