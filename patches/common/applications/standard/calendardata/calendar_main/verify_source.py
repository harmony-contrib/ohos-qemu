#!/usr/bin/env python3
"""Exact installed editor/dispatch predecessor or complete Calendar Main successor."""
import hashlib
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


def regular_path(root, relative):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe Calendar Main relative path')
    target = root / PROJECT / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('Calendar Main path contains a symlink: ' + relative)
        cursor = cursor.parent
    if target.exists() and not target.is_file():
        raise ValueError('Calendar Main path is not a regular file: ' + relative)
    return target


def validate(root, require_patched=False):
    root = Path(root).resolve(strict=True)
    project = root / PROJECT
    if (project / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('Calendar Main requires the pinned CalendarData revision')
    for relative, expected in MANIFEST['dependencies'].items():
        target = regular_path(root, relative)
        if not target.exists() or digest(target.read_bytes()) != expected:
            raise ValueError('unknown/incomplete installed editor dependency: ' + relative)
    states = []
    for relative, before, after in FILES:
        target = regular_path(root, relative)
        actual = digest(target.read_bytes()) if target.exists() else None
        if actual == after:
            states.append(True)
        elif actual == before and not require_patched:
            states.append(False)
        else:
            raise ValueError('unknown Calendar Main source; preserving all files: ' + relative)
    if len(set(states)) != 1:
        raise ValueError('partial Calendar Main state; preserving all files')
    return states[0]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('patched' if validate(args.source_root, args.require_patched) else 'installed_predecessor')
