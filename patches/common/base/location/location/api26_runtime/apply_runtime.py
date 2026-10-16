#!/usr/bin/env python3
"""Validate exact source bytes, preflight the stack, then apply a known prefix."""
import argparse
import fcntl
import importlib.util
import os
from pathlib import Path
import tempfile

import verify_source

COMPONENT = Path(__file__).resolve().parent
LIBRARY = COMPONENT.parents[4] / 'lib'
spec = importlib.util.spec_from_file_location('location_component_stack', LIBRARY / 'apply_component_stack.py')
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)


def run(source):
    source = Path(source)
    state = verify_source.validate(source)
    source = source.resolve()
    if state == 'final':
        return
    lock_dir = source / '.ohos-qemu-patches'
    if lock_dir.is_symlink():
        raise ValueError('location lock directory must be owned')
    lock_dir.mkdir(exist_ok=True)
    descriptor = os.open(lock_dir / 'location-api26-runtime.exact.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock, tempfile.TemporaryDirectory(prefix='location-runtime-exact-') as directory:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = verify_source.validate(source)
        if state == 'final':
            return
        staged = Path(directory)
        names = verify_source.manifest()['files']
        snapshots = {}
        for name in names:
            original = source / verify_source.PROJECT / name
            target = staged / verify_source.PROJECT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            snapshots[name] = original.read_bytes()
            target.write_bytes(snapshots[name])
        # The shared stack runner recognizes overlapping contiguous prefixes.
        # Exact final file bytes, not successful contextual application, authorize writing.
        stack.run(COMPONENT, staged)
        verify_source.validate(staged, require_patched=True, check_revision=False)
        if verify_source.validate(source) != state or any(
                (source / verify_source.PROJECT / name).read_bytes() != value for name, value in snapshots.items()):
            raise ValueError('location source changed during exact preflight')
        stack.run(COMPONENT, source)
        verify_source.validate(source, require_patched=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root)
    print('verified exact location API 26 runtime component')


if __name__ == '__main__':
    main()
