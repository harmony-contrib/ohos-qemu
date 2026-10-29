#!/usr/bin/env python3
"""Install this component from one complete pinned state, with checked rollback."""
import argparse
import base64
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
MANIFEST = json.loads((COMPONENT / 'source_states.json').read_text())
PROJECT = MANIFEST['project']
REVISION = MANIFEST['revision']


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def checked_root(root):
    root = Path(root).absolute()
    for cursor in (root, *root.parents):
        if cursor.is_symlink():
            raise ValueError('source root/ancestor is a symlink: ' + str(cursor))
    if not root.is_dir():
        raise ValueError('source root must be an existing directory')
    return root


def checked_target(root, relative):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe component member')
    target = root / PROJECT / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('component input contains a symlink: ' + str(cursor))
        cursor = cursor.parent
    if target.exists() and not target.is_file():
        raise ValueError('component member is not a regular file: ' + relative)
    return target


def snapshot(root):
    result = {}
    for name in MANIFEST['files']:
        target = checked_target(root, name)
        result[name] = target.read_bytes() if target.exists() else None
    return result


def verify_revision(root):
    project = root / PROJECT
    if (project / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('component requires pinned audio_framework revision ' + REVISION)


def state(root, require_patched=False):
    root = checked_root(root)
    verify_revision(root)
    values = {name: digest(data) for name, data in snapshot(root).items()}
    matches = [name for name, expected in MANIFEST['states'].items() if values == expected]
    if len(matches) != 1:
        raise ValueError('unknown/mixed MIC frame assembly state; preserving all source files')
    if require_patched and matches[0] != 'after':
        raise ValueError('complete frame assembly source state is required')
    return matches[0]


def replacement(target, data, mode):
    descriptor, temporary = tempfile.mkstemp(prefix='.mic-frame-assembly-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        return Path(temporary)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def install(root, after_write=None):
    """after_write is an in-process test seam; no CLI fault injection is exposed."""
    root = checked_root(root)
    state(root)  # Reject foreign state before even creating component-owned locks.
    lockdir = root / '.ohos-qemu-patches'
    if lockdir.is_symlink():
        raise ValueError('component lock directory is a symlink')
    lockdir.mkdir(exist_ok=True)
    descriptor = os.open(lockdir / 'mic-frame-assembly-incarnation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prior_state = state(root)
        if prior_state == 'after':
            return prior_state
        originals = snapshot(root)
        modes = {}
        staged = {}
        written = []
        try:
            for name, entry in MANIFEST['files'].items():
                data = gzip.decompress(base64.b64decode(entry['after_gzip_base64'], validate=True))
                if digest(data) != MANIFEST['states']['after'][name]:
                    raise ValueError('corrupt component payload: ' + name)
                target = checked_target(root, name)
                modes[name] = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
                staged[name] = replacement(target, data, modes[name])
            # A writer outside our component lock is never silently overwritten.
            if snapshot(root) != originals or state(root) != prior_state:
                raise ValueError('source changed while staging MIC frame assembly component')
            for name in MANIFEST['files']:
                target = checked_target(root, name)
                present = target.read_bytes() if target.exists() else None
                if present != originals[name]:
                    raise ValueError('source changed before replacement: ' + name)
                os.replace(staged[name], target)
                written.append(name)
                if after_write is not None:
                    after_write(name, len(written))
            state(root, require_patched=True)
        except BaseException as failure:
            errors = []
            for name in reversed(written):
                try:
                    target = checked_target(root, name)
                    current = target.read_bytes() if target.exists() else None
                    if digest(current) != MANIFEST['states']['after'][name]:
                        raise ValueError('foreign edit after replacement; not overwriting: ' + name)
                    if originals[name] is None:
                        target.unlink()
                    else:
                        restore = replacement(target, originals[name], modes[name])
                        try:
                            os.replace(restore, target)
                        finally:
                            restore.unlink(missing_ok=True)
                except BaseException as rollback_error:
                    errors.append(str(rollback_error))
            if not errors:
                try:
                    if snapshot(root) != originals or state(root) != prior_state:
                        raise ValueError('rollback did not restore the exact complete preimage')
                except BaseException as rollback_error:
                    errors.append(str(rollback_error))
            if errors:
                raise RuntimeError('MIC frame assembly apply failed; incomplete rollback: ' + '; '.join(errors)) from failure
            raise
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)
        return 'after'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product')
    args = parser.parse_args()
    print('verified complete MIC frame assembly state: ' + install(args.source_root))


if __name__ == '__main__':
    main()
