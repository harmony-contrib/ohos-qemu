#!/usr/bin/env python3
"""Prepare a finite pinned source vector, including new files, with rollback.

This is ordinary product source preparation. It cannot accept runtime behavior.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relative_path(name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or str(relative) != name:
        raise ValueError('noncanonical source path: ' + name)
    return relative


def target(root, name):
    relative_path(name)
    path = root / name
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('linked source input refused: ' + name)
    if path.exists() and not path.is_file():
        raise ValueError('regular source file required: ' + name)
    return path


def identity(path):
    s = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(s.st_mode):
        raise ValueError('regular source inode required')
    return s.st_dev, s.st_ino, stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid


def load(component):
    value = json.loads((component / 'source_states.json').read_text())
    if value.get('schema') != 'guarded-product-source-vector579/v1' or not value.get('files'):
        raise ValueError('fixed complete source manifest required')
    for project, revision in value['projects'].items():
        relative_path(project)
        if re.fullmatch('[a-f0-9]{40}', revision) is None:
            raise ValueError('fixed actual project revision required')
    for name, hashes in value['files'].items():
        relative_path(name)
        if (len(hashes) != 2 or hashes[0] == hashes[1] or
                any(h is not None and re.fullmatch('[a-f0-9]{64}', h) is None for h in hashes) or
                hashes[1] is None or not any(name.startswith(p + '/') for p in value['projects'])):
            raise ValueError('finite whole-file source pair required: ' + name)
    return value


def heads(root, value):
    for project, expected in value['projects'].items():
        directory = root / project
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('actual project directory required: ' + project)
        actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('actual fixed project HEAD differs: ' + project)


def vector(root, value):
    states = []
    for name, pair in value['files'].items():
        p = target(root, name)
        digest = sha(p.read_bytes()) if p.exists() else None
        if digest not in pair:
            raise ValueError('unknown source bytes preserved: ' + name)
        states.append(pair.index(digest))
    if len(set(states)) != 1:
        raise ValueError('mixed source vector preserved')
    return 'before' if states[0] == 0 else 'final'


def matches(path, original):
    return (not path.exists()) if original is None else (
        path.exists() and identity(path) == original['identity'] and path.read_bytes() == original['bytes'])


def replace(path, content, metadata, installed, name):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.qemu-source579-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            if metadata is not None:
                current = os.fstat(stream.fileno())
                if (current.st_uid, current.st_gid) != metadata[3:]:
                    os.fchown(stream.fileno(), metadata[3], metadata[4])
            os.fchmod(stream.fileno(), metadata[2] if metadata else 0o644)
            os.fsync(stream.fileno())
            installed[name] = identity(temporary)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply(root, component, value, *, reverse=False, patch_name='0001-product-source.patch'):
    heads(root, value)
    if vector(root, value) == 'final':
        return
    originals = {}
    for name in value['files']:
        p = target(root, name)
        originals[name] = {'bytes': p.read_bytes(), 'identity': identity(p)} if p.exists() else None
    with tempfile.TemporaryDirectory(prefix='qemu-vector579-') as temporary:
        staged = Path(temporary)
        for name, original in originals.items():
            if original is not None:
                p = staged / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(original['bytes'])
        if vector(staged, value) != 'before':
            raise ValueError('actual preimage changed during snapshot')
        subprocess.run(['patch', '--binary', '--batch', '--reverse' if reverse else '--forward', '--fuzz=0', '-p1', '-i',
            str(component / patch_name)], cwd=staged, check=True)
        if vector(staged, value) != 'final' or {
                str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()} != {
                    n for n, pair in value['files'].items() if pair[1] is not None}:
            raise ValueError('finite complete final source vector required')
        finals = {n: (staged / n).read_bytes() if pair[1] is not None else None
                  for n, pair in value['files'].items()}
    heads(root, value)
    if vector(root, value) != 'before':
        raise ValueError('actual source changed before commit')
    installed, directories = {}, []
    try:
        for name, original in originals.items():
            p = target(root, name)
            if not matches(p, original):
                raise ValueError('actual source inode changed before replacement: ' + name)
            if finals[name] is None:
                installed[name] = None
                p.unlink()
                continue
            missing = []
            parent = p.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                s = directory.stat(follow_symlinks=False)
                directories.append((directory, (s.st_dev, s.st_ino)))
            replace(p, finals[name], original['identity'] if original else None, installed, name)
        if vector(root, value) != 'final':
            raise ValueError('final actual source vector differs')
    except BaseException as error:
        failures = []
        for name, original in reversed(list(originals.items())):
            try:
                p = target(root, name)
                if matches(p, original):
                    continue
                if name not in installed:
                    raise ValueError('unknown concurrent source preserved')
                if installed[name] is None:
                    if p.exists():
                        raise ValueError('concurrent source appeared after owned removal')
                elif (not p.exists() or identity(p) != installed[name] or
                        sha(p.read_bytes()) != value['files'][name][1]):
                    raise ValueError('unknown concurrent source preserved')
                if original is None:
                    p.unlink()
                else:
                    replace(p, original['bytes'], original['identity'], {}, name)
            except BaseException as rollback_error:
                failures.append(name + ': ' + str(rollback_error))
        for directory, inode in reversed(directories):
            try:
                s = directory.stat(follow_symlinks=False)
                if not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != inode:
                    raise ValueError('created source directory changed: ' + str(directory))
                directory.rmdir()
            except (OSError, ValueError):
                failures.append('created source directory not empty: ' + str(directory))
        if failures:
            raise RuntimeError('source rollback incomplete: ' + '; '.join(failures)) from error
        if vector(root, value) != 'before':
            raise RuntimeError('source rollback did not restore complete preimage') from error
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component-dir', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--require-final', action='store_true')
    mode.add_argument('--rewind', action='store_true',
        help='restore only the exact complete final vector before re-entering earlier source components')
    args = parser.parse_args()
    root, component = args.source_root.resolve(), args.component_dir.resolve()
    value = load(component)
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('source lock directory is linked')
    marker.mkdir(exist_ok=True)
    name = sha(str(component).encode()) + '.lock'
    fd = os.open(marker / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.require_final:
            heads(root, value)
            if vector(root, value) != 'final':
                raise ValueError('complete final source vector required')
        else:
            if args.rewind:
                value = dict(value, files={n: list(reversed(pair)) for n, pair in value['files'].items()})
            apply(root, component, value, reverse=args.rewind)
    print('Product source vector prepared; QEMU acceptance remains pending')


if __name__ == '__main__':
    main()
