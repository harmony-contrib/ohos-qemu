#!/usr/bin/env python3
"""Exact installed editor/dispatch predecessor or complete Calendar filter async lifetime successor."""
import hashlib
import base64
import gzip
import json
from pathlib import Path
import subprocess

COMPONENT = Path(__file__).resolve().parent
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())
PROJECT = MANIFEST['project']
REVISION = MANIFEST['revision']
FILES = tuple((name, entry['before_sha256'], entry['after_sha256'])
              for name, entry in MANIFEST['files'].items())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_payload(relative):
    entry = MANIFEST['files'][relative]
    path = COMPONENT / 'files' / entry.get('payload_path', relative)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing/nonregular calendar filter postimage: ' + relative)
    data = path.read_bytes()
    if entry.get('payload_encoding') == 'gzip_base64':
        data = gzip.decompress(base64.b64decode(data, validate=True))
    if digest(data) != entry['after_sha256']:
        raise ValueError('calendar filter postimage differs from manifest: ' + relative)
    return data


def regular_path(root, relative):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe Calendar filter async lifetime relative path')
    target = root / PROJECT / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('Calendar filter async lifetime path contains a symlink: ' + relative)
        cursor = cursor.parent
    if target.exists() and not target.is_file():
        raise ValueError('Calendar filter async lifetime path is not a regular file: ' + relative)
    return target


def source_state(root):
    root = Path(root).resolve(strict=True)
    project = root / PROJECT
    if (project / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('Calendar filter async lifetime requires the pinned CalendarData revision')
    for relative, expected in MANIFEST['dependencies'].items():
        target = regular_path(root, relative)
        if not target.exists() or digest(target.read_bytes()) != expected:
            raise ValueError('unknown/incomplete installed editor dependency: ' + relative)
    actual_files = {}
    for relative, before, after in FILES:
        target = regular_path(root, relative)
        actual_files[relative] = digest(target.read_bytes()) if target.exists() else None
    expected = {
        'original': {name: before for name, before, _ in FILES},
        'previous_candidate': MANIFEST['previous_complete_candidate'],
        'final': {name: after for name, _, after in FILES},
    }
    for name, state in expected.items():
        if actual_files == state:
            return name
    raise ValueError('unknown or partial Calendar filter async lifetime state; preserving all files')


def validate(root, require_patched=False):
    state = source_state(root)
    if require_patched and state != 'final':
        raise ValueError('complete final Calendar filter async lifetime state required')
    return state == 'final'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('patched' if validate(args.source_root, args.require_patched) else 'installed_predecessor')
