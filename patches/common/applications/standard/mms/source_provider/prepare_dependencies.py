#!/usr/bin/env python3
"""Fetch only the fixed upstream class-transformer used by the real MMS app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from verify_source import validate

NAME = 'class-transformer-0.5.1.tgz'
URL = 'https://registry.npmjs.org/class-transformer/-/' + NAME
SHA256 = '49efad879d3cc811a46e6baf72b0454a4f271c0da6b7899d024bdfcf94961f7e'


def checked(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('redirected MMS dependency path')
    if path.exists() and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256):
        raise ValueError('unknown MMS dependency; preserving source/cache')
    return path


def prepare(root, cache):
    validate(root, require_patched=True)
    target = checked(root / 'applications/standard/mms' / NAME)
    asset = checked(cache / NAME)
    cache.mkdir(parents=True, exist_ok=True)
    if not asset.exists():
        with tempfile.TemporaryDirectory(prefix='mms-dependency-', dir=cache) as temporary:
            pending = Path(temporary) / NAME
            subprocess.run(['curl', '-fL', '--proto', '=https', '--proto-redir', '=https',
                '--connect-timeout', '30', '--max-time', '300', '--retry', '2', '-o', str(pending), URL], check=True)
            checked(pending)
            if asset.exists(): raise ValueError('MMS dependency cache changed during fetch')
            pending.rename(asset)
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.mms-dependency-', dir=target.parent) as temporary:
            pending = Path(temporary) / NAME
            shutil.copy2(asset, pending);checked(pending)
            if target.exists(): raise ValueError('MMS dependency source changed during installation')
            pending.rename(target)
    checked(target)
    return {'name': NAME, 'url': URL, 'sha256': SHA256, 'bytes': target.stat().st_size,
            'scope': 'actual_pinned_upstream_dependency_ONLY_NOT_application_compile_or_guest'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve(), args.cache_root.resolve())))
