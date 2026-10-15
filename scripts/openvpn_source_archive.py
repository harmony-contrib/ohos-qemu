#!/usr/bin/env python3
"""Materialize the exact locked upstream source without replacing caller files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request


def validate(path, lock):
    if path.is_symlink() or not path.is_file():
        raise ValueError('materialized pinned OpenVPN archive required')
    if (path.stat().st_size != lock['archive_bytes'] or
            hashlib.sha256(path.read_bytes()).hexdigest() != lock['archive_sha256']):
        raise ValueError('OpenVPN archive differs from the fixed source lock')


def prepare(path, lock):
    if path.exists() or path.is_symlink():
        validate(path, lock)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.openvpn-download-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            request = urllib.request.Request(lock['archive_url'], headers={'User-Agent': 'ohos-qemu-fixed-source'})
            with urllib.request.urlopen(request, timeout=120) as response:
                remaining = lock['archive_bytes']
                while chunk := response.read(min(1024 * 1024, remaining + 1)):
                    if len(chunk) > remaining:
                        raise ValueError('OpenVPN download exceeds the fixed archive length')
                    output.write(chunk)
                    remaining -= len(chunk)
            output.flush()
            os.fsync(output.fileno())
        validate(temporary, lock)
        try:
            os.link(temporary, path)
        except FileExistsError:
            validate(path, lock)
        return path
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(Path(__file__).with_name('openvpn_source_lock.json').read_text())
    print(prepare(args.output, lock))
