#!/usr/bin/env python3
"""Migrate only the exact previously applied two-patch thermal component."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from verify_source import PROJECT, REVISION, PREVIOUS, validate, validate_component


def previous(root):
    try:
        return validate_component(root, PROJECT, REVISION, PREVIOUS, require_patched=True)
    except (ValueError, FileNotFoundError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    root = parser.parse_args().source_root.resolve()
    if not previous(root):
        return  # Original/final/unknown states are checked by the exact applicator.
    component = Path(__file__).resolve().parent
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker.mkdir(exist_ok=True)
    name = hashlib.sha256((PROJECT + '/' + component.name).encode()).hexdigest() + '.lock'
    fd = os.open(marker / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not previous(root):
            return
        patch = component / '0003-match-the-packaged-kernel-battery-zone.patch'
        with tempfile.TemporaryDirectory(prefix='thermal-zone-upgrade-') as directory:
            staged = Path(directory)
            for relative, _, _ in PREVIOUS:
                target = staged / PROJECT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / PROJECT / relative, target)
            subprocess.run(['git', '-C', str(staged), 'apply', '--check', str(patch)], check=True)
            subprocess.run(['git', '-C', str(staged), 'apply', str(patch)], check=True)
            validate(staged, require_patched=True)
            if not previous(root):
                raise ValueError('prior thermal component changed during migration preparation')
            subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], check=True)
            subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
            validate(root, require_patched=True)


if __name__ == '__main__':
    main()
