#!/usr/bin/env python3
"""Install six exact Calendar Main postimages, rolling back any failed commit."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import stat
import tempfile

from verify_source import COMPONENT, FILES, PROJECT, digest, regular_path, validate


def apply(root, replace=os.replace):
    root = Path(root).resolve(strict=True)
    if validate(root):
        return
    markers = root / '.ohos-qemu-patches'
    if markers.is_symlink():
        raise ValueError('Calendar Main lock directory must not be a symlink')
    markers.mkdir(exist_ok=True)
    descriptor = os.open(markers / 'calendar-main.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if validate(root):
            return
        transaction = Path(tempfile.mkdtemp(prefix='calendar-main-', dir=markers))
        committed = []
        directories = []
        try:
            for index, (relative, before, after) in enumerate(FILES):
                payload = COMPONENT / 'files' / relative
                if payload.is_symlink() or not payload.is_file() or digest(payload.read_bytes()) != after:
                    raise ValueError('Calendar Main postimage differs from manifest: ' + relative)
                target = regular_path(root, relative)
                staged = transaction / str(index)
                staged.write_bytes(payload.read_bytes())
                os.chmod(staged, stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644)
                if target.exists():
                    shutil.copy2(target, transaction / (str(index) + '.before'))
            # Complete dependency/whole-state check immediately before mutation.
            if validate(root):
                raise ValueError('Calendar Main source changed during preparation')
            for index, (relative, before, after) in enumerate(FILES):
                target = regular_path(root, relative)
                missing = []
                parent = target.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir()
                    directories.append(directory)
                replace(transaction / str(index), target)
                committed.append((index, target, before))
            validate(root, require_patched=True)
        except BaseException:
            # Backups contain the exact installed predecessor bytes/modes.
            # A failed rename or final verification never leaves a mixed set.
            for index, target, before in reversed(committed):
                if before is None:
                    target.unlink()
                else:
                    os.replace(transaction / (str(index) + '.before'), target)
            for directory in reversed(directories):
                directory.rmdir()
            raise
        finally:
            shutil.rmtree(transaction)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    apply(args.source_root)
    print('verified complete exact Calendar Main component; no runtime claim')


if __name__ == '__main__':
    main()
