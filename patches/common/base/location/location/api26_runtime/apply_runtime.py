#!/usr/bin/env python3
"""Validate exact source bytes, preflight the stack, then apply a known prefix."""
import argparse
import fcntl
import os
from pathlib import Path
import tempfile
import subprocess
import stat

import verify_source

COMPONENT = Path(__file__).resolve().parent


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
            snapshots[name] = original.read_bytes() if original.exists() else None
            if snapshots[name] is not None:
                target.write_bytes(snapshots[name])
        # Only the exact already-verified whole prefix chooses the remaining
        # patch suffix. New owned headers are represented by explicit absence.
        offset = 0 if state == 'original' else int(state.removeprefix('prefix_'))
        for patch in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))[offset:]:
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=staged, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=staged, check=True)
        verify_source.validate(staged, require_patched=True, check_revision=False)
        if verify_source.validate(source) != state or any(
                ((source / verify_source.PROJECT / name).read_bytes()
                 if (source / verify_source.PROJECT / name).exists() else None) != value for name, value in snapshots.items()):
            raise ValueError('location source changed during exact preflight')
        for name in names:
            target = source / verify_source.PROJECT / name
            final = (staged / verify_source.PROJECT / name).read_bytes()
            if snapshots[name] == final:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.location-exact-', delete=False) as output:
                temporary = Path(output.name)
                try:
                    output.write(final)
                    output.flush()
                    os.fchmod(output.fileno(), mode)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        verify_source.validate(source, require_patched=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root)
    print('verified exact location API 26 runtime component')


if __name__ == '__main__':
    main()
