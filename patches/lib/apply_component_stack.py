#!/usr/bin/env python3
"""Validate and apply an ordered component, including overlapping patches.

Recognize pristine, complete or contiguous earlier prefixes from actual source
content, never from legacy marker files. Validate the entire remaining stack in
owned scratch before changing source. Preserve unrelated source content.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile


def apply(root, patch, reverse=False):
    argv = ['git', '-C', str(root), 'apply', '--whitespace=nowarn']
    if reverse:
        argv.append('--reverse')
    checked = subprocess.run(argv + ['--check', str(patch)], capture_output=True)
    if checked.returncode:
        return False
    subprocess.run(argv + [str(patch)], check=True, capture_output=True)
    return True


def run(component, source):
    component, source = Path(component).resolve(), Path(source).resolve()
    patches = sorted(component.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if not patches:
        raise ValueError('numbered component stack required')
    names = set()
    for patch in patches:
        if patch.is_symlink():
            raise ValueError('owned component patch required')
        rows = subprocess.check_output(['git', 'apply', '--numstat', str(patch)], text=True)
        for row in rows.splitlines():
            name = row.split('\t')[-1]
            parsed = PurePosixPath(name)
            if parsed.is_absolute() or '..' in parsed.parts or '\\' in name:
                raise ValueError('unsafe component patch target')
            names.add(name)
    if not names:
        raise ValueError('nonempty component changes required')
    lock_dir = source / '.ohos-qemu-patches'
    if lock_dir.is_symlink():
        raise ValueError('owned component lock directory required')
    lock_dir.mkdir(exist_ok=True)
    key = hashlib.sha256(json.dumps({'component': component.name, 'files': sorted(names)}).encode()).hexdigest()
    descriptor = os.open(lock_dir / (key + '.stack.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock, tempfile.TemporaryDirectory(prefix='ohos-component-stack-') as directory:
        fcntl.flock(lock, fcntl.LOCK_EX)
        scratch = Path(directory)
        snapshots = {}
        for name in names:
            path = source / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
                raise ValueError('owned existing component source required: ' + name)
            snapshots[name] = path.read_bytes()
        frozen = []
        for original in patches:
            target = scratch / 'patches' / original.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(original, target)
            frozen.append(target)
        selected = None
        for count in range(len(frozen), -1, -1):
            candidate = scratch / ('prefix-' + str(count))
            for name in names:
                target = candidate / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(snapshots[name])
            if not all(apply(candidate, patch, reverse=True) for patch in reversed(frozen[:count])):
                continue
            if not all(apply(candidate, patch) for patch in frozen):
                continue
            selected = count, candidate
            break
        if selected is None:
            raise ValueError('source is not a valid contiguous component state; no patches applied')
        count, final = selected
        if any((source / name).read_bytes() != value for name, value in snapshots.items()):
            raise ValueError('component source changed during whole-stack verification')
        for patch in frozen[count:]:
            if not apply(source, patch):
                raise ValueError('verified component application changed concurrently')
        if any((source / name).read_bytes() != (final / name).read_bytes() for name in names):
            raise ValueError('component final source differs from verified stack')
    print('verified whole component stack: ' + component.name + ', prior prefix=' + str(count))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component-dir', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.component_dir, args.source_root)


if __name__ == '__main__':
    main()
