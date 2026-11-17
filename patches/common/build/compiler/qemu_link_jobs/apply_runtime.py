#!/usr/bin/env python3
"""Apply one whole-source linker-budget delta with one atomic replacement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    states = json.loads((HERE / 'source_states.json').read_text())
    if states['file'] != 'build/config/compiler/BUILD.gn':
        raise ValueError('fixed compiler file required')
    path = root / states['file']
    if path.is_symlink() or not path.is_file() or path.resolve() != path:
        raise ValueError('actual regular compiler source required')
    current = sha(path)
    if current == states['final_sha256']:
        print('QEMU linker budget source already applied; runtime acceptance pending')
        return
    if args.require_patched or current != states['before_sha256']:
        raise ValueError('unknown compiler source; preserve it without patching')
    metadata = path.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    identity = (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_gid)
    original = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='qemu-link-jobs-') as scratch:
        staged = Path(scratch) / states['file']
        staged.parent.mkdir(parents=True)
        shutil.copyfile(path, staged)
        subprocess.run(['patch', '--binary', '--batch', '--forward', '-p1', '-i',
            str(HERE / '0001-bound-qemu-lto-workers.patch')], cwd=scratch, check=True)
        if sha(staged) != states['final_sha256'] or path.read_bytes() != original:
            raise ValueError('staged delta or original source changed; nothing replaced')
        fd, temporary = tempfile.mkstemp(prefix='.qemu-link-jobs-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(staged.read_bytes()); stream.flush(); os.fsync(stream.fileno())
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
            os.chmod(temporary, mode)
            current_metadata = path.stat()
            current_identity = (current_metadata.st_dev, current_metadata.st_ino,
                                current_metadata.st_mode, current_metadata.st_uid, current_metadata.st_gid)
            if path.is_symlink() or current_identity != identity or path.read_bytes() != original:
                raise ValueError('compiler source changed before atomic replacement')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if sha(path) != states['final_sha256']:
        raise ValueError('final compiler source differs')
    print('QEMU linker budget source applied; compilation and QEMU acceptance pending')


if __name__ == '__main__':
    main()
