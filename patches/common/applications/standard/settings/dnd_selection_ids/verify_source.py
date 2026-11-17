#!/usr/bin/env python3
"""Exact complete single-project vector, never a build or runtime acceptance."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

HERE = Path(__file__).resolve().parent


def manifest():
    value = json.loads((HERE / 'source_states.json').read_text())
    if value.get('schema') != 'settings579-dnd-source-vector/v1' or len(value['files']) != 3:
        raise ValueError('Fixed complete 3-file manifest required')
    for name, hashes in value['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or len(hashes) != 2 or hashes[0] == hashes[1]:
            raise ValueError('Finite exact source path/vector required: ' + name)
        if not any(name.startswith(project + '/') for project in value['projects']):
            raise ValueError('Source outside the actual build project: ' + name)
    return value


def target(root, name):
    path = root / name
    for parent in path.relative_to(root).parents:
        if (root / parent).is_symlink():
            raise ValueError('Source parent symlink rejected: ' + name)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Complete regular source missing: ' + name)
    return path


def heads(root, value):
    for project, expected in value['projects'].items():
        path = root / project
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Actual regular project missing: ' + project)
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('Actual fixed project HEAD required: ' + project)


def vector(root, value):
    observed = []
    for name, hashes in value['files'].items():
        digest = hashlib.sha256(target(root, name).read_bytes()).hexdigest()
        if digest not in hashes:
            raise ValueError('Unknown actual source bytes: ' + name)
        observed.append(hashes.index(digest))
    if not observed or len(set(observed)) != 1:
        raise ValueError('Mixed QEMU provider source vector rejected')
    return 'before' if observed[0] == 0 else 'final'


def state(root):
    value = manifest()
    heads(root, value)
    return vector(root, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    observed = state(args.source_root.resolve())
    if args.require_final and observed != 'final':
        raise ValueError('Complete final QEMU provider source vector required')
    print(json.dumps({'state': observed, 'scope': 'source_only_NOT_runtime_acceptance'}))


if __name__ == '__main__':
    main()
