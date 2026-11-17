#!/usr/bin/env python3
"""Install one exact prepared audio sink preimage; unknown edits remain untouched."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE/'manifest.json').read_text())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def target(root, name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('unsafe audio sink path')
    path = root/name
    for node in (path, *path.parents):
        if node == root:
            break
        if node.is_symlink():
            raise ValueError('linked audio sink path; preserving source')
    return path


def validate(root, require_patched=False):
    root = Path(root).resolve()
    for name, revision in MANIFEST['projects'].items():
        project = root/name
        if (project/'.git').exists():
            actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != revision:
                raise ValueError('audio sink requires fixed project revision')
    states = []
    for name, entry in MANIFEST['files'].items():
        path = target(root, name)
        if not path.is_file():
            raise ValueError('exact regular audio sink source required')
        current = sha(path.read_bytes())
        if current == entry['after']:
            states.append(True)
        elif current == entry['before']:
            states.append(False)
        else:
            raise ValueError('unknown audio sink changes; preserving source')
    if len(set(states)) != 1 or (require_patched and not all(states)):
        raise ValueError('audio sink component is not completely patched')
    return all(states)


def run(root):
    root = Path(root).resolve()
    if validate(root):
        return
    directory = root/'.ohos-qemu-patches'
    if directory.is_symlink():
        raise ValueError('linked audio sink patch lock')
    directory.mkdir(exist_ok=True)
    fd = os.open(directory/'audio-vivid-integrity.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if validate(root):
            return
        outputs = []
        for name, entry in MANIFEST['files'].items():
            path = target(root, name)
            payload = (HERE/'files'/entry['payload']).read_bytes()
            if sha(payload) != entry['after']:
                raise ValueError('audio sink payload differs from manifest')
            outputs.append((path, path.read_bytes(), payload))
        for path, original, payload in outputs:
            if path.read_bytes() != original:
                raise ValueError('audio sink changed during preparation')
            mode = path.stat().st_mode & 0o777
            fd, temporary = tempfile.mkstemp(prefix='.audio-vivid-integrity-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, mode)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    validate(root, True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    parser.add_argument('--product')
    args = parser.parse_args()
    if args.require_patched:
        validate(args.source_root, True)
    else:
        run(args.source_root)
    print('verified audio sink metadata/data integrity; plugin/runtime acceptance remains separate')
