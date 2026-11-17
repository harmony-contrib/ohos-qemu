#!/usr/bin/env python3
"""Exact QEMU RIL PTY policy source guard; no compiled policy/runtime proof."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def state(root):
    manifest = json.loads((HERE / 'source_states.json').read_text())
    for project, revision in manifest['projects'].items():
        head = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
        if head != revision:
            raise ValueError('Fixed policy project revision required: ' + project)
    indices = []
    for name, hashes in manifest['files'].items():
        target = root / name
        if target.is_symlink() or not target.is_file():
            raise ValueError('Complete regular actual policy source required: ' + name)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest not in hashes:
            raise ValueError('Unknown actual policy bytes: ' + name)
        indices.append(hashes.index(digest))
    if len(set(indices)) != 1:
        raise ValueError('Mixed policy source vector rejected')
    return 'before' if indices[0] == 0 else 'final'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    result = state(args.source_root.resolve())
    if args.require_final and result != 'final':
        raise ValueError('Complete final QEMU RIL PTY policy source required')
    print(json.dumps({'state': result, 'scope': 'source_only_NOT_runtime_acceptance'}))


if __name__ == '__main__':
    main()
