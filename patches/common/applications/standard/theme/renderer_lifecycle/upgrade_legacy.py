#!/usr/bin/env python3
"""Upgrade only the complete, previously shipped two-file renderer state."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import verify_source as baseline
from exact_source_states import validate_component


LEGACY_SHA256 = '84cde2fbed244e1e6e3562096f66d5948d9124c4030e7d1bd54b3fa39e761dac'
PATCH_NAME = '0002-use-runtime-wallpaper-extension-hooks.patch'
PATCH_SHA256 = '436685652c37752031b7504c740c4d662f12251caa2ef09295f703c387454be2'


def legacy_state(root):
    files = tuple((relative, LEGACY_SHA256, repaired)
                  for relative, original, repaired in baseline.FILES)
    return validate_component(root, baseline.PROJECT, baseline.REVISION, files)


def apply_patch(root, patch):
    subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)], check=True)


def upgrade(root, component):
    # The lock is identical to the shared exact component helper's lock.
    marker_dir = root / '.ohos-qemu-patches'
    if marker_dir.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker_dir.mkdir(exist_ok=True)
    lock_name = hashlib.sha256((baseline.PROJECT + '/' + component.name).encode()).hexdigest() + '.lock'
    descriptor = os.open(marker_dir / lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            baseline.validate(root)
        except ValueError:
            # Only the complete exact legacy pair may take the incremental path.
            # This also checks the project revision and rejects symlink inputs.
            if legacy_state(root):
                raise ValueError('unexpected current renderer state during legacy upgrade')
        else:
            # Original and current states remain the shared helper's contract.
            return
        original_patch = component / PATCH_NAME
        if original_patch.is_symlink():
            raise ValueError('renderer upgrade patch must not be a symlink')
        patch_bytes = original_patch.read_bytes()
        if hashlib.sha256(patch_bytes).hexdigest() != PATCH_SHA256:
            raise ValueError('renderer upgrade patch identity changed')
        with tempfile.TemporaryDirectory(prefix='ohos-wallpaper-upgrade-') as temporary:
            temporary = Path(temporary)
            staged = temporary / 'source'
            for relative, original, repaired in baseline.FILES:
                target = staged / baseline.PROJECT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / baseline.PROJECT / relative, target)
            patch = temporary / PATCH_NAME
            patch.write_bytes(patch_bytes)
            if legacy_state(staged):
                raise ValueError('renderer legacy snapshot changed')
            apply_patch(staged, patch)
            baseline.validate(staged, require_patched=True)
            if legacy_state(root):
                raise ValueError('renderer legacy source changed before upgrade')
            apply_patch(root, patch)
            baseline.validate(root, require_patched=True)
    print('upgraded complete legacy wallpaper renderer component')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    upgrade(args.source_root.resolve(), Path(__file__).resolve().parent)


if __name__ == '__main__':
    main()
