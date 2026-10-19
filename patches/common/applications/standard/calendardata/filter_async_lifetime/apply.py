#!/usr/bin/env python3
"""Install two exact Calendar filter async lifetime postimages, rolling back any failed commit."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import stat
import tempfile

from verify_source import FILES, digest, regular_path, source_state, validate, read_payload


def apply(root, replace=os.replace):
    root = Path(root).resolve(strict=True)
    if source_state(root) == 'final':
        return
    markers = root / '.ohos-qemu-patches'
    if markers.is_symlink():
        raise ValueError('Calendar filter async lifetime lock directory must not be a symlink')
    markers.mkdir(exist_ok=True)
    descriptor = os.open(markers / 'calendar-filter-async-lifetime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        initial_state = source_state(root)
        if initial_state == 'final':
            return
        transaction = Path(tempfile.mkdtemp(prefix='calendar-filter-async-lifetime-', dir=markers))
        committed = []
        directories = []
        preserve_transaction = False
        try:
            originals = {}
            for index, (relative, before, after) in enumerate(FILES):
                payload = read_payload(relative)
                target = regular_path(root, relative)
                staged = transaction / str(index)
                staged.write_bytes(payload)
                os.chmod(staged, stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644)
                if target.exists():
                    shutil.copy2(target, transaction / (str(index) + '.before'))
                    originals[relative] = digest(target.read_bytes())
                else:
                    originals[relative] = None
            # Complete dependency/whole-state check immediately before mutation.
            if source_state(root) != initial_state:
                raise ValueError('Calendar filter async lifetime source changed during preparation')
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
                actual = digest(target.read_bytes()) if target.exists() else None
                if actual != originals[relative]:
                    raise ValueError('Calendar filter target changed before publication: ' + relative)
                # A replacement may publish successfully and then raise. Record
                # the attempt before calling it so both outcomes roll back.
                committed.append((index, target, before))
                replace(transaction / str(index), target)
                if digest(target.read_bytes()) != after:
                    raise ValueError('Calendar filter published bytes differ: ' + relative)
            validate(root, require_patched=True)
        except BaseException as original_error:
            # Backups contain the exact installed predecessor bytes/modes.
            # A failed rename or final verification never leaves a mixed set.
            for index, target, before in reversed(committed):
                relative, _, after = FILES[index]
                try:
                    regular_path(root, relative)
                    actual = digest(target.read_bytes()) if target.is_file() else None
                except (ValueError, OSError):
                    preserve_transaction = True
                    continue
                if actual == originals[relative]:
                    continue  # This replacement failed before publication.
                if actual != after:
                    # Never overwrite an unrelated concurrent edit during
                    # rollback. Preserve the exact backup for root inspection.
                    preserve_transaction = True
                    continue
                try:
                    if originals[relative] is None:
                        target.unlink()
                    else:
                        os.replace(transaction / (str(index) + '.before'), target)
                except OSError:
                    # Failed restoration must not delete the only retained
                    # predecessor while cleaning the staging directory.
                    preserve_transaction = True
            for directory in reversed(directories):
                if not preserve_transaction:
                    directory.rmdir()
            if preserve_transaction:
                raise RuntimeError('Calendar rollback preserved unknown target and backups at ' + str(transaction)) from original_error
            raise
        finally:
            if not preserve_transaction:
                shutil.rmtree(transaction)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    apply(args.source_root)
    print('verified complete exact Calendar filter async lifetime component; no runtime claim')


if __name__ == '__main__':
    main()
