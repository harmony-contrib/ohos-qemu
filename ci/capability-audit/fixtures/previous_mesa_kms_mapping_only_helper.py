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
            environment = os.environ.copy()
            for variable in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
                environment.pop(variable, None)
            environment['GIT_CEILING_DIRECTORIES'] = str(staged.parent)
            for operation in ('--check', '--whitespace=nowarn'):
                subprocess.run(['git', '-C', str(staged), 'apply', operation, str(patch)],
                               env=environment, check=True)
            if digest(target) != REPAIRED_SHA:
                raise ValueError('historical mapping patch produced an unexpected complete file')
            # Extracted build sources live inside the Mesa 25 checkout. Git
            # discovers that outer repository and silently skips these paths.
            # Publish only the verified historical file, atomically, rather
            # than applying a patch in an unrelated parent Git worktree.
            replacement_name = None
            try:
                with tempfile.NamedTemporaryFile(dir=source.parent, prefix='.ohos-qemu-kms-mapping-',
                                                 delete=False) as replacement:
                    replacement_name = Path(replacement.name)
                    with target.open('rb') as repaired:
                        shutil.copyfileobj(repaired, replacement)
                    os.fchmod(replacement.fileno(), source.stat().st_mode & 0o777)
                    replacement.flush()
                    os.fsync(replacement.fileno())
                if digest(replacement_name) != REPAIRED_SHA:
                    raise ValueError('verified historical mapping copy differs')
                check_path(source, root)
                if digest(source) != ORIGINAL_SHA:
                    raise ValueError('historical mapping source changed before atomic publication')
                os.replace(replacement_name, source)
            finally:
                if replacement_name is not None:
                    replacement_name.unlink(missing_ok=True)
        if digest(source) != REPAIRED_SHA:
            raise ValueError('historical mapping source is incomplete after application')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source_root, Path(__file__).with_name('0001-serialize-displaytarget-mapping.patch'))
    print('verified historical Mesa KMS mapping synchronization')
