#!/usr/bin/env python3
"""Bound note parsing in the exact historical QEMU Mesa 21.3.3 source."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

RELATIVE = Path('src/util/build_id.c')
ORIGINAL_SHA = '3c09c299f7453f95c77cf460c6fc02074dae38979365f4e13beda8f8d5da543e'
REPAIRED_SHA = 'f8c5be520628c679208d54fff1c06e43691e627a5a6f5e8ccec94bc475b485db'
PATCH_NAME = '0001-bound-ELF-note-payloads-before-reading-or-advancing.patch'
PATCH_SHA = 'f91b910bd66337b349455429c8c63632d73b1a1545c4c3d28f3dbf0bb5db1cea'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_path(root, relative):
    path = root / relative
    for current in (path, *path.parents):
        if current == root:
            return path
        if current.is_symlink():
            raise ValueError('symlink in historical Mesa build-ID input')
    raise ValueError('build-ID input outside source root')


def apply(root, patch):
    root = Path(root).resolve()
    source = checked_path(root, RELATIVE)
    if (checked_path(root, 'VERSION').read_text().strip() != '21.3.3' or
            patch.is_symlink() or digest(patch) != PATCH_SHA):
        raise ValueError('exact historical Mesa build-ID recipe required')
    state = digest(source)
    if state == REPAIRED_SHA:
        return
    if state != ORIGINAL_SHA:
        raise ValueError('unknown historical build-ID edits; preserving source')
    descriptor = os.open(root / '.ohos-qemu-build-id.lock',
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = checked_path(root, RELATIVE)
        if digest(source) == REPAIRED_SHA:
            return
        if digest(source) != ORIGINAL_SHA:
            raise ValueError('historical build-ID source changed before lock acquisition')
        with tempfile.TemporaryDirectory(prefix='mesa-build-id-') as directory:
            staged = Path(directory)
            target = staged / RELATIVE
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
            environment = os.environ.copy()
            for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
                environment.pop(name, None)
            environment['GIT_CEILING_DIRECTORIES'] = str(staged.parent)
            for operation in ('--check', '--whitespace=nowarn'):
                subprocess.run(['git', '-C', str(staged), 'apply', operation, str(patch)],
                               check=True, env=environment)
            repaired = target.read_bytes()
            if hashlib.sha256(repaired).hexdigest() != REPAIRED_SHA:
                raise ValueError('unexpected complete repaired build-ID source')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=source.parent, prefix='.build-id-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(repaired)
                os.fchmod(stream.fileno(), source.stat().st_mode & 0o777)
                stream.flush()
                os.fsync(stream.fileno())
            checked_path(root, RELATIVE)
            if digest(source) != ORIGINAL_SHA:
                raise ValueError('build-ID source changed before publication')
            os.replace(temporary, source)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source_root, Path(__file__).with_name(PATCH_NAME))
    print('verified historical Mesa ELF note boundaries')
