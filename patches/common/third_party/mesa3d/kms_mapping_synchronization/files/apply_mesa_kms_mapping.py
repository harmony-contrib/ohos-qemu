#!/usr/bin/env python3
"""Apply the exact mapping backport only to the historical QEMU Mesa source."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RELATIVE = Path('src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c')
ORIGINAL_SHA = 'b8b8736f347fb473a718c610abf3099bfb72d5a9f28bf75e3620fb72f8592194'
REPAIRED_SHA = 'e5fef3b60fa2c555bc4447cba13a2dd23819fd7f6bf33c065a597a9bca909670'
PATCH_SHA = '6286238e04e7545a5c63c4bd0f3fa9b8c16f5d690b252498c4119b700c47da55'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_path(path, root):
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError('symlink in historical mapping input: ' + str(path))
        current = current.parent


def apply(root, patch):
    root = Path(root).resolve()
    patch = Path(patch).resolve()
    source = root / RELATIVE
    check_path(source, root)
    check_path(root / 'VERSION', root)
    if (root / 'VERSION').read_text().strip() != '21.3.3' or digest(patch) != PATCH_SHA:
        raise ValueError('requires exact historical Mesa 21.3.3 mapping recipe')
    state = digest(source)
    if state == REPAIRED_SHA:
        return
    if state != ORIGINAL_SHA:
        raise ValueError('unknown historical mapping edits; preserving source')
    lock = root / '.ohos-qemu-kms-mapping.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        state = digest(source)
        if state == REPAIRED_SHA:
            return
        if state != ORIGINAL_SHA:
            raise ValueError('historical mapping source changed before lock acquisition')
        with tempfile.TemporaryDirectory(prefix='mesa-kms-map-') as temporary:
            staged = Path(temporary)
            target = staged / RELATIVE
            target.parent.mkdir(parents=True)
            shutil.copy2(source, target)
            for operation in ('--check', '--whitespace=nowarn'):
                subprocess.run(['git', '-C', str(staged), 'apply', operation, str(patch)], check=True)
            if digest(target) != REPAIRED_SHA:
                raise ValueError('historical mapping patch produced an unexpected complete file')
        if digest(source) != ORIGINAL_SHA:
            raise ValueError('historical mapping source changed before patch application')
        subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)], check=True)
        if digest(source) != REPAIRED_SHA:
            raise ValueError('historical mapping source is incomplete after application')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source_root, Path(__file__).with_name('0001-serialize-displaytarget-mapping.patch'))
    print('verified historical Mesa KMS mapping synchronization')
